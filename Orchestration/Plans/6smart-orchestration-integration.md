# Feature: Smart Orchestration — Phase 4 Reasoning Integration

> This plan is context-complete. Read every MANDATORY FILE before implementing each phase.
> Execute phases and tasks in order — each phase depends on the one before.

---

## Feature Description

Integrate the Phase 4 deterministic reasoning layer (`proposal.md`) with the existing FastAPI + DAG orchestration system so that every supply chain decision is made by a principled deterministic engine (gates, compliance, refusal, scoring) and LLM agents are demoted to narrative-only roles. The result is a traceable, auditable, replayable pipeline where you can see *exactly* which gate failed and why — with LLM polish on top, not in place of, the reasoning chain.

## User Story

As a sourcing analyst using Agnes,  
I want every supplier recommendation to include a full gate trace (why this supplier passed, why others were refused) with a confidence score,  
So that I can justify switching decisions to legal/finance and replay any run deterministically.

## Problem Statement

Current `ComplianceGateTool` checks `confidence >= 0.6` as a proxy for all compliance — it does not actually evaluate form, grade, regulatory jurisdiction, or morphology compatibility. `ReactiveAgent` makes recommendations via LLM free-form reasoning, which is neither auditable nor replayable. `RfqFormatterTool` produces in-memory dicts that disappear after a run.

## Solution Statement

Replace the thin compliance gate with a 4-gate deterministic qualification chain (grade → regulatory → confidence floor → supplier score) adapted from `proposal.md`. Introduce a `SupplierScorerTool` with Q·C·L·R formula. Persist RFQs to the DB. Demote all LLM agents to narrative polish — they explain a pre-decided verdict, they do not decide. Wire `ResearchAgent` with `search_sub_agent`. Initialize the Wiki system.

## Feature Metadata

**Feature Type**: Enhancement + Integration  
**Estimated Complexity**: High  
**Primary Systems Affected**: `orchestration/tools/`, `orchestration/pipelines/`, `orchestration/agents/`, `orchestration/api/`, `orchestration/schema/`  
**Dependencies**: `google-adk>=1.0.0`, `google-genai`, `anthropic`, Phase 4 `proposal.md` reasoning spec

---

## Architecture Map — Read This First

```
EVERY PIPELINE FLOW:

  HTTP trigger / chat
       │
       ▼
RouterAgent (Claude Haiku) ─── intent classify ──→ pipeline_name + params
       │
       ▼
dag_executor: topological sort → parallel layers → write events → orchestration.db
       │
       ▼
DETERMINISTIC TOOLS (synchronous, no LLM)         LLM AGENTS (narrative only)
  SupplierAlternativesTool   find candidates        ReactiveAgent    explains verdict
  SubstitutionWalkerTool     walk graph             ProactiveAgent   writes proposals
  BomImpactTool              count impact           ProposalWriter   writes summaries
  QualifyCandidateTool  ←──  4-gate qualify         ResearchAgent    web search + extract
  SupplierScorerTool         Q·C·L·R rank
  DraftRfqTool               persist RFQ
  OpportunityRankerTool      pull top-N COs
  PriceBenchmarkTool         flag outliers
```

### Pipeline Overview (post-integration)

```
supplier_fallout:
  find-alternatives → build-sku-profiles → qualify-candidates → score-suppliers → draft-rfqs → write-proposal
                    ↘                                                          ↗
                      bom-impact ──────────────────────────────────────────────

proactive_consolidation:
  scan-opportunities → qualify-candidates → score-suppliers → draft-rfqs → write-proposals
  scan-opportunities → bom-impact

substitution_discovery:
  find-substitutes → qualify-substitutes → score-substitutes → write-proposal

new_ingredient_research:
  web-research → gate-qualify → write-proposal

price_audit:
  find-alternatives → benchmark-prices → write-audit
```

### Agent Map

| Agent | Model | Trigger | Role | Prompt file |
|---|---|---|---|---|
| `RouterAgent` | claude-haiku-4-5-20251001 | Every `/chat` | Intent classify → pipeline + params | `agents/prompts/router_agent.md` |
| `ReactiveAgent` | gemini-2.5-flash | `supplier_fallout` final node | Explain pre-decided verdict in natural language | `agents/prompts/reactive_agent.md` |
| `ProactiveAgent` | gemini-2.5-flash | `proactive_consolidation` final node | Write executive proposal narratives | `agents/prompts/proactive_agent.md` |
| `ProposalWriter` | gemini-2.5-flash | `substitution_discovery`, `price_audit` final node | Write proposal/audit summary | `agents/prompts/proposal_writer.md` |
| `ResearchAgent` | gemini-2.5-flash | `new_ingredient_research` first node | Web search + structured supplier extraction | `agents/prompts/research_agent.md` |

### Tool Map

| Tool | Type | Input node outputs | Key output fields | Used in pipelines |
|---|---|---|---|---|
| `SupplierAlternativesTool` | Det. | trigger_payload | `alternatives[]`, `canonical_id` | supplier_fallout, new_ingredient_research |
| `BomImpactTool` | Det. | find-alternatives or scan-opportunities | `affected_products[]`, `product_count`, `company_count` | supplier_fallout, proactive_consolidation |
| `SkuProfileBuilderTool` | Det. NEW | find-alternatives | `profiles[]` (SkuProfile-shaped dicts) | supplier_fallout, substitution_discovery |
| `QualifyCandidateTool` | Det. NEW | build-sku-profiles OR find-substitutes | `qualified[]`, `refused[]`, `gate_traces[]` | supplier_fallout, proactive_consolidation, substitution_discovery |
| `SupplierScorerTool` | Det. NEW | qualify-candidates | `ranked_suppliers[]` (Q/C/L/R scored) | supplier_fallout, proactive_consolidation, substitution_discovery |
| `DraftRfqTool` | Det. NEW | score-suppliers | `rfq_ids[]`, `rfqs[]` persisted to DB | supplier_fallout, proactive_consolidation |
| `OpportunityRankerTool` | Det. | trigger_payload | `opportunities[]` | proactive_consolidation |
| `SubstitutionWalkerTool` | Det. | trigger_payload | `substitutes[]`, `canonical_id` | substitution_discovery |
| `PriceBenchmarkTool` | Det. | trigger_payload | `outliers[]`, `benchmark` | price_audit |
| `RfqFormatterTool` | DEPRECATED | — | — | Remove from registry |
| `ComplianceGateTool` | DEPRECATED | — | — | Remove from registry |

