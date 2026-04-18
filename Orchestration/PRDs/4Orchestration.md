# Agnes — Stage 3 Orchestration Layer PRD

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Active  
**Owner:** timbtz  
**Prerequisite:** Stage 2 complete (`db_enriched.sqlite` at v1.1, all enrichment phases run, 123 scored consolidation opportunities)

---

## 1. Executive Summary

Agnes Stage 3 builds the agent orchestration layer that sits on top of the enriched SQLite database and produces actionable supply chain intelligence. Where Stage 2 collected and structured data, Stage 3 reasons over it: detecting consolidation opportunities, responding to supplier disruptions, discovering new suppliers, and writing durable conclusions back to a persistent wiki so reasoning compounds across runs.

The orchestration layer is built around three coordinated components: **Google ADK agents** (`LlmAgent` with Gemini 2.5 Flash as primary model) that carry out reasoning and web research; a **YAML-defined DAG pipeline system** that makes every workflow declarative, auditable, and re-runnable; and a **Python DAG executor** that runs each pipeline deterministically — one node at a time, logging inputs and outputs at every step. A lightweight wiki (`Orchestration/Wiki/`) serves as the persistent reasoning layer between runs: agents read from it before deciding and write conclusions back after.

**MVP goal:** Three working agent pipelines (reactive, proactive, research), a functional DAG executor, an initialized wiki, and at least one end-to-end reactive agent run with a full logged evidence trail — all demonstrable in a hackathon context.

---

## 2. Mission

**Agnes Stage 3 exists to turn a richly-enriched static database into a living, reasoning supply chain intelligence system — one where every agent recommendation is traceable, auditable, and gets smarter with every run.**

### Core Principles

1. **Determinism over autonomy.** Every workflow is a named DAG of discrete steps. No free-form agent loops. The executor can pause, resume, or replay any step.
2. **Files are the message bus.** Agents communicate through wiki markdown files on disk — not session state or in-memory queues. This makes every intermediate conclusion durable and human-readable.
3. **YAML defines behavior; Python executes it.** Pipeline structure is declared in `.yaml` files validated by Pydantic. Changing a workflow means editing YAML, not Python.
4. **Reasoning compounds.** Every agent conclusion that matters is written back to the wiki. The next run starts richer than the last.
5. **Evidence everywhere.** Every agent decision links to the DAG step, wiki pages read, and data fields consulted. Nothing is a black box.

---

## 3. Target Users

### Primary: Sourcing Analyst (B2B)
- Manages procurement for 1–3 CPG supplement brands
- Comfortable with spreadsheets; not a developer
- Needs to understand *why* a recommendation was made, not just what it is
- Key pain: can't see cross-company purchasing patterns; negotiates blind

### Secondary: Agnes Operator / Developer
- Runs agent pipelines on demand or on schedule
- Needs clear logs, idempotent runs, and inspectable intermediate steps
- Key pain: black-box LLM outputs that can't be debugged when wrong

### Technical Profile
- The operator interface for Stage 3 MVP is **command-line** (`python orchestration/dag_executor.py --pipeline reactive_fallout --trigger supplier_id=42`)
- Stage 4 will add a web UI (out of scope here)

---

## 4. MVP Scope

### Core Functionality
- ✅ `orchestration/dag_executor.py` — deterministic DAG runner, per-node `InMemoryRunner`, step logging
- ✅ `orchestration/pipeline_loader.py` — Pydantic v2 YAML schema loader + validator
- ✅ `orchestration/context.py` — `AgnesContext` dataclass passed through all nodes
- ✅ `orchestration/agents/reactive_agent.py` — supplier fallout → find alternatives pipeline
- ✅ `orchestration/agents/proactive_agent.py` — consolidation opportunity refresh pipeline
- ✅ `orchestration/agents/research_agent.py` — new supplier discovery pipeline
- ✅ `orchestration/tools/db_tools.py` — SQLite query/upsert tools for agents
- ✅ `orchestration/tools/wiki_tools.py` — read/write/append wiki markdown tools
- ✅ `orchestration/tools/search_tools.py` — isolated Google ADK search sub-agent
- ✅ `orchestration/pipelines/reactive_fallout.yaml` — DAG definition for reactive pipeline
- ✅ `orchestration/pipelines/proactive_consolidation.yaml` — DAG definition for proactive pipeline
- ✅ `orchestration/pipelines/research_discovery.yaml` — DAG definition for research pipeline
- ✅ `Orchestration/Wiki/index.md` + `log.md` initialized
- ✅ YAML frontmatter headers in all Python agent files (metadata + trigger spec)
- ✅ At least one full end-to-end reactive run logged in `Wiki/log.md`

