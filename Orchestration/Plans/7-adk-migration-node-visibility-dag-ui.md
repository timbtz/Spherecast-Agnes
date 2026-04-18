# Feature: ADK Migration, Node Visibility & DAG Visualization

The following plan should be complete, but validate documentation and codebase patterns before starting.
Pay special attention to ADK import paths (`from google.adk.agents import LlmAgent`, NOT `from google.adk import Agent`)
and the `GOOGLE_GENAI_USE_VERTEXAI=false` env requirement for API-key auth.

## Feature Description

Migrate all orchestration agents from the Anthropic SDK (Claude Haiku) to Google ADK / Gemini 2.5 Flash — except `ProposalWriter`, which keeps Claude Sonnet for the same reason Haiku was too weak: executive-quality proposals require multi-dimensional trade-off reasoning that Flash does not reliably produce. Simultaneously: (1) add a `node_started` event to the DAG executor so frontends can show in-progress nodes; (2) eliminate hardcoded `db_enriched.sqlite` paths in all 7 tools by routing through `AgnesContext`; (3) properly wire `search_sub_agent.py` into `ResearchAgent`; (4) fix the benign `RouterAgent` registry entry; and (5) build a lightweight SSE-powered DAG visualization page served by FastAPI.

## User Story

As an Agnes operator  
I want to watch a live pipeline execute node-by-node in a browser  
So that I can debug, demo, and trust the deterministic execution layer

## Problem Statement

- All agents use Claude Haiku despite most tasks being simple narrative generation or classification — Gemini Flash is faster, cheaper, and native to ADK/google_search
- `ResearchAgent` never calls `search_sub_agent.py`; it falls back to Claude's training knowledge instead of live web search
- `node_started` event is missing — frontend can only show final node states, not in-progress nodes
- All 7 tools hardcode the `db_enriched.sqlite` path; any project relocation breaks them silently
- `RouterAgent` is registered as `router_agent:run` but the module exports `classify()` — will crash if ever invoked as a pipeline node
- No browser UI exists to observe pipeline execution

## Solution Statement

1. Create a shared ADK helper (`_adk_runner.py`) and rewrite four agents to use `LlmAgent` + `InMemoryRunner` with `gemini-2.5-flash`
2. Keep `ProposalWriter` on Claude but upgrade Haiku → Sonnet 4.6 (reasoning quality justification below)
3. Wire `search_sub_agent.search()` into `ResearchAgent` as the real search path
4. Add `enriched_db_path: Path` to `AgnesContext`; all tools use `ctx.enriched_db_path`
5. Emit `node_started` event at the top of `_run_node` in `dag_executor.py`
6. Add `GET /pipelines/{name}/graph` endpoint returning DAG layers as JSON
7. Serve `orchestration/ui/index.html` as static files; page subscribes to SSE and renders live node states

## Model Selection Rationale

| Agent | Model | Reason |
|---|---|---|
| RouterAgent | `gemini-2.5-flash` | JSON classification from 5-option enum — trivially within Flash capability |
| ReactiveAgent | `gemini-2.5-flash` | Structured narrative from already-structured data in context; no reasoning needed, just formatting |
| ProactiveAgent | `gemini-2.5-flash` | Template-style proposal from scored rows; Flash produces consistent prose for this |
| ResearchAgent | `gemini-2.5-flash` | Orchestrates `search_sub_agent` (already Gemini/google_search); matching model is natural |
| ProposalWriter | `claude-sonnet-4-6` | **Keep Claude, upgrade Haiku→Sonnet.** Reason: ProposalWriter synthesizes across compliance certs, multi-supplier pricing, BOM impact, substitution edges, and grade data to produce an executive memo with nuanced trade-off reasoning. Flash hallucinates or flattens these trade-offs. Sonnet's stronger instruction-following and multi-step reasoning produce proposals that can go directly to procurement executives without editing. This is the only high-stakes output of the system — the cost of a bad proposal outweighs inference cost. |

## Feature Metadata

**Feature Type**: Enhancement + Refactor  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `orchestration/agents/`, `orchestration/api/dag_executor.py`, `orchestration/api/agnes_context.py`, `orchestration/tools/` (all 7), `orchestration/api/routes/pipelines.py`, `orchestration/api/main.py`  
**Dependencies**: `google-adk>=0.5.0`, `google-genai>=1.0.0` (already in requirements.txt), `anthropic>=0.40.0` (keep for ProposalWriter), `GOOGLE_API_KEY` + `GOOGLE_GENAI_USE_VERTEXAI=false` env vars

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `orchestration/api/agnes_context.py` — full file, 23 lines — add `enriched_db_path` field here
- `orchestration/api/dag_executor.py` — `_run_node()` function — add `node_started` event before line 59 (condition check)
- `orchestration/api/agent_registry.py` — `_AGENT_REGISTRY` dict — remove or fix RouterAgent entry
- `orchestration/agents/reactive_agent.py` — full file, ADK migration target
- `orchestration/agents/proactive_agent.py` — full file, ADK migration target
- `orchestration/agents/research_agent.py` — full file, ADK migration + search wiring target
- `orchestration/agents/router_agent.py` — full file, ADK migration target (keep `classify()` export)
- `orchestration/agents/proposal_writer.py` — full file, model upgrade only (Haiku → Sonnet)
- `orchestration/agents/search_sub_agent.py` — full file, existing ADK google_search pattern to reuse
- `orchestration/api/db.py` — `write_event()` signature (lines 77-93) — pattern for adding node_started
- `orchestration/api/event_bus.py` — full file, publish pattern
- `orchestration/api/routes/pipelines.py` — full file — add graph endpoint here
- `orchestration/api/main.py` — add `StaticFiles` mount
- `orchestration/tools/supplier_alternatives.py` — `_DB` usage pattern (line 11, used in `run()`) — same fix applies to all 7 tools
- `orchestration/tools/compliance_gate.py` — same hardcoded `_DB` pattern
- `orchestration/tools/bom_impact.py` — same
- `orchestration/tools/rfq_formatter.py` — no DB (skip this one)
- `orchestration/tools/opportunity_ranker.py` — same
- `orchestration/tools/price_benchmark.py` — same
- `orchestration/tools/substitution_walker.py` — same