---

## CONTEXT REFERENCES

### MANDATORY: Read Before Implementing

- `orchestration/api/agnes_context.py` (lines 1–24) — `AgnesContext` shape; all tools take and return `ctx`
- `orchestration/api/dag_executor.py` (lines 55–76) — `_run_node` contract: `tool_class` → `run(ctx) -> dict`; `agent_class` → `await run(ctx) -> dict`
- `orchestration/api/agent_registry.py` (lines 1–41) — how to register new tools and agents
- `orchestration/api/conditions.py` (lines 1–53) — how condition guards work; pattern for adding new ones
- `orchestration/tools/supplier_alternatives.py` (lines 1–68) — canonical tool pattern: sqlite3.connect, row_factory, dict(r)
- `orchestration/tools/compliance_gate.py` (lines 1–86) — current gate tool to REPLACE (understand shape)
- `orchestration/tools/rfq_formatter.py` (lines 1–39) — current RFQ tool to REPLACE (understand shape)
- `orchestration/agents/reactive_agent.py` (lines 1–73) — current agent pattern: `_SYSTEM`, `LlmAgent`, `InMemoryRunner`
- `orchestration/pipelines/supplier_fallout.yaml` — YAML schema: name, trigger, nodes (id/tool_class/agent_class/depends_on/when)
- `orchestration/schema/pipeline_schema.sql` — existing DB schema for `orchestration.db`
- `Orchestration/Briefings by Agents for Agents/proposal.md` (§3–§6) — Phase 4 tool specs (GateEngine, ComplianceReasoner, RefusalEngine, SupplierScorer, qualify_candidate, draft_rfq)
- `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK.md` (§LlmAgent, §Per-Node InMemoryRunner) — ADK patterns
- `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK-RESEARCH-AGENT.md` (§5) — ResearchAgent system prompt + step-by-step instructions

### New Files to Create

```
orchestration/
  schema/
    reasoning_schema.sql          # New tables: Refusal_Record, Supplier_Score, RFQ, Substitution_Gate_Result
  tools/
    sku_profile_builder.py        # Adapter: supplier candidates → SkuProfile dicts
    qualify_candidate.py          # 4-gate + confidence floor qualify per candidate
    supplier_scorer.py            # Q·C·L·R weighted ranking
    draft_rfq.py                  # Persist RFQ rows to orchestration.db
  agents/
    prompts/
      router_agent.md             # Extract from router_agent.py _SYSTEM
      reactive_agent.md           # Rewrite: narrative-only, NOT decision-making
      proactive_agent.md          # Extract + refine from proactive_agent.py _SYSTEM
      proposal_writer.md          # New: for substitution/price_audit/research
      research_agent.md           # Full prompt from REF-GOOGLE-ADK-RESEARCH-AGENT.md §5

Orchestration/
  Wiki/
    index.md                      # LLM-maintained page catalog
    log.md                        # Append-only run log
```

### Files to Modify

```
orchestration/schema/pipeline_schema.sql       # Already exists; kept as-is; new schema in separate file
orchestration/api/db.py                        # Apply reasoning_schema.sql on init
orchestration/api/agent_registry.py            # Register 4 new tools, remove 2 deprecated
orchestration/api/conditions.py                # Add has_recommendations, has_verdict
orchestration/agents/reactive_agent.py         # Load prompt from file; strip decision logic
orchestration/agents/proactive_agent.py        # Load prompt from file; strip decision logic
orchestration/agents/research_agent.py         # Wire search_sub_agent + insert to Discovered_Supplier
orchestration/agents/proposal_writer.py        # Implement fully
orchestration/pipelines/supplier_fallout.yaml            # Add 2 new nodes, replace 2
orchestration/pipelines/proactive_consolidation.yaml     # Add qualify/score/draft nodes
orchestration/pipelines/substitution_discovery.yaml      # Add qualify/score nodes
```

---

## Patterns to Follow

### Tool Pattern (synchronous, deterministic)
```python
# Mirror: orchestration/tools/supplier_alternatives.py lines 14–68
import sqlite3
from pathlib import Path
from orchestration.api.agnes_context import AgnesContext

_DB_ENRICHED = Path(__file__).parent.parent.parent / "db_enriched.sqlite"
_DB_ORCH = Path(__file__).parent.parent.parent / "orchestration.db"

def run(ctx: AgnesContext) -> dict:
    prior_output = ctx.get("prior-node-id", {})
    # ... query, transform ...
    return {"key": value, "_source_node": "this-node-id"}
```

**Rules:**
- Always `conn.row_factory = sqlite3.Row` then `dict(r)` for each row
- Always read from `db_enriched.sqlite`; write to `orchestration.db` only
- Return dict with clearly named keys — downstream nodes call `ctx.get("this-node-id", {}).get("key")`
- Never raise — return `{"error": "...", "key": []}` on failure

### Agent Pattern (async, LLM narrative only)
```python
# Mirror: orchestration/agents/reactive_agent.py lines 1–73
from pathlib import Path
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types

_MODEL = "gemini-2.5-flash"
_SYSTEM = (Path(__file__).parent / "prompts" / "reactive_agent.md").read_text()

async def run(ctx: AgnesContext) -> dict:
    payload = json.dumps({...relevant ctx outputs...}, indent=2)
    agent = LlmAgent(name="...", model=_MODEL, instruction=_SYSTEM)
    runner = InMemoryRunner(agent=agent, app_name="agnes")
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="agnes", user_id="system")
    output_text = ""
    async for event in runner.run_async(...):
        if event.content and event.content.parts:
            output_text += event.content.parts[-1].text or ""
    return {"narrative": output_text.strip()}
```

**Rules for agents:**
- System prompt = explain/narrate the pre-decided verdict; never decide
- Build payload from `ctx.get("prior-node-id")` outputs; pass as JSON to LLM
- Check for missing API key; return graceful skip dict if absent
- `InMemoryRunner` fresh per invocation