### Simple Python Utility Scripts (non-ADK)
- ✅ `orchestration/scripts/query_opportunities.py` — ranked CO table to stdout
- ✅ `orchestration/scripts/query_ingredient.py` — full ingredient profile to stdout
- ✅ `orchestration/scripts/query_supplier.py` — supplier + coverage data to stdout

### Out of Scope
- ❌ Stage 4 frontend / web UI (DAG canvas, proposal viewer, wiki browser)
- ❌ Scheduled / cron-based agent triggers (manual CLI only for MVP)
- ❌ Grade_Flag classifier and substitution rule name-fix (handled by parallel work stream)
- ❌ Molport commercial enrichment (needs `MOLPORT_API_KEY` — separate task)
- ❌ LLM proposal generation for top-50 COs (needs `ANTHROPIC_API_KEY` — separate task)
- ❌ Multi-user auth or access control
- ❌ Cloud deployment / containerization
- ❌ FastAPI backend (Stage 4)

---

## 5. User Stories

**US-1 — Reactive: Supplier fallout response**  
*As a sourcing analyst, when a supplier drops out, I want Agnes to automatically identify all affected ingredients and surface ranked alternative suppliers, so I can make a same-day switch with full compliance context.*  
Example: "Supplier 42 (Prinova USA) is dropping Vitamin D3. Show me alternative NSF-certified suppliers and which of our 12 affected companies each one can serve."

**US-2 — Proactive: Consolidation opportunity refresh**  
*As a sourcing analyst, I want to run a weekly consolidation scan that refreshes the top-10 scored opportunities with current reasoning and updated wiki pages, so proposals don't go stale.*  
Example: Vitamin C is top-ranked (33 companies, score=0.893). Re-query current suppliers, check if any new commercial data exists, update the proposal text.

**US-3 — Research: New supplier discovery**  
*As a sourcing analyst, when no suitable alternative exists in the database, I want Agnes to search the web for net-new compliant suppliers and stage them for review, so I'm never blocked by database gaps.*  
Example: "No NSF-certified Vitamin K2 supplier found in db.sqlite — search web for 'Vitamin K2 MK-7 bulk supplier NSF certificate' and extract contact + pricing."

**US-4 — Auditability: DAG step inspection**  
*As an operator, I want to inspect every step of any agent run — inputs, outputs, LLM calls — so I can debug wrong recommendations without re-running the full pipeline.*  
Example: `cat Orchestration/Wiki/log.md | grep "run_id=abc123"` shows exactly which data went into Node 4 and what came out.

**US-5 — Determinism: Idempotent re-runs**  
*As an operator, I want to re-run any pipeline safely without corrupting prior conclusions, so I can refresh stale data without risk.*

**US-6 — Wiki compounding: Rich starting context**  
*As an agent (technical story), before reasoning about Vitamin D3 consolidation, I want to read `Wiki/ingredients/vitamin-d3.md` to see all prior conclusions, so I don't start from scratch every run.*

**US-7 — CLI trigger: Simple operator UX**  
*As an operator, I want to trigger any pipeline from a single CLI command with clear arguments, so I don't need to understand ADK internals to run an agent.*  
Example: `python -m orchestration.dag_executor --pipeline reactive_fallout --supplier-id 42`

---

## 6. Core Architecture & Patterns

### High-Level Architecture

```
CLI trigger / FastAPI (future)
        │
        ▼
dag_executor.py          ← reads YAML, builds DAG, executes nodes in order
        │
        ├─ pipeline_loader.py    ← Pydantic v2 validates .yaml → PipelineDef
        ├─ context.py            ← AgnesContext dataclass (shared state object)
        │
        ├─ Node execution loop:
        │    for each node in topological order:
        │      1. resolve inputs (from context or prior node outputs)
        │      2. instantiate LlmAgent(model, instruction, tools)
        │      3. run via InMemoryRunner (fresh per node)
        │      4. store output in context
        │      5. append to Wiki/log.md
        │
        ├─ agents/               ← LlmAgent definitions (one file per agent type)
        │    reactive_agent.py   ← nodes: query_db → search → filter → rank → propose → wiki
        │    proactive_agent.py  ← nodes: rank_cos → enrich → generate → wiki
        │    research_agent.py   ← nodes: search → extract → validate → stage
        │
        ├─ tools/                ← plain Python functions registered as ADK FunctionTools
        │    db_tools.py         ← query_affected_ingredients, get_compliance_reqs, upsert_supplier
        │    wiki_tools.py       ← read_page, write_page, append_log, search_wiki
        │    search_tools.py     ← isolated LlmAgent with google_search (sub-agent pattern)
        │
        └─ pipelines/            ← YAML DAG definitions
             reactive_fallout.yaml
             proactive_consolidation.yaml
             research_discovery.yaml
```

