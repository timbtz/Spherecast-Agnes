# Plan 7 Handover: ADK Migration, Node Visibility & DAG UI

**Written by:** Claude (implementation session)  
**Date:** 2026-04-18  
**For:** Next Claude instance — testing only, no implementation needed

---

## What Was Implemented

Plan 7 (`Orchestration/Plans/7-adk-migration-node-visibility-dag-ui.md`) was fully implemented. All 14 tasks complete.

### Changes in one line each

| File | Change |
|---|---|
| `orchestration/api/agnes_context.py` | Added `enriched_db_path` + `orchestration_db_path` Path fields with project-relative defaults |
| `orchestration/api/agent_registry.py` | Removed `RouterAgent` entry (was pointing at non-existent `:run` export) |
| `orchestration/api/dag_executor.py` | Emits `node_started` event at top of `_run_node`; passes `orchestration_db_path` to `AgnesContext` |
| `orchestration/api/main.py` | Mounts `orchestration/ui/` at `/ui/` via `StaticFiles` |
| `orchestration/api/routes/pipelines.py` | Added `GET /pipelines/{name}/graph` endpoint returning DAG layers + node metadata |
| `orchestration/api/routes/chat.py` | `classify()` is now async — updated to `await classify(req.message)` |
| `orchestration/tools/*.py` (6 files) | Removed module-level `_DB` constant; all `sqlite3.connect()` calls now use `ctx.enriched_db_path` |
| `orchestration/agents/_adk_runner.py` | **New.** Shared `run_adk_agent(agent, payload, run_id)` helper using `InMemoryRunner` |
| `orchestration/agents/router_agent.py` | Rewritten: Anthropic SDK → ADK/Gemini Flash; `classify()` is now async |
| `orchestration/agents/reactive_agent.py` | Rewritten: Anthropic SDK → ADK/Gemini Flash |
| `orchestration/agents/proactive_agent.py` | Rewritten: Anthropic SDK → ADK/Gemini Flash |
| `orchestration/agents/research_agent.py` | Rewritten: ADK/Gemini Flash + now calls `search_sub_agent.search()` for real web results |
| `orchestration/agents/proposal_writer.py` | Model upgraded: `claude-haiku-4-5-20251001` → `claude-sonnet-4-6`. Anthropic SDK kept. |
| `orchestration/ui/index.html` | **New.** Single-file DAG visualization UI; SSE-powered live node state updates |

---

## Testing Strategy

### Prerequisites

```bash
# Ensure .env has these keys set (check with cat .env):
ANTHROPIC_API_KEY=...         # for ProposalWriter
GOOGLE_API_KEY=...            # for all 4 ADK agents
GOOGLE_GENAI_USE_VERTEXAI=false  # REQUIRED — without this ADK auth fails locally
```

### Step 1 — Import smoke test (no server needed)

```bash
cd "/home/developer/Projects/Spherecast Agnes"
PYTHONPATH=. python3 -c "
from orchestration.api.agnes_context import AgnesContext
from orchestration.api.dag_executor import execute_pipeline
from orchestration.agents._adk_runner import run_adk_agent
from orchestration.agents.reactive_agent import run
from orchestration.agents.proactive_agent import run
from orchestration.agents.research_agent import run
from orchestration.agents.router_agent import classify
from orchestration.agents.proposal_writer import run, _MODEL
assert _MODEL == 'claude-sonnet-4-6'
ctx = AgnesContext('r','p','t')
assert ctx.enriched_db_path.exists()
assert ctx.orchestration_db_path.exists()
print('all ok')
"
```

### Step 2 — Static API checks (no LLM calls)

```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000 &
sleep 3

# Health
curl -s http://localhost:8000/health

# Pipeline list
curl -s http://localhost:8000/pipelines | python3 -m json.tool

# DAG graph (new endpoint)
curl -s http://localhost:8000/pipelines/supplier_fallout/graph | python3 -m json.tool
curl -s http://localhost:8000/pipelines/proactive_consolidation/graph | python3 -m json.tool

# UI served
curl -s http://localhost:8000/ui/ | head -3
```

**Expected:** graph endpoint returns `layers` (array of arrays) and `nodes` with `type`, `class`, `depends_on`, `when`.

### Step 3 — node_started event check (requires live pipeline run)

```bash
RUN_ID=$(curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H 'Content-Type: application/json' \
  -d '{"params": {"ingredient_name": "Vitamin C"}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")

echo "Run: $RUN_ID"
sleep 15

sqlite3 orchestration.db \
  "SELECT event_type, node_id FROM pipeline_events WHERE run_id='$RUN_ID' ORDER BY id;"
```

**Expected:** Each node appears twice — once as `node_started`, once as `node_completed` or `node_skipped`. No node should appear only as `node_completed` without a prior `node_started`.

### Step 4 — ADK agent graceful degradation (no API key)

```bash
PYTHONPATH=. python3 -c "
import asyncio, os
os.environ.pop('GOOGLE_API_KEY', None)
from orchestration.agents.reactive_agent import run
from orchestration.api.agnes_context import AgnesContext
ctx = AgnesContext('test','supplier_fallout','manual', trigger_payload={'ingredient_name':'X'})
result = asyncio.run(run(ctx))
assert result.get('skipped') == 'GOOGLE_API_KEY not set', f'expected skipped, got: {result}'
print('graceful degradation ok:', result)
"
```

### Step 5 — ProposalWriter model check

```bash
PYTHONPATH=. python3 -c "
from orchestration.agents.proposal_writer import _MODEL
assert _MODEL == 'claude-sonnet-4-6', f'wrong model: {_MODEL}'
print('ProposalWriter model ok:', _MODEL)
"
```

### Step 6 — Browser UI test (manual)

1. Open `http://localhost:8000/ui/` in browser
2. Sidebar should show recent runs (or "No runs yet")
3. Pipeline dropdown should list all 5 pipelines
4. Trigger "supplier_fallout" with ingredient "Vitamin C" → click Run
5. Select the new run in sidebar → DAG renders with layered boxes
6. Nodes transition: grey (pending) → blue pulsing (started) → green (completed) / amber (skipped)
7. Event log at bottom shows timestamped entries

### Known gotchas

- `GOOGLE_GENAI_USE_VERTEXAI=false` **must** be in `.env` — ADK will fail with a confusing auth error without it
- `search_sub_agent` in `ResearchAgent` requires `GOOGLE_API_KEY`; the try/except in `research_agent.run()` catches failures gracefully
- `classify()` in `router_agent.py` is now **async** — `chat.py` already updated to `await` it, but any other direct callers would need the same update
- `orchestration_db_path.exists()` check in Step 1 requires `orchestration.db` to exist — it's created on first server startup via `init_db()`

---

## Acceptance Criteria Checklist

- [ ] All imports pass (Step 1)
- [ ] `/pipelines/{name}/graph` returns correct layers and node types (Step 2)
- [ ] `/ui/` serves the HTML page (Step 2)
- [ ] `node_started` events appear in DB for every node (Step 3)
- [ ] ADK agents return `{"skipped": ...}` when `GOOGLE_API_KEY` absent (Step 4)
- [ ] `proposal_writer._MODEL == "claude-sonnet-4-6"` (Step 5)
- [ ] Browser DAG animates correctly end-to-end (Step 6)