### New Files to Create

- `orchestration/agents/_adk_runner.py` — shared ADK InMemoryRunner helper, prevents code duplication across 4 agents
- `orchestration/ui/index.html` — DAG visualization frontend (single-file HTML/CSS/JS, no build step)

### Relevant Documentation — READ BEFORE IMPLEMENTING

- `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK.md` — LlmAgent constructor, InMemoryRunner pattern, `from google.adk.agents import LlmAgent` import
- `Orchestration/References/Tech/Orchestration/REF-GOOGLE-ADK-RESEARCH-AGENT.md` — ResearchAgent system prompt and step-by-step instructions; tool patterns
- `Orchestration/References/Tech/Orchestration/google-adk-search-guide.md` — google_search constraints (cannot mix with custom tools), per-node runner pattern, `GOOGLE_GENAI_USE_VERTEXAI=false` requirement

### Patterns to Follow

**ADK Agent Module Structure (new standard for all migrated agents):**
```python
# Module-level agent definition (create once)
from google.adk.agents import LlmAgent
_AGENT = LlmAgent(name="reactive_agent", model="gemini-2.5-flash", instruction=_SYSTEM)

# Per-call runner (per the HappyRobot per-node pattern from REF-GOOGLE-ADK.md)
async def run(ctx: AgnesContext) -> dict:
    from orchestration.agents._adk_runner import run_adk_agent
    payload = json.dumps({...})
    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)
    return {"narrative": narrative, ...}
```

**Shared ADK runner helper (new file):**
```python
# orchestration/agents/_adk_runner.py
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def run_adk_agent(agent: LlmAgent, payload: str, run_id: str) -> str:
    session_service = InMemorySessionService()
    runner = InMemoryRunner(agent=agent, app_name=agent.name, session_service=session_service)
    session = await session_service.create_session(app_name=agent.name, user_id=run_id)
    final = ""
    async for event in runner.run_async(
        user_id=run_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=payload)]),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    final += part.text
    return final.strip()
```

**Tool DB path pattern (after fix):**
```python
# BEFORE (remove this line from all tools):
_DB = Path(__file__).parent.parent.parent / "db_enriched.sqlite"

# AFTER (in run()):
def run(ctx: AgnesContext) -> dict:
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    ...
```

**node_started event (dag_executor.py `_run_node`):**
```python
async def _run_node(node: PipelineNode, ctx: AgnesContext) -> tuple[str, Optional[dict], Optional[str]]:
    start = time.monotonic()
    # NEW — emit started before condition check so frontend knows node is being evaluated
    await _db.write_event(ctx.run_id, "node_started", node.id, {}, ctx.orchestration_db_path)
    try:
        if node.when and not evaluate(node.when, ctx):
            return node.id, None, None  # skipped
        ...
```

**Naming conventions:**
- Keep all existing function names (`run`, `classify`, `get_agent`, `get_tool`)
- New file: `_adk_runner.py` (underscore prefix = internal module)
- Frontend: `orchestration/ui/index.html`
- New endpoint: `GET /pipelines/{name}/graph`

**Graceful degradation pattern (keep for all agents):**
```python
if not os.environ.get("GOOGLE_API_KEY"):
    return {"narrative": None, "skipped": "GOOGLE_API_KEY not set", ...}
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation — Context & DAG Events

Prerequisite for everything else. No agent changes yet.

**Tasks:**

1. Add `enriched_db_path` and `orchestration_db_path` to `AgnesContext`
2. Fix all 6 DB-using tools to use `ctx.enriched_db_path`
3. Add `node_started` event in `dag_executor._run_node` using `ctx.orchestration_db_path`
4. Fix RouterAgent registry entry (remove from `_AGENT_REGISTRY` — it's not a pipeline node)
5. Add `GOOGLE_API_KEY` and `GOOGLE_GENAI_USE_VERTEXAI=false` to `.env` instructions

### Phase 2: Shared ADK Helper

**Tasks:**

6. Create `orchestration/agents/_adk_runner.py` with `run_adk_agent()` helper

### Phase 3: ADK Agent Migration (4 agents)

Migrate each agent independently; test one before moving to next.

**Tasks:**

7. Migrate `router_agent.py` — keep `classify()` export, use ADK internally
8. Migrate `reactive_agent.py` — full ADK rewrite, same `run()` signature and return shape
9. Migrate `proactive_agent.py` — full ADK rewrite, same `run()` signature
10. Migrate `research_agent.py` — ADK rewrite + wire `search_sub_agent.search()` as real path

### Phase 4: ProposalWriter Upgrade (keep Claude)

**Tasks:**

11. Upgrade `proposal_writer.py` model: `claude-haiku-4-5-20251001` → `claude-sonnet-4-6`

### Phase 5: Frontend — DAG Graph Endpoint + UI

**Tasks:**

12. Add `GET /pipelines/{name}/graph` to `routes/pipelines.py`
13. Mount `orchestration/ui/` as static files in `main.py`
14. Create `orchestration/ui/index.html` — SSE-powered DAG visualization

---

## STEP-BY-STEP TASKS

### TASK 1: UPDATE `orchestration/api/agnes_context.py`

- **ADD**: Two new fields with project-relative defaults
- **IMPORTS**: `from pathlib import Path`
- **PATTERN**: Existing `node_outputs` field_factory pattern

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parent.parent.parent

@dataclass
class AgnesContext:
    run_id: str
    pipeline_name: str
    trigger_source: str
    trigger_payload: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    enriched_db_path: Path = field(default_factory=lambda: _PROJECT_ROOT / "db_enriched.sqlite")
    orchestration_db_path: Path = field(default_factory=lambda: _PROJECT_ROOT / "orchestration.db")
    
    def get(self, node_id: str, default: Any = None) -> Any:
        return self.node_outputs.get(node_id, default)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "trigger_source": self.trigger_source,
            "trigger_payload": self.trigger_payload,
            "node_outputs": self.node_outputs,
        }
```