### Directory Structure

```
Agnes/
├── orchestration/
│   ├── __init__.py
│   ├── dag_executor.py          # Main entry point + DAG runner
│   ├── pipeline_loader.py       # YAML → PipelineDef (Pydantic v2)
│   ├── context.py               # AgnesContext dataclass
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── reactive_agent.py    # YAML-headered; defines LlmAgent nodes for supplier fallout
│   │   ├── proactive_agent.py   # YAML-headered; defines LlmAgent nodes for consolidation
│   │   └── research_agent.py    # YAML-headered; defines LlmAgent nodes for discovery
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── db_tools.py          # SQLite FunctionTools
│   │   ├── wiki_tools.py        # Wiki read/write FunctionTools
│   │   └── search_tools.py      # Isolated google_search sub-agent wrapper
│   ├── pipelines/
│   │   ├── reactive_fallout.yaml
│   │   ├── proactive_consolidation.yaml
│   │   └── research_discovery.yaml
│   └── scripts/
│       ├── query_opportunities.py
│       ├── query_ingredient.py
│       └── query_supplier.py
└── Orchestration/
    └── Wiki/
        ├── index.md             # Page catalog (LLM-maintained)
        ├── log.md               # Append-only agent action log
        ├── ingredients/         # Per-canonical-ingredient pages
        ├── suppliers/           # Per-supplier profile pages
        └── proposals/           # Full evidence trail per proposal
```

### YAML Frontmatter Pattern (Python Agent Files)

Every agent Python file carries a YAML frontmatter block at the top as a module docstring. This gives operators and future LLM instances instant context without reading the code:

```python
"""
---
agent: reactive_agent
version: 1.0
trigger: supplier_fallout
model: gemini-2.5-flash
inputs:
  - supplier_id: int
outputs:
  - wiki_page: Orchestration/Wiki/proposals/{run_id}.md
  - log_entry: Orchestration/Wiki/log.md
nodes:
  - query_affected_ingredients
  - query_compliance_requirements
  - search_alternative_suppliers
  - filter_by_certification
  - rank_by_score
  - generate_proposal
  - update_wiki
wiki_reads:
  - Orchestration/Wiki/ingredients/{canonical_name}.md
  - Orchestration/Wiki/suppliers/{supplier_name}.md
wiki_writes:
  - Orchestration/Wiki/proposals/{run_id}.md
  - Orchestration/Wiki/log.md
description: >
  Given a supplier fallout event, identifies all affected canonical ingredients,
  queries compliance requirements, searches for alternative suppliers via web,
  filters by certification fit, ranks alternatives, and generates a structured
  proposal written to the wiki with full evidence trail.
---
"""
```

### YAML Pipeline DAG Schema

Each pipeline YAML defines nodes, their agent, prompt template, inputs, outputs, and dependencies:

```yaml
# orchestration/pipelines/reactive_fallout.yaml
pipeline: reactive_fallout
version: "1.0"
description: Supplier fallout → find compliant alternatives for all affected ingredients
trigger:
  type: manual
  required_args:
    - name: supplier_id
      type: int
      description: ID of the dropped supplier

nodes:
  - id: query_affected_ingredients
    agent: db_query_agent
    prompt: |
      Query db_enriched.sqlite for all canonical ingredients supplied by supplier_id={{ supplier_id }}.
      Return a JSON list: [{"canonical_id": int, "name": str, "cas": str}]
    outputs:
      - key: ingredient_list
        type: json_list

  - id: query_compliance_requirements
    agent: db_query_agent
    depends_on: [query_affected_ingredients]
    prompt: |
      For each ingredient in {{ ingredient_list }}, query Product_Compliance for required certifications.
      Return: {"canonical_id": int, "required_certs": ["NSF", "USP", ...]}
    outputs:
      - key: cert_requirements
        type: json_list

  - id: search_alternative_suppliers
    agent: search_agent
    depends_on: [query_affected_ingredients]
    prompt: |
      For each ingredient in {{ ingredient_list }}, search for bulk compliant suppliers.
      Query pattern: "{ingredient_name} bulk supplier certificate NSF"
      Return structured list with name, country, url, certifications, price_range.
    outputs:
      - key: candidate_list
        type: json_list

  - id: filter_by_certification
    agent: reasoning_agent
    depends_on: [query_compliance_requirements, search_alternative_suppliers]
    prompt: |
      Filter {{ candidate_list }} to only suppliers that meet {{ cert_requirements }}.
      Flag any compliance gaps with notes. Return filtered list with gap_notes field.
    outputs:
      - key: filtered_candidates
        type: json_list

  - id: rank_by_score
    agent: reasoning_agent
    depends_on: [filter_by_certification]
    prompt: |
      Rank {{ filtered_candidates }} by: compliance_fit (40%), price_competitiveness (35%),
      geographic_risk (25%). Return top-5 with rank, score, rationale per supplier.
    outputs:
      - key: ranked_list
        type: json_list

  - id: generate_proposal
    agent: reasoning_agent
    depends_on: [rank_by_score]
    wiki_reads:
      - ingredients/{canonical_name}.md
    prompt: |
      Generate a structured supplier switch proposal for each ingredient in {{ ranked_list }}.
      Read the wiki page for prior context if it exists.
      Output: markdown proposal with evidence trail + JSON summary.
    outputs:
      - key: proposal_text
        type: markdown

  - id: update_wiki
    agent: wiki_agent
    depends_on: [generate_proposal]
    wiki_writes:
      - proposals/{run_id}.md
      - log.md
    prompt: |
      Write {{ proposal_text }} to Wiki/proposals/{{ run_id }}.md.
      Append a log entry to Wiki/log.md with run_id, trigger, nodes_run, timestamp.
    outputs:
      - key: wiki_updated
        type: bool
```

