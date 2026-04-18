# Feature: Supplier Price Intelligence — Web Enrichment, Price Monitor & Proactive Alerts

---

## PRODUCT INTENT & CONTEXT

Agnes is a CPG supplement procurement intelligence platform. This feature addresses a critical gap: **the Suppliers tab is useless without real data**. The Molport API key is pending, so `Supplier_Commercial` is empty. That means the Supplier Scoring tab shows EmptyState for every ingredient, and the `SupplierScorer` has nothing to rank.

The solution is a three-tier escalation of market intelligence:

1. **Tier 1 — Web Enrichment (unblocks everything):** Use Google Search (already wired via `search_sub_agent`) to discover real bulk suppliers, extract prices/MOQ/lead-time, and write them into `Supplier_Commercial`. Once this runs, the Suppliers tab shows real data and the scorer can rank.

2. **Tier 2 — Price Monitor (ongoing intelligence):** A `price_monitor` pipeline that periodically re-fetches prices, compares them to stored values, writes `Price_Change_Alert` rows when changes ≥15% are detected, and produces a Gemini narrative. A dedicated "Price Alerts" tab in the UI surfaces these as actionable events (dismiss flow included).

3. **Tier 3 — Scheduled Execution + Supplier Wiki (ambient intelligence):** Background task triggers `price_monitor` every 24h automatically. Static wiki files (`Orchestration/Data/supplier_wiki/`) give `SupplierScorer` grade-level benchmarks so it can flag outlier prices even with a single supplier.

**The end goal:** Agnes automatically keeps the sourcing picture fresh — when a supplier drops Vitamin C by 20%, procurement sees an alert the same day, not the same quarter.

---

## CURRENT STATUS (as of 2026-04-18)

### ✅ FULLY IMPLEMENTED — ALL CODE COMPLETE

Every file from Tasks 1–20 has been created. All registrations, routes, and frontend views are wired.

| Component | File | Status |
|---|---|---|
| Schema doc | `schema/enriched_schema.sql` | ✅ Updated |
| DB migration | `enrichment/db_migrate_price_monitor.py` | ✅ Created |
| Supplier web enricher | `enrichment/enrichers/supplier_web_enricher.py` | ✅ Created |
| Backfill script | `enrichment/backfill_supplier_web.py` | ✅ Created |
| Staleness checker tool | `orchestration/tools/price_staleness_checker.py` | ✅ Created |
| Price fetch agent | `orchestration/agents/price_fetch_agent.py` | ✅ Created |
| Price alert writer | `orchestration/agents/price_alert_writer.py` | ✅ Created |
| Pipeline YAML | `orchestration/pipelines/price_monitor.yaml` | ✅ Created |
| Conditions | `has_stale_prices`, `has_price_alerts` in `conditions.py` | ✅ Registered |
| Agent registry | `agent_registry.py` | ✅ PriceFetchAgent, PriceAlertWriter, PriceStalenesCheckerTool registered |
| Alerts API | `orchestration/api/routes/alerts.py` | ✅ Created + registered in `main.py` |
| Frontend types | `PriceAlert`, `AlertCount` in `types/agnes.ts` | ✅ Added |
| Frontend API | `alertCount()`, `listAlerts()`, `dismissAlert()` in `agnesApi.ts` | ✅ Added |
| Alerts view | `orchestration/ui/src/components/views/AlertsView.tsx` | ✅ Created |
| Sidebar tab | "Price Alerts" tab in `Sidebar.tsx` + `Index.tsx` | ✅ Added |
| Supplier guidelines | `reasoning/supplier_guidelines.py` + wiki markdown files | ✅ Created |
| Supplier scorer | `score_suppliers_with_context()` in `supplier_scorer.py` | ✅ Added |
| Tier 3 scheduler | `_price_monitor_scheduler()` in `main.py` lifespan | ✅ Added (24h loop) |

### 🔴 NOT YET RUN (data execution pending — requires GOOGLE_API_KEY)

- **`Supplier_Commercial`: 0 rows** — `backfill_supplier_web.py` has NOT been run
- **`Price_Change_Alert`: 0 rows** — `price_monitor` pipeline has NOT been run
- The Suppliers tab shows EmptyState for every ingredient
- Price alerts tab shows EmptyState

### ❓ WHAT STILL NEEDS TO BE DONE

**Immediate — unblocks the Suppliers tab:**
1. **Run the web enrichment backfill** (requires `GOOGLE_API_KEY` in `.env`):
   ```bash
   PYTHONPATH=. python3 enrichment/backfill_supplier_web.py
   ```
   This will call Google Search for each UNII-bearing canonical ingredient (~129 ingredients), extract bulk supplier prices, and write them to `Supplier_Commercial`. Expect 3–8 suppliers per ingredient. Slow (~5 min for all; Google Search is rate-limited).

2. **Trigger the price_monitor pipeline** after first enrichment to establish price baselines:
   ```bash
   curl -X POST http://localhost:8001/pipelines/run/price_monitor \
     -H "Content-Type: application/json" -d '{}'
   ```
   First run writes new Supplier_Commercial rows but creates 0 alerts (no prior price to compare). Alerts start appearing on the second+ run.

**Near-term — improve UX:**
3. **TopBar notification badge** — `usePriceAlerts.ts` hook was not created. The plan called for a small badge on the TopBar showing the unread alert count. The `GET /api/alerts/count` endpoint exists; it just needs a hook + badge in `TopBar.tsx`. This is a small task.

4. **Regulatory Alerts tab in Sidebar** — Currently regulatory drift data is only visible through the Opportunities tab (drift flag) and the raw API endpoint. Adding a dedicated "Regulatory" tab (similar to Price Alerts) would surface the `/api/data/regulatory-alerts` data with severity, before/after MDE, and a trigger-pipeline CTA.

**Further development — expanding pipeline depth:**
5. **Extend `proactive_consolidation`** — Currently only 2 nodes (scan-opportunities → write-proposals). Could add `ComplianceReasonerTool`, `BomImpactTool`, and `PriceBenchmarkTool` before `write-proposals`, making it a 5-node pipeline like `supplier_fallout`. This would give the ProactiveAgent richer context.

6. **Run Phase 4 proposals** — `reasoning/proposal_generator.py` hasn't been run. `Proposals` tab is empty because `Proposal_Text IS NULL` for all opportunities. Running it populates text for the top-N consolidation opportunities.
   ```bash
   PYTHONPATH=. python3 reasoning/proposal_generator.py
   ```

7. **Price confidence escalation** — Web-search prices have `Confidence=0.65`. Once Molport API key is available, Molport prices (`Confidence=0.70`) should be preferred. The `SupplierScorer` already normalises both; no code change needed when Molport is wired.

8. **Wiki self-update loop** — The `supplier_wiki/` markdown files are static. A `WikiUpdateAgent` could receive `price_alert_writer` output and update the relevant wiki file with fresh price benchmarks — closing the feedback loop. Not in scope now but the architecture supports it.

---

## WHAT'S MISSING FROM THE PLAN (found during implementation)

- **`usePriceAlerts.ts` hook not created** — Plan Task 15 mentioned it for TopBar badge but it was skipped. Small gap: create this hook + add badge to `TopBar.tsx`.
- **Scheduler in production** — The `_price_monitor_scheduler()` runs inside FastAPI lifespan, meaning it only works while the server is up. For production, this should be a proper cron job or a persistent task queue. For the hackathon demo this is fine.
- **`Supplier_Commercial` PK awareness** — The `INSERT OR REPLACE` on `(SupplierId, CanonicalIngredientId)` means re-running the backfill silently overwrites prices. This is intentional and correct for the use case; just document the behavior in demos.

---

## ORIGINAL PLAN — IMPLEMENTATION REFERENCE

Three coordinated capability tiers that transform Agnes from a static DB-driven scorer into a live market-intelligence system:

**Tier 1 — Supplier Web Enricher** (Highest Value): Uses the existing `search_sub_agent` (Gemini 2.5 Flash + Google Search grounding, already wired at `orchestration/agents/search_sub_agent.py`) to discover real bulk ingredient suppliers from the web and write structured price/MOQ/lead-time/country data into `Supplier_Commercial`. This unblocks the entire Suppliers tab (currently showing EmptyState for every ingredient) and gives the `SupplierScorer` real data to rank.

**Tier 2 — Price Monitor Pipeline + Alert System** (Medium Value): New `price_monitor` pipeline that runs on demand (or scheduled) to fetch fresh market prices for stale ingredients, compares them against stored prices, detects significant changes (≥15%), writes `Price_Change_Alert` records, and produces a Gemini-authored narrative summary. New alert endpoints expose this data; a frontend notification badge and `AlertsView` tab surface it to the user.

**Tier 3 — Scheduled Execution + Supplier Intelligence Wiki** (Lower Value): FastAPI lifespan background task triggers `price_monitor` every 24h automatically. A `Orchestration/Data/supplier_wiki/` markdown directory (one file per ingredient grade category) is injected as grounding context into `SupplierScorer`, turning the scorer from a pure-normalization engine into a reasoning-aware one that can flag outliers even with a single supplier.

---

## User Story

As a CPG procurement manager  
I want Agnes to automatically discover real supplier prices from the web, monitor them for significant changes, and alert me when a major price drop creates a sourcing opportunity  
So that I can act on market movements in real time instead of discovering them weeks later

---

## Problem Statement

