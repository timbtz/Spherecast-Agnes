# REF-GOOGLE-ADK-RESEARCH-AGENT

**Audience:** Implementation agents building `ResearchAgent` for Agnes — the supply chain intelligence system.
**Last updated:** 2026-04-18
**Status:** Authoritative — use alongside REF-GOOGLE-ADK.md for all ResearchAgent work.

---

## Quick Facts

| Property | Value |
|---|---|
| Agent file | `orchestration/agents/research_agent.py` |
| Model | `gemini-2.5-flash` |
| Pipeline | `research_new_supplier` — triggered on demand or as fallback from `reactive_fallout` |
| Trigger inputs | `canonical_id: int`, `required_certs: list[str]` |
| Primary DB output | `Discovered_Supplier` table rows (flagged `unverified`) |
| Secondary DB output | `API_Response_Cache` rows (`Source='google_adk'`) |
| Run log | `Enrichment_Run_Log` rows (Phase=4, Step='supplier_discovery') |
| Forbidden writes | `db.sqlite` (read-only source of truth), `Ingredient_Canonical`, `Supplier_Commercial` |

---

## 1. `google_search` Tool Reference

### 1.1 What it is

`google.adk.tools.google_search` is a **built-in grounding tool** for the Google Agent Development Kit. It is not a callable function that returns a Python dict; instead, it triggers Gemini's **Google Search grounding mechanism** internally. The model decides when to invoke it, formulates one or more search queries, receives grounding results, and incorporates them into its response — all within the same token generation step.

This means: **the agent cannot programmatically inspect individual search result dicts.** The LLM reads the grounded content and produces its text output. The raw results are surfaced to the model as context, not as structured Python objects your code can iterate over.

### 1.2 What the model receives from a grounding call

When grounding fires, the Gemini API populates `groundingMetadata` on the response candidate. The relevant fields surfaced to the model as context are:

```
groundingChunks[]
  .web.uri        — URL of the source page
  .web.title      — Page title

groundingSupports[]
  .segment.text   — Sentence in the model's answer
  .groundingChunkIndices[]  — Which groundingChunks back this sentence

webSearchQueries[]  — Actual queries submitted to Google Search
```

In practice, `groundingChunks` provides **5–10 web sources per model call**, each with a title and URL. The model sees the underlying page content during generation but does not return it as a raw field.

### 1.3 Known limitation: grounding chunks not always populated in ADK runner events