### Per-Node InMemoryRunner Pattern

The DAG executor creates a **fresh `InMemoryRunner` per node** — not one runner for the whole pipeline. This prevents state bleed between nodes and makes each node independently replayable:

```python
async def execute_node(node_def: NodeDef, context: AgnesContext) -> NodeOutput:
    agent = build_agent(node_def)   # instantiate LlmAgent with correct model + tools
    session_service = InMemorySessionService()
    runner = InMemoryRunner(agent=agent, app_name=agent.name, session_service=session_service)
    session = await session_service.create_session(
        app_name=agent.name,
        user_id=context.run_id,
        session_id=f"{context.run_id}-{node_def.id}",
    )
    prompt = render_prompt(node_def.prompt, context)
    final_text = ""
    async for event in runner.run_async(
        user_id=context.run_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    final_text += part.text
    return NodeOutput(node_id=node_def.id, raw=final_text, context=context)
```

### google_search Isolation Pattern

`google_search` cannot be combined with other tools in the same `LlmAgent`. Use an isolated search sub-agent:

```python
# tools/search_tools.py
from google.adk.agents import LlmAgent
from google.adk.tools import google_search

_search_agent = LlmAgent(
    name="agnes_searcher",
    model="gemini-2.5-flash",
    instruction="Search the web for supply chain data. Return results with source URLs.",
    tools=[google_search],   # ← ONLY tool — no mixing
)

async def web_search(query: str) -> dict:
    """Search the web for supply chain data. Returns results with source URLs."""
    # Run via InMemoryRunner per-call pattern
    ...
```

The `search_agent` node type in YAML maps to this isolated wrapper.

---

## 7. Agent Specifications

### 7A — ReactiveAgent (`reactive_agent.py`)

**Trigger:** Supplier fallout event (manual CLI for MVP)  
**Input:** `supplier_id: int`  
**Nodes:** 7 (see YAML above)  
**Wiki reads:** `ingredients/{name}.md`, `suppliers/{name}.md`  
**Wiki writes:** `proposals/{run_id}.md`, `log.md`  
**Key tool requirements:** `db_tools.query_affected_ingredients`, `db_tools.query_compliance_requirements`, `search_tools.web_search`, `wiki_tools.read_page`, `wiki_tools.write_page`

### 7B — ProactiveAgent (`proactive_agent.py`)

**Trigger:** On-demand consolidation refresh  
**Input:** `top_n: int = 10` (how many top COs to process)  
**Nodes:**
1. `rank_consolidation_opportunities` — query CO table, sort by score, take top N
2. `read_wiki_context` — for each CO, read existing wiki page if present
3. `enrich_stale_data` — for COs with `Generated_At` > 7 days old, trigger search refresh
4. `generate_proposals` — Claude-quality reasoning over top opportunities
5. `update_opportunities_db` — upsert `Proposal_Text` + `Generated_At` in CO table
6. `update_wiki` — write/update ingredient wiki pages + log entry  
**Wiki reads:** `ingredients/{name}.md` per CO  
**Wiki writes:** `ingredients/{name}.md` (updated), `log.md`

### 7C — ResearchAgent (`research_agent.py`)