### YAML Pipeline Schema
```yaml
# Mirror: orchestration/pipelines/supplier_fallout.yaml
name: pipeline_name
trigger: chat          # chat | data_update | manual | schedule
nodes:
  - id: node-id-kebab
    tool_class: RegistryKeyName       # OR
    agent_class: RegistryKeyName
    depends_on: [other-node-id]
    when: condition_name              # optional guard from conditions.py
```

### Condition Guard Pattern
```python
# Mirror: orchestration/api/conditions.py lines 7–13
def has_recommendations(ctx: AgnesContext) -> bool:
    out = ctx.get("qualify-candidates", {})
    return bool(out.get("qualified"))
```

---

## IMPLEMENTATION PLAN

### Phase 1: Schema — Reasoning Output Tables

Add tables for deterministic engine outputs so every decision is persisted and auditable.

**Tasks:**

**CREATE `orchestration/schema/reasoning_schema.sql`**
- **IMPLEMENT**: Four new tables applied against `orchestration.db`
- **CONTENT**:
```sql
-- Gate + compliance results per candidate per run
CREATE TABLE IF NOT EXISTS substitution_gate_result (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL,
    node_id         TEXT    NOT NULL,
    canonical_id    INTEGER NOT NULL,
    candidate_id    INTEGER,               -- supplier_id or substitute canonical_id
    candidate_name  TEXT    NOT NULL,
    gate_grade      TEXT,                  -- grade_gate: pass|fail
    gate_regulatory TEXT,                  -- regulatory_gate: pass|fail
    gate_confidence TEXT,                  -- confidence_gate: pass|fail
    gate_notes      TEXT    NOT NULL DEFAULT '{}',  -- JSON: per-gate reasoning
    compound_conf   REAL    NOT NULL DEFAULT 0.0,
    passed          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

-- Refused candidates with logged reason
CREATE TABLE IF NOT EXISTS refusal_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL,
    canonical_id    INTEGER NOT NULL,
    candidate_name  TEXT    NOT NULL,
    decision        TEXT    NOT NULL,  -- refuse_grade_fail|refuse_regulatory_fail|refuse_low_confidence|defer_human_review
    failing_gate    TEXT,
    compound_conf   REAL    NOT NULL DEFAULT 0.0,
    evidence        TEXT    NOT NULL DEFAULT '{}',  -- JSON: gate_result_id, cert_gaps
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

-- Q·C·L·R scores per supplier per run
CREATE TABLE IF NOT EXISTS supplier_score (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL,
    canonical_id    INTEGER NOT NULL,
    supplier_id     INTEGER,
    supplier_name   TEXT    NOT NULL,
    score_q         REAL,   -- quality: purity + grade match + confidence
    score_c         REAL,   -- cost: normalized price (lower = higher score)
    score_l         REAL,   -- logistics: normalized lead time (shorter = higher)
    score_r         REAL,   -- risk: single_source + country_risk
    total_score     REAL,
    weights         TEXT    NOT NULL DEFAULT '{}',  -- JSON: w_q/w_c/w_l/w_r used
    compliance_pass INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

-- Draft RFQs (Status='draft'; human must flip to 'sent')
CREATE TABLE IF NOT EXISTS rfq (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL,
    canonical_id    INTEGER NOT NULL,
    ingredient_name TEXT    NOT NULL,
    supplier_id     INTEGER,
    supplier_name   TEXT    NOT NULL,
    spec_json       TEXT    NOT NULL DEFAULT '{}',  -- full RFQ spec
    status          TEXT    NOT NULL DEFAULT 'draft',  -- draft|sent|responded|rejected
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    sent_at         TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_gate_result_run ON substitution_gate_result(run_id);
CREATE INDEX IF NOT EXISTS idx_refusal_run ON refusal_record(run_id);
CREATE INDEX IF NOT EXISTS idx_supplier_score_run ON supplier_score(run_id);
CREATE INDEX IF NOT EXISTS idx_rfq_run ON rfq(run_id);
CREATE INDEX IF NOT EXISTS idx_rfq_status ON rfq(status);
```
- **VALIDATE**: `sqlite3 /tmp/test_orch.db < orchestration/schema/reasoning_schema.sql && echo OK`

**UPDATE `orchestration/api/db.py`**
- **IMPLEMENT**: Apply `reasoning_schema.sql` in `init_db()` alongside `pipeline_schema.sql`
- **PATTERN**: Find existing `pipeline_schema.sql` apply block; mirror for `reasoning_schema.sql`
- **VALIDATE**: `uvicorn orchestration.api.main:app --port 8001` starts without error; check `orchestration.db` has all 6 tables

---

### Phase 2: Core Reasoning Tools

Three new deterministic tools that replace the thin `ComplianceGateTool` with a principled chain.

**Tasks:**

**CREATE `orchestration/tools/sku_profile_builder.py`**
- **IMPLEMENT**: Adapter that enriches supplier candidates from `find-alternatives` with data from `Ingredient_Canonical` and `Supplier_Commercial` into SkuProfile-shaped dicts needed by qualify_candidate
- **INPUT**: `ctx.get("find-alternatives", {})` → `alternatives[]`, `canonical_id`
- **DB READS**: `Ingredient_Canonical` (Id, Name, SMILES, UNII_Code, CAS_Number, Grade_Flag), `Supplier_Commercial` (Purity_Qualifier, Grade_Unverified, Country_Shipping)
- **OUTPUT**: `{"profiles": [SkuProfile...], "canonical_id": int, "ingredient_name": str}`
- **SkuProfile shape**:
```python
{
    "canonical_id": int,
    "supplier_id": int,
    "supplier_name": str,
    "smiles": str | None,           # from Ingredient_Canonical.SMILES
    "unii": str | None,             # from Ingredient_Canonical.UNII_Code
    "grade": str,                   # Grade_Flag: supplement|food|excipient|pharma
    "grade_supplier": str | None,   # Supplier_Commercial.Grade_Unverified (raw claim)
    "purity_pct": float | None,     # Supplier_Commercial.Purity_Pct
    "purity_qualifier": str | None, # Supplier_Commercial.Purity_Qualifier
    "country_shipping": str | None, # Supplier_Commercial.Country_Shipping (ISO 2)
    "price_usd_per_kg": float | None,
    "moq_kg": float | None,
    "lead_time_days": int | None,
    "confidence": float,
}
```
- **GOTCHA**: Also handles `find-substitutes` output (SubstitutionWalkerTool) — check both `ctx.get("find-alternatives")` and `ctx.get("find-substitutes")` for input
- **VALIDATE**: `python3 -c "from orchestration.tools.sku_profile_builder import run; print('OK')"`