A known issue in `google/adk-python` (tracked as issue #1693 and #3287) means that `grounding_chunks` and `grounding_supports` may not be populated in ADK `runner.run_async()` event objects even when search grounded successfully. The **model output text** is still grounded and correct — the metadata is just not reliably surfaced in Python-side events. Do not write code that depends on parsing `event.grounding_metadata.grounding_chunks` at runtime.

### 1.4 Number of search calls and results

- The model internally decides how many search queries to run within a single `run_async()` call.
- Typical result: **5–10 grounded web sources** per model generation step that triggers search.
- Control total search usage by instructing the model in the system prompt: **MAX 5 google_search invocations** per pipeline run.
- There is no hard-coded "results per call" parameter the agent controls.

### 1.5 What happens with no results

If Google Search returns no results, the model generates its answer from training knowledge only and will not raise an exception. The prompt must instruct the agent to detect this and write `status: no_results_found` in its DB output.

### 1.6 What happens on rate limit / quota

`google_search` uses the Gemini API's built-in grounding quota, billed per prompt (not per search query). If the API returns a quota error, it surfaces as an exception from `runner.run_async()`, which `execute_node` in `dag_executor.py` catches and converts to a node failure logged in `Enrichment_Run_Log`.

### 1.7 Compatibility requirement

`google_search` is only compatible with **Gemini 2.x and later models**. `gemini-2.5-flash` is fully compatible. Do not switch to `gemini-1.x` for this agent.

### 1.8 Tool combination constraint

ADK enforces a restriction: **you cannot mix `google_search` with `code_execution` in the same agent**. However, you CAN combine `google_search` with custom function tools. Agnes's ResearchAgent uses exactly this — `google_search` alongside `db_tools` and `pubchem_tools`. This combination is supported and is the correct pattern.

**Critical isolation:** `google_search` must live in a dedicated `search_agent` instance. The parent `research_agent` calls it as a sub-agent. This prevents tool-mixing errors and makes the search agent independently testable.

```python
# orchestration/agents/search_agent.py — ONLY google_search here
search_agent = LlmAgent(
    name="agnes_searcher",
    model="gemini-2.5-flash",
    instruction="Search the web for supply chain supplier data. Return results with source URLs.",
    tools=[google_search],
)

# orchestration/agents/research_agent.py — custom tools only, calls search_agent
research_agent = LlmAgent(
    name="agnes_researcher",
    model="gemini-2.5-flash",
    instruction="...",
    tools=[query_ingredient_profile, insert_discovered_supplier, log_run_step, cache_search_result],
    # search is invoked by calling the search_agent node before this one in the DAG
)
```

---

## 2. Pipeline Context for ResearchAgent

### 2.1 The `AgnesContext` received by the agent

`execute_node()` in `orchestration/dag_executor.py` constructs the `user_message` from `AgnesContext`:

```
Pipeline: research_new_supplier
Run ID: {run_id}
Canonical ID: {canonical_id}
Required certs: {required_certs}
Context: {json.dumps(context.to_dict())}
```

Example for a real run:

```
Pipeline: research_new_supplier
Run ID: a3f2b1c0
Canonical ID: 7
Required certs: ["NSF", "Kosher"]
Context: {
  "pipeline_name": "research_new_supplier",
  "run_id": "a3f2b1c0",
  "triggered_at": "2026-04-18T14:00:00Z",
  "canonical_id": 7,
  "required_certs": ["NSF", "Kosher"],
  "node_outputs": {
    "query_ingredient_profile": "{\"name\": \"Coenzyme Q10\", \"cas\": \"303-98-0\", \"smiles\": \"...\", \"grade\": \"supplement\", \"company_count\": 8, \"current_supplier_count\": 2}"
  }
}
```

### 2.2 What the agent reads from the database before searching

The `query_ingredient_profile` node runs before ResearchAgent and its output is available in `context.node_outputs`. The agent should read:

| Data | Source | How to access |
|---|---|---|
| Ingredient name, CAS, SMILES | `node_outputs["query_ingredient_profile"]` | JSON string from prior node |
| Current suppliers in DB | `node_outputs["query_ingredient_profile"]` | `current_suppliers` field |
| Required certifications | `context.required_certs` | Direct from AgnesContext |
| Existing `Discovered_Supplier` rows | `db_tools.query_discovered_suppliers(canonical_id)` | DB tool call |

The agent must **check existing `Discovered_Supplier` rows first** before searching — avoid duplicating already-staged suppliers.

### 2.3 What the agent must NOT read

- `db.sqlite` — read-only source; access only via `db_enriched.sqlite`
- `Supplier_Commercial` — this table holds verified/enriched supplier data; research output goes to `Discovered_Supplier` only

---

## 3. Write Domain for ResearchAgent

### 3.1 Authoritative write table

| Target | Can write? | Reason |
|---|---|---|
| `Discovered_Supplier` table | **YES** | Primary output — new supplier candidates flagged `unverified` |
| `API_Response_Cache` (Source='google_adk') | **YES** | Cache search results for 7-day TTL reuse |
| `Enrichment_Run_Log` | **YES** | Record each discovery attempt (success/no_match/error) |
| `Ingredient_Canonical` | **NO** | Phase 1 domain only |
| `Supplier_Commercial` | **NO** | Verified supplier data only; ResearchAgent finds candidates, not verified records |
| `Consolidation_Opportunity` | **NO** | Phase 4 scorer domain |
| `db.sqlite` | **NO** | Read-only source of truth — never write |

### 3.2 What `insert_discovered_supplier` enforces

The `db_tools.insert_discovered_supplier()` function hard-codes `Verified=0` and `Source='google_adk'` on every insert — the agent cannot override these. Promotion to `Supplier_Commercial` requires a separate human-review step.

```python
def insert_discovered_supplier(
    canonical_id: int,
    name: str,
    country: str,
    url: str,
    certs_claimed: list[str],
    price_range_usd_kg: str,
    confidence: float,
) -> dict:
    """Stage a net-new supplier candidate for human review.

    Always inserts with Verified=0. Never writes to Supplier_Commercial.
    Returns dict with 'status' and 'id' of inserted row.
    """
```

---

## 4. `Discovered_Supplier` Table Schema

This is the **primary output target** for ResearchAgent. Schema:

```sql
CREATE TABLE IF NOT EXISTS Discovered_Supplier (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId INTEGER NOT NULL,
    Name                TEXT    NOT NULL,
    Country             TEXT,                  -- ISO 3166-1 alpha-2 (e.g. 'US', 'CN', 'DE')
    URL                 TEXT,                  -- Source URL where supplier was found
    Certs_Claimed       TEXT,                  -- JSON array: ["NSF", "Kosher"]
    Price_Range_USD_KG  TEXT,                  -- Free-text, e.g. "$12–18/kg at 25kg MOQ"
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    Source              TEXT    NOT NULL DEFAULT 'google_adk',
    Verified            INTEGER NOT NULL DEFAULT 0,  -- Always 0 until human review
    Discovered_At       TEXT    NOT NULL DEFAULT (datetime('now')),
    Notes               TEXT,
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);
```

**Status values written to `Enrichment_Run_Log.Status`:**

| Status | Meaning |
|---|---|
| `success` | ≥ 1 supplier candidates staged in `Discovered_Supplier` |
| `partial` | Suppliers found but cert requirements not fully matched |
| `no_match` | No suppliers found meeting minimum criteria |
| `cache_hit` | Prior search result reused from `API_Response_Cache` |
| `error` | Search or DB write failed |

---

## 5. Complete ResearchAgent System Prompt

This is the system prompt for `orchestration/agents/research_agent.py`. Pass it as the `instruction` parameter to `LlmAgent`.

```
You are ResearchAgent for Agnes, an AI supply chain intelligence system.

## Your Role

You are the `search_suppliers` node in the `research_new_supplier` pipeline. You run after
the ingredient profile has been queried from db_enriched.sqlite, and your job is to discover
net-new supplier candidates for a canonical ingredient that has gaps in coverage — either no
suppliers at all, or no suppliers meeting specific certification requirements.

You write all output to db_enriched.sqlite via tool calls. You do not write files.

## Your Task

Given a canonical ingredient with required certifications, search the web for bulk ingredient
suppliers, extract structured records, and stage candidates in the Discovered_Supplier table
for human review.

## Step-by-Step Instructions

### Step 1 — Read ingredient profile from context

Parse the JSON in `node_outputs["query_ingredient_profile"]` to extract:
- `name` — canonical ingredient name (e.g. "Coenzyme Q10")
- `cas` — CAS number (e.g. "303-98-0") — use in searches if present
- `current_suppliers` — list of supplier names already in db_enriched.sqlite
- `grade` — Grade_Flag (supplement/excipient/food/etc.)

Also read `required_certs` from the context — these are the certifications the discovered
supplier must claim.

### Step 2 — Check existing discovered suppliers

Call `query_discovered_suppliers(canonical_id)` to avoid staging duplicates.
If high-quality candidates already exist in Discovered_Supplier for this ingredient
(Confidence >= 0.7, Discovered_At within 7 days), skip search and log `cache_hit`.

### Step 3 — Build search queries

Construct 3–5 targeted queries based on ingredient name, CAS, and required certs.

**Query pattern examples:**
- `"{ingredient_name}" bulk supplier {cert} certificate`
- `"{ingredient_name}" {cas} manufacturer wholesale ingredient`
- `"{ingredient_name}" bulk ingredient supplier NSF GMP certificate site:.com`
- `"{ingredient_name}" raw material supplier Europe OR USA OR China`
- `"{ingredient_name}" OR "{cas}" supplement ingredient manufacturer`

Adapt queries to the grade:
- `supplement` → add "supplement grade", "USP grade", cert names
- `excipient` → add "pharma grade", "NF grade", "excipient"
- `food` → add "food grade", "GRAS", "food ingredient"

### Step 4 — Run google_search (MAX 5 calls)

Execute searches via the search_agent node output (available in context as
`node_outputs["search_suppliers"]`). Parse the text output for supplier records.

If context does not contain search results (this node runs search directly):
Invoke up to 5 searches. Stop early if you have ≥ 3 qualifying candidates.

**Hard limit: MAX 5 google_search invocations per pipeline run.**

### Step 5 — Extract structured supplier records

From search results, extract one record per supplier found:

```json
{
  "name": "DSM Nutritional Products",
  "country": "US",
  "url": "https://www.dsm.com/human-nutrition/...",
  "certs_claimed": ["NSF", "ISO9001", "Kosher"],
  "price_range_usd_kg": "$45–65/kg at 25kg MOQ",
  "confidence": 0.75,
  "notes": "Listed as CoQ10 bulk supplier on official product page. NSF cert mentioned."
}
```

**Confidence scoring:**
- 0.9 — Official manufacturer/supplier website, cert explicitly listed, ingredient page found
- 0.75 — Supplier listed on a B2B marketplace (Alibaba, Thomasnet, etc.) with cert claims
- 0.6 — Mentioned in an article or directory; no direct product page found
- 0.4 — Company name found but no clear supply of this specific ingredient confirmed

**Cert extraction rules:**
- Only include certs explicitly mentioned near the ingredient name — do not infer from company-level claims
- Map variants: "NSF certified" → "NSF", "USDA Organic" → "Organic", "non-GMO project" → "NonGMO"
- If certs are not mentioned for this ingredient specifically, set `certs_claimed` to []

### Step 6 — Filter and deduplicate

Before staging:
- Remove any supplier already in `current_suppliers` (from Step 1)
- Remove any supplier already in `Discovered_Supplier` (from Step 2)
- Remove duplicate names from the current search batch
- Only stage candidates with `confidence >= 0.5`

### Step 7 — Write to Discovered_Supplier

For each qualifying candidate, call `insert_discovered_supplier()`:

```python
insert_discovered_supplier(
    canonical_id=canonical_id,
    name="DSM Nutritional Products",
    country="US",
    url="https://www.dsm.com/...",
    certs_claimed=["NSF", "Kosher"],
    price_range_usd_kg="$45–65/kg at 25kg MOQ",
    confidence=0.75,
)
```

Each call returns `{"status": "inserted", "id": 42}`. Log each result.

### Step 8 — Cache search results

For each search query run, call `cache_search_result()` to store the raw result text in
`API_Response_Cache` with `Source='google_adk'`, `TTL_Days=7`. This prevents re-running
the same searches within the TTL window.

### Step 9 — Log the run

Call `log_run_step()` with:
- `canonical_id` — the ingredient searched
- `phase=4`, `step='supplier_discovery'`
- `status` — 'success' if ≥ 1 candidate staged, 'no_match' if none found
- `confidence` — average confidence of staged candidates (0.0 if none)
- `method` — 'google_adk'

### Step 10 — Output

End your response with exactly this summary line:

```
DISCOVERY_COMPLETE: {N} candidates staged for canonical_id={canonical_id}
```

Where N is the number of rows inserted into Discovered_Supplier. If zero: `DISCOVERY_COMPLETE: 0 candidates staged`.

---

## Write Domain Constraints — MANDATORY

**YOU MAY WRITE (via tool calls only):**
- `Discovered_Supplier` — staged candidates, always with Verified=0
- `API_Response_Cache` — search result cache, Source='google_adk'
- `Enrichment_Run_Log` — run audit trail

**YOU MUST NEVER WRITE:**
- `Ingredient_Canonical` — Phase 1 domain only
- `Supplier_Commercial` — verified data only; your output is unverified by definition
- `Consolidation_Opportunity` — scorer domain
- `SKU_To_Canonical` — Phase 1 domain only
- `db.sqlite` — read-only source; any write attempt will raise an error
```

---

## 6. Rate Limiting and Cost Control

### 6.1 Billing model

`google_search` grounding in Gemini API is billed **per prompt** (i.e., per `run_async()` call that triggers a grounding step), not per search query. Consult [https://ai.google.dev/pricing](https://ai.google.dev/pricing) for current rates.

### 6.2 Search result caching

All search results are cached in `API_Response_Cache` with `TTL_Days=7`. Before running any search query, `dag_executor.py` checks the cache key `(Source='google_adk', Cache_Key=sha256(query))`. Cache hits skip the Gemini API call entirely and return the cached text.

For Agnes's typical usage (supplier discovery per ingredient), the cache hit rate on re-runs is near 100% after the first run per ingredient.

### 6.3 Per-run search cap

The system prompt instructs **MAX 5 google_search invocations** per run. This is sufficient because:
- The first call returns 5–10 grounded sources from the Google Search index.
- If a supplier is not findable in 3 attempts with different query formulations, additional searches won't help.
- 5 calls × 5–10 sources = 25–50 data points — sufficient for ingredient supplier discovery.

### 6.4 Total tokens per run

With the 5-call cap, token consumption per ResearchAgent run:
- Input: system prompt (~800 tokens) + ingredient profile (~300 tokens) + grounded content (~2000–4000 tokens) = ~3000–5000 input tokens
- Output: structured records + sentinel line (~400–600 tokens)

Well within `gemini-2.5-flash`'s context window.

---

## 7. Integration with Surrounding Pipeline Nodes

### 7.1 Data flow

```
CLI trigger:
  python -m orchestration.dag_executor \
    --pipeline research_new_supplier \
    --canonical-id 7 \
    --required-certs NSF Kosher
    |
    v
query_ingredient_profile  (node: db_query_agent)
  - Reads: db_enriched.sqlite — Ingredient_Canonical, Consolidation_Opportunity,
           Supplier_Commercial, Product_Compliance
  - Output: ingredient name, CAS, current suppliers, compliance requirements, grade
    |
    v
search_suppliers  (node: search_agent — google_search ONLY)
  - Reads: AgnesContext.node_outputs["query_ingredient_profile"]
  - Runs: up to 5 google_search calls
  - Output: raw text with supplier candidates and source URLs
    |
    v
extract_and_stage  (node: research_agent)  ← THIS NODE
  - Reads: node_outputs["query_ingredient_profile"] + node_outputs["search_suppliers"]
  - Writes: Discovered_Supplier (N rows), API_Response_Cache, Enrichment_Run_Log
    |
    v
[Optional: human review step]
  - Operator inspects Discovered_Supplier WHERE Verified=0
  - Promotes to Supplier_Commercial after verification
```

### 7.2 What downstream consumers read from ResearchAgent output

| Consumer | Reads from | Field |
|---|---|---|
| Human reviewer | `Discovered_Supplier` | All fields, filtered by `Verified=0` |
| `reactive_fallout` pipeline (if called as fallback) | `Discovered_Supplier` | `Name`, `Certs_Claimed`, `Confidence` for ranking |
| `proactive_consolidation` pipeline | `Discovered_Supplier` | Supplements `Supplier_Commercial` gaps |
| `query_supplier.py` script | `Discovered_Supplier` | Shows unverified candidates alongside verified ones |

---

## 8. Model Choice Rationale

### Why `gemini-2.5-flash`

| Consideration | Flash | Pro |
|---|---|---|
| Task type | Retrieval + structured extraction | Deep reasoning |
| Speed | Faster (lower latency per node) | Slower |
| Cost | Significantly cheaper | More expensive |
| Quality for this task | Sufficient — supplier discovery is read-and-extract | Overkill |

Supplier research is primarily **retrieval and structured extraction**: find a supplier mention, extract name/country/URL/certs. `gemini-2.5-flash` handles this well. The grounded content it receives is factual (from Google Search), so hallucination risk is low.

### When to upgrade to Pro

Switch to `gemini-2.5-pro` if:
- Supplier names are in non-Latin scripts (Chinese, Arabic) and the agent confuses entities.
- The ingredient has ambiguous names (e.g. "Calcium" — carbonate vs citrate vs gluconate) and the agent fails to disambiguate.
- Cert extraction is consistently wrong (claiming NSF for a supplier that doesn't have it).

To switch: change `model="gemini-2.5-flash"` to `model="gemini-2.5-pro"` in `orchestration/agents/research_agent.py`. No other changes required.

---

## 9. Testing ResearchAgent

### 9.1 Manual test invocation

```bash
cd "/home/developer/Projects/Spherecast Agnes"
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from orchestration.dag_executor import run_pipeline
from orchestration.context import AgnesContext

ctx = AgnesContext(
    pipeline_name='research_new_supplier',
    canonical_id=7,           # Coenzyme Q10 — known DB gap
    required_certs=['NSF', 'Kosher'],
)
asyncio.run(run_pipeline('research_new_supplier', ctx))
"
```

### 9.2 What to verify in the output

After running, check:

1. **Discovered_Supplier rows written:**
```python
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
rows = conn.execute(
    "SELECT Name, Country, Certs_Claimed, Confidence FROM Discovered_Supplier "
    "WHERE CanonicalIngredientId = 7 AND Verified = 0"
).fetchall()
for r in rows: print(r)
```

2. **Run logged in Enrichment_Run_Log:**
```python
conn.execute(
    "SELECT Status, Method, Confidence FROM Enrichment_Run_Log "
    "WHERE Step = 'supplier_discovery' ORDER BY Run_At DESC LIMIT 5"
).fetchall()
```

3. **Search results cached:**
```python
conn.execute(
    "SELECT Cache_Key, LENGTH(Response) FROM API_Response_Cache "
    "WHERE Source = 'google_adk' ORDER BY Fetched_At DESC LIMIT 5"
).fetchall()
```

4. **Sentinel line present in agent output:**
```
DISCOVERY_COMPLETE: {N} candidates staged for canonical_id=7
```

5. **No writes to protected tables:**
```python
# Supplier_Commercial should be unchanged
count_before = 126  # known count before run
count_after = conn.execute("SELECT COUNT(*) FROM Supplier_Commercial").fetchone()[0]
assert count_after == count_before, "ResearchAgent wrote to Supplier_Commercial — forbidden"
```

---

## 10. Common Failure Modes

| Failure | Symptom | Fix |
|---|---|---|
| `GOOGLE_API_KEY` not set | Search returns no grounding; agent stages no candidates | Set `GOOGLE_API_KEY` in `.env` |
| Agent writes to `Supplier_Commercial` | Verified supplier table polluted with unverified data | `insert_discovered_supplier` tool hard-codes target table; if agent bypasses tool and uses raw SQL, add a write guard in `db_tools.py` |
| No `DISCOVERY_COMPLETE:` sentinel | DAG executor cannot confirm node completion | System prompt must explicitly end with sentinel. Add post-processing check in `execute_node`. |
| Duplicate suppliers staged | `Discovered_Supplier` fills with near-identical rows across runs | Step 2 (check existing rows) + `INSERT OR IGNORE` on `(CanonicalIngredientId, Name)` unique constraint |
| Certs over-claimed | Agent marks "NSF" for a supplier that only mentions "GMP" | Tighten cert extraction rules in prompt: "only include certs explicitly mentioned adjacent to this ingredient" |
| CAS-based queries return wrong compound | CAS is shared across salt forms (e.g. elemental Zn vs Zinc glycinate) | Use ingredient name + CAS together in queries, not CAS alone |
| Grounding metadata missing from ADK events | `event.grounding_metadata.grounding_chunks` empty | Known ADK issue (#1693, #3287). Rely on model text output — it is correctly grounded. Do not parse grounding chunks in code. |
| Search cache not hit on re-run | Same queries re-run instead of using cache | Verify `Cache_Key` computation uses identical string normalization (lowercase, stripped). Check `TTL_Days` not expired. |

---

## 11. Cross-Reference

| Document | Relevant sections |
|---|---|
| `REF-GOOGLE-ADK.md` | LlmAgent instantiation, InMemoryRunner per-node pattern, FunctionTool docstring format |
| `REF-YAML-PIPELINE-SCHEMA.md` | `research_new_supplier.yaml` DAG definition, node depends_on ordering |
| `google-adk-search-guide.md` | google_search isolation constraint, grounding metadata gotchas, batch_search pattern |
| `orchestration/tools/db_tools.py` | `insert_discovered_supplier`, `query_discovered_suppliers`, `log_run_step` implementations |
| `orchestration/agents/search_agent.py` | Isolated search sub-agent (google_search only) |
| `schema/enriched_schema.sql` | `Discovered_Supplier`, `API_Response_Cache`, `Enrichment_Run_Log` DDL |
| Google ADK docs | [Built-in tools](https://google.github.io/adk-docs/tools/built-in-tools/), [Google Search Grounding](https://google.github.io/adk-docs/grounding/google_search_grounding/) |