**Trigger:** On-demand (called as fallback by ReactiveAgent, or standalone)  
**Input:** `canonical_id: int`, `required_certs: list[str]`  
**Nodes:**
1. `build_search_queries` — construct 3–5 targeted queries from ingredient name + required certs
2. `search_suppliers` — run each query via `search_tools.web_search`, collect results
3. `extract_supplier_records` — structured extraction from result snippets (name, country, url, certs, price_range)
4. `validate_via_pubchem` — cross-check any provided CAS numbers against PubChem
5. `stage_discovered_suppliers` — insert into `Discovered_Supplier` table (flagged `unverified`)
6. `update_wiki` — write `suppliers/{name}.md` stub pages + log entry  
**Wiki reads:** `ingredients/{name}.md`  
**Wiki writes:** `suppliers/{name}.md` (new stubs), `index.md` (updated), `log.md`

---

## 8. Tool Specifications

### `db_tools.py`

All tools accept a `db_path` defaulting to `ROOT/db_enriched.sqlite`. All return `dict` (ADK FunctionTool requirement).

| Tool Function | Purpose | Returns |
|---|---|---|
| `query_affected_ingredients(supplier_id)` | Get all canonicals supplied by given supplier | `list[dict]` with canonical_id, name, cas |
| `query_compliance_requirements(canonical_ids)` | Get required certs per canonical from Product_Compliance | `list[dict]` |
| `query_consolidation_opportunities(top_n, min_score)` | Ranked CO rows with stats | `list[dict]` |
| `query_ingredient_profile(canonical_id)` | Full canonical row + SKU count + company count | `dict` |
| `query_supplier_profile(supplier_id)` | Supplier row + ingredient coverage | `dict` |
| `upsert_proposal(co_id, proposal_text, proposal_json)` | Write proposal back to CO table | `dict` with status |
| `insert_discovered_supplier(name, country, url, certs, price_range, canonical_id)` | Stage net-new supplier | `dict` with id |

### `wiki_tools.py`

Wiki root: `AGNES_ROOT/Orchestration/Wiki/`

| Tool Function | Purpose | Returns |
|---|---|---|
| `read_page(relative_path)` | Read a wiki markdown file | `dict` with status + content |
| `write_page(relative_path, content)` | Write/overwrite a wiki markdown file | `dict` with status |
| `append_log(entry)` | Append entry to `log.md` with timestamp prefix | `dict` with status |
| `search_wiki(query)` | Grep-based search across all wiki pages | `list[dict]` with path + snippet |
| `list_pages(subdirectory)` | List all .md files under a wiki subdirectory | `list[str]` |

Log entry format:
```
## [2026-04-18T14:32:01Z] reactive_fallout | run_id=abc123 | supplier_id=42
Nodes run: 7/7 | Duration: 42s | Ingredients affected: 3 | Proposals written: 3
```

### `search_tools.py`

| Tool Function | Purpose | Returns |
|---|---|---|
| `web_search(query)` | Google ADK search (isolated sub-agent) | `dict` with text + source_urls |
| `batch_search(queries, delay_sec)` | Run multiple queries with politeness delay | `list[dict]` |

Search caching: all search results are cached in `API_Response_Cache` table (`Source='google_adk'`, `TTL_Days=7`).

---

## 9. AgnesContext Dataclass

Adapted from the HappyRobot `PipelineContext` pattern to Agnes's domain:

```python
# orchestration/context.py
from dataclasses import dataclass, field
from datetime import datetime
import uuid

@dataclass
class AgnesContext:
    pipeline_name: str              # "reactive_fallout" | "proactive_consolidation" | "research_discovery"
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    triggered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Trigger-specific inputs (populated by CLI / caller)
    supplier_id: int | None = None
    canonical_id: int | None = None
    top_n: int = 10
    required_certs: list[str] = field(default_factory=list)

    # Accumulated node outputs (populated by executor as nodes complete)
    node_outputs: dict[str, str] = field(default_factory=dict)

    # Wiki paths resolved at runtime
    wiki_root: str = ""             # absolute path to Orchestration/Wiki/

    def store(self, node_id: str, output: str) -> None:
        self.node_outputs[node_id] = output

    def get(self, node_id: str) -> str | None:
        return self.node_outputs.get(node_id)
```

---

## 10. Pipeline Loader (YAML → Pydantic)