**CREATE `orchestration/tools/qualify_candidate.py`**
- **IMPLEMENT**: 4-gate deterministic qualification chain per `proposal.md` §4.2–§4.4, adapted to available DB fields
- **INPUT**: `ctx.get("build-sku-profiles", {}).get("profiles", [])`; also reads `Product_Compliance` for required certs
- **GATES** (applied in order; first failure short-circuits):
  1. **Grade gate** — `profile.grade` must be ≥ product grade (supplement ≥ food ≥ excipient); never silently downshift
  2. **Regulatory gate** — supplier's `certs_claimed` (from `Product_Compliance` required certs) must cover required set; gap = gate fail
  3. **Confidence gate** — `profile.confidence >= 0.60`; below = `refuse_low_confidence`
  4. **Human-review flag** — if cert data absent and confidence 0.60–0.70, flag `defer_human_review` (pass but flagged)
- **WRITES TO DB** (`orchestration.db`): `substitution_gate_result` (one row per candidate), `refusal_record` (one row per refused candidate)
- **OUTPUT**:
```python
{
    "qualified": [profile + gate_trace_dict...],
    "refused": [profile + reason + failing_gate...],
    "deferred": [profile + defer_reason...],
    "gate_traces": [{candidate_name, grade_gate, regulatory_gate, conf_gate, compound_conf}],
    "qualified_count": int,
    "refused_count": int,
}
```
- **COMPOUND CONFIDENCE**: `grade_conf × regulatory_conf × base_confidence`; grade_conf=0.9 if match, 0.5 if gap, 0.0 if downshift; regulatory_conf=cert_coverage_ratio
- **GOTCHA**: Read `run_id` from `ctx.run_id` for DB writes; use `ctx.get("build-sku-profiles", {}).get("canonical_id")` to look up Product_Compliance
- **VALIDATE**: `python3 -c "from orchestration.tools.qualify_candidate import run; print('OK')"`

**CREATE `orchestration/tools/supplier_scorer.py`**
- **IMPLEMENT**: Q·C·L·R weighted ranking of qualified candidates per `proposal.md` §4.5
- **INPUT**: `ctx.get("qualify-candidates", {}).get("qualified", [])`
- **FORMULA**: `score = w_Q·Q + w_C·C + w_L·L − w_R·R` (weights: 0.35/0.30/0.20/0.15)
- **NORMALIZATION** (within current batch, not global):
  - Q (Quality): `purity_pct/100 * 0.6 + confidence * 0.4` → [0,1]
  - C (Cost): `1 - (price / max_price_in_batch)` if price available, else 0.5
  - L (Logistics): `1 - (lead_time / max_lead_time_in_batch)` if lead_time available, else 0.5
  - R (Risk): 0.3 if single supplier in DB, 0.1 if country_shipping in ['CN'] (higher risk), else 0.05
- **WRITES TO DB** (`orchestration.db`): `supplier_score` (one row per candidate including compliance-fail rows for audit trail)
- **OUTPUT**:
```python
{
    "ranked_suppliers": [
        {**profile, "score": float, "score_q": float, "score_c": float,
         "score_l": float, "score_r": float, "rank": int}
    ],
    "weights": {"w_q": 0.35, "w_c": 0.30, "w_l": 0.20, "w_r": 0.15},
    "top_supplier": supplier_name | None,
}
```
- **VALIDATE**: `python3 -c "from orchestration.tools.supplier_scorer import run; print('OK')"`

**CREATE `orchestration/tools/draft_rfq.py`**
- **IMPLEMENT**: Persist draft RFQ rows to `rfq` table in `orchestration.db` for top-3 ranked suppliers; replace `rfq_formatter.py`
- **INPUT**: `ctx.get("score-suppliers", {}).get("ranked_suppliers", [])`, BOM impact from `ctx.get("bom-impact", {})`
- **WRITES TO DB** (`orchestration.db`): `rfq` table (Status='draft'), top 3 suppliers
- **OUTPUT**:
```python
{
    "rfq_ids": [int, int, int],
    "rfqs": [{rfq_id, supplier_name, ingredient_name, spec_json}],
    "pricing_note": "Pricing indicative at research quantities — production volume requires direct negotiation.",
}
```
- **GOTCHA**: Include pricing disclaimer per `proposal.md` §6.3 (required whenever Price_Type='retail_proxy')
- **VALIDATE**: `python3 -c "from orchestration.tools.draft_rfq import run; print('OK')"`

---

### Phase 3: Registry + Conditions Update

**UPDATE `orchestration/api/agent_registry.py`**
- **ADD** to `_TOOL_REGISTRY`:
```python
"SkuProfileBuilderTool":  "orchestration.tools.sku_profile_builder:run",
"QualifyCandidateTool":   "orchestration.tools.qualify_candidate:run",
"SupplierScorerTool":     "orchestration.tools.supplier_scorer:run",
"DraftRfqTool":           "orchestration.tools.draft_rfq:run",
```
- **REMOVE** from `_TOOL_REGISTRY`:
```python
"ComplianceGateTool":     ...   # deprecated — delete this line
"RfqFormatterTool":       ...   # deprecated — delete this line
```
- **VALIDATE**: `python3 -c "from orchestration.api.agent_registry import get_tool; get_tool('QualifyCandidateTool'); print('OK')"`