- **VALIDATE**: `python -c "from orchestration.api.agnes_context import AgnesContext; ctx = AgnesContext('r','p','t'); print(ctx.enriched_db_path)"`

---

### TASK 2: UPDATE all 6 DB-using tools to use `ctx.enriched_db_path`

Apply the same change to each of these files:
- `orchestration/tools/supplier_alternatives.py`
- `orchestration/tools/compliance_gate.py`
- `orchestration/tools/bom_impact.py`
- `orchestration/tools/opportunity_ranker.py`
- `orchestration/tools/price_benchmark.py`
- `orchestration/tools/substitution_walker.py`

Also apply to `research_agent.py` (`_DB` used in `_stage_suppliers`).

**Change per file:**
- **REMOVE**: Module-level `_DB = Path(__file__).parent.parent.parent / "db_enriched.sqlite"` line
- **REMOVE**: `from pathlib import Path` import if it was only used for `_DB`
- **UPDATE**: Every `sqlite3.connect(str(_DB))` → `sqlite3.connect(str(ctx.enriched_db_path))`
- **GOTCHA**: `rfq_formatter.py` has no DB connection — skip it

- **VALIDATE**: `python -c "from orchestration.tools.supplier_alternatives import run; print('ok')"`

---

### TASK 3: UPDATE `orchestration/api/dag_executor.py` — add `node_started` event

- **LOCATION**: `_run_node()` function, before the `if node.when` check
- **ADD**: `await _db.write_event(ctx.run_id, "node_started", node.id, {}, ctx.orchestration_db_path)`
- **ALSO UPDATE**: All existing `_db.write_event(run_id, ...)` calls inside `_execute()` to pass `ctx.orchestration_db_path` instead of the function-local `db_path` parameter — or simply pass `db_path` when constructing `ctx` (see note below)
- **NOTE**: `_execute()` already has `db_path` param. Pass it to `AgnesContext` construction on line ~97: `ctx = AgnesContext(run_id=run_id, pipeline_name=pipeline_name, ..., orchestration_db_path=db_path)`
- **GOTCHA**: `_run_node` currently returns `(node_id, None, None)` for skipped nodes. The `node_started` event should still fire (it means "evaluation started"), then `node_skipped` fires. This is correct — the frontend shows the node was reached and then skipped.

```python
# In _run_node, add at top of try block:
await _db.write_event(ctx.run_id, "node_started", node.id, {}, ctx.orchestration_db_path)
```

```python
# In _execute(), update AgnesContext construction:
ctx = AgnesContext(
    run_id=run_id,
    pipeline_name=pipeline_name,
    trigger_source=trigger_source,
    trigger_payload=trigger_payload,
    orchestration_db_path=db_path,
)
```

- **VALIDATE**: Start server, trigger a pipeline, check `orchestration.db`:
  `sqlite3 orchestration.db "SELECT event_type, node_id FROM pipeline_events ORDER BY id DESC LIMIT 20;"`

---

### TASK 4: UPDATE `orchestration/api/agent_registry.py` — fix RouterAgent

- **REMOVE**: `"RouterAgent": "orchestration.agents.router_agent:run"` from `_AGENT_REGISTRY`
- **REASON**: RouterAgent is never used as a pipeline node. The `/chat` endpoint imports `classify()` directly. Keeping `:run` in registry would crash if ever invoked since the module exports `classify`, not `run`.
- **VALIDATE**: `python -c "from orchestration.api.agent_registry import _AGENT_REGISTRY; assert 'RouterAgent' not in _AGENT_REGISTRY; print('ok')"`

---

### TASK 5: UPDATE `.env` — add Google API credentials