```python
# orchestration/pipeline_loader.py
from pydantic import BaseModel, field_validator
from pathlib import Path
import yaml

class NodeDef(BaseModel):
    id: str
    agent: str                      # "db_query_agent" | "search_agent" | "reasoning_agent" | "wiki_agent"
    prompt: str
    depends_on: list[str] = []
    wiki_reads: list[str] = []
    wiki_writes: list[str] = []
    outputs: list[dict] = []

class PipelineDef(BaseModel):
    pipeline: str
    version: str
    description: str
    trigger: dict
    nodes: list[NodeDef]

    @field_validator("nodes")
    @classmethod
    def no_circular_deps(cls, nodes):
        # Topological sort validation — raises ValueError on cycle
        ...
        return nodes

def load_pipeline(name: str) -> PipelineDef:
    path = Path(__file__).parent / "pipelines" / f"{name}.yaml"
    raw = yaml.safe_load(path.read_text())
    return PipelineDef.model_validate(raw)
```

---

## 11. Wiki Initialization

`Orchestration/Wiki/` must be initialized before any agent runs. The DAG executor auto-initializes on first run if the directory is absent.

### `index.md` initial content

```markdown
# Agnes Wiki — Page Index

> LLM-maintained. Last updated: {date}. Do not edit manually.

## Ingredients
(empty — populated by first proactive agent run)

## Suppliers
(empty — populated by first research or reactive agent run)

## Proposals
(empty — populated by first reactive agent run)
```

### `log.md` initial content

```markdown
# Agnes Agent Action Log

> Append-only. Format: `## [ISO_TIMESTAMP] pipeline_name | run_id=... | ...`

## [2026-04-18T00:00:00Z] init | system
Wiki initialized. Agnes Stage 3 orchestration layer active.
```

---

## 12. Technology Stack

### Core
| Library | Version | Purpose |
|---|---|---|
| `google-adk` | `>=1.0.0` | LlmAgent, InMemoryRunner, InMemorySessionService |
| `google-genai` | `>=1.0.0` | Gemini model client |
| `pydantic` | `>=2.0.0` | YAML schema validation |
| `pyyaml` | `>=6.0` | YAML parsing |
| `anthropic` | `>=0.40.0` | Claude API (optional nodes) |
| `python-dotenv` | `>=1.0.0` | `.env` loading |
| `jinja2` | `>=3.1.0` | Prompt template rendering (`{{ variable }}` in YAML) |

### Models
| Model | Use | Notes |
|---|---|---|
| `gemini-2.5-flash` | **Primary** — all reasoning, query, proposal nodes | Fast, cost-effective, ADK-native |
| `gemini-2.5-pro` | Optional upgrade for proposal generation nodes | Higher quality, slower |
| `claude-sonnet-4-6` | Optional — proposal nodes if `ANTHROPIC_API_KEY` set | Requires env var; not default |

### Already in `requirements.txt` (Stage 2 carryover)
`requests`, `sqlite3` (stdlib), `rapidfuzz`, `playwright`, `beautifulsoup4`, `python-dotenv`

### New additions to `requirements.txt`
```
# Stage 3 additions
pyyaml>=6.0
jinja2>=3.1.0
```

Note: `google-adk>=0.5.0` in current `requirements.txt` is too loose — update to `>=1.0.0` (latest stable: 1.29.0; avoid 1.27.0 which was yanked).

### Environment Variables
```bash
# Required for Stage 3
GOOGLE_API_KEY=AIza...                  # From aistudio.google.com (free)
GOOGLE_GENAI_USE_VERTEXAI=false        # Required for API key auth (not Vertex AI)

# Optional
ANTHROPIC_API_KEY=sk-ant-...           # Only needed if using Claude nodes
```

---

## 13. Security & Configuration

### Authentication
- Google Gemini: API key via `GOOGLE_API_KEY` env var + `GOOGLE_GENAI_USE_VERTEXAI=false`
- No user-facing auth in Stage 3 (CLI-only operator interface)
- Wiki files are local filesystem — no access control needed for MVP

### Configuration Management
- All keys in `.env` (copy from `.env.template`)
- No secrets in YAML pipeline files or Python agent files
- `YAML_PIPELINE_DIR` defaults to `orchestration/pipelines/` — can be overridden via env var for testing

### Path Safety
- `wiki_tools.write_page()` must validate all paths remain within `WIKI_ROOT` (no path traversal)
- `db_tools` operate on `db_enriched.sqlite` only — never touch `db.sqlite`

### In-Scope Security
- ✅ Wiki path traversal prevention
- ✅ No writes to `db.sqlite` (read-only source of truth)
- ✅ All agent-discovered supplier data flagged `unverified` until human review

### Out-of-Scope Security
- ❌ API key rotation / secrets management
- ❌ Multi-user RBAC
- ❌ Network egress controls

---

## 14. CLI Interface

```bash
# Run reactive pipeline (supplier fallout)
python -m orchestration.dag_executor \
  --pipeline reactive_fallout \
  --supplier-id 42