- `Supplier_Commercial` is currently empty — the Suppliers tab shows EmptyState for every ingredient; the `SupplierScorer` has nothing to rank
- The `search_sub_agent` already does Google Search with structured JSON output, but its results are only logged to `Agent_Log` and never written to `Supplier_Commercial`
- `research_agent.py` has a working `_parse_suppliers()` regex pattern for extracting supplier JSON from model output, but it's only used for in-pipeline discovery, not persistent enrichment
- No price change detection or alerting mechanism exists — price drops that could save 20% go unnoticed
- The `price_audit` pipeline only analyses existing DB data; it cannot fetch fresh market prices

---

## Solution Statement

**Tier 1:** Create `enrichment/enrichers/supplier_web_enricher.py` — an async enricher class that calls `search_sub_agent.search()` per canonical ingredient, parses the JSON output via the existing `_parse_suppliers()` regex, upserts `Supplier` rows for newly discovered suppliers, and writes structured `Supplier_Commercial` rows with `Price_Type='web_search'`, `Price_Source='google_search'`, `Confidence=0.65`. A `enrichment/backfill_supplier_web.py` script runs it for all UNII-bearing canonicals with no existing commercial rows.

**Tier 2:** Add `Price_Change_Alert` table (migration). Create `orchestration/tools/price_staleness_checker.py` (sync tool, identifies ingredients needing a refresh) and `orchestration/agents/price_fetch_agent.py` (async agent, calls search_sub_agent per stale ingredient, compares to stored prices, writes alerts). Create `orchestration/agents/price_alert_writer.py` (async, Gemini narrative). Wire into `price_monitor.yaml` pipeline. Add `has_stale_prices` and `has_price_alerts` conditions. New `orchestration/api/routes/alerts.py` endpoints. Frontend: TopBar badge + `AlertsView.tsx`.

**Tier 3:** FastAPI lifespan background `asyncio` task that calls `execute_pipeline("price_monitor", "scheduled", {})` every 24h. `Orchestration/Data/supplier_wiki/` markdown files per ingredient grade, read by a new `reasoning/supplier_guidelines.py` module injected into `SupplierScorer`.

---

## Feature Metadata

**Feature Type**: New Capability (Tier 1, 2) + Enhancement (Tier 3)  
**Estimated Complexity**: High  
**Primary Systems Affected**: enrichment pipeline, orchestration agents/tools/pipelines, API routes, frontend views  
**Dependencies**: `google-adk` (already installed), `google-genai` (already installed), `requests` (already in requirements.txt), `APScheduler` optional (use `asyncio.sleep` loop instead if not installed)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `orchestration/agents/search_sub_agent.py` — The Google Search grounding agent. Returns raw text string from `runner.run_async()`. **Key**: `search(ingredient_name, query_hint)` is `async def` — callers must be async or use `asyncio.run()`.
- `orchestration/agents/research_agent.py` (lines 57-88) — **Critical**: `_parse_suppliers(raw, ingredient_name)` at line 57 is the battle-tested regex parser for extracting JSON supplier arrays from model output. `_stage_suppliers()` at line 70 shows the Supplier+Agent_Log upsert pattern. **Mirror this in Tier 1**.
- `orchestration/agents/_adk_runner.py` — `run_adk_agent(agent, payload, run_id)` shared async helper. Use for `price_alert_writer.py` (Gemini narrative). **Note**: creates a fresh `InMemoryRunner` per call.
- `enrichment/enrichers/commercial_enricher.py` (lines 65-103) — `INSERT OR IGNORE INTO Supplier (Name, Country)` + `INSERT OR REPLACE INTO Supplier_Commercial` upsert pattern. **Mirror exactly in `supplier_web_enricher.py`**.
- `orchestration/agents/proactive_agent.py` — Agent pattern: module-level `LlmAgent`, `async def run(ctx: AgnesContext)`, reads upstream node output via `ctx.get("node-id", {})`, returns structured dict. Mirror for `price_fetch_agent.py` and `price_alert_writer.py`.
- `orchestration/tools/price_benchmark.py` — Sync tool pattern: `def run(ctx: AgnesContext) -> dict`, direct sqlite3, `ctx.trigger_payload.get("canonical_id")`, deviance calculation. Mirror for `price_staleness_checker.py`.
- `orchestration/api/conditions.py` — Add `has_stale_prices` and `has_price_alerts` conditions here. Pattern: reads `ctx.get("node-id", {})`, returns bool. Register in `_REGISTRY` dict at line 45.
- `orchestration/api/agent_registry.py` — Register `PriceFetchAgent` and `PriceAlertWriter` in `_AGENT_REGISTRY`, `PriceStalenesCheckerTool` in `_TOOL_REGISTRY`. Pattern: `"ClassName": "module.path:run"`.
- `orchestration/api/main.py` — Add alerts router: `from orchestration.api.routes import ... alerts` + `app.include_router(alerts.router)`. Also add lifespan background task for scheduler (Tier 3).
- `orchestration/api/routes/data.py` (lines 1-18) — Read-only route pattern: `get_db()` with `mode=ro` URI, `sqlite3.Row` row_factory. Mirror for `alerts.py`.
- `orchestration/api/routes/scoring.py` — New route file pattern with `APIRouter(prefix=...)`, `_DB = Path(...)`, RW connection for writes. Mirror for `alerts.py` dismiss endpoint.
- `schema/enriched_schema.sql` — Add `Price_Change_Alert` table definition here (after `Scoring_Config`, before views).
- `enrichment/db_migrate_fda_scoring.py` — Migration pattern: `_add_col()`, `CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE` defaults, `Enrichment_Run_Log` insert. Mirror for `db_migrate_price_monitor.py`.
- `orchestration/pipelines/proactive_consolidation.yaml` — Two-node pipeline pattern. Mirror YAML structure for `price_monitor.yaml`.
- `orchestration/pipelines/price_audit.yaml` — Four-node pipeline pattern with `when:` conditions. Mirror for `price_monitor.yaml`.
- `orchestration/ui/src/components/layout/Sidebar.tsx` — `TabKey` union type, `ITEMS` array. Add "alerts" entry.
- `orchestration/ui/src/pages/Index.tsx` — `TAB_TITLES` record, tab render switch.
- `orchestration/ui/src/components/shared/States.tsx` — `LoadingState`, `EmptyState`, `ErrorState` — reuse in `AlertsView.tsx`.
- `orchestration/ui/src/components/layout/TopBar.tsx` — Add notification badge here (fetch unread alert count).

### New Files to Create

**Backend:**
- `enrichment/enrichers/supplier_web_enricher.py` — Async enricher: calls `search_sub_agent.search()`, parses JSON, upserts Supplier + Supplier_Commercial
- `enrichment/backfill_supplier_web.py` — Batch script: runs `SupplierWebEnricher` for all UNII canonicals with no commercial rows
- `enrichment/db_migrate_price_monitor.py` — Idempotent migration: creates `Price_Change_Alert` table
- `orchestration/tools/price_staleness_checker.py` — Sync DAG tool: identifies ingredients with stale or missing web prices
- `orchestration/agents/price_fetch_agent.py` — Async DAG agent: fetches fresh prices via search_sub_agent, compares to stored, writes Price_Change_Alert rows, updates Supplier_Commercial
- `orchestration/agents/price_alert_writer.py` — Async DAG agent: Gemini narrative summarizing detected price changes
- `orchestration/pipelines/price_monitor.yaml` — New pipeline YAML
- `orchestration/api/routes/alerts.py` — Alert endpoints: GET list, POST dismiss, GET count

**Frontend:**
- `orchestration/ui/src/components/views/AlertsView.tsx` — Alert cards: ingredient, direction, % change, narrative, dismiss button
- `orchestration/ui/src/hooks/usePriceAlerts.ts` — React Query hook for alert count (for TopBar badge)

**Tier 3:**
- `Orchestration/Data/supplier_wiki/supplements.md` — Guidelines for supplement-grade ingredients
- `Orchestration/Data/supplier_wiki/excipients.md` — Guidelines for excipients/binders
- `Orchestration/Data/supplier_wiki/food.md` — Guidelines for food-grade ingredients
- `reasoning/supplier_guidelines.py` — Reads wiki markdown for an ingredient's grade, returns context string

### Relevant Documentation