Ensure `.env` (or `.env.example` if that's the tracked file) has:

```bash
# Google ADK / Gemini
GOOGLE_API_KEY=AIza...           # get from console.cloud.google.com → APIs & Services → Credentials
GOOGLE_GENAI_USE_VERTEXAI=false  # REQUIRED for API key auth (not Vertex AI ADC)
```

- **GOTCHA**: Without `GOOGLE_GENAI_USE_VERTEXAI=false`, ADK will try Application Default Credentials (GCP service account) and fail locally with API keys
- **VALIDATE**: `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.environ.get('GOOGLE_GENAI_USE_VERTEXAI'))"`

---

### TASK 6: CREATE `orchestration/agents/_adk_runner.py`

Shared async helper used by all four ADK-migrated agents. Eliminates 30+ lines of boilerplate per agent.

```python
"""Shared per-node InMemoryRunner helper for ADK agents."""
import os
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types


async def run_adk_agent(agent: LlmAgent, payload: str, run_id: str) -> str:
    """Run one ADK LlmAgent as a single DAG node. Returns final text output."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return ""  # caller handles empty string as graceful skip
    session_service = InMemorySessionService()
    runner = InMemoryRunner(agent=agent, app_name=agent.name, session_service=session_service)
    session = await session_service.create_session(app_name=agent.name, user_id=run_id)
    final = ""
    async for event in runner.run_async(
        user_id=run_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=payload)]),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    final += part.text
    return final.strip()
```

- **IMPORTS**: `google.adk.agents`, `google.adk.runners`, `google.adk.sessions`, `google.genai.types`
- **GOTCHA**: `InMemorySessionService` must be created fresh per call — not shared. This prevents session state from bleeding between parallel node executions.
- **VALIDATE**: `python -c "from orchestration.agents._adk_runner import run_adk_agent; print('ok')"`

---

### TASK 7: UPDATE `orchestration/agents/router_agent.py` — migrate to ADK

Keep `classify()` export with identical signature. Swap internals from Anthropic SDK to ADK.

```python
"""RouterAgent: intent classifier. Classifies natural-language chat → pipeline + params JSON."""
import json
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent

load_dotenv()

_MODEL = "gemini-2.5-flash"

_SYSTEM = """You are Agnes's intent router. Classify the user's message into exactly one of these pipelines:

- supplier_fallout: A supplier is unavailable or needs replacement. Params: {"ingredient_name": "..."}
- proactive_consolidation: Scan for consolidation opportunities. Params: {}
- new_ingredient_research: Research new supplier candidates. Params: {"ingredient_name": "..."}
- substitution_discovery: Find substitution options for an ingredient. Params: {"ingredient_name": "..."}
- price_audit: Audit pricing for an ingredient. Params: {"ingredient_name": "..."}

Respond with ONLY valid JSON:
{"pipeline": "<name>", "params": {<extracted params>}, "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}
"""

_AGENT = LlmAgent(name="router_agent", model=_MODEL, instruction=_SYSTEM)


async def classify(message: str) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": "GOOGLE_API_KEY not set"}
    
    raw = await run_adk_agent(_AGENT, message, run_id="router")
    try:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": raw[:100]}
    except Exception:
        return {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": "parse error"}
```

- **GOTCHA**: The `/chat` endpoint calls `from orchestration.agents.router_agent import classify` — keep that export name exactly
- **VALIDATE**: `python -c "import asyncio; from orchestration.agents.router_agent import classify; r = asyncio.run(classify('Vitamin C supplier is out of stock')); print(r)"`

---

### TASK 8: UPDATE `orchestration/agents/reactive_agent.py` — migrate to ADK

Same `run(ctx)` signature and return shape. Swap Anthropic SDK for ADK internally.

```python
"""ReactiveAgent: supplier fallout narrative from structured context data."""
import json
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_AGENT = LlmAgent(
    name="reactive_agent",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain analyst. A supplier fallout event has occurred.
You receive structured supply chain data and must produce a concise, actionable response for a procurement manager.

Your response must include:
1. A brief situation summary (1-2 sentences)
2. Ranked alternative suppliers with key metrics (price, MOQ, lead time, purity)
3. A recommended immediate action
4. Any risk flags

Be factual, cite specific numbers. Note: pricing marked retail_proxy is indicative only.
Keep your response under 200 words.""",
)


async def run(ctx: AgnesContext) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"narrative": None, "ingredient_name": ctx.trigger_payload.get("ingredient_name"), "skipped": "GOOGLE_API_KEY not set"}

    payload = json.dumps({
        "trigger": ctx.trigger_payload,
        "alternatives": ctx.get("find-alternatives", {}),
        "compliance_gate": ctx.get("gate-qualify", {}),
        "bom_impact": ctx.get("bom-impact", {}),
        "rfqs": ctx.get("format-rfqs", {}),
    }, indent=2)

    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    compliance = ctx.get("gate-qualify", {})
    bom = ctx.get("bom-impact", {})
    return {
        "narrative": narrative,
        "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
        "qualified_supplier_count": len(compliance.get("qualified", [])),
        "affected_product_count": bom.get("product_count", 0),
    }
```

- **VALIDATE**: Server running → `curl -X POST http://localhost:8000/pipelines/run/supplier_fallout -H 'Content-Type: application/json' -d '{"params": {"ingredient_name": "Vitamin C"}}'`

---

### TASK 9: UPDATE `orchestration/agents/proactive_agent.py` — migrate to ADK

```python
"""ProactiveAgent: consolidation proposals from opportunity scanner output."""
import json
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_AGENT = LlmAgent(
    name="proactive_agent",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain consolidation advisor for CPG supplement companies.
You receive scored consolidation opportunities and must produce executive-ready proposals.

For each opportunity produce:
- A one-sentence headline: "Consolidate [ingredient] across [N] companies → est. [X]% savings"
- Current fragmentation: N suppliers, M companies, K SKUs
- Recommended supplier and why (price, quality, compliance)
- Estimated savings narrative (be conservative, cite assumptions)
- Next step: "Issue RFQ to [supplier] for [quantity range]"

One proposal ≤ 150 words. Flag data gaps honestly.
Pricing marked as retail_proxy is indicative only — note this.""",
)


async def run(ctx: AgnesContext) -> dict:
    opportunities = ctx.get("scan-opportunities", {}).get("opportunities", [])
    if not opportunities:
        return {"proposals": [], "count": 0}
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"proposals_narrative": None, "opportunity_count": len(opportunities), "top_ingredient": opportunities[0].get("ingredient_name") if opportunities else None, "skipped": "GOOGLE_API_KEY not set"}

    payload = json.dumps({"opportunities": opportunities}, indent=2)
    proposals_narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    return {
        "proposals_narrative": proposals_narrative,
        "opportunity_count": len(opportunities),
        "top_ingredient": opportunities[0]["ingredient_name"] if opportunities else None,
    }
```

- **VALIDATE**: `curl -X POST http://localhost:8000/pipelines/run/proactive_consolidation -H 'Content-Type: application/json' -d '{"params": {}}'`

---

### TASK 10: UPDATE `orchestration/agents/research_agent.py` — ADK + wire search_sub_agent

Key change: actually call `search_sub_agent.search()` as the real search path.

```python
"""ResearchAgent: discovers new suppliers via web search (google_search via ADK)."""
import json
import os
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_SYSTEM = """You are Agnes, a supply chain research agent.
You receive raw web search results about bulk ingredient suppliers.
Extract and return a JSON array of supplier records:
[{"supplier_name": "...", "country": "...", "website": "...", "certifications": ["NSF", ...],
  "price_range_usd_per_kg": "...", "moq_range_kg": "...", "notes": "..."}]
Include only suppliers clearly offering this ingredient in bulk B2B quantities.
Mark uncertain fields as null. Include 3-8 suppliers.
"""

_AGENT = LlmAgent(name="research_agent", model="gemini-2.5-flash", instruction=_SYSTEM)


async def run(ctx: AgnesContext) -> dict:
    ingredient_name: str = ctx.trigger_payload.get("ingredient_name", "")
    if not ingredient_name:
        return {"discovered_suppliers": [], "error": "no ingredient_name in payload"}

    if not os.environ.get("GOOGLE_API_KEY"):
        return {"discovered_suppliers": [], "ingredient_name": ingredient_name, "count": 0, "skipped": "GOOGLE_API_KEY not set"}

    # Real web search via search_sub_agent (google_search ADK tool)
    try:
        from orchestration.agents.search_sub_agent import search
        raw_search = await search(ingredient_name, query_hint="bulk supplier B2B certificate")
    except Exception as e:
        raw_search = f"Search unavailable: {e}"

    # Extract structured supplier records from search output
    payload = f"Ingredient: {ingredient_name}\n\nSearch results:\n{raw_search}"
    raw = await run_adk_agent(_AGENT, payload, ctx.run_id)
    discovered = _parse_suppliers(raw, ingredient_name)

    if discovered:
        _stage_suppliers(discovered, ingredient_name, ctx.enriched_db_path)

    return {
        "discovered_suppliers": discovered,
        "ingredient_name": ingredient_name,
        "count": len(discovered),
        "raw_output": raw[:500],
    }


def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    import re
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    if raw.strip():
        return [{"supplier_name": "research_result", "notes": raw[:400]}]
    return []


def _stage_suppliers(suppliers: list[dict], ingredient_name: str, db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
        (ingredient_name,),
    ).fetchone()
    canonical_id = row[0] if row else None
    for s in suppliers:
        try:
            conn.execute(
                """INSERT INTO Agent_Log (Run_Id, Agent, Node, Status, Input_JSON, Output_JSON, Related_IngredientId, Logged_At)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("research_run", "research_agent", "stage_discovered_supplier", "success",
                 json.dumps({"ingredient_name": ingredient_name}), json.dumps(s), canonical_id, datetime.utcnow().isoformat()),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()
```

- **GOTCHA**: `search_sub_agent.search()` requires `GOOGLE_API_KEY` in env. The try/except ensures graceful fallback if the key is missing or search quota is exhausted.
- **VALIDATE**: `curl -X POST http://localhost:8000/pipelines/run/new_ingredient_research -H 'Content-Type: application/json' -d '{"params": {"ingredient_name": "Coenzyme Q10"}}'`

---

### TASK 11: UPDATE `orchestration/agents/proposal_writer.py` — upgrade model only

**Single change**: `claude-haiku-4-5-20251001` → `claude-sonnet-4-6`

- **FIND**: `_MODEL = "claude-haiku-4-5-20251001"`
- **REPLACE**: `_MODEL = "claude-sonnet-4-6"`
- **NO OTHER CHANGES** — keep Anthropic SDK, keep `run()` signature, keep system prompt
- **VALIDATE**: `python -c "from orchestration.agents.proposal_writer import _MODEL; assert _MODEL == 'claude-sonnet-4-6'; print('ok')"`

---

### TASK 12: ADD `GET /pipelines/{name}/graph` endpoint to `routes/pipelines.py`

This provides the DAG structure the frontend needs to render nodes and edges.

```python
from orchestration.api.dag_executor import _topological_layers
from orchestration.api.pipeline_def import PipelineNode

@router.get("/pipelines/{name}/graph")
def get_pipeline_graph(name: str):
    available = list_pipelines()
    if name not in available:
        raise HTTPException(404, f"Pipeline {name!r} not found")
    pipeline = load_pipeline(name)
    layers = _topological_layers(pipeline.nodes)
    return {
        "name": pipeline.name,
        "trigger": pipeline.trigger,
        "layers": [[n.id for n in layer] for layer in layers],
        "nodes": [
            {
                "id": n.id,
                "type": "agent" if n.agent_class else "tool",
                "class": n.agent_class or n.tool_class,
                "depends_on": n.depends_on,
                "when": n.when,
            }
            for n in pipeline.nodes
        ],
    }
```

Add the import `from orchestration.api.dag_executor import _topological_layers` and `from orchestration.api.pipeline_loader import load as load_pipeline` at the top (check if `load_pipeline` is already imported — it is via `list_pipelines`; you may need to add the direct `load` import).

- **VALIDATE**: `curl http://localhost:8000/pipelines/supplier_fallout/graph | python -m json.tool`

---

### TASK 13: UPDATE `orchestration/api/main.py` — mount static files

```python
from fastapi.staticfiles import StaticFiles

# In lifespan or after app definition (not inside a route):
_UI_DIR = Path(__file__).parent.parent / "ui"
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
```

- **IMPORTS**: `from fastapi.staticfiles import StaticFiles`, `from pathlib import Path`
- **GOTCHA**: `StaticFiles` with `html=True` serves `index.html` for directory requests
- **NOTE**: The mount must come AFTER route definitions, or it will shadow API routes
- **VALIDATE**: `curl http://localhost:8000/ui/` returns HTML

---

### TASK 14: CREATE `orchestration/ui/index.html` — DAG visualization

A single HTML file with vanilla JS. No build step. Uses EventSource API for SSE and plain CSS for layout.

Features:
- Lists recent runs from `GET /runs`
- Click a run → fetches pipeline graph from `GET /pipelines/{name}/graph`
- Renders nodes as boxes grouped by layer (layer = column)
- Subscribes to `GET /runs/{run_id}/stream` for live state updates
- Node states: `pending` (grey) → `started` (blue + pulse animation) → `completed` (green) / `failed` (red) / `skipped` (amber)
- Shows elapsed ms on completed nodes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Agnes — Pipeline Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; }
  header { padding: 16px 24px; border-bottom: 1px solid #2d3748; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; }
  .layout { display: grid; grid-template-columns: 280px 1fr; height: calc(100vh - 57px); }
  .sidebar { border-right: 1px solid #2d3748; overflow-y: auto; }
  .run-item { padding: 12px 16px; border-bottom: 1px solid #1a202c; cursor: pointer; }
  .run-item:hover { background: #1a202c; }
  .run-item.active { background: #1a365d; }
  .run-meta { font-size: 11px; color: #718096; margin-top: 4px; }
  .status-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-left: 6px; }
  .s-completed { background: #22543d; color: #9ae6b4; }
  .s-running { background: #1a365d; color: #90cdf4; }
  .s-failed { background: #742a2a; color: #feb2b2; }
  .s-pending { background: #2d3748; color: #a0aec0; }
  .canvas { padding: 24px; overflow: auto; }
  .pipeline-name { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
  .pipeline-meta { font-size: 12px; color: #718096; margin-bottom: 24px; }
  .dag { display: flex; gap: 32px; align-items: flex-start; }
  .layer { display: flex; flex-direction: column; gap: 12px; position: relative; }
  .layer::after { content: '→'; position: absolute; right: -22px; top: 50%; transform: translateY(-50%); color: #4a5568; font-size: 18px; }
  .layer:last-child::after { display: none; }
  .node { min-width: 160px; padding: 12px 14px; border-radius: 8px; border: 2px solid #2d3748; background: #1a202c; transition: all 0.3s; }
  .node.pending { border-color: #2d3748; }
  .node.started { border-color: #3182ce; background: #1a365d; animation: pulse 1.5s infinite; }
  .node.completed { border-color: #38a169; background: #1c4532; }
  .node.failed { border-color: #e53e3e; background: #742a2a; }
  .node.skipped { border-color: #d69e2e; background: #5f370e; opacity: 0.7; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
  .node-id { font-size: 13px; font-weight: 600; }
  .node-class { font-size: 10px; color: #718096; margin-top: 3px; }
  .node-type { font-size: 9px; padding: 1px 5px; border-radius: 3px; display: inline-block; margin-top: 4px; }
  .type-tool { background: #2c5282; color: #90cdf4; }
  .type-agent { background: #553c9a; color: #d6bcfa; }
  .node-elapsed { font-size: 10px; color: #68d391; margin-top: 6px; }
  .node-when { font-size: 10px; color: #f6ad55; margin-top: 3px; }
  .log { margin-top: 24px; background: #1a202c; border-radius: 8px; padding: 12px; max-height: 200px; overflow-y: auto; }
  .log-entry { font-size: 11px; font-family: monospace; padding: 3px 0; color: #a0aec0; border-bottom: 1px solid #2d3748; }
  .log-entry.ev-node_completed { color: #68d391; }
  .log-entry.ev-node_failed { color: #fc8181; }
  .log-entry.ev-node_started { color: #90cdf4; }
  .log-entry.ev-node_skipped { color: #f6ad55; }
  .empty { color: #4a5568; font-size: 14px; padding: 40px; text-align: center; }
  #trigger-form { display: flex; gap: 8px; margin-bottom: 24px; }
  #trigger-form select, #trigger-form input { background: #2d3748; border: 1px solid #4a5568; color: #e2e8f0; padding: 6px 10px; border-radius: 6px; font-size: 13px; }
  #trigger-form button { background: #3182ce; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }
  #trigger-form button:hover { background: #2b6cb0; }
</style>
</head>
<body>
<header>
  <h1>Agnes — Pipeline Monitor</h1>
  <span id="conn-status" style="font-size:12px;color:#718096;">●</span>
</header>
<div class="layout">
  <div class="sidebar" id="runs-list"><div class="empty">Loading runs…</div></div>
  <div class="canvas" id="canvas">
    <div id="trigger-form">
      <select id="pipeline-select"><option value="">Select pipeline…</option></select>
      <input id="ingredient-input" placeholder="ingredient_name (optional)" style="width:220px">
      <button onclick="triggerPipeline()">Run Pipeline</button>
    </div>
    <div id="dag-view"><div class="empty">Select a run to visualize its execution graph</div></div>
    <div id="event-log" style="display:none"><div class="log" id="log-entries"></div></div>
  </div>
</div>

<script>
const API = '';
let activeRunId = null;
let activeEventSource = null;
let nodeStates = {};
let pipelineGraph = null;

async function loadRuns() {
  const resp = await fetch(`${API}/runs?limit=30`);
  const { runs } = await resp.json();
  const el = document.getElementById('runs-list');
  if (!runs.length) { el.innerHTML = '<div class="empty">No runs yet</div>'; return; }
  el.innerHTML = runs.map(r => `
    <div class="run-item" data-id="${r.id}" data-pipeline="${r.pipeline_name}" onclick="selectRun('${r.id}','${r.pipeline_name}','${r.status}')">
      <div>${r.pipeline_name} <span class="status-badge s-${r.status}">${r.status}</span></div>
      <div class="run-meta">${r.id.slice(0,8)}… · ${r.started_at ? new Date(r.started_at).toLocaleTimeString() : ''}</div>
    </div>`).join('');
  await loadPipelines();
}

async function loadPipelines() {
  const resp = await fetch(`${API}/pipelines`);
  const { pipelines } = await resp.json();
  const sel = document.getElementById('pipeline-select');
  sel.innerHTML = '<option value="">Select pipeline…</option>' + pipelines.map(p => `<option value="${p}">${p}</option>`).join('');
}

async function selectRun(runId, pipelineName, status) {
  document.querySelectorAll('.run-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`[data-id="${runId}"]`)?.classList.add('active');
  activeRunId = runId;
  nodeStates = {};
  document.getElementById('event-log').style.display = 'block';
  document.getElementById('log-entries').innerHTML = '';

  // Load graph structure
  const gResp = await fetch(`${API}/pipelines/${pipelineName}/graph`);
  pipelineGraph = await gResp.json();
  renderDag();

  // Load historical events and apply
  const rResp = await fetch(`${API}/runs/${runId}`);
  const runData = await rResp.json();
  (runData.events || []).forEach(ev => applyEvent(JSON.parse(ev.data || '{}'), ev.event_type, ev.node_id));
  renderDag();

  // Subscribe live if running
  if (activeEventSource) activeEventSource.close();
  if (status === 'running' || status === 'pending') {
    activeEventSource = new EventSource(`${API}/runs/${runId}/stream`);
    document.getElementById('conn-status').style.color = '#48bb78';
    activeEventSource.onmessage = e => {
      const ev = JSON.parse(e.data);
      applyEvent(ev, ev.event_type, ev.node_id);
      renderDag();
      logEvent(ev);
      if (ev.event_type === 'stream_closed') { activeEventSource.close(); document.getElementById('conn-status').style.color = '#718096'; loadRuns(); }
    };
    activeEventSource.onerror = () => { document.getElementById('conn-status').style.color = '#fc8181'; };
  }
}

function applyEvent(data, type, nodeId) {
  if (!nodeId) return;
  if (type === 'node_started') nodeStates[nodeId] = { state: 'started' };
  if (type === 'node_completed') nodeStates[nodeId] = { state: 'completed', elapsed: data.node_output?._elapsed_ms };
  if (type === 'node_failed') nodeStates[nodeId] = { state: 'failed', error: data.error };
  if (type === 'node_skipped') nodeStates[nodeId] = { state: 'skipped' };
}

function renderDag() {
  if (!pipelineGraph) return;
  const nodeMap = Object.fromEntries(pipelineGraph.nodes.map(n => [n.id, n]));
  const html = `
    <div class="pipeline-name">${pipelineGraph.name}</div>
    <div class="pipeline-meta">trigger: ${pipelineGraph.trigger} · ${pipelineGraph.nodes.length} nodes</div>
    <div class="dag">
      ${pipelineGraph.layers.map(layer => `
        <div class="layer">
          ${layer.map(nodeId => {
            const n = nodeMap[nodeId];
            const s = nodeStates[nodeId] || { state: 'pending' };
            return `<div class="node ${s.state}">
              <div class="node-id">${nodeId}</div>
              <div class="node-class">${n.class}</div>
              <span class="node-type type-${n.type}">${n.type}</span>
              ${n.when ? `<div class="node-when">when: ${n.when}</div>` : ''}
              ${s.elapsed ? `<div class="node-elapsed">✓ ${s.elapsed}ms</div>` : ''}
            </div>`;
          }).join('')}
        </div>`).join('')}
    </div>`;
  document.getElementById('dag-view').innerHTML = html;
}

function logEvent(ev) {
  const el = document.getElementById('log-entries');
  const ts = new Date().toLocaleTimeString();
  el.innerHTML = `<div class="log-entry ev-${ev.event_type}">[${ts}] ${ev.event_type}${ev.node_id ? ' · ' + ev.node_id : ''}${ev._elapsed_ms ? ' · ' + ev._elapsed_ms + 'ms' : ''}</div>` + el.innerHTML;
}

async function triggerPipeline() {
  const pipeline = document.getElementById('pipeline-select').value;
  if (!pipeline) return alert('Select a pipeline first');
  const ingredient = document.getElementById('ingredient-input').value.trim();
  const params = ingredient ? { ingredient_name: ingredient } : {};
  const resp = await fetch(`${API}/pipelines/run/${pipeline}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ params })
  });
  const { run_id } = await resp.json();
  await loadRuns();
  setTimeout(() => selectRun(run_id, pipeline, 'running'), 200);
}

loadRuns();
setInterval(loadRuns, 10000);
</script>
</body>
</html>
```

- **VALIDATE**: Browser → `http://localhost:8000/ui/` → page loads, runs list appears, trigger a pipeline and watch nodes animate from started → completed

---

## TESTING STRATEGY

### Manual Validation (primary — no test framework in project)

#### Smoke tests per agent:
```bash
# 1. Start server
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000

# 2. Trigger all 5 pipelines and check events
curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H 'Content-Type: application/json' \
  -d '{"params": {"ingredient_name": "Vitamin C"}}' | python -m json.tool

# 3. Watch SSE stream for node_started events (new)
RUN_ID=$(curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H 'Content-Type: application/json' \
  -d '{"params": {"ingredient_name": "Vitamin C"}}' | python -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
curl -N "http://localhost:8000/runs/$RUN_ID/stream"

# 4. Check DB for node_started events
sqlite3 orchestration.db "SELECT event_type, node_id FROM pipeline_events ORDER BY id DESC LIMIT 20;"

# 5. Pipeline graph endpoint
curl http://localhost:8000/pipelines/supplier_fallout/graph | python -m json.tool
```

#### Import validation:
```bash
PYTHONPATH=. python -c "
from orchestration.agents._adk_runner import run_adk_agent
from orchestration.agents.reactive_agent import run
from orchestration.agents.proactive_agent import run
from orchestration.agents.research_agent import run
from orchestration.agents.router_agent import classify
from orchestration.agents.proposal_writer import run
print('all imports ok')
"
```

### Edge Cases to Verify

- `GOOGLE_API_KEY` not set: all 4 migrated agents return graceful `skipped` dict (not exception)
- `ANTHROPIC_API_KEY` not set: `proposal_writer` returns graceful `skipped` dict (not exception)
- Pipeline with skipped node (condition false): `node_started` fires first, then `node_skipped`
- Frontend: run that's already completed → historical events replayed correctly, no live subscription

---

## VALIDATION COMMANDS

### Level 1: Import Check
```bash
PYTHONPATH=. python -c "
from orchestration.api.agnes_context import AgnesContext
from orchestration.api.dag_executor import execute_pipeline
from orchestration.agents._adk_runner import run_adk_agent
from orchestration.agents.reactive_agent import run
from orchestration.agents.router_agent import classify
print('imports ok')
"
```

### Level 2: Context fields
```bash
PYTHONPATH=. python -c "
from orchestration.api.agnes_context import AgnesContext
ctx = AgnesContext('r','p','t')
assert ctx.enriched_db_path.exists(), f'enriched_db_path does not exist: {ctx.enriched_db_path}'
assert ctx.orchestration_db_path.exists(), f'orchestration_db_path does not exist: {ctx.orchestration_db_path}'
print('paths ok:', ctx.enriched_db_path)
"
```

### Level 3: Server startup
```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/health
curl -s http://localhost:8000/pipelines | python -m json.tool
curl -s http://localhost:8000/pipelines/supplier_fallout/graph | python -m json.tool
curl -s http://localhost:8000/ui/ | head -5
```

### Level 4: End-to-end pipeline with event check
```bash
RUN_ID=$(curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H 'Content-Type: application/json' -d '{"params": {"ingredient_name": "Vitamin C"}}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
sleep 10
sqlite3 orchestration.db "SELECT event_type, node_id FROM pipeline_events WHERE run_id='$RUN_ID' ORDER BY id;"
```

Expected output includes `node_started` rows for each node.

### Level 5: Frontend manual test

1. Open `http://localhost:8000/ui/` in browser
2. Select "supplier_fallout" pipeline, enter "Vitamin C", click Run
3. Watch: nodes transition from grey → blue pulsing → green
4. Event log shows `node_started` and `node_completed` entries with timestamps

---

## ACCEPTANCE CRITERIA

- [ ] All 4 ADK-migrated agents use `gemini-2.5-flash` via `LlmAgent` + `InMemoryRunner`
- [ ] `ProposalWriter` uses `claude-sonnet-4-6` (upgraded from haiku, kept on Anthropic SDK)
- [ ] `ResearchAgent` calls `search_sub_agent.search()` for real web results
- [ ] `RouterAgent` removed from `_AGENT_REGISTRY`; `classify()` export unchanged
- [ ] `AgnesContext` has `enriched_db_path` and `orchestration_db_path` fields with correct defaults
- [ ] All 6 DB-using tools use `ctx.enriched_db_path` (no module-level `_DB` constant)
- [ ] `node_started` event appears in `pipeline_events` for every node in every run
- [ ] `GET /pipelines/{name}/graph` returns correct layers and node metadata
- [ ] `orchestration/ui/index.html` served at `/ui/`
- [ ] Frontend renders DAG and animates nodes from started → completed in real time
- [ ] All agents degrade gracefully when API keys are absent (no exceptions, `skipped` key in return)
- [ ] Server starts without errors: `uvicorn orchestration.api.main:app --port 8000`

---

## NOTES

**Why not use ADK SequentialAgent for the whole pipeline?**
Agnes already has a bespoke DAG executor (Kahn's algorithm, asyncio.gather, SSE events) that handles parallel execution, conditional skipping, and per-node logging. Replacing it with `SequentialAgent` would lose the parallel layer execution, the `node_started`/`node_skipped` event semantics, and the `orchestration.db` run log. The existing executor is better for this use case; ADK is used only for LLM inference within nodes.

**ProposalWriter: why keep Claude Sonnet and not flash?**
ProposalWriter synthesizes across 5+ data dimensions simultaneously (price outliers, compliance certs, BOM impact, substitution alternatives, grade flags) to produce a structured executive memo. Gemini Flash reliably produces fluent prose but tends to flatten multi-constraint reasoning problems — it will write a coherent narrative but miss or misweight constraints. Sonnet 4.6's instruction-following and extended thinking capability handles the trade-off analysis correctly. The asymmetric cost (one API call per top-50 opportunity) is acceptable given the proposal is the system's primary output.

**google_search isolation constraint**
`search_sub_agent.py` correctly keeps `google_search` isolated from custom tools. `ResearchAgent` calls it as a black-box function (`await search(ingredient_name)`), then passes the text output to a second `_AGENT` (also gemini-2.5-flash) for structured extraction. This two-step pattern is the correct ADK pattern for combining web search with custom DB tools.

**`GOOGLE_GENAI_USE_VERTEXAI=false` is mandatory**
Without this env var, the ADK will attempt Vertex AI Application Default Credentials and fail locally with API keys. This is the #1 cause of ADK auth failures in local development. It must be added to `.env`.