# Run proactive pipeline (top-10 consolidation refresh)
python -m orchestration.dag_executor \
  --pipeline proactive_consolidation \
  --top-n 10

# Run research pipeline (discover new suppliers for ingredient)
python -m orchestration.dag_executor \
  --pipeline research_discovery \
  --canonical-id 7 \
  --required-certs NSF USP

# Dry-run: print DAG without executing
python -m orchestration.dag_executor \
  --pipeline reactive_fallout \
  --supplier-id 42 \
  --dry-run

# Utility scripts (non-ADK)
python orchestration/scripts/query_opportunities.py --top 20
python orchestration/scripts/query_ingredient.py --name "Vitamin C"
python orchestration/scripts/query_supplier.py --id 42
```

---

## 15. Success Criteria

### MVP Success Definition
A working Stage 3 orchestration layer that can run a full reactive pipeline for any supplier ID from the database, produce a structured proposal in `Orchestration/Wiki/proposals/`, log every step in `Wiki/log.md`, and be demonstrated live in a hackathon context.

### Functional Requirements
- ✅ `dag_executor.py` runs a full 7-node reactive pipeline to completion without error
- ✅ YAML pipeline files load and validate via Pydantic without errors
- ✅ At least one end-to-end reactive run produces a logged wiki proposal
- ✅ All three pipeline YAML files exist and are syntactically valid
- ✅ All three agent Python files exist with correct YAML frontmatter
- ✅ `wiki_tools.py` read/write/append all work correctly
- ✅ `db_tools.py` can query affected ingredients, compliance, and COs
- ✅ `search_tools.py` google_search isolation pattern works (search sub-agent)
- ✅ `Wiki/index.md` and `Wiki/log.md` exist and are updated after first run
- ✅ CLI `--dry-run` prints DAG topology without executing
- ✅ All three utility scripts produce output without error

### Quality Indicators
- DAG executor respects `depends_on` ordering (no node runs before its dependencies)
- Each node's output is captured in `AgnesContext.node_outputs` and readable in subsequent nodes
- Re-running the same pipeline produces updated wiki content without corrupting prior entries (log.md is append-only; proposal pages are overwritten with `run_id` versioning)
- `requirements.txt` `google-adk` version updated to `>=1.0.0`

---

## 16. Implementation Phases

### Phase A — Foundation (DAG executor + loader + context)
**Goal:** The execution engine exists and can run a trivial 2-node pipeline end-to-end.  
**Deliverables:**
- ✅ `orchestration/__init__.py`, `context.py`, `pipeline_loader.py`, `dag_executor.py`
- ✅ `orchestration/tools/db_tools.py` (query functions)
- ✅ `orchestration/tools/wiki_tools.py` (read/write/append/search)
- ✅ `Orchestration/Wiki/index.md` + `log.md` initialized
- ✅ `requirements.txt` updated (`pyyaml`, `jinja2`, `google-adk>=1.0.0`)

**Validation:** `python -m orchestration.dag_executor --dry-run` runs without import error.

### Phase B — Search tools + reactive pipeline
**Goal:** The reactive supplier fallout pipeline runs end-to-end.  
**Deliverables:**
- ✅ `orchestration/tools/search_tools.py` (isolated google_search sub-agent)
- ✅ `orchestration/agents/reactive_agent.py` (with YAML frontmatter)
- ✅ `orchestration/pipelines/reactive_fallout.yaml` (7-node DAG)
- ✅ First full reactive run logged in `Wiki/log.md`
- ✅ Proposal written to `Wiki/proposals/`

**Validation:** `python -m orchestration.dag_executor --pipeline reactive_fallout --supplier-id 1` completes, produces a wiki proposal, and logs all 7 steps.

### Phase C — Proactive + research pipelines
**Goal:** All three pipelines exist and run.  
**Deliverables:**
- ✅ `orchestration/agents/proactive_agent.py` (with YAML frontmatter)
- ✅ `orchestration/pipelines/proactive_consolidation.yaml`
- ✅ `orchestration/agents/research_agent.py` (with YAML frontmatter)
- ✅ `orchestration/pipelines/research_discovery.yaml`
- ✅ Wiki ingredient and supplier pages populated after proactive + research runs

**Validation:** All three pipelines run without error from CLI; wiki has pages in `ingredients/`, `suppliers/`, and `proposals/` after the three runs.

### Phase D — Utility scripts + polish
**Goal:** Operator usability and README accuracy.  
**Deliverables:**
- ✅ `orchestration/scripts/query_opportunities.py`
- ✅ `orchestration/scripts/query_ingredient.py`
- ✅ `orchestration/scripts/query_supplier.py`
- ✅ `README.md` updated: correct `Orchestration/References/` structure, `orchestration/` section marked as built
- ✅ `CLAUDE.md` Current State table updated with Stage 3 status

**Validation:** All three query scripts run and produce formatted output; README accurately reflects repository structure.

---

## 17. Future Considerations (Stage 4 + beyond)

- **FastAPI backend** (`GET /proposals`, `GET /agents/{run_id}`, `GET /wiki/{page}`) — Stage 4 foundation
- **DAG canvas visualization** with Alpine.js (reference: `REF-DAG-CANVAS-ALPINEJS.md`) — nodes light up live during execution
- **Scheduled triggers** via cron or APScheduler — weekly proactive consolidation refresh
- **SSE streaming** (reference: `REF-SSE-STREAMING-FASTAPI.md`) — stream node completions to the DAG canvas in real time
- **Human-in-the-loop review** — `Wiki/proposals/` pages show Approve/Flag/Reject actions in the Stage 4 UI
- **Discovered supplier verification** — `Discovered_Supplier` table rows promoted to `Supplier_Product` after human review
- **Multi-run diffing** — compare two wiki proposal pages for the same ingredient to see what changed
- **Grade_Flag integration** — once `grade_classifier.py` is done, proactive agent can filter COs by grade type

---

## 18. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `google_search` quota exhaustion (100 req/day free tier) | Medium | Cache all search results in `API_Response_Cache` with 7-day TTL; batch queries; `--dry-run` mode for testing without consuming quota |
| ADK version instability (1.27.0 was yanked) | Low | Pin to `>=1.0.0,!=1.27.0` in requirements; reference `REF-GOOGLE-ADK.md` for confirmed-working patterns |
| LLM hallucination in supplier extraction (wrong CAS, invented certifications) | Medium | All discovered suppliers flagged `unverified`; proposal text includes explicit `data_gaps` field; agents instructed never to invent regulatory data |
| DAG cycle / dependency error in YAML | Low | Pydantic validator runs topological sort on load; invalid YAML fails at import time, not runtime |
| Wiki file conflicts on parallel runs | Low | MVP is single-process CLI; parallel runs are Stage 4 concern; `run_id` in proposal filenames prevents overwrite |

---

## 19. Appendix

### Related Documents
| Document | Path | Purpose |
|---|---|---|
| ADK Reference | `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK.md` | LlmAgent, InMemoryRunner, per-node pattern |
| ADK Research Agent | `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK-RESEARCH-AGENT.md` | ResearchAgent node patterns |
| YAML Pipeline Schema | `Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md` | Pydantic v2 YAML loader reference |
| DAG Canvas UI | `Orchestration/References/Tech/Orchestration/REF-DAG-CANVAS-ALPINEJS.md` | Stage 4 DAG visualization (future) |
| Google ADK Search | `Orchestration/References/Tech/Orchestration/google-adk-search-guide.md` | google_search isolation constraint + caching |
| Claude API Patterns | `Orchestration/References/Tech/APIS/claude-api-patterns-guide.md` | Claude tool use patterns (optional nodes) |
| LLM Wiki Pattern | `Orchestration/Data/llm-wiki.md` | Wiki architecture rationale |
| Full PRD | `Orchestration/PRDs/PRD.md` | Complete Agnes product requirements |
| meta-workflow | `Orchestration/PRDs/meta-workflow.md` | Four-stage implementation plan |
| NextSessionBrief | `Orchestration/Briefings by Agents for Agents/NextSessionBrief.md` | Current DB state + remaining data gaps |

### Key Constants
```python
AGNES_ROOT = Path(__file__).parent.parent          # repo root
ENRICHED_DB = AGNES_ROOT / "db_enriched.sqlite"
WIKI_ROOT = AGNES_ROOT / "Orchestration" / "Wiki"
PIPELINE_DIR = AGNES_ROOT / "orchestration" / "pipelines"
```

### README Stale Paths (to fix in Phase D)
The README and meta-workflow.md describe `Orchestration/References/` as a flat directory. Actual structure:
```
References/
├── APIS/         ← dsld-, molport-, usda-fdc-, free-apis-, claude-api-patterns guides
└── Tech/
    ├── General/  ← FastAPI, SSE streaming guides
    ├── Orchestration/ ← ADK, YAML schema, DAG canvas, search guides
    └── Scraping/ ← browser, retailer, image extraction guides
```