**UPDATE `orchestration/api/conditions.py`**
- **ADD** three new conditions:
```python
def has_recommendations(ctx: AgnesContext) -> bool:
    """True if qualify-candidates produced at least one qualified candidate."""
    return bool(ctx.get("qualify-candidates", {}).get("qualified"))

def has_verdict(ctx: AgnesContext) -> bool:
    """True if score-suppliers produced at least one ranked result."""
    return bool(ctx.get("score-suppliers", {}).get("ranked_suppliers"))

def has_rfqs(ctx: AgnesContext) -> bool:
    """True if draft-rfqs produced persisted RFQ rows."""
    return bool(ctx.get("draft-rfqs", {}).get("rfq_ids"))
```
- **ADD** to `_REGISTRY`: `"has_recommendations"`, `"has_verdict"`, `"has_rfqs"`
- **VALIDATE**: `python3 -c "from orchestration.api.conditions import evaluate; print('OK')"`

---

### Phase 4: Pipeline YAML Updates

**UPDATE `orchestration/pipelines/supplier_fallout.yaml`**
- **REWRITE** with new node sequence (add build-sku-profiles, qualify-candidates, score-suppliers, draft-rfqs; remove gate-qualify and format-rfqs):
```yaml
name: supplier_fallout
trigger: chat
# US-01: Supplier can no longer deliver. Find alternatives → gate qualify → score → draft RFQs → narrative.
# Decision chain: deterministic. LLM (ReactiveAgent) explains verdict only.
nodes:
  - id: find-alternatives
    tool_class: SupplierAlternativesTool
    depends_on: []

  - id: bom-impact
    tool_class: BomImpactTool
    depends_on: [find-alternatives]

  - id: build-sku-profiles
    tool_class: SkuProfileBuilderTool
    depends_on: [find-alternatives]
    when: has_alternatives

  - id: qualify-candidates
    tool_class: QualifyCandidateTool
    depends_on: [build-sku-profiles]
    when: has_alternatives

  - id: score-suppliers
    tool_class: SupplierScorerTool
    depends_on: [qualify-candidates]
    when: has_recommendations

  - id: draft-rfqs
    tool_class: DraftRfqTool
    depends_on: [score-suppliers, bom-impact]
    when: has_verdict

  - id: write-proposal
    agent_class: ReactiveAgent
    depends_on: [draft-rfqs, qualify-candidates, bom-impact]
```

**UPDATE `orchestration/pipelines/proactive_consolidation.yaml`**
```yaml
name: proactive_consolidation
trigger: data_update
# US-02: Weekly/on-data-change consolidation scan.
# Ranks opportunities → qualify candidates → score → draft RFQs → executive proposals.
nodes:
  - id: scan-opportunities
    tool_class: OpportunityRankerTool
    depends_on: []

  - id: bom-impact
    tool_class: BomImpactTool
    depends_on: [scan-opportunities]

  - id: build-sku-profiles
    tool_class: SkuProfileBuilderTool
    depends_on: [scan-opportunities]
    when: above_score_threshold

  - id: qualify-candidates
    tool_class: QualifyCandidateTool
    depends_on: [build-sku-profiles]
    when: above_score_threshold

  - id: score-suppliers
    tool_class: SupplierScorerTool
    depends_on: [qualify-candidates]
    when: has_recommendations

  - id: draft-rfqs
    tool_class: DraftRfqTool
    depends_on: [score-suppliers, bom-impact]
    when: has_verdict

  - id: write-proposals
    agent_class: ProactiveAgent
    depends_on: [draft-rfqs, qualify-candidates, scan-opportunities]
```

**UPDATE `orchestration/pipelines/substitution_discovery.yaml`**
```yaml
name: substitution_discovery
trigger: chat
# US-04: Find functionally equivalent substitute ingredients.
# Graph walk → qualify substitutes → score → narrative.
nodes:
  - id: find-substitutes
    tool_class: SubstitutionWalkerTool
    depends_on: []

  - id: build-sku-profiles
    tool_class: SkuProfileBuilderTool
    depends_on: [find-substitutes]
    when: has_substitutes

  - id: qualify-substitutes
    tool_class: QualifyCandidateTool
    depends_on: [build-sku-profiles]
    when: has_substitutes

  - id: score-substitutes
    tool_class: SupplierScorerTool
    depends_on: [qualify-substitutes]
    when: has_recommendations

  - id: write-proposal
    agent_class: ProposalWriter
    depends_on: [score-substitutes, qualify-substitutes]
```

**VERIFY `orchestration/pipelines/price_audit.yaml`** — no changes needed; `PriceBenchmarkTool` → `ProposalWriter` flow is fine as-is.

---

### Phase 5: Agent Prompts as Markdown Files + Narrative Refactoring

**CREATE `orchestration/agents/prompts/` directory and all 5 prompt files.**

**CREATE `orchestration/agents/prompts/router_agent.md`**
- **IMPLEMENT**: Extract and expand the `_SYSTEM` string from `router_agent.py` line 15–33
- **CONTENT**: Keep the JSON format instruction, pipeline list, and param extraction. Add the 3 new pipelines: `substitution_discovery` and `price_audit` (already in router but missing from docstring). No behavioral changes.

**CREATE `orchestration/agents/prompts/reactive_agent.md`**
- **REWRITE**: Critical — change from "make recommendations" to "explain a pre-decided verdict"
- **CONTENT STRUCTURE**:
```markdown
You are Agnes, an AI supply chain analyst. A supplier fallout response has been computed.

## Your Role
You receive the output of a deterministic gate + scoring engine. You do NOT make 
qualification decisions — those have already been made. Your job is to explain 
the result in clear, professional language for a procurement manager.

## Input Structure
You will receive JSON with:
- `trigger`: the original request (ingredient, affected supplier)
- `bom_impact`: affected products and companies
- `qualify_candidates.qualified[]`: candidates that PASSED all gates (with gate_trace)
- `qualify_candidates.refused[]`: candidates that FAILED with reason + failing_gate
- `score_suppliers.ranked_suppliers[]`: gate-passed suppliers ranked by Q·C·L·R
- `draft_rfqs.rfqs[]`: draft RFQ records (id, supplier, spec)

## Output Format
1. **Situation** (1 sentence): what happened, how many products affected
2. **Recommendations** (table): rank / supplier / score / key metric / why it passed
3. **Refused suppliers** (list): name + reason (be specific about which gate failed)
4. **Immediate action**: "Issue RFQ #{id} to {top_supplier} for {ingredient}"
5. **Flags**: any deferred_human_review items, pricing disclaimers if retail_proxy

## Rules
- Never invent facts not present in the JSON payload
- If qualify_candidates.qualified is empty, say so clearly and explain why
- Always include the pricing disclaimer if Price_Type is 'retail_proxy'
```