- [Google ADK LlmAgent — tools constraint](https://google.github.io/adk-docs/agents/llm-agents/#tool-use)
  - `google_search` tool **cannot be mixed with other tools** in the same `LlmAgent` instance — must stay isolated in `search_sub_agent.py`. Do NOT add it to other agents.
  - Why: `price_fetch_agent.py` must call `search_sub_agent.search()` as a Python coroutine, not via `tools=[google_search]`
- [Google ADK InMemoryRunner — session per call](https://google.github.io/adk-docs/runtime/)
  - Each `run_adk_agent()` call creates a fresh `InMemoryRunner` and session — no shared state between calls
  - Why: `price_fetch_agent` loops over multiple ingredients; each search must be a fresh session
- [openFDA Adverse Events](https://open.fda.gov/apis/drug/event/) — already integrated (reference for pattern parity only)
- [FastAPI Background Tasks via lifespan](https://fastapi.tiangolo.com/advanced/events/#lifespan)
  - Use `asyncio.create_task()` inside the `lifespan` async generator to spawn a long-running background loop
  - Why: Tier 3 scheduled price_monitor trigger

### Patterns to Follow

**Async enricher calling `search_sub_agent.search()` (mirror from `research_agent.py:35-43`):**
```python
from orchestration.agents.search_sub_agent import search

raw_search = await search(ingredient_name, query_hint="bulk supplier B2B price MOQ certificate")
discovered = _parse_suppliers(raw_search, ingredient_name)
```

**`_parse_suppliers()` — copy verbatim from `research_agent.py:57-67`:**
```python
def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    import re, json
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    if raw.strip():
        return [{"supplier_name": "research_result", "notes": raw[:400]}]
    return []
```

**Supplier upsert (mirror from `commercial_enricher.py:70-83`):**
```python
existing = conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()
if existing:
    supplier_id = existing[0]
else:
    cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name, Country) VALUES (?, ?)", (supplier_name, country))
    supplier_id = cur.lastrowid or conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()[0]
```

**Supplier_Commercial upsert for web-sourced data:**
```python
conn.execute(
    """INSERT OR REPLACE INTO Supplier_Commercial
       (SupplierId, CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG, Lead_Time_Days,
        Country_Origin, Price_Type, Price_Source, Confidence, Source_URL, Last_Updated,
        Grade_Unverified, Purity_Qualifier)
       VALUES (?, ?, ?, ?, ?, ?, 'web_search', 'google_search', 0.65, ?, datetime('now'), 1, ?)""",
    (supplier_id, canonical_id, price, moq, lead_time, country, source_url, purity_qualifier)
)
```

**Condition registration (`conditions.py:45-53`):**
```python
_REGISTRY: dict[str, ConditionFn] = {
    ...existing...,
    "has_stale_prices": has_stale_prices,   # ADD
    "has_price_alerts": has_price_alerts,   # ADD
}
```

**Tool registration (`agent_registry.py:12-20`):**
```python
_TOOL_REGISTRY: dict[str, str] = {
    ...existing...,
    "PriceStalenesCheckerTool": "orchestration.tools.price_staleness_checker:run",
}
_AGENT_REGISTRY: dict[str, str] = {
    ...existing...,
    "PriceFetchAgent":    "orchestration.agents.price_fetch_agent:run",
    "PriceAlertWriter":   "orchestration.agents.price_alert_writer:run",
}
```

**Pipeline YAML trigger convention:**  
- `trigger: chat` — callable via natural language through router_agent  
- `trigger: data_update` — callable via `POST /data-update`  
- `trigger: scheduled` — new value; `price_monitor` should accept both `scheduled` AND `chat` since users can also ask Agnes to "check prices"  
- The `pipeline_loader.py` reads YAML but `trigger` is only stored in the `Pipeline` dataclass for reference — it doesn't gate execution. Any pipeline can be run via `POST /pipelines/run/{name}`.

**Naming conventions:**
- Python: `snake_case` functions, `PascalCase` classes, `UPPER_CASE` constants
- YAML: `kebab-case` node IDs, `PascalCase` class names in `tool_class:` / `agent_class:`
- DB tables: `PascalCase_With_Underscores`
- Route prefix: `/api/data/...` (read), `/api/alerts/...` (alert management)

---

## IMPLEMENTATION PLAN

### Tier 1 — Supplier Web Enricher (Foundation for everything else)

**Tasks 1-5** must be done before Tier 2, because `Price_Change_Alert` comparison logic needs existing `Supplier_Commercial` rows to compare against.

### Tier 2 — Price Monitor Pipeline + Alert System

**Tasks 6-16** build the monitoring and alerting layer on top of Tier 1 data.

### Tier 3 — Scheduled Execution + Supplier Intelligence Wiki

**Tasks 17-20** are additive enhancements that don't block Tiers 1 or 2.

---

## STEP-BY-STEP TASKS

### TASK 1: UPDATE `schema/enriched_schema.sql`

- **ADD** `Price_Change_Alert` table after `Scoring_Config`:

```sql
-- Price change alerts — detected by price_monitor pipeline
CREATE TABLE IF NOT EXISTS Price_Change_Alert (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId   INTEGER NOT NULL,
    SupplierId              INTEGER,
    Ingredient_Name         TEXT NOT NULL,
    Supplier_Name           TEXT,
    Previous_Price_USD      REAL,
    New_Price_USD           REAL,
    Change_Pct              REAL,           -- signed: negative = drop, positive = increase
    Direction               TEXT NOT NULL,  -- 'up' | 'down'
    Severity                TEXT NOT NULL DEFAULT 'info',  -- 'info' (5-14%) | 'warning' (15-29%) | 'critical' (≥30%)
    Alert_Narrative         TEXT,           -- filled by PriceAlertWriterAgent
    Dismissed               INTEGER NOT NULL DEFAULT 0,
    Detected_At             TEXT NOT NULL DEFAULT (datetime('now')),
    Run_Id                  TEXT,
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (SupplierId) REFERENCES Supplier(Id)
);
CREATE INDEX IF NOT EXISTS idx_price_alert_canonical ON Price_Change_Alert(CanonicalIngredientId);
CREATE INDEX IF NOT EXISTS idx_price_alert_dismissed ON Price_Change_Alert(Dismissed, Detected_At);
```

- **VALIDATE**: `grep -n "Price_Change_Alert" schema/enriched_schema.sql`

---

### TASK 2: CREATE `enrichment/db_migrate_price_monitor.py`

- **IMPLEMENT**: Idempotent migration creating `Price_Change_Alert` table and its indexes
- **PATTERN**: Mirror `enrichment/db_migrate_fda_scoring.py` exactly — `_add_col()`, `CREATE TABLE IF NOT EXISTS`, log to `Enrichment_Run_Log`
- **IMPORTS**: `import sqlite3, logging; from pathlib import Path; from dotenv import load_dotenv; load_dotenv()`

```python
"""Idempotent migration: Price_Change_Alert table for price monitor pipeline."""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_price_monitor")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS Price_Change_Alert (
        Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        CanonicalIngredientId   INTEGER NOT NULL,
        SupplierId              INTEGER,
        Ingredient_Name         TEXT NOT NULL,
        Supplier_Name           TEXT,
        Previous_Price_USD      REAL,
        New_Price_USD           REAL,
        Change_Pct              REAL,
        Direction               TEXT NOT NULL,
        Severity                TEXT NOT NULL DEFAULT 'info',
        Alert_Narrative         TEXT,
        Dismissed               INTEGER NOT NULL DEFAULT 0,
        Detected_At             TEXT NOT NULL DEFAULT (datetime('now')),
        Run_Id                  TEXT,
        FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
        FOREIGN KEY (SupplierId) REFERENCES Supplier(Id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_alert_canonical ON Price_Change_Alert(CanonicalIngredientId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_alert_dismissed ON Price_Change_Alert(Dismissed, Detected_At)")
    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_price_monitor', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Price monitor migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 enrichment/db_migrate_price_monitor.py`

---

### TASK 3: CREATE `enrichment/enrichers/supplier_web_enricher.py`

- **IMPLEMENT**: Async enricher class. Calls `search_sub_agent.search()`, parses supplier JSON with `_parse_suppliers()` (copied verbatim from `research_agent.py:57-67`), upserts `Supplier` rows, writes `Supplier_Commercial` rows
- **PATTERN**: Supplier upsert from `commercial_enricher.py:70-83`; `_parse_suppliers` from `research_agent.py:57-67`
- **GOTCHA**: `search_sub_agent.search()` is `async` — the `run_batch()` method must be `async` and called via `asyncio.run()` from the batch script
- **GOTCHA**: Price range strings from the model (e.g. `"$12-18"`, `"12.50"`, `"~$15"`) need `_parse_price()` helper
- **GOTCHA**: Supplier names from web search may be long brand names — truncate to 200 chars; skip rows where `supplier_name` is "research_result" (fallback noise)
- **IMPORTS**: `import asyncio, json, logging, re, sqlite3; from pathlib import Path; from datetime import datetime; from dotenv import load_dotenv; load_dotenv()`

```python
"""Async enricher: discovers bulk ingredient suppliers via Google Search → Supplier_Commercial."""
import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.supplier_web_enricher")

_CHANGE_THRESHOLD = 0.15  # 15% — flag as stale/changed
_CONFIDENCE_WEB = 0.65


def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    """Mirror of research_agent._parse_suppliers — extract JSON array from model output."""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    if raw.strip():
        return [{"supplier_name": "research_result", "notes": raw[:400]}]
    return []


def _parse_price(price_str: str | None) -> float | None:
    """Extract a float from strings like '$12-18', '~15', '12.50 USD/kg'."""
    if not price_str:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(price_str))
    if not nums:
        return None
    # Average if range (e.g. "12-18" → 15.0)
    values = [float(n) for n in nums[:2]]
    return round(sum(values) / len(values), 4)


def _parse_moq(moq_str: str | None) -> float | None:
    """Extract float from '25 kg', '1-5 kg', '100kg'."""
    if not moq_str:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(moq_str))
    return float(nums[0]) if nums else None


class SupplierWebEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def _get_targets(self) -> list[tuple[int, str, str | None]]:
        """Return (canonical_id, name, grade_flag) for canonicals with no web-search commercial rows."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT ic.Id, ic.Name, ic.Grade_Flag
               FROM Ingredient_Canonical ic
               WHERE ic.UNII_Code IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM Supplier_Commercial sc
                   WHERE sc.CanonicalIngredientId = ic.Id
                     AND sc.Price_Source = 'google_search'
               )
               ORDER BY ic.Name"""
        ).fetchall()
        conn.close()
        return [(r[0], r[1], r[2]) for r in rows]

    def _upsert_supplier(self, conn: sqlite3.Connection, supplier_name: str, country: str | None) -> int:
        existing = conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()
        if existing:
            return existing[0]
        cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name, Country) VALUES (?, ?)", (supplier_name, country))
        sid = cur.lastrowid or conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()[0]
        return sid

    def _write_commercial(
        self, conn: sqlite3.Connection,
        supplier_id: int, canonical_id: int,
        parsed: dict, source_url: str | None
    ) -> None:
        price = _parse_price(parsed.get("price_range_usd_per_kg"))
        moq = _parse_moq(parsed.get("moq_range_kg"))
        country = (parsed.get("country") or "")[:10] or None
        purity_q = (parsed.get("certifications") or [])
        purity_qualifier = ", ".join(purity_q[:3]) if purity_q else None

        conn.execute(
            """INSERT OR REPLACE INTO Supplier_Commercial
               (SupplierId, CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG,
                Country_Origin, Price_Type, Price_Source, Confidence,
                Source_URL, Last_Updated, Grade_Unverified, Purity_Qualifier)
               VALUES (?, ?, ?, ?, ?, 'web_search', 'google_search', ?, ?, datetime('now'), 1, ?)""",
            (supplier_id, canonical_id, price, moq, country, _CONFIDENCE_WEB, source_url, purity_qualifier)
        )

    async def enrich_ingredient(self, canonical_id: int, ingredient_name: str) -> int:
        """Discover and persist suppliers for one ingredient. Returns count inserted."""
        from orchestration.agents.search_sub_agent import search
        try:
            raw = await search(ingredient_name, query_hint="bulk supplier B2B price MOQ certificate")
        except Exception as e:
            logger.warning(f"Search failed for {ingredient_name}: {e}")
            return 0

        suppliers = _parse_suppliers(raw, ingredient_name)
        written = 0
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for s in suppliers:
            name = (s.get("supplier_name") or "").strip()[:200]
            if not name or name == "research_result":
                continue
            try:
                supplier_id = self._upsert_supplier(conn, name, s.get("country"))
                self._write_commercial(conn, supplier_id, canonical_id, s, s.get("website"))
                written += 1
            except Exception as e:
                logger.warning(f"  Failed to write supplier {name!r}: {e}")
        conn.execute(
            """INSERT INTO Enrichment_Run_Log (ProductId, Phase, Step, Status, Confidence, Method)
               VALUES (NULL, 3, 'supplier_web_enrich', 'success', 0.65, 'google_search')"""
        )
        conn.commit()
        conn.close()
        logger.info(f"  {ingredient_name}: {len(suppliers)} found → {written} written to Supplier_Commercial")
        return written

    async def run_batch(self, limit: int | None = None) -> dict:
        targets = self._get_targets()
        if limit:
            targets = targets[:limit]
        logger.info(f"SupplierWebEnricher: {len(targets)} ingredients to enrich")
        total = 0
        for canonical_id, name, grade in targets:
            n = await self.enrich_ingredient(canonical_id, name)
            total += n
        return {"processed": len(targets), "total_suppliers_written": total}
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from enrichment.enrichers.supplier_web_enricher import SupplierWebEnricher; print('import ok')"`

---

### TASK 4: CREATE `enrichment/backfill_supplier_web.py`

- **IMPLEMENT**: Batch script that runs `SupplierWebEnricher.run_batch()` for all eligible canonicals
- **PATTERN**: Mirror `enrichment/backfill_openfda.py` — `load_dotenv()` at top, `asyncio.run()` entry point, `logging.basicConfig()`
- **GOTCHA**: `asyncio.run()` is needed because `run_batch()` is async; do NOT call from inside an already-running event loop

```python
"""Batch supplier web enrichment: populate Supplier_Commercial from Google Search."""
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_supplier_web")


async def _run():
    import os
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not set — cannot run web enrichment")
        return
    from enrichment.enrichers.supplier_web_enricher import SupplierWebEnricher
    enricher = SupplierWebEnricher(ENRICHED_DB)
    result = await enricher.run_batch()
    print(f"Done: {result['processed']} ingredients processed, {result['total_suppliers_written']} suppliers written")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from enrichment.backfill_supplier_web import _run; print('import ok')"`
- **RUN** (when GOOGLE_API_KEY is set): `PYTHONPATH=. python3 enrichment/backfill_supplier_web.py`
- **CHECK**: `PYTHONPATH=. python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Supplier_Commercial WHERE Price_Source=\'google_search\'').fetchone())"`

---

### TASK 5: CREATE `orchestration/tools/price_staleness_checker.py`

- **IMPLEMENT**: Sync DAG tool. Identifies ingredients that need a price refresh: either (a) `Price_Source = 'google_search'` and `Last_Updated < 7 days ago`, or (b) no `Supplier_Commercial` rows at all for UNII-bearing canonicals
- **PATTERN**: Sync `def run(ctx: AgnesContext) -> dict`, direct sqlite3, `ctx.enriched_db_path`. Mirror `price_benchmark.py` structure.
- **OUTPUT**: `{"stale_ingredients": [{"canonical_id": int, "name": str, "reason": str, "days_since_update": int | None}], "count": int}`
- **GOTCHA**: `trigger_payload` may contain `ingredient_name` to scope to one ingredient; if absent, return ALL stale ingredients (up to 20 — don't flood search API)

```python
"""Sync tool: find canonical ingredients with stale or missing web-sourced prices."""
import sqlite3
from datetime import datetime, timedelta
from orchestration.api.agnes_context import AgnesContext

_STALE_DAYS = 7
_MAX_RESULTS = 20


def run(ctx: AgnesContext) -> dict:
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "")
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # Ingredients with no web-search price data
    q_missing = """
        SELECT ic.Id, ic.Name, NULL as last_updated, 'no_web_data' as reason
        FROM Ingredient_Canonical ic
        WHERE ic.UNII_Code IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM Supplier_Commercial sc
            WHERE sc.CanonicalIngredientId = ic.Id AND sc.Price_Source = 'google_search'
        )
    """
    # Ingredients with stale web-search price data
    stale_cutoff = (datetime.utcnow() - timedelta(days=_STALE_DAYS)).strftime("%Y-%m-%d")
    q_stale = """
        SELECT ic.Id, ic.Name, MAX(sc.Last_Updated) as last_updated, 'stale' as reason
        FROM Ingredient_Canonical ic
        JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
        WHERE sc.Price_Source = 'google_search'
        GROUP BY ic.Id
        HAVING MAX(sc.Last_Updated) < ?
    """
    params_stale = [stale_cutoff]

    if ingredient_name:
        q_missing += " AND LOWER(ic.Name) = LOWER(?)"
        q_stale = q_stale.replace("HAVING", f"AND LOWER(ic.Name) = LOWER(?) HAVING")
        params_stale = [ingredient_name, stale_cutoff]

    missing = conn.execute(q_missing, [ingredient_name] if ingredient_name else []).fetchall()
    stale = conn.execute(q_stale, params_stale).fetchall()
    conn.close()

    results = []
    seen = set()
    for r in list(missing) + list(stale):
        if r["Id"] in seen:
            continue
        seen.add(r["Id"])
        last_updated = r["last_updated"]
        days_ago = None
        if last_updated:
            try:
                days_ago = (datetime.utcnow() - datetime.fromisoformat(last_updated)).days
            except Exception:
                pass
        results.append({
            "canonical_id": r["Id"],
            "name": r["Name"],
            "reason": r["reason"],
            "days_since_update": days_ago,
        })
        if len(results) >= _MAX_RESULTS:
            break

    return {"stale_ingredients": results, "count": len(results)}
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.tools.price_staleness_checker import run; print('import ok')"`

---

### TASK 6: CREATE `orchestration/agents/price_fetch_agent.py`

- **IMPLEMENT**: Async DAG agent. Iterates `stale_ingredients` from upstream `find-stale` node. For each, calls `search_sub_agent.search()`, parses suppliers, compares new prices to existing stored prices, writes `Price_Change_Alert` if Δ ≥ 15%, updates `Supplier_Commercial`
- **PATTERN**: `async def run(ctx: AgnesContext) -> dict`. Module-level LlmAgent NOT needed here — this agent does Python logic, not LLM calls. Uses `search_sub_agent.search()` directly.
- **CRITICAL**: No module-level `LlmAgent` needed — this is a Python logic agent, not a narrative writer. The LLM call happens in `price_alert_writer.py`.
- **IMPORTS**: `import asyncio, json, logging, re, sqlite3; from datetime import datetime; from dotenv import load_dotenv; load_dotenv()`

```python
"""Async DAG agent: fetch fresh prices for stale ingredients, detect changes, write alerts."""
import json
import logging
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.price_fetch_agent")
_ALERT_THRESHOLD = 0.15  # 15% change triggers an alert


def _parse_price(s: str | None) -> float | None:
    if not s:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(s))
    if not nums:
        return None
    return round(sum(float(n) for n in nums[:2]) / min(len(nums), 2), 4)


def _severity(change_pct: float) -> str:
    abs_pct = abs(change_pct)
    if abs_pct >= 30:
        return "critical"
    if abs_pct >= 15:
        return "warning"
    return "info"


async def run(ctx: AgnesContext) -> dict:
    stale = ctx.get("find-stale", {}).get("stale_ingredients", [])
    if not stale:
        return {"alerts_created": [], "suppliers_updated": 0, "count": 0}

    import os
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"alerts_created": [], "suppliers_updated": 0, "count": 0, "skipped": "GOOGLE_API_KEY not set"}

    from orchestration.agents.search_sub_agent import search
    from enrichment.enrichers.supplier_web_enricher import _parse_suppliers, SupplierWebEnricher

    enricher = SupplierWebEnricher(ctx.enriched_db_path)
    alerts_created = []
    suppliers_updated = 0

    for item in stale:
        canonical_id = item["canonical_id"]
        name = item["name"]
        logger.info(f"Fetching fresh prices for {name} (canonical_id={canonical_id})")

        try:
            raw = await search(name, query_hint="bulk supplier B2B price per kg 2025")
        except Exception as e:
            logger.warning(f"Search failed for {name}: {e}")
            continue

        parsed_suppliers = _parse_suppliers(raw, name)
        if not parsed_suppliers:
            continue

        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row

        for s in parsed_suppliers:
            sname = (s.get("supplier_name") or "").strip()[:200]
            if not sname or sname == "research_result":
                continue
            new_price = _parse_price(s.get("price_range_usd_per_kg"))
            if new_price is None:
                continue

            supplier_id = enricher._upsert_supplier(conn, sname, s.get("country"))

            # Check existing price
            existing = conn.execute(
                """SELECT Price_USD_Per_KG FROM Supplier_Commercial
                   WHERE SupplierId = ? AND CanonicalIngredientId = ?""",
                (supplier_id, canonical_id)
            ).fetchone()

            old_price = existing["Price_USD_Per_KG"] if existing else None

            # Write/update Supplier_Commercial
            enricher._write_commercial(conn, supplier_id, canonical_id, s, s.get("website"))
            suppliers_updated += 1

            # Detect significant change
            if old_price and old_price > 0:
                change_pct = (new_price - old_price) / old_price
                if abs(change_pct) >= _ALERT_THRESHOLD:
                    direction = "down" if change_pct < 0 else "up"
                    severity = _severity(change_pct)
                    conn.execute(
                        """INSERT INTO Price_Change_Alert
                           (CanonicalIngredientId, SupplierId, Ingredient_Name, Supplier_Name,
                            Previous_Price_USD, New_Price_USD, Change_Pct, Direction,
                            Severity, Run_Id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (canonical_id, supplier_id, name, sname,
                         old_price, new_price, round(change_pct * 100, 2),
                         direction, severity, ctx.run_id)
                    )
                    alerts_created.append({
                        "ingredient": name, "supplier": sname,
                        "old_price": old_price, "new_price": new_price,
                        "change_pct": round(change_pct * 100, 2),
                        "direction": direction, "severity": severity,
                    })
                    logger.info(f"  ALERT: {name} @ {sname}: ${old_price}→${new_price} ({change_pct:+.1%})")

        conn.commit()
        conn.close()

    return {
        "alerts_created": alerts_created,
        "suppliers_updated": suppliers_updated,
        "count": len(alerts_created),
    }
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.agents.price_fetch_agent import run; print('import ok')"`

---

### TASK 7: CREATE `orchestration/agents/price_alert_writer.py`

- **IMPLEMENT**: Async DAG agent. Uses Gemini (`gemini-2.5-flash` via `run_adk_agent`) to write a ≤200-word executive narrative summarizing detected price changes. Updates `Price_Change_Alert.Alert_Narrative` for the current run.
- **PATTERN**: Module-level `LlmAgent` + `run_adk_agent`. Mirror `proactive_agent.py` exactly.
- **OUTPUT**: `{"alert_narrative": str, "alert_count": int, "run_id": str}`

```python
"""Async DAG agent: Gemini narrative summarizing detected price changes."""
import json
import logging
import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import LlmAgent
from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.price_alert_writer")

_AGENT = LlmAgent(
    name="price_alert_writer",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain advisor. You receive a list of ingredient price changes
detected from live market data. Write a ≤200-word executive briefing:

- Open with the most significant change (largest % drop/increase)
- Group by direction: drops first (opportunity), then increases (risk)
- For each: ingredient, supplier, old price → new price, % change, recommended action
- Close with a one-sentence priority recommendation

Use bullet points. Be concrete. Flag data-confidence caveats (web-search prices are indicative).
No headers. Plain prose bullets.""",
)


async def run(ctx: AgnesContext) -> dict:
    alerts = ctx.get("fetch-prices", {}).get("alerts_created", [])
    if not alerts:
        return {"alert_narrative": None, "alert_count": 0, "run_id": ctx.run_id}

    if not os.environ.get("GOOGLE_API_KEY"):
        return {"alert_narrative": None, "alert_count": len(alerts), "run_id": ctx.run_id, "skipped": "GOOGLE_API_KEY not set"}

    payload = json.dumps({"price_changes": alerts}, indent=2)
    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    # Persist narrative back to Price_Change_Alert rows for this run
    if narrative:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute(
            "UPDATE Price_Change_Alert SET Alert_Narrative = ? WHERE Run_Id = ? AND Alert_Narrative IS NULL",
            (narrative, ctx.run_id)
        )
        conn.commit()
        conn.close()

    return {
        "alert_narrative": narrative,
        "alert_count": len(alerts),
        "run_id": ctx.run_id,
        "top_change": max(alerts, key=lambda a: abs(a["change_pct"]), default=None),
    }
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.agents.price_alert_writer import run; print('import ok')"`

---

### TASK 8: CREATE `orchestration/pipelines/price_monitor.yaml`

- **IMPLEMENT**: Three-node pipeline: staleness check → price fetch → alert narrative
- **PATTERN**: Mirror `proactive_consolidation.yaml` (two `when:` conditions) + `price_audit.yaml` (four nodes, multiple conditions)
- **GOTCHA**: Node IDs must match what agents read via `ctx.get("node-id", {})` — use `find-stale`, `fetch-prices`, `write-alert-narrative` exactly

```yaml
name: price_monitor
trigger: scheduled
nodes:
  - id: find-stale
    tool_class: PriceStalenesCheckerTool
    depends_on: []

  - id: fetch-prices
    agent_class: PriceFetchAgent
    depends_on: [find-stale]
    when: has_stale_prices

  - id: write-alert-narrative
    agent_class: PriceAlertWriter
    depends_on: [fetch-prices]
    when: has_price_alerts
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.pipeline_loader import load_pipeline; p = load_pipeline('orchestration/pipelines/price_monitor.yaml'); print(p.name, [n.id for n in p.nodes])"`

---

### TASK 9: ADD conditions to `orchestration/api/conditions.py`

- **ADD** two new condition functions and register them in `_REGISTRY`
- **PATTERN**: Mirror existing functions at lines 7-43

```python
# ADD after `has_research_results`:

def has_stale_prices(ctx: AgnesContext) -> bool:
    out = ctx.get("find-stale", {})
    return out.get("count", 0) > 0


def has_price_alerts(ctx: AgnesContext) -> bool:
    out = ctx.get("fetch-prices", {})
    return out.get("count", 0) > 0
```

```python
# ADD to _REGISTRY dict:
    "has_stale_prices":  has_stale_prices,
    "has_price_alerts":  has_price_alerts,
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.conditions import evaluate; print('conditions ok')"`

---

### TASK 10: REGISTER in `orchestration/api/agent_registry.py`

- **ADD** to both registries:

```python
# In _AGENT_REGISTRY:
    "PriceFetchAgent":   "orchestration.agents.price_fetch_agent:run",
    "PriceAlertWriter":  "orchestration.agents.price_alert_writer:run",

# In _TOOL_REGISTRY:
    "PriceStalenesCheckerTool": "orchestration.tools.price_staleness_checker:run",
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.agent_registry import get_agent, get_tool; get_tool('PriceStalenesCheckerTool'); get_agent('PriceFetchAgent'); get_agent('PriceAlertWriter'); print('registry ok')"`

---

### TASK 11: CREATE `orchestration/api/routes/alerts.py`

- **IMPLEMENT**: Four endpoints: GET list (with filters), GET unread count, POST dismiss, GET per-ingredient
- **PATTERN**: Mirror `orchestration/api/routes/data.py` for read endpoints, `orchestration/api/routes/scoring.py` for write endpoints (RW connection for dismiss)
- **NOTE**: Import `HTTPException` at top — do not inline-import inside functions

```python
"""Price change alert endpoints."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"


def _get_db_ro():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_db_rw():
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/count")
def alert_count():
    """Unread (non-dismissed) alert count — used for TopBar badge."""
    with _get_db_ro() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM Price_Change_Alert WHERE Dismissed = 0"
        ).fetchone()
    return {"count": row[0]}


@router.get("/")
def list_alerts(
    dismissed: bool = Query(default=False),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    with _get_db_ro() as db:
        q = """SELECT a.*, ic.Grade_Flag as grade
               FROM Price_Change_Alert a
               JOIN Ingredient_Canonical ic ON ic.Id = a.CanonicalIngredientId
               WHERE a.Dismissed = ?"""
        params: list = [int(dismissed)]
        if severity:
            q += " AND a.Severity = ?"
            params.append(severity)
        q += " ORDER BY a.Detected_At DESC LIMIT ?"
        params.append(limit)
        rows = db.execute(q, params).fetchall()
    return {"alerts": [dict(r) for r in rows], "count": len(rows)}


@router.post("/{alert_id}/dismiss")
def dismiss_alert(alert_id: int):
    with _get_db_rw() as db:
        row = db.execute("SELECT Id FROM Price_Change_Alert WHERE Id = ?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        db.execute("UPDATE Price_Change_Alert SET Dismissed = 1 WHERE Id = ?", (alert_id,))
        db.commit()
    return {"status": "dismissed", "alert_id": alert_id}


@router.get("/ingredient/{ingredient_id}")
def ingredient_alerts(ingredient_id: int, limit: int = Query(default=20, le=100)):
    with _get_db_ro() as db:
        rows = db.execute(
            """SELECT * FROM Price_Change_Alert
               WHERE CanonicalIngredientId = ?
               ORDER BY Detected_At DESC LIMIT ?""",
            (ingredient_id, limit)
        ).fetchall()
    return {"ingredient_id": ingredient_id, "alerts": [dict(r) for r in rows], "count": len(rows)}
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.routes.alerts import router; print([r.path for r in router.routes])"`

---

### TASK 12: REGISTER alerts router in `orchestration/api/main.py`

- **ADD** to import and `app.include_router()`:

```python
# Modify import line:
from orchestration.api.routes import chat, pipelines, data_update, data, scoring, alerts

# Add after app.include_router(scoring.router):
app.include_router(alerts.router)
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.main import app; print([r.path for r in app.routes if 'alerts' in r.path])"`

---

### TASK 13: ADD frontend types to `orchestration/ui/src/types/agnes.ts`

- **ADD** at end of file:

```typescript
export interface PriceAlert {
  Id: number;
  CanonicalIngredientId: number;
  SupplierId: number | null;
  Ingredient_Name: string;
  Supplier_Name: string | null;
  Previous_Price_USD: number | null;
  New_Price_USD: number | null;
  Change_Pct: number | null;           // signed percentage: -15.2 means 15.2% drop
  Direction: "up" | "down";
  Severity: "info" | "warning" | "critical";
  Alert_Narrative: string | null;
  Dismissed: number;
  Detected_At: string;
  Run_Id: string | null;
}

export interface AlertCount {
  count: number;
}
```

---

### TASK 14: ADD API methods to `orchestration/ui/src/lib/agnesApi.ts`

- **ADD** after `fdaLimits()` method:

```typescript
async alertCount(): Promise<AlertCount> {
  return safeFetch<AlertCount>("/api/alerts/count");
},

async listAlerts(dismissed = false): Promise<{ alerts: PriceAlert[]; count: number }> {
  return safeFetch(`/api/alerts/?dismissed=${dismissed}`);
},

async dismissAlert(alertId: number): Promise<{ status: string }> {
  return safeFetch(`/api/alerts/${alertId}/dismiss`, { method: "POST" });
},
```

- **ADD** `PriceAlert, AlertCount` to the import from `"@/types/agnes"` at the top of the file

---

### TASK 15: CREATE `orchestration/ui/src/components/views/AlertsView.tsx`

- **IMPLEMENT**: Alert cards showing ingredient, direction arrow, price change, severity badge, narrative, dismiss button
- **PATTERN**: `useQuery` for data, `useMutation` for dismiss. Mirror `OpportunitiesView.tsx` for query pattern, `SuppliersView.tsx` for mutation pattern.
- **USE**: `LoadingState`, `EmptyState`, `ErrorState` from `@/components/shared/States`
- **ICONS**: `TrendingDown` (drop/opportunity), `TrendingUp` (increase/risk), `Bell`, `X` from `lucide-react`

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { TrendingDown, TrendingUp, X, Bell } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { PriceAlert } from "@/types/agnes";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES = {
  critical: "bg-red-500/10 border-red-500/30 text-red-500",
  warning: "bg-amber-500/10 border-amber-500/30 text-amber-500",
  info: "bg-blue-500/10 border-blue-500/30 text-blue-500",
};

export function AlertsView() {
  const qc = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["price-alerts", showDismissed],
    queryFn: () => agnesApi.listAlerts(showDismissed),
  });

  const dismissMutation = useMutation({
    mutationFn: (id: number) => agnesApi.dismissAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["price-alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-count"] });
    },
  });

  if (isLoading) return <LoadingState label="Loading alerts…" />;
  if (error) return <ErrorState message="Failed to load price alerts." />;
  if (!data?.alerts?.length) {
    return (
      <EmptyState
        icon={<Bell className="size-4" />}
        title="No price alerts"
        body={showDismissed ? "No dismissed alerts." : "Run the price_monitor pipeline to check for market price changes."}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[12px] text-muted-foreground">{data.count} alert{data.count !== 1 ? "s" : ""}</p>
        <button
          onClick={() => setShowDismissed(!showDismissed)}
          className="text-[12px] text-primary hover:underline"
        >
          {showDismissed ? "Show active" : "Show dismissed"}
        </button>
      </div>
      {data.alerts.map((alert) => (
        <AlertCard
          key={alert.Id}
          alert={alert}
          onDismiss={() => dismissMutation.mutate(alert.Id)}
          dismissing={dismissMutation.isPending}
        />
      ))}
    </div>
  );
}

function AlertCard({ alert, onDismiss, dismissing }: {
  alert: PriceAlert;
  onDismiss: () => void;
  dismissing: boolean;
}) {
  const isDown = alert.Direction === "down";
  const Icon = isDown ? TrendingDown : TrendingUp;
  const changePct = alert.Change_Pct != null ? Math.abs(alert.Change_Pct) : null;

  return (
    <div className={cn(
      "rounded-lg border p-4 space-y-2",
      alert.Severity === "critical" ? "border-red-500/30 bg-red-500/5"
        : alert.Severity === "warning" ? "border-amber-500/30 bg-amber-500/5"
        : "border-border bg-background"
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon
            className={cn("size-4 shrink-0", isDown ? "text-emerald-500" : "text-red-400")}
            strokeWidth={2.5}
          />
          <div className="min-w-0">
            <span className="text-[13px] font-medium">{alert.Ingredient_Name}</span>
            {alert.Supplier_Name && (
              <span className="text-[11px] text-muted-foreground ml-1.5">via {alert.Supplier_Name}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {changePct != null && (
            <span className={cn(
              "text-[12px] font-mono font-semibold px-1.5 py-0.5 rounded",
              isDown ? "text-emerald-500 bg-emerald-500/10" : "text-red-400 bg-red-400/10"
            )}>
              {isDown ? "−" : "+"}{changePct.toFixed(1)}%
            </span>
          )}
          {!alert.Dismissed && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-muted-foreground"
              onClick={onDismiss}
              disabled={dismissing}
            >
              <X className="size-3" />
            </Button>
          )}
        </div>
      </div>

      {alert.Previous_Price_USD != null && alert.New_Price_USD != null && (
        <p className="text-[12px] text-muted-foreground font-mono">
          ${alert.Previous_Price_USD.toFixed(2)} → ${alert.New_Price_USD.toFixed(2)}/kg
        </p>
      )}

      {alert.Alert_Narrative && (
        <p className="text-[12px] text-foreground/80 leading-relaxed border-t border-border pt-2 mt-2">
          {alert.Alert_Narrative}
        </p>
      )}

      <p className="text-[10px] text-muted-foreground/60">
        Detected {new Date(alert.Detected_At).toLocaleDateString()}
        {alert.Severity !== "info" && (
          <span className={cn(
            "ml-2 uppercase font-semibold text-[9px] px-1 py-0.5 rounded",
            SEVERITY_STYLES[alert.Severity]
          )}>
            {alert.Severity}
          </span>
        )}
      </p>
    </div>
  );
}
```

---

### TASK 16: ADD "alerts" tab to Sidebar + Index

**UPDATE `orchestration/ui/src/components/layout/Sidebar.tsx`:**
```typescript
// Add to import:
import { ..., Bell } from "lucide-react";

// Add to TabKey union:
export type TabKey = "agnes" | "opportunities" | "ingredients" | "compliance" | "proposals" | "runs" | "suppliers" | "alerts";

// Add to ITEMS array after "suppliers":
{ key: "suppliers" as TabKey, label: "Suppliers", icon: Package },
{ key: "alerts" as TabKey, label: "Price Alerts", icon: Bell },
```

**UPDATE `orchestration/ui/src/pages/Index.tsx`:**
```typescript
// Add import:
import { AlertsView } from "@/components/views/AlertsView";

// Add to TAB_TITLES:
alerts: { title: "Price Alerts", subtitle: "Market price changes detected by Agnes — drops are sourcing opportunities, increases are cost risks." },

// Add to render switch (before the final fallback):
: tab === "alerts" ? <AlertsView />
```

- **VALIDATE**: `cd orchestration/ui && npm run build 2>&1 | tail -5`

---

### TASK 17 (Tier 3): ADD scheduled background task to `orchestration/api/main.py`

- **IMPLEMENT**: Inside the `lifespan` context manager, after `_db.init_db(_DB_PATH)`, spawn an asyncio background task that loops every 24h and triggers `price_monitor`
- **PATTERN**: `asyncio.create_task()` inside the lifespan `async with` block

```python
# Add to imports:
import asyncio
import logging
logger = logging.getLogger("agnes.scheduler")

# Add schedule function before lifespan:
_PRICE_MONITOR_INTERVAL_H = 24

async def _price_monitor_scheduler():
    """Background loop: trigger price_monitor pipeline every 24h."""
    import os
    from orchestration.api.pipeline_loader import load_pipelines_dir
    from orchestration.api import dag_executor

    await asyncio.sleep(60)  # Wait 60s after startup before first run
    while True:
        if os.environ.get("GOOGLE_API_KEY"):
            try:
                logger.info("Scheduler: triggering price_monitor pipeline")
                await dag_executor.execute_pipeline("price_monitor", "scheduled", {})
            except Exception as e:
                logger.error(f"Scheduler: price_monitor failed: {e}")
        await asyncio.sleep(_PRICE_MONITOR_INTERVAL_H * 3600)

# Modify lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    _db.init_db(_DB_PATH)
    task = asyncio.create_task(_price_monitor_scheduler())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python3 -c "from orchestration.api.main import app; print('lifespan ok')"`

---

### TASK 18 (Tier 3): CREATE `reasoning/supplier_guidelines.py`

- **IMPLEMENT**: Reads the appropriate markdown wiki file for a given ingredient grade, returns a context string for injection into `SupplierScorer`

```python
"""Supplier intelligence wiki reader — injects grade-level guidelines into scoring context."""
from pathlib import Path

_WIKI_DIR = Path(__file__).parent.parent / "Orchestration" / "Data" / "supplier_wiki"

_GRADE_TO_FILE = {
    "supplement": "supplements.md",
    "excipient": "excipients.md",
    "food": "food.md",
    "sweetener": "food.md",
    "flavor": "food.md",
    "unknown": "supplements.md",  # pessimistic default
}


def get_guidelines(grade: str | None) -> str:
    """Return markdown guidelines text for the given ingredient grade, or empty string."""
    fname = _GRADE_TO_FILE.get((grade or "unknown").lower(), "supplements.md")
    fpath = _WIKI_DIR / fname
    if fpath.exists():
        return fpath.read_text(encoding="utf-8")
    return ""
```

---

### TASK 19 (Tier 3): CREATE wiki markdown files

**CREATE `Orchestration/Data/supplier_wiki/supplements.md`:**

```markdown
# Supplement-Grade Ingredient Sourcing Guidelines

## Typical Price Ranges (USD/kg, bulk B2B, 2024-2025)

| Ingredient Category | Low | Mid | High | Notes |
|---|---|---|---|---|
| Water-soluble vitamins (C, B-complex) | $5 | $15 | $50 | Ascorbic acid $5–12; Niacinamide $8–20 |
| Fat-soluble vitamins (D, E, K) | $15 | $80 | $300 | D3 cholecalciferol $25–80; K2 MK-7 $150–400 |
| Minerals (chelated forms) | $10 | $40 | $120 | Magnesium glycinate $20–50; Zinc bisglycinate $30–80 |
| Amino acids | $8 | $25 | $60 | Taurine $8–15; L-Glutamine $10–25 |
| Botanical extracts | $20 | $100 | $500 | Quality varies widely; standardization matters |

## Quality Flags
- USP grade: purity ≥ 99.0% for vitamins, ≥ 98.0% for minerals
- NSF Sport certified: preferred for finished goods sold at retail
- "Food grade" from Chinese manufacturers: verify with CoA; do NOT assume pharma grade
- MOQ < 1 kg: research/lab quantities — not B2B bulk pricing; flag in notes
- MOQ > 1,000 kg: bulk/industrial pricing — may need different logistics

## Lead Time Norms
- China-origin (sea freight): 30–45 days standard; 15–20 days expedited (premium)
- EU-origin (Lonza, DSM, BASF): 14–21 days to US; higher price, better documentation
- US domestic: 3–7 days; premium pricing; useful for compliance-sensitive ingredients

## Red Flags
- Price > 3× category median from a single supplier: verify before alerting
- No country of origin listed: treat as unverified
- Price listed in "per gram" units: convert before comparison (× 1000 for per-kg)
- Web-search prices are indicative only — production volume requires direct RFQ negotiation
```

**CREATE `Orchestration/Data/supplier_wiki/excipients.md`:**

```markdown
# Excipient & Binder Sourcing Guidelines

## Typical Price Ranges (USD/kg, 2024-2025)

| Excipient | Low | Mid | High | Notes |
|---|---|---|---|---|
| Microcrystalline Cellulose (MCC) | $1.5 | $3 | $6 | Commodity; Avicel PH-101/102 standards |
| Magnesium Stearate | $2 | $5 | $12 | Vegetable vs. animal source matters for labeling |
| Silicon Dioxide | $2 | $6 | $15 | Flow agent; fumed vs. precipitated grades |
| Maltodextrin | $0.80 | $1.5 | $3 | Spray-dry carrier; DE10–DE18 most common |
| HPMC (Hydroxypropyl Methylcellulose) | $5 | $12 | $25 | Capsule shells and film coating |
| Stearic Acid | $1 | $3 | $8 | Check Palm-Free sourcing for brand requirements |

## Quality Considerations
- NF/EP grade required for pharmaceutical use; FCC grade sufficient for food supplements
- Particle size distribution matters for tableting performance — verify D50/D90
- Certificate of Analysis (CoA) with heavy metals panel required for supplement-grade

## Lead Times
- Most excipients are commodity materials with domestic US stock available: 3–10 days
- Specialty excipients (modified starches, novel capsule materials): 3–6 weeks
```

**CREATE `Orchestration/Data/supplier_wiki/food.md`:**

```markdown
# Food-Grade Ingredient Sourcing Guidelines

## Typical Price Ranges (USD/kg, 2024-2025)

| Ingredient | Low | Mid | High | Notes |
|---|---|---|---|---|
| Citric Acid | $0.80 | $1.5 | $3 | Commodity; China dominant; watch anti-dumping |
| Sucralose | $50 | $120 | $200 | Spot price volatile; check HFCS pricing as proxy |
| Erythritol | $1.5 | $3 | $6 | Corn-fermented; seasonal variation |
| Stevia (Reb-A 95%) | $8 | $20 | $45 | Spec purity drives price; Reb-D/M more expensive |
| Xanthan Gum | $4 | $8 | $15 | Food/pharma grades; oil & gas grade not acceptable |
| Maltodextrin | $0.80 | $1.5 | $3 | FCC grade standard; check DE value |

## Regulatory Notes
- FCC (Food Chemicals Codex) grade minimum for food use
- Non-GMO verification adds 10–30% premium; verify with IP certification
- Organic certification requires NOP/USDA audit trail back to farm
- Kosher/Halal certification: add 2–5% to cost; requires annual audit
```

- **VALIDATE**: `PYTHONPATH=. python3 -c "from reasoning.supplier_guidelines import get_guidelines; print(get_guidelines('supplement')[:50])"`

---

### TASK 20 (Tier 3): UPDATE `reasoning/supplier_scorer.py` to inject guidelines

- **ADD** `get_guidelines()` call inside `score_suppliers()` and return guidelines text in the result dict
- **PATTERN**: Import `get_guidelines` at function call time (lazy), not at module top (avoid circular import risk)

```python
# In score_suppliers() method, before `results.sort(...)`:
try:
    from reasoning.supplier_guidelines import get_guidelines
    grade_flag = conn.execute(
        "SELECT Grade_Flag FROM Ingredient_Canonical WHERE Id = ?", (canonical_ingredient_id,)
    ).fetchone()
    guidelines = get_guidelines(grade_flag[0] if grade_flag else None)
except Exception:
    guidelines = ""

# In the return statement, add:
results.sort(key=lambda x: x["weighted_score"], reverse=True)
return results  # already returns a list; ADD guidelines to metadata in a wrapper
```

- **GOTCHA**: The `score_suppliers()` method currently returns `list[dict]`. Rather than breaking the existing interface, add a `score_suppliers_with_context()` method that returns `{"suppliers": results, "guidelines": guidelines}`. The existing `score_suppliers()` stays unchanged (used by the scoring router).

```python
def score_suppliers_with_context(self, canonical_ingredient_id: int) -> dict:
    """Like score_suppliers() but also returns grade guidelines for UI context."""
    suppliers = self.score_suppliers(canonical_ingredient_id)
    try:
        from reasoning.supplier_guidelines import get_guidelines
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT Grade_Flag FROM Ingredient_Canonical WHERE Id = ?", (canonical_ingredient_id,)
        ).fetchone()
        conn.close()
        guidelines = get_guidelines(row[0] if row else None)
    except Exception:
        guidelines = ""
    return {"suppliers": suppliers, "guidelines": guidelines}
```

---

### TASK 21: RUN MIGRATION + VALIDATE

```bash
cd "/home/developer/Projects/Spherecast Agnes"

# 1. Run Price_Change_Alert migration
PYTHONPATH=. python3 enrichment/db_migrate_price_monitor.py

# 2. Validate tables created
PYTHONPATH=. python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
tables = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print('Price_Change_Alert:', 'Price_Change_Alert' in tables)
print('All tables:', sorted(tables))
"

# 3. Run supplier web backfill (requires GOOGLE_API_KEY)
PYTHONPATH=. python3 enrichment/backfill_supplier_web.py

# 4. Build frontend
cd orchestration/ui && npm run build && cd ../..

# 5. Start server for API smoke tests
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
```

---

## TESTING STRATEGY

No formal test framework in the project — validate via direct Python imports, print assertions, and curl smoke tests.

### Integration Checks (after server starts at `http://localhost:8000`)

```bash
# Alert count (unread)
curl -s http://localhost:8000/api/alerts/count | python3 -m json.tool
# Expected: {"count": N}

# List alerts
curl -s "http://localhost:8000/api/alerts/" | python3 -m json.tool

# Dismiss alert (replace 1 with actual ID)
curl -s -X POST http://localhost:8000/api/alerts/1/dismiss | python3 -m json.tool

# Ingredient alerts
curl -s http://localhost:8000/api/alerts/ingredient/1 | python3 -m json.tool

# Trigger price_monitor pipeline via API
curl -s -X POST http://localhost:8000/pipelines/run/price_monitor | python3 -m json.tool
# Expected: {"run_id": "..."}

# Check scored suppliers (after backfill)
curl -s http://localhost:8000/api/scoring/suppliers/1 | python3 -m json.tool
# Expected: {"suppliers": [...], "count": N > 0}
```

### Edge Cases

- **`search_sub_agent` returns malformed JSON**: `_parse_suppliers()` regex falls back to `[{"supplier_name": "research_result", "notes": "..."}]` — these are filtered out in `supplier_web_enricher.py` by the `name == "research_result"` guard
- **No `GOOGLE_API_KEY`**: Both `price_fetch_agent.run()` and the enricher return gracefully with `skipped` field — pipeline continues without crashing
- **First run (no stored prices to compare)**: `price_fetch_agent` writes new `Supplier_Commercial` rows but creates 0 alerts (no old price to compare against) — correct behavior
- **Price strings without numbers** (e.g. `"price on request"`): `_parse_price()` returns `None`; row is skipped — no crash
- **Scheduled task when server not started**: Background task only runs when FastAPI is running; no external scheduler dependency

---

## VALIDATION COMMANDS

### Level 1: Python imports

```bash
cd "/home/developer/Projects/Spherecast Agnes"
PYTHONPATH=. python3 -c "from enrichment.enrichers.supplier_web_enricher import SupplierWebEnricher; print('web enricher ok')"
PYTHONPATH=. python3 -c "from orchestration.tools.price_staleness_checker import run; print('staleness tool ok')"
PYTHONPATH=. python3 -c "from orchestration.agents.price_fetch_agent import run; print('fetch agent ok')"
PYTHONPATH=. python3 -c "from orchestration.agents.price_alert_writer import run; print('alert writer ok')"
PYTHONPATH=. python3 -c "from orchestration.api.routes.alerts import router; print([r.path for r in router.routes])"
PYTHONPATH=. python3 -c "from orchestration.api.main import app; print([r.path for r in app.routes if 'alert' in r.path])"
PYTHONPATH=. python3 -c "from orchestration.api.conditions import evaluate; print('conditions ok')"
PYTHONPATH=. python3 -c "from orchestration.api.agent_registry import get_agent, get_tool; get_tool('PriceStalenesCheckerTool'); get_agent('PriceFetchAgent'); get_agent('PriceAlertWriter'); print('registry ok')"
```

### Level 2: DB migration

```bash
PYTHONPATH=. python3 enrichment/db_migrate_price_monitor.py
PYTHONPATH=. python3 -c "
import sqlite3; c = sqlite3.connect('db_enriched.sqlite')
print(c.execute('SELECT COUNT(*) FROM Price_Change_Alert').fetchone())
print(c.execute('SELECT * FROM Scoring_Config').fetchall())
"
```

### Level 3: Frontend build

```bash
cd "/home/developer/Projects/Spherecast Agnes/orchestration/ui"
npm run build 2>&1 | tail -5
# Expected: "built in X.XXs" with zero errors
```

### Level 4: API endpoints (server running)

```bash
curl -s http://localhost:8000/api/alerts/count | python3 -m json.tool
curl -s "http://localhost:8000/api/alerts/" | python3 -m json.tool
curl -s -X POST http://localhost:8000/pipelines/run/price_monitor | python3 -m json.tool
curl -s http://localhost:8000/api/scoring/suppliers/1 | python3 -m json.tool
curl -s http://localhost:8000/health
```

---

## ACCEPTANCE CRITERIA

- [ ] `Price_Change_Alert` table created in `db_enriched.sqlite`
- [ ] `enrichment/backfill_supplier_web.py` runs and populates `Supplier_Commercial` with `Price_Source='google_search'` rows
- [ ] `Suppliers` tab shows non-empty supplier list after backfill
- [ ] `orchestration/pipelines/price_monitor.yaml` loads without error
- [ ] `PriceStalenesCheckerTool`, `PriceFetchAgent`, `PriceAlertWriter` all registered and importable
- [ ] `has_stale_prices` and `has_price_alerts` conditions registered and evaluate correctly
- [ ] `GET /api/alerts/count` returns `{"count": N}`
- [ ] `POST /api/alerts/{id}/dismiss` correctly sets `Dismissed = 1`
- [ ] `POST /pipelines/run/price_monitor` triggers pipeline execution
- [ ] Frontend builds with zero TypeScript errors
- [ ] "Price Alerts" tab visible in sidebar and renders `AlertsView`
- [ ] `AlertsView` shows EmptyState when no alerts, card list when alerts exist
- [ ] Dismiss button updates alert list without page reload
- [ ] Supplier Intelligence Wiki files exist and `get_guidelines()` returns content
- [ ] Tier 3 scheduler starts without error on server boot (no GOOGLE_API_KEY = graceful skip)
- [ ] No regressions in existing tabs (Opportunities, Proposals, Compliance, Ingredients, Suppliers, Runs)

---

## COMPLETION CHECKLIST

- [ ] Task 1: schema/enriched_schema.sql updated with Price_Change_Alert
- [ ] Task 2: db_migrate_price_monitor.py created and run
- [ ] Task 3: supplier_web_enricher.py created
- [ ] Task 4: backfill_supplier_web.py created (run when GOOGLE_API_KEY available)
- [ ] Task 5: price_staleness_checker.py created
- [ ] Task 6: price_fetch_agent.py created
- [ ] Task 7: price_alert_writer.py created
- [ ] Task 8: price_monitor.yaml created
- [ ] Task 9: conditions.py updated with has_stale_prices + has_price_alerts
- [ ] Task 10: agent_registry.py updated
- [ ] Task 11: alerts.py route created
- [ ] Task 12: main.py updated with alerts router
- [ ] Task 13: agnes.ts updated with PriceAlert + AlertCount types
- [ ] Task 14: agnesApi.ts updated with alert methods
- [ ] Task 15: AlertsView.tsx created
- [ ] Task 16: Sidebar.tsx + Index.tsx updated with alerts tab
- [ ] Task 17: main.py lifespan updated with scheduler (Tier 3)
- [ ] Task 18-19: supplier_guidelines.py + wiki markdown files created (Tier 3)
- [ ] Task 20: supplier_scorer.py augmented with score_suppliers_with_context() (Tier 3)
- [ ] Task 21: migration run, backfill run, frontend built, server smoke-tested

---

## NOTES

**Supplier_Commercial PK constraint**: The primary key is `(SupplierId, CanonicalIngredientId)` — `INSERT OR REPLACE` will overwrite an existing row for the same supplier × ingredient pair. This is intentional: re-running the backfill updates prices in place. `Price_Change_Alert` stores the historical diff before the overwrite.

**search_sub_agent isolation**: `google_search` tool CANNOT be mixed with other tools in the same `LlmAgent`. `price_fetch_agent.py` calls `search_sub_agent.search()` as a coroutine, not via ADK tool registration — this is correct. Never pass `google_search` to `price_fetch_agent`'s `LlmAgent.tools`.

**`price_fetch_agent` has no LlmAgent**: It's registered as an agent class in the DAG registry but contains no LLM call itself — it's pure Python logic calling `search_sub_agent`. This is an intentional architecture choice: agents can be Python logic runners, not just LLM callers. The `_adk_runner.py` is only needed for `price_alert_writer.py`.

**Price comparison first-run behavior**: On the first enrichment run, all `Supplier_Commercial` rows are new (no previous price to compare). `price_fetch_agent` will write 0 `Price_Change_Alert` rows on the first run — correct. Alerts start appearing on the second+ run. Consider seeding the wiki with expected price ranges (Tier 3) to enable day-one alerting against known benchmarks.

**Web search price reliability**: Google Search results include retailer pages, forum posts, and outdated catalogs. `Confidence=0.65` (vs. Molport's `0.70`) signals this uncertainty. Always label web-search prices as "indicative" in narratives (already in `price_alert_writer` system prompt).

**Scheduled trigger type**: `trigger: scheduled` is a new value not currently handled by `pipeline_loader.py` or `dag_executor.py`. Since `trigger` is only stored in the `Pipeline` dataclass for documentation, no code change is needed — the pipeline executes identically regardless of trigger value. The scheduled trigger can also be run on-demand via `POST /pipelines/run/price_monitor` or via chat ("check current prices for Vitamin C").

**LLM Wiki → future extension**: The Tier 3 wiki is intentionally simple (static markdown files). A future enhancement would wire a `WikiUpdateAgent` that receives `price_alert_writer` output and updates the relevant wiki file with a new price benchmark entry — closing the LLWiki loop. This is not in scope for this plan but the directory structure and `get_guidelines()` loader are designed to support it.