**CREATE `orchestration/agents/prompts/proactive_agent.md`**
- **REWRITE**: Same narrative-only pattern; explain ranked+gated opportunity list
- **CONTENT**: headline → context → recommended supplier (from ranked_suppliers[0]) → savings narrative → compliance summary → next step (RFQ ID)

**CREATE `orchestration/agents/prompts/proposal_writer.md`**
- **IMPLEMENT**: Generic proposal writer for substitution_discovery and price_audit outputs
- **CONTENT**: Structured proposal with substitute options (for substitution) or price outlier report (for price_audit)

**CREATE `orchestration/agents/prompts/research_agent.md`**
- **IMPLEMENT**: Extract the full system prompt from `REF-GOOGLE-ADK-RESEARCH-AGENT.md` §5 (lines 228–384)
- **ADAPT**: Replace HappyRobot-specific fields with Agnes context fields

**UPDATE `orchestration/agents/reactive_agent.py`**
- **PATTERN**: `_SYSTEM = (Path(__file__).parent / "prompts" / "reactive_agent.md").read_text()`
- **REMOVE**: Old inline `_SYSTEM` string
- **UPDATE** payload assembly (lines 39–47): include `qualify_candidates`, `score_suppliers`, `draft_rfqs` from ctx; remove old `gate-qualify` key
- **VALIDATE**: `python3 -c "from orchestration.agents.reactive_agent import run; print('OK')"`

**UPDATE `orchestration/agents/proactive_agent.py`**
- **PATTERN**: Same `Path(__file__).parent / "prompts" / ...` pattern
- **UPDATE** payload assembly: include `qualify-candidates`, `score-suppliers`, `draft-rfqs` outputs
- **VALIDATE**: `python3 -c "from orchestration.agents.proactive_agent import run; print('OK')"`

**IMPLEMENT `orchestration/agents/proposal_writer.py`** (currently stub)
- **IMPLEMENT**: Same ADK InMemoryRunner pattern as reactive_agent.py
- **PROMPT FILE**: `agents/prompts/proposal_writer.md`
- **INPUT**: build payload from `ctx.get("score-substitutes")` or `ctx.get("benchmark-prices")`
- **VALIDATE**: `python3 -c "from orchestration.agents.proposal_writer import run; print('OK')"`

---

### Phase 6: ResearchAgent Full Implementation

**UPDATE `orchestration/agents/research_agent.py`** (currently returns empty stubs)

- **IMPLEMENT** full `run(ctx: AgnesContext) -> dict`:
  1. Load system prompt from `agents/prompts/research_agent.md`
  2. Get `ingredient_name` from `ctx.trigger_payload`
  3. Call `search_sub_agent.search(ingredient_name)` → raw text results
  4. Run extraction LlmAgent (second ADK agent, NO google_search) to parse supplier records from raw text
  5. For each extracted supplier: INSERT into `Discovered_Supplier` table in `db_enriched.sqlite` with `Verified=0`, `Source='google_adk'`
  6. Return structured dict
- **REQUIRES**: `GOOGLE_API_KEY` in env; graceful skip if absent
- **TOOL FLOW**: search_sub_agent (google_search isolated) → extraction agent (no tools, just structured parsing)
- **OUTPUT**:
```python
{
    "discovered_suppliers": [{"name", "country", "url", "certs_claimed", "price_range", "confidence"}],
    "staged_count": int,
    "search_query": str,
    "skipped": reason | None,
}
```
- **VERIFY** `Discovered_Supplier` table exists in `db_enriched.sqlite` — check `schema/enriched_schema.sql`; if not, `ALTER TABLE` or create it in a migration
- **VALIDATE**: `python3 -c "from orchestration.agents.research_agent import run; print('OK')"`

---

### Phase 7: Wiki Initialization

**CREATE `Orchestration/Wiki/index.md`**
```markdown
# Agnes Wiki — Page Index

> LLM-maintained. Last updated: 2026-04-18. Do not edit manually.

## Ingredients
(empty — populated by first proactive agent run)

## Suppliers  
(empty — populated by first research or reactive agent run)

## Proposals
(empty — populated by first reactive agent run)
```

**CREATE `Orchestration/Wiki/log.md`**
```markdown
# Agnes Agent Action Log

> Append-only. Format: `## [ISO_TIMESTAMP] pipeline_name | run_id=... | ...`

## [2026-04-18T00:00:00Z] init | system
Wiki initialized. Agnes orchestration layer active. Phase 4 reasoning integrated.
```

---

### Phase 8: Cleanup — Remove Deprecated Tools

**UPDATE `orchestration/api/agent_registry.py`**
- **REMOVE**: `ComplianceGateTool` and `RfqFormatterTool` entries from `_TOOL_REGISTRY`

**UPDATE `orchestration/agents/router_agent.py`**
- **REMOVE**: Inline `_SYSTEM` string; load from `agents/prompts/router_agent.md`
- **PATTERN**: `_SYSTEM = (Path(__file__).parent / "prompts" / "router_agent.md").read_text()`

---

## STEP-BY-STEP TASKS (Atomic Checklist)

Execute in this exact order — each builds on the previous.

### Task 1 — CREATE `orchestration/schema/reasoning_schema.sql`
- All 4 tables + 5 indexes
- **VALIDATE**: `sqlite3 /tmp/t.db < orchestration/schema/reasoning_schema.sql && echo "Schema OK"`

### Task 2 — UPDATE `orchestration/api/db.py` to apply reasoning_schema.sql
- **VALIDATE**: `python3 -c "from orchestration.api.db import init_db; from pathlib import Path; init_db(Path('/tmp/test_orch.db')); print('DB init OK')"`

### Task 3 — CREATE `orchestration/tools/sku_profile_builder.py`
- **VALIDATE**: `python3 -c "from orchestration.tools.sku_profile_builder import run; print('SKU builder OK')"`

### Task 4 — CREATE `orchestration/tools/qualify_candidate.py`
- **VALIDATE**: `python3 -c "from orchestration.tools.qualify_candidate import run; print('Qualify OK')"`

### Task 5 — CREATE `orchestration/tools/supplier_scorer.py`
- **VALIDATE**: `python3 -c "from orchestration.tools.supplier_scorer import run; print('Scorer OK')"`

### Task 6 — CREATE `orchestration/tools/draft_rfq.py`
- **VALIDATE**: `python3 -c "from orchestration.tools.draft_rfq import run; print('DraftRfq OK')"`

### Task 7 — UPDATE `orchestration/api/agent_registry.py` (add 4, remove 2)
- **VALIDATE**: `python3 -c "from orchestration.api.agent_registry import get_tool; [get_tool(t) for t in ['SkuProfileBuilderTool','QualifyCandidateTool','SupplierScorerTool','DraftRfqTool']]; print('Registry OK')"`

### Task 8 — UPDATE `orchestration/api/conditions.py` (add 3 conditions)
- **VALIDATE**: `python3 -c "from orchestration.api.conditions import _REGISTRY; assert 'has_recommendations' in _REGISTRY; print('Conditions OK')"`

### Task 9 — CREATE `orchestration/agents/prompts/` directory and all 5 `.md` files
- **VALIDATE**: `ls orchestration/agents/prompts/*.md | wc -l` → 5

### Task 10 — UPDATE `orchestration/agents/reactive_agent.py` (prompt from file, new payload keys)
- **VALIDATE**: `python3 -c "from orchestration.agents.reactive_agent import run; print('ReactiveAgent OK')"`

### Task 11 — UPDATE `orchestration/agents/proactive_agent.py` (prompt from file, new payload keys)
- **VALIDATE**: `python3 -c "from orchestration.agents.proactive_agent import run; print('ProactiveAgent OK')"`

### Task 12 — IMPLEMENT `orchestration/agents/proposal_writer.py` (from stub)
- **VALIDATE**: `python3 -c "from orchestration.agents.proposal_writer import run; print('ProposalWriter OK')"`

### Task 13 — IMPLEMENT `orchestration/agents/research_agent.py` (from stub)
- **VALIDATE**: `python3 -c "from orchestration.agents.research_agent import run; print('ResearchAgent OK')"`

### Task 14 — UPDATE `orchestration/agents/router_agent.py` (prompt from file)
- **VALIDATE**: `python3 -c "from orchestration.agents.router_agent import classify; print('RouterAgent OK')"`

### Task 15 — REWRITE `orchestration/pipelines/supplier_fallout.yaml`
- **VALIDATE**: `python3 -c "from orchestration.api.pipeline_loader import load; p = load('supplier_fallout'); print([n.id for n in p.nodes])"`
  - Expected: `['find-alternatives', 'bom-impact', 'build-sku-profiles', 'qualify-candidates', 'score-suppliers', 'draft-rfqs', 'write-proposal']`

### Task 16 — REWRITE `orchestration/pipelines/proactive_consolidation.yaml`
- **VALIDATE**: `python3 -c "from orchestration.api.pipeline_loader import load; p = load('proactive_consolidation'); print([n.id for n in p.nodes])"`

### Task 17 — REWRITE `orchestration/pipelines/substitution_discovery.yaml`
- **VALIDATE**: `python3 -c "from orchestration.api.pipeline_loader import load; p = load('substitution_discovery'); print([n.id for n in p.nodes])"`

### Task 18 — CREATE `Orchestration/Wiki/index.md` and `Orchestration/Wiki/log.md`
- **VALIDATE**: `ls Orchestration/Wiki/` → `index.md log.md`

### Task 19 — End-to-end dry run validation
- **VALIDATE**: 
```bash
cd "/home/developer/Projects/Spherecast Agnes"
uvicorn orchestration.api.main:app --port 8001 &
sleep 2
curl -s -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Our supplier for Vitamin C dropped out, find alternatives"}' | python3 -m json.tool
# Expect: run_id, pipeline=supplier_fallout, status=started
curl -s http://localhost:8001/runs/<run_id> | python3 -m json.tool
# Expect: events for all 7 nodes; status=completed or failed with traceable error
kill %1
```

---

## TESTING STRATEGY

### Unit Tests (if time permits)

**`tests/tools/test_qualify_candidate.py`**
- Test grade gate: supplement→supplement (pass), supplement→food (fail downshift)
- Test regulatory gate: required_certs=["NSF"], supplier has NSF (pass); supplier missing NSF (fail)
- Test confidence gate: 0.55 → refuse_low_confidence; 0.65 → pass; 0.62 → defer_human_review
- Test DB writes: verify `substitution_gate_result` and `refusal_record` rows created

**`tests/tools/test_supplier_scorer.py`**
- Test score formula: perfect profile (purity=100, lowest price, shortest lead) → score near 1.0
- Test normalization: batch of 3 suppliers, verify ranks are stable with different price ranges
- Test DB writes: verify `supplier_score` rows for ALL candidates (including compliance-fail)

**`tests/tools/test_sku_profile_builder.py`**
- Test with known canonical from db_enriched.sqlite: Vitamin C (canonical_id where Grade_Flag='supplement')
- Verify all SkuProfile fields populated or gracefully null

### Edge Cases to Test
- `find-alternatives` returns empty list → `build-sku-profiles` skipped (condition `has_alternatives` = false)
- All candidates fail gates → `score-suppliers` skipped; `ReactiveAgent` receives empty qualified list; must explain refusals
- `GOOGLE_API_KEY` absent → `ResearchAgent` returns `{"skipped": "GOOGLE_API_KEY not set", "discovered_suppliers": []}`; pipeline continues
- `ANTHROPIC_API_KEY` absent → `RouterAgent` raises; verify error is caught before classify() is called

---

## VALIDATION COMMANDS

### Level 1 — Import Sanity
```bash
cd "/home/developer/Projects/Spherecast Agnes"
python3 -c "
from orchestration.tools.sku_profile_builder import run
from orchestration.tools.qualify_candidate import run
from orchestration.tools.supplier_scorer import run
from orchestration.tools.draft_rfq import run
from orchestration.api.agent_registry import get_tool, get_agent
from orchestration.api.conditions import _REGISTRY
print('All imports OK')
print('New tools:', [k for k in ['SkuProfileBuilderTool','QualifyCandidateTool','SupplierScorerTool','DraftRfqTool']])
print('New conditions:', [k for k in _REGISTRY if k in ['has_recommendations','has_verdict','has_rfqs']])
"
```

### Level 2 — Pipeline Load
```bash
python3 -c "
from orchestration.api.pipeline_loader import load, list_pipelines
for name in list_pipelines():
    p = load(name)
    print(f'{name}: {[n.id for n in p.nodes]}')
"
```

### Level 3 — Server Startup
```bash
uvicorn orchestration.api.main:app --port 8001 --timeout-keep-alive 5 &
sleep 2
curl -s http://localhost:8001/ | python3 -m json.tool
curl -s http://localhost:8001/health
curl -s http://localhost:8001/pipelines | python3 -m json.tool
kill %1
```

### Level 4 — Full Pipeline Run (Deterministic Tools Only, No API Key Needed)
```bash
# Start server, trigger proactive_consolidation (uses OpportunityRankerTool first — no API needed)
uvicorn orchestration.api.main:app --port 8001 &
sleep 2
RUN_ID=$(curl -s -X POST http://localhost:8001/pipelines/run/proactive_consolidation \
  -H "Content-Type: application/json" \
  -d '{"top_n": 5}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
sleep 3
curl -s "http://localhost:8001/runs/$RUN_ID" | python3 -m json.tool
# Check: events for scan-opportunities, build-sku-profiles, qualify-candidates, score-suppliers
# Check: supplier_score and substitution_gate_result rows in orchestration.db
sqlite3 orchestration.db "SELECT COUNT(*) FROM supplier_score WHERE run_id='$RUN_ID'"
kill %1
```

### Level 5 — Reasoning DB Audit
```bash
sqlite3 orchestration.db "
SELECT COUNT(*) AS gate_results FROM substitution_gate_result;
SELECT COUNT(*) AS refusals FROM refusal_record;
SELECT COUNT(*) AS scores FROM supplier_score;
SELECT COUNT(*) AS rfqs FROM rfq;
SELECT decision, COUNT(*) FROM refusal_record GROUP BY decision;
"
```

---

## ACCEPTANCE CRITERIA

- [ ] `qualify_candidate.py` persists gate results to `substitution_gate_result` table with `passed`, `failing_gate`, `compound_conf` per candidate
- [ ] `qualify_candidate.py` persists all refusals to `refusal_record` with specific `decision` code (not just "failed")
- [ ] `supplier_scorer.py` persists Q/C/L/R breakdown to `supplier_score` for ALL candidates (including gate-failed ones for audit)
- [ ] `draft_rfq.py` inserts RFQ rows with `status='draft'`; never auto-sends
- [ ] `supplier_fallout.yaml` has 7 nodes in correct topological order; DAG executor respects `depends_on`
- [ ] `ReactiveAgent` system prompt contains NO decision-making instructions; only explain/narrate
- [ ] All 5 agent system prompts loaded from markdown files (no inline `_SYSTEM` strings > 5 lines)
- [ ] `ResearchAgent.run()` is fully implemented (not stub); returns structured dict with `discovered_suppliers`
- [ ] `Orchestration/Wiki/index.md` and `log.md` exist
- [ ] All deprecated tools (`ComplianceGateTool`, `RfqFormatterTool`) removed from registry
- [ ] Server starts clean: `uvicorn orchestration.api.main:app` with no import errors
- [ ] `/pipelines` endpoint lists all 5 pipelines
- [ ] End-to-end `supplier_fallout` run for Vitamin C produces gate traces in DB

---

## NOTES

### On `SkuProfileBuilderTool` for `proactive_consolidation`
The `scan-opportunities` output contains `canonical_id` and `recommended_supplier_id`. `SkuProfileBuilderTool` needs to handle this shape (one canonical, one supplier as recommended) vs. the `find-alternatives` shape (one canonical, many alternative suppliers). Check `ctx.get("scan-opportunities")` and `ctx.get("find-alternatives")` in priority order — the tool works for both.

### On Gate Simplification
The Phase 4 `proposal.md` specifies 6 gates including morphology (psd_bucket, surface_area, bulk_density). These fields are not in `db_enriched.sqlite`. Implement 4 gates only (grade, regulatory, confidence, human-review flag) for now. Add a `"morphology_gate": "skipped_no_data"` field in gate_notes JSON so the audit trail is honest about what was and wasn't checked.

### On `ComplianceGateTool` Deprecation
`new_ingredient_research.yaml` currently uses `ComplianceGateTool`. After this integration, replace its `gate-qualify` node with `build-sku-profiles → qualify-candidates` sequence (same as other pipelines). The `web-research` node outputs can be adapted by `SkuProfileBuilderTool` if it checks for `ctx.get("web-research")` as a third input source.

### On Phase 4 Branch Merge
If the `phase-4` branch has mature implementations of `GateEngine`, `ComplianceReasoner`, etc., cherry-pick and move them to `orchestration/tools/` rather than re-implementing. The plan above implements the gate logic from scratch within the tool contract but the logic spec in `proposal.md` §4.2–§4.4 is the source of truth either way.

### System Prompt Philosophy
Agents in this system are **narrators, not decision-makers**. Every decision (qualify/refuse/score/rank) is made by a deterministic tool and persisted to the DB before the LLM sees it. The LLM's job is to produce a human-readable explanation of what the engine decided and why. This is the auditable-by-design principle from `proposal.md` §1.

---

**Confidence Score: 8/10**  
High confidence because all integration points are clearly defined, the existing tool pattern is simple and consistent, and the gate logic spec is fully documented in `proposal.md`. Main risk: `SkuProfileBuilderTool` must handle two different input node shapes correctly (find-alternatives vs scan-opportunities), and `research_agent.py` depends on `GOOGLE_API_KEY` being set. Both are manageable with graceful fallbacks.
