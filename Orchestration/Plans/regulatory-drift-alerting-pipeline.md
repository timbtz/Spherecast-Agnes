# Feature: Regulatory Drift Alerting & Proactive Pipeline

---

## PRODUCT INTENT & CONTEXT

Agnes is a CPG supplement procurement intelligence platform. One of its core value propositions is **proactive regulatory compliance monitoring**: instead of waiting for a formulator to discover that an FDA inactive ingredient limit changed, Agnes automatically ingests quarterly FDA IID change logs, cross-references them against the portfolio's canonical ingredient set, and surfaces prioritised alerts with supplier alternatives and an AI-generated executive narrative.

**Why this matters:** The FDA publishes quarterly corrections (C), deletions (D), and revisions (R) to the Inactive Ingredient Database. Supplement brands using excipients or carriers that appear in that log may be sourcing ingredients at doses that are now out-of-compliance — without knowing it. Agnes surfaces this proactively, with enough context to act: what changed, which products are affected, what alternatives exist.

**User:** Supply chain analyst / procurement manager at a CPG supplement brand. They don't monitor the FDA website manually. Agnes does it for them.

---

## CURRENT STATUS (as of 2026-04-18)

### ✅ FULLY IMPLEMENTED — CODE COMPLETE

All files have been created. The full pipeline, tool, agent, API, and condition chain is wired.

| Component | File | Status |
|---|---|---|
| DB migration | `enrichment/db_migrate_iid_changelog.py` | ✅ Created + run |
| CSV loader | `enrichment/sources/fda_iid_changelog.py` | ✅ Created + run |
| Backfill runner | `enrichment/backfill_iid_changelog.py` | ✅ Created + run |
| Drift detection tool | `orchestration/tools/regulatory_drift_tool.py` | ✅ Created |
| Research agent | `orchestration/agents/regulatory_research_agent.py` | ✅ Created |
| Narrative agent | `orchestration/agents/regulatory_drift_agent.py` | ✅ Created |
| Pipeline YAML | `orchestration/pipelines/regulatory_drift_alert.yaml` | ✅ Created |
| Condition guard | `has_regulatory_drift` in `conditions.py` | ✅ Registered |
| Agent registry | `agent_registry.py` | ✅ RegulatoryDriftTool, RegulatoryResearchAgent, RegulatoryDriftAgent all registered |
| API endpoint | `GET /api/data/regulatory-alerts` in `routes/data.py` | ✅ Added |
| Opportunity ranker | `opportunity_ranker.py` | ✅ Returns `regulatory_drift_flag` + `regulatory_drift_reason` |
| DB columns | `Consolidation_Opportunity.regulatory_drift_flag/reason` | ✅ Exist |

### ✅ DATA LOADED

- `FDA_IID_Change_Log`: **187 rows** loaded from `Orchestration/Data/api/Change_Log_Data.csv`
- **27 rows** matched to canonical ingredients (fuzzy + exact name matching)
- Status breakdown: 36 C (Corrected), 83 D (Deleted), 68 R (Revised) — Q1/Q2 2026 snapshot

### 🔴 NOT YET RUN (pipeline execution pending)

- `regulatory_drift_alert` pipeline has **never been triggered** → 0 opportunities flagged for regulatory drift
- `Consolidation_Opportunity.regulatory_drift_flag` is 0 for all rows (column exists, not populated)
- The `RegulatoryDriftAgent` has not produced any narratives yet

### ❓ WHAT STILL NEEDS TO BE DONE

1. **Run the pipeline** to populate drift flags and generate the first alert narrative:
   ```bash
   curl -X POST http://localhost:8001/pipelines/run/regulatory_drift_alert \
     -H "Content-Type: application/json" -d '{}'
   ```
   Then poll `GET /runs/{run_id}` until `status: completed`.

2. **Verify match quality** — 27/187 rows matched is expected (pharma excipients vs. supplement canonicals). Check which 27 matched:
   ```sql
   SELECT cl.IngredientName, ic.Name, cl.Status, cl.MatchMethod
   FROM FDA_IID_Change_Log cl
   JOIN Ingredient_Canonical ic ON ic.Id = cl.CanonicalIngredientId
   ORDER BY cl.Status;
   ```

3. **Surface alerts in the UI** — A dedicated "Regulatory Alerts" tab is not yet in the Sidebar. Currently the alerts are accessible via:
   - `GET /api/data/regulatory-alerts` (works)
   - The `regulatory_drift_flag` field in the Opportunities tab (rendered after `opportunity_ranker` integration)
   
   **Intent:** Add a "Regulatory" tab to the Sidebar (similar to Price Alerts) that shows the `/api/data/regulatory-alerts` data with severity badges, before/after MDE comparisons, and a "run pipeline" CTA.

4. **Live FDA fetch** — `RegulatoryResearchAgent` is wired but the live web-fetch path hasn't been exercised. Requires `GOOGLE_API_KEY`. If it fails (FDA changes URL), the pipeline still works from the static CSV baseline.

5. **Schema SQL documentation** — `schema/enriched_schema.sql` may not yet document `FDA_IID_Change_Log` and the new `Consolidation_Opportunity` columns. Update it.

6. **Expand match coverage** — 27 matches out of 135 unique change IDs. Consider adding more supplement-focused synonyms to the fuzzy match. Some misses: if the canonical name is "Vitamin C" but the FDA log says "ASCORBIC ACID", the fuzzy match may miss at threshold 80. A synonym table or lowering the threshold for well-known ingredient pairs could improve coverage.

---

## ORIGINAL PLAN — IMPLEMENTATION REFERENCE

---

## Feature Description

Integrate the FDA Inactive Ingredient Database quarterly change log (`Change_Log_Data.csv`) into the Agnes enrichment database, then build a full pipeline that detects regulatory drift against our canonical ingredient set, surfaces high-priority alerts, optionally fetches fresh change data live from the FDA website via a research sub-agent, and automatically flags affected consolidation opportunities. The pipeline is triggered by `data_update` events and produces an executive narrative of what changed and what actions to take.

## User Story

As a supply chain analyst using Agnes,
I want to be automatically alerted when FDA inactive ingredient limits for my portfolio ingredients have been corrected, deleted, or revised,
So that I can proactively adjust formulations, sourcing strategies, and compliance posture before regulatory risk materialises.

## Problem Statement

The FDA publishes quarterly change logs to its Inactive Ingredient Database. Agnes currently holds a static snapshot of IIR_OCOMM.csv (9,067 rows) but has no mechanism to detect when limits for matched canonical ingredients have been corrected (Status=C), deleted (Status=D), or revised (Status=R). Procurement and compliance decisions may be based on stale FDA limits without any alert surface.

## Solution Statement

1. **Ingest** `Change_Log_Data.csv` into a new `FDA_IID_Change_Log` table, matching rows to canonical ingredients by name.
2. **Detect drift** via a new deterministic tool that pairs before/after snapshot rows, computes severity, and cross-references against Consolidation_Opportunity.
3. **Fetch live updates** via a research sub-agent that searches for the latest FDA quarterly change log and ingests new rows.
4. **Surface alerts** via a new pipeline and API endpoint; flag affected opportunities in the DB.
5. **Integrate** the drift flag into the existing opportunity_ranker so ProactiveAgent proposals include regulatory context.

## Feature Metadata

**Feature Type**: New Capability  
**Estimated Complexity**: High  
**Primary Systems Affected**: enrichment layer, orchestration tools, orchestration agents, pipeline YAML, API routes, schema  
**Dependencies**: rapidfuzz (already in project for substitution_graph), sqlite3, google ADK (for research agent), search_sub_agent pattern

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `enrichment/sources/fda_iid.py` (full file, 89 lines) — **Mirror this exactly** for CSV loading pattern: `encoding='utf-8-sig'`, `INSERT OR IGNORE`, UNII→canonical lookup map, Enrichment_Run_Log write, `ROOT / "Orchestration" / "Data" / "api"` CSV path constant
- `enrichment/db_migrate_fda_scoring.py` (full file) — **Mirror this exactly** for migration pattern: `CREATE TABLE IF NOT EXISTS`, `_add_col()` with `PRAGMA table_info()` guard, `INSERT OR IGNORE` for defaults
- `enrichment/db_migrate_v11.py` (full file) — Alternative `_add_col()` implementation; check which version is more current and mirror it
- `orchestration/api/conditions.py` (full file, 61 lines) — Read entire file; add new guard here and to `_REGISTRY` dict
- `orchestration/tools/opportunity_ranker.py` (full file, 54 lines) — Read and modify this; add LEFT JOIN to FDA_IID_Change_Log
- `orchestration/agents/proactive_agent.py` (full file, 52 lines) — Mirror this pattern for RegulatoryDriftAgent: LlmAgent + run_adk_agent + GOOGLE_API_KEY guard + ctx.get() pattern
- `orchestration/agents/research_agent.py` (full file, 89 lines) — **Primary pattern to mirror** for RegulatoryResearchAgent: search_sub_agent usage, Agent_Log writes, DB path, JSON extraction from LLM output
- `orchestration/agents/_adk_runner.py` — Read to understand `run_adk_agent(agent, payload, run_id)` signature
- `orchestration/agents/search_sub_agent.py` — Read to understand `search(query, query_hint)` call signature
- `orchestration/api/routes/data.py` (full file, 157 lines) — Add new endpoint here; mirror read-only SQLite connect pattern (`sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)`) and `sqlite3.Row` row_factory
- `orchestration/api/routes/scoring.py` — Verify `_DB` path constant (`Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"`) — confirm it is still correct; mirror for data.py endpoint
- `orchestration/api/main.py` — Verify data.router is still included; confirm no change needed
- `orchestration/pipelines/proactive_consolidation.yaml` — Read current state; understand trigger and node structure before deciding whether to add a cross-reference node or rely on opportunity_ranker change alone
- `orchestration/pipelines/supplier_fallout.yaml` — Reference for 4-node pipeline with condition guards
- `reasoning/substitution_graph.py` — Find rapidfuzz import and fuzzy threshold used (≥85); mirror that threshold or use ≥80 for name matching

### Data Files — READ THESE

- `Orchestration/Data/api/Change_Log_Data.csv` — **Verified structure**:
  - 187 data rows, 9 columns, UTF-8 BOM header (`encoding='utf-8-sig'`)
  - Columns: `Change ID`, `Snapshot Date`, `Inactive Ingredient`, `Route of Administration`, `Dosage Form`, `Maximum Potency per Unit Dose`, `Maximum Daily Exposure`, `Maximum Daily Exposure UOM`, `Status`
  - Status values: `C`=36 rows (Corrected — before/after pairs), `D`=83 rows (Deleted — Q1 only, no Q2), `R`=68 rows (Revised/MDE replacement)
  - Snapshot Dates: `Q1 2026`, `Q2 2026`
  - 135 unique Change IDs; Status=C rows appear in BOTH Q1 and Q2 (before/after); Status=D rows appear in Q1 only
  - **No UNII column** — canonical matching must be by ingredient name
  - MaxPotencyPerUnit and MaxDailyExposure are mixed-type text (numeric, `%w/v`, `NA`, blank) — store as TEXT not REAL

### New Files to Create

- `enrichment/db_migrate_iid_changelog.py` — idempotent migration: creates `FDA_IID_Change_Log` table; adds `regulatory_drift_flag` and `regulatory_drift_reason` columns to `Consolidation_Opportunity`
- `enrichment/sources/fda_iid_changelog.py` — CSV loader + name-based canonical matching with fuzzy fallback
- `enrichment/backfill_iid_changelog.py` — top-level runner: runs migration then loads CSV; callable as `python enrichment/backfill_iid_changelog.py`
- `orchestration/tools/regulatory_drift_tool.py` — deterministic tool: pairs C-status rows, assigns severity, cross-references opportunities
- `orchestration/agents/regulatory_research_agent.py` — async ADK agent: searches for latest FDA quarterly change log, attempts to parse and ingest new rows
- `orchestration/agents/regulatory_drift_agent.py` — async ADK agent: generates executive narrative + writes `regulatory_drift_flag` to Consolidation_Opportunity
- `orchestration/pipelines/regulatory_drift_alert.yaml` — new pipeline definition

### Files to Modify

- `orchestration/api/conditions.py` — add `has_regulatory_drift` function and registry entry
- `orchestration/tools/opportunity_ranker.py` — add LEFT JOIN to `FDA_IID_Change_Log` and `regulatory_drift_flag` field in output
- `orchestration/api/routes/data.py` — add `GET /api/data/regulatory-alerts` endpoint
- `schema/enriched_schema.sql` — document new table and new columns (documentation only, no execution)

### Patterns to Follow

**DB Path constant in tools:**
```python
# From orchestration/tools/compliance_reasoner_tool.py — verify this is still the pattern
import sqlite3
from pathlib import Path
# DB accessed via ctx.enriched_db_path
conn = sqlite3.connect(str(ctx.enriched_db_path))
```
Verify `AgnesContext` still has `enriched_db_path` attribute by reading `orchestration/api/agnes_context.py`.

**Migration idempotency pattern** (from `enrichment/db_migrate_fda_scoring.py`):
```python
conn.execute("CREATE TABLE IF NOT EXISTS ...")
conn.execute("CREATE INDEX IF NOT EXISTS ...")
# Column additions:
existing = {r[1] for r in conn.execute("PRAGMA table_info(TableName)")}
if "new_col" not in existing:
    conn.execute("ALTER TABLE TableName ADD COLUMN new_col TYPE DEFAULT val")
```

**CSV loading pattern** (from `enrichment/sources/fda_iid.py`):
```python
ROOT = Path(__file__).parent.parent.parent
CSV_DIR = ROOT / "Orchestration" / "Data" / "api"
with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader: ...
```

**Condition guard pattern** (from `orchestration/api/conditions.py`):
```python
def has_regulatory_drift(ctx: AgnesContext) -> bool:
    out = ctx.get("scan-drift", {})
    return bool(out.get("drift_alerts"))
# Then add to _REGISTRY dict: "has_regulatory_drift": has_regulatory_drift
```

**Sync tool pattern** (from `orchestration/tools/opportunity_ranker.py`):
```python
def run(ctx: AgnesContext) -> dict:
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row
    ...
    conn.close()
    return { ... }
```

**Async agent pattern** (from `orchestration/agents/proactive_agent.py`):
```python
async def run(ctx: AgnesContext) -> dict:
    data = ctx.get("upstream-node", {})
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"skipped": "GOOGLE_API_KEY not set"}
    payload = json.dumps(data, indent=2)
    result = await run_adk_agent(_AGENT, payload, ctx.run_id)
    return {...}
```

**Pipeline YAML structure** (from `orchestration/pipelines/proactive_consolidation.yaml` — verify current format):
```yaml
name: regulatory_drift_alert
trigger: data_update
nodes:
  - id: fetch-latest-changes
    agent_class: RegulatoryResearchAgent
  - id: scan-drift
    tool_class: RegulatoryDriftTool
    depends_on: [fetch-latest-changes]
  - id: find-alternatives
    tool_class: SupplierAlternativesTool
    depends_on: [scan-drift]
    when: has_regulatory_drift
  - id: write-alerts
    agent_class: RegulatoryDriftAgent
    depends_on: [scan-drift, find-alternatives]
    when: has_regulatory_drift
```

**API read-only endpoint pattern** (from `orchestration/api/routes/data.py` — verify `_DB` path and connection pattern before implementing):
```python
router = APIRouter()  # or APIRouter(prefix=...) — check existing prefix in data.py
@router.get("/api/data/regulatory-alerts")
def get_regulatory_alerts():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    ...
    conn.close()
    return {...}
```

**Tool/Agent registration** — verify current `get_tool()` and `get_agent()` registries by reading `orchestration/api/dag_executor.py` or wherever these registries live. The new tool class name `RegulatoryDriftTool` and agent class names `RegulatoryResearchAgent`, `RegulatoryDriftAgent` must be registered there.

**rapidfuzz import** — check `reasoning/substitution_graph.py` for exact import: likely `from rapidfuzz import fuzz, process`. Use `fuzz.token_sort_ratio(a, b) >= 80` for name matching (slightly lower threshold than substitution graph's 85 since ingredient names in the change log use FDA naming conventions which may differ from canonical names).

---

## IMPLEMENTATION PLAN

### Phase 1: Schema & Data Ingestion Foundation

Create the `FDA_IID_Change_Log` table with proper idempotency, add two new columns to `Consolidation_Opportunity`, and load the static CSV. This is a prerequisite for all downstream phases.

**Tasks:**
- Migration script with `CREATE TABLE IF NOT EXISTS` + column additions
- CSV loader with name-based canonical matching (no UNII available)
- Top-level backfill runner

### Phase 2: Drift Detection Tool & Condition Guard

The synchronous tool queries the change log, pairs before/after snapshot rows for Status=C, computes severity, and cross-references with consolidation opportunities. The condition guard gates downstream nodes.

**Tasks:**
- `RegulatoryDriftTool` with severity logic
- `has_regulatory_drift` condition guard + registry entry

### Phase 3: Research Sub-Agent (Live FDA Fetch)

An async ADK agent that searches for the latest FDA quarterly change log, attempts to download/parse it, and ingests new rows into `FDA_IID_Change_Log`. Handles failure gracefully (returns what it found even if download fails).

**Tasks:**
- `RegulatoryResearchAgent` with search_sub_agent integration
- Ingest logic that deduplicates via UNIQUE constraint

### Phase 4: Regulatory Drift Agent (Narrative + DB Write)

An async ADK agent that receives drift alerts + alternatives and produces an executive narrative. Also writes `regulatory_drift_flag=1` to affected `Consolidation_Opportunity` rows.

**Tasks:**
- `RegulatoryDriftAgent` with Gemini 2.5-flash
- SQLite write pattern for flagging opportunities (writable connection, not read-only)

### Phase 5: Pipeline & Condition Registration

Wire all components into a pipeline YAML. Register the new tool and agents in the DAG executor's registries. Register the condition guard.

**Tasks:**
- `regulatory_drift_alert.yaml` pipeline definition
- Register `RegulatoryDriftTool`, `RegulatoryResearchAgent`, `RegulatoryDriftAgent` in registries

### Phase 6: API Endpoint & Opportunity Ranker Integration

Surface drift alerts via API and enrich the existing opportunity_ranker output with drift flags so ProactiveAgent proposals automatically include regulatory context.

**Tasks:**
- `GET /api/data/regulatory-alerts` endpoint in `routes/data.py`
- LEFT JOIN in `opportunity_ranker.py` to include `regulatory_drift_flag`

---

## STEP-BY-STEP TASKS

### Task 1.1 — CREATE `enrichment/db_migrate_iid_changelog.py`

- **IMPLEMENT**: Idempotent migration that:
  1. Creates `FDA_IID_Change_Log` table with `UNIQUE(ChangeId, SnapshotDate, Route, DosageForm)` constraint (prevents duplicate ingestion on re-run)
  2. Creates indices on `CanonicalIngredientId` and `Status`
  3. Adds `regulatory_drift_flag INTEGER DEFAULT 0` to `Consolidation_Opportunity` if not exists
  4. Adds `regulatory_drift_reason TEXT` to `Consolidation_Opportunity` if not exists
- **PATTERN**: `enrichment/db_migrate_fda_scoring.py` — mirror `CREATE TABLE IF NOT EXISTS`, `_add_col()` helper, `PRAGMA journal_mode=WAL`
- **SCHEMA** for `FDA_IID_Change_Log`:
  ```sql
  CREATE TABLE IF NOT EXISTS FDA_IID_Change_Log (
      Id                    INTEGER PRIMARY KEY AUTOINCREMENT,
      ChangeId              INTEGER NOT NULL,
      SnapshotDate          TEXT NOT NULL,
      IngredientName        TEXT NOT NULL,
      Route                 TEXT,
      DosageForm            TEXT,
      MaxPotencyPerUnit     TEXT,
      MaxDailyExposure      TEXT,
      MaxDailyExposureUOM   TEXT,
      Status                TEXT NOT NULL CHECK(Status IN ('C','D','R')),
      CanonicalIngredientId INTEGER,
      MatchMethod           TEXT,
      MatchScore            REAL,
      IngestedAt            TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
      UNIQUE(ChangeId, SnapshotDate, Route, DosageForm)
  );
  CREATE INDEX IF NOT EXISTS idx_iid_cl_canonical ON FDA_IID_Change_Log(CanonicalIngredientId);
  CREATE INDEX IF NOT EXISTS idx_iid_cl_status    ON FDA_IID_Change_Log(Status);
  CREATE INDEX IF NOT EXISTS idx_iid_cl_changeid  ON FDA_IID_Change_Log(ChangeId);
  ```
- **IMPORTS**: `sqlite3`, `logging`, `pathlib.Path`
- **GOTCHA**: `Consolidation_Opportunity` has no UNIQUE on CanonicalIngredientId; previous migration scripts have handled this pattern (see `_add_col()` in `db_migrate_v11.py`). Read that file's `_add_col()` exactly and copy it.
- **VALIDATE**: `python enrichment/db_migrate_iid_changelog.py && python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'FDA_IID_Change_Log\'').fetchone())"`

### Task 1.2 — CREATE `enrichment/sources/fda_iid_changelog.py`

- **IMPLEMENT**: `load_iid_changelog(db_path=ENRICHED_DB) -> int` function that:
  1. Opens `Orchestration/Data/api/Change_Log_Data.csv` with `encoding='utf-8-sig'`
  2. Builds a name→canonical_id lookup from `Ingredient_Canonical` (lowercased Name)
  3. Also builds UNII-based lookup as secondary (change log has no UNII but we can try CAS → UNII → canonical as a bonus if we have time; skip if adds complexity)
  4. For each CSV row:
     - Try exact lowercase match: `name_map.get(row["Inactive Ingredient"].strip().lower())`
     - If no match: try rapidfuzz `process.extractOne(name, name_map.keys(), scorer=fuzz.token_sort_ratio, score_cutoff=80)` — if found, use it with `MatchMethod='fuzzy'` and `MatchScore=score`
     - If exact match: `MatchMethod='exact'`, `MatchScore=1.0`
     - Execute `INSERT OR IGNORE INTO FDA_IID_Change_Log (ChangeId, SnapshotDate, IngredientName, Route, DosageForm, MaxPotencyPerUnit, MaxDailyExposure, MaxDailyExposureUOM, Status, CanonicalIngredientId, MatchMethod, MatchScore) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  5. Commit once after all rows
  6. Log matched count and write `Enrichment_Run_Log` row
  7. Return count of rows processed
- **PATTERN**: Mirror `enrichment/sources/fda_iid.py` exactly — same ROOT/CSV_DIR constants, same `conn.execute("PRAGMA journal_mode=WAL")`, same `Enrichment_Run_Log` insert
- **IMPORTS**: `csv`, `sqlite3`, `logging`, `pathlib.Path`, `rapidfuzz.fuzz`, `rapidfuzz.process`
- **GOTCHA**: CSV column names have spaces — use exact column names: `row["Change ID"]`, `row["Snapshot Date"]`, `row["Inactive Ingredient"]`, `row["Route of Administration"]`, `row["Dosage Form"]`, `row["Maximum Potency per Unit Dose"]`, `row["Maximum Daily Exposure"]`, `row["Maximum Daily Exposure UOM"]`, `row["Status"]`
- **GOTCHA**: rapidfuzz `process.extractOne` returns `(match, score, key)` in newer versions or `(match, score)` — verify import signature from `reasoning/substitution_graph.py`
- **GOTCHA**: Store MaxPotencyPerUnit and MaxDailyExposure as TEXT (values like `"0.30 mg"`, `"NA"`, `""` exist — they are NOT pure floats)
- **VALIDATE**: `python enrichment/sources/fda_iid_changelog.py && python3 -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*), SUM(CASE WHEN CanonicalIngredientId IS NOT NULL THEN 1 END) FROM FDA_IID_Change_Log').fetchone())"`

### Task 1.3 — CREATE `enrichment/backfill_iid_changelog.py`

- **IMPLEMENT**: Simple top-level script that:
  1. Calls `db_migrate_iid_changelog.migrate()`
  2. Calls `fda_iid_changelog.load_iid_changelog()`
  3. Prints summary
- **PATTERN**: Look at any existing top-level backfill script (e.g. `enrichment/backfill_openfda.py`) for the `if __name__ == "__main__"` + `logging.basicConfig` pattern
- **IMPORTS**: local migration and source modules
- **VALIDATE**: `python enrichment/backfill_iid_changelog.py` — should print row count and match count

### Task 2.1 — CREATE `orchestration/tools/regulatory_drift_tool.py`

- **IMPLEMENT**: Sync `def run(ctx: AgnesContext) -> dict` that:
  1. Opens `ctx.enriched_db_path` read-only (`sqlite3.connect(str(ctx.enriched_db_path))`)  
  2. Queries all change log rows with a matched canonical:
     ```sql
     SELECT cl.ChangeId, cl.SnapshotDate, cl.IngredientName, cl.Route,
            cl.DosageForm, cl.MaxPotencyPerUnit, cl.MaxDailyExposure,
            cl.MaxDailyExposureUOM, cl.Status, cl.CanonicalIngredientId,
            ic.Name AS canonical_name,
            co.Id AS opportunity_id, co.Consolidation_Score
     FROM FDA_IID_Change_Log cl
     JOIN Ingredient_Canonical ic ON ic.Id = cl.CanonicalIngredientId
     LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = cl.CanonicalIngredientId
     ORDER BY cl.ChangeId, cl.SnapshotDate
     ```
  3. Build drift_alerts list:
     - **Status D** (Deleted): single row, severity=`"HIGH"`, summary=`"{name} ({route}/{form}) was DELETED from FDA IID Q1→Q2 2026"`
     - **Status C** (Corrected): group Q1 and Q2 rows by ChangeId; if Q2 MaxDailyExposure < Q1 MaxDailyExposure → severity=`"HIGH"` (more restrictive); if ingredient name changed (Q1 vs Q2) → severity=`"MEDIUM"`; else severity=`"LOW"`; summary=`"{name}: MDE corrected {old}→{new} {uom}"`
     - **Status R** (Revised): severity=`"MEDIUM"`, summary=`"{name} ({route}/{form}) was REVISED in Q2 2026"`
  4. Return:
     ```python
     {
         "drift_alerts": alerts_list,   # list of dicts, sorted by severity HIGH→MED→LOW
         "canonical_id": top_alert["canonical_id"] if alerts_list else None,  # for downstream SupplierAlternativesTool
         "count": len(alerts_list),
         "high_severity_count": sum(1 for a in alerts_list if a["severity"] == "HIGH"),
     }
     ```
  Each alert dict:
  ```python
  {
      "canonical_id": int,
      "ingredient_name": str,
      "change_id": int,
      "status": "C" | "D" | "R",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "change_summary": str,
      "route": str,
      "dosage_form": str,
      "q1_mde": str | None,
      "q2_mde": str | None,
      "has_opportunity": bool,
      "opportunity_id": int | None,
      "consolidation_score": float | None,
  }
  ```
- **PATTERN**: `orchestration/tools/opportunity_ranker.py` — exact same `run(ctx)` signature, `conn.row_factory = sqlite3.Row`, `conn.close()` pattern
- **IMPORTS**: `sqlite3`, `orchestration.api.agnes_context.AgnesContext`
- **GOTCHA**: MaxDailyExposure is stored as TEXT (e.g. `"1600"`, `"1080"`, `"NA"`, `""`). Convert to float with try/except for severity comparison. If either is `"NA"` or blank, fall back to severity MEDIUM for Status C.
- **GOTCHA**: For Status D rows, no Q2 row exists — detect as single-row group where SnapshotDate == "Q1 2026" and Status == "D"
- **GOTCHA**: Multiple rows in FDA_IID_Change_Log can share the same CanonicalIngredientId (different routes/forms) — deduplicate by canonical_id in the output but keep ALL alert details
- **VALIDATE**: `python3 -c "from orchestration.tools.regulatory_drift_tool import run; from unittest.mock import MagicMock; ctx=MagicMock(); ctx.enriched_db_path='db_enriched.sqlite'; print(run(ctx))"`

### Task 2.2 — UPDATE `orchestration/api/conditions.py`

- **ADD** after the last condition function (before `_REGISTRY`):
  ```python
  def has_regulatory_drift(ctx: AgnesContext) -> bool:
      out = ctx.get("scan-drift", {})
      return bool(out.get("drift_alerts"))
  ```
- **ADD** to `_REGISTRY` dict: `"has_regulatory_drift": has_regulatory_drift`
- **VALIDATE**: `python3 -c "from orchestration.api.conditions import evaluate; from unittest.mock import MagicMock; ctx=MagicMock(); ctx.node_outputs={'scan-drift': {'drift_alerts': [{'severity': 'HIGH'}]}}; ctx.get=lambda k, d={}: ctx.node_outputs.get(k, d); print(evaluate('has_regulatory_drift', ctx))"`

### Task 3.1 — CREATE `orchestration/agents/regulatory_research_agent.py`

- **IMPLEMENT**: Async `async def run(ctx: AgnesContext) -> dict` that:
  1. Guard: `if not os.environ.get("GOOGLE_API_KEY"): return {"skipped": "GOOGLE_API_KEY not set", "new_rows_ingested": 0}`
  2. Use `search_sub_agent.search("FDA Inactive Ingredient Database quarterly change log 2026 site:fda.gov", query_hint="CSV download quarterly IID changes")` to find the latest change log URL
  3. Pass search results to LlmAgent (gemini-2.5-flash) with instruction to extract: the direct CSV download URL, the snapshot date (quarter + year), and a list of ingredient names that appear in the change log
  4. Parse JSON response from agent (mirror research_agent.py regex fallback pattern)
  5. If a download URL is found: attempt `urllib.request.urlretrieve(url, tmp_path)` or `requests.get(url)` — wrap in try/except, graceful failure
  6. If download succeeded: call `fda_iid_changelog.load_iid_changelog(db_path=ctx.enriched_db_path, csv_path=tmp_path)` — note this requires `load_iid_changelog` to accept optional `csv_path` param (add it in Task 1.2)
  7. Return:
     ```python
     {
         "search_completed": True,
         "download_url_found": bool,
         "new_rows_ingested": int,
         "snapshot_date": str | None,
         "raw_summary": str,
     }
     ```
- **PATTERN**: Mirror `orchestration/agents/research_agent.py` exactly — `load_dotenv()`, `LlmAgent(name=..., model="gemini-2.5-flash", instruction=...)`, `run_adk_agent(_AGENT, payload, ctx.run_id)`, same `Agent_Log` write if needed, same JSON regex extraction
- **IMPORTS**: `json`, `os`, `re`, `urllib.request` (stdlib), `dotenv.load_dotenv`, `google.adk.agents.LlmAgent`, `orchestration.agents._adk_runner.run_adk_agent`, `orchestration.agents.search_sub_agent` (check exact import path), `orchestration.api.agnes_context.AgnesContext`
- **GOTCHA**: The FDA IID change log is published quarterly at https://www.fda.gov/drugs/drug-approvals-and-databases/quarterly-inactive-ingredient-database-iid-change-log — agent should be instructed to look for a downloadable CSV link on that page
- **GOTCHA**: If download fails or URL not found, the pipeline must still continue gracefully — `scan-drift` will then work with whatever is already in `FDA_IID_Change_Log`. Return `new_rows_ingested: 0` rather than raising.
- **GOTCHA**: Verify `search_sub_agent` import path from `orchestration/agents/research_agent.py` before implementing
- **VALIDATE**: `PYTHONPATH=. python3 -c "import asyncio; from orchestration.agents.regulatory_research_agent import run; from unittest.mock import MagicMock; ctx=MagicMock(); ctx.enriched_db_path='db_enriched.sqlite'; ctx.run_id='test'; print(asyncio.run(run(ctx)))"`

### Task 4.1 — CREATE `orchestration/agents/regulatory_drift_agent.py`

- **IMPLEMENT**: Async `async def run(ctx: AgnesContext) -> dict` that:
  1. Reads `ctx.get("scan-drift", {})` for `drift_alerts` and counts
  2. Reads `ctx.get("find-alternatives", {})` for alternatives to the top-affected canonical
  3. Guard: `if not drift_alerts: return {"alerts_narrative": None, "count": 0}`
  4. Guard: `if not os.environ.get("GOOGLE_API_KEY"): return {"skipped": "GOOGLE_API_KEY not set"}`
  5. Build payload JSON with drift_alerts + alternatives
  6. Call `run_adk_agent(_AGENT, payload, ctx.run_id)` — agent instruction:
     ```
     You are Agnes, an AI supply chain compliance advisor.
     You receive a list of FDA Inactive Ingredient Database regulatory changes
     affecting ingredients in a supplement company's supply chain.
     
     For each HIGH severity alert produce:
     - One-sentence headline: "[Ingredient] FDA limit [DELETED/CORRECTED from X to Y mg]"
     - Compliance risk: what this means for products using this ingredient
     - Recommended action: re-qualify supplier, reformulate, or request new CoA
     - If alternatives are available: "Consider switching to [alternative]"
     
     For MEDIUM/LOW alerts: one line each.
     Flag data gaps. Total narrative ≤ 300 words.
     ```
  7. **WRITE drift flags to DB** (after LLM call, before return):
     ```python
     conn = sqlite3.connect(str(ctx.enriched_db_path))  # writable, not read-only
     conn.execute("PRAGMA journal_mode=WAL")
     for alert in drift_alerts:
         if alert.get("opportunity_id"):
             conn.execute(
                 "UPDATE Consolidation_Opportunity SET regulatory_drift_flag=1, regulatory_drift_reason=? WHERE Id=?",
                 (f"{alert['status']}: {alert['change_summary']}", alert["opportunity_id"])
             )
     conn.commit()
     conn.close()
     ```
  8. Return:
     ```python
     {
         "alerts_narrative": narrative_text,
         "drift_count": len(drift_alerts),
         "high_severity_count": ctx.get("scan-drift", {}).get("high_severity_count", 0),
         "opportunities_flagged": count_of_flagged,
     }
     ```
- **PATTERN**: Mirror `orchestration/agents/proactive_agent.py` for LlmAgent + run_adk_agent. The writable DB write pattern comes from `orchestration/agents/research_agent.py` (which writes to Agent_Log).
- **IMPORTS**: `json`, `os`, `sqlite3`, `dotenv.load_dotenv`, `google.adk.agents.LlmAgent`, `orchestration.agents._adk_runner.run_adk_agent`, `orchestration.api.agnes_context.AgnesContext`
- **VALIDATE**: `PYTHONPATH=. python3 -c "import asyncio; from orchestration.agents.regulatory_drift_agent import run; from unittest.mock import MagicMock; ctx=MagicMock(); ctx.node_outputs={'scan-drift': {'drift_alerts': [], 'high_severity_count': 0}, 'find-alternatives': {}}; ctx.get=lambda k, d={}: ctx.node_outputs.get(k, d); ctx.enriched_db_path='db_enriched.sqlite'; ctx.run_id='test'; print(asyncio.run(run(ctx)))"`

### Task 5.1 — CREATE `orchestration/pipelines/regulatory_drift_alert.yaml`

- **VERIFY FIRST**: Read current YAML format from `orchestration/pipelines/proactive_consolidation.yaml` — confirm field names (`agent_class`, `tool_class`, `depends_on`, `when`) before writing
- **IMPLEMENT**:
  ```yaml
  name: regulatory_drift_alert
  trigger: data_update
  nodes:
    - id: fetch-latest-changes
      agent_class: RegulatoryResearchAgent

    - id: scan-drift
      tool_class: RegulatoryDriftTool
      depends_on: [fetch-latest-changes]

    - id: find-alternatives
      tool_class: SupplierAlternativesTool
      depends_on: [scan-drift]
      when: has_regulatory_drift

    - id: write-alerts
      agent_class: RegulatoryDriftAgent
      depends_on: [scan-drift, find-alternatives]
      when: has_regulatory_drift
  ```
- **GOTCHA**: `SupplierAlternativesTool` reads `canonical_id` from the `find-alternatives` node output in some tools. Verify how it resolves `canonical_id` from context — it may use `ctx.trigger_payload.get("canonical_id")` or upstream node output. Read `orchestration/tools/supplier_alternatives.py` before implementing this task. If it can't resolve `canonical_id` from `scan-drift`'s `canonical_id` key, add a note in the plan and consider replacing this node with a simpler fallback.
- **VALIDATE**: `PYTHONPATH=. python3 -c "from orchestration.api.pipeline_loader import load; p=load('regulatory_drift_alert'); print(p.name, len(p.nodes))"`

### Task 5.2 — REGISTER tools and agents in DAG executor registries

- **VERIFY FIRST**: Read `orchestration/api/dag_executor.py` fully to find `get_tool()` and `get_agent()` registry — they may be simple dicts, module imports, or dynamic class instantiation
- **ADD** `RegulatoryDriftTool` to tool registry pointing to `orchestration.tools.regulatory_drift_tool`
- **ADD** `RegulatoryResearchAgent` to agent registry pointing to `orchestration.agents.regulatory_research_agent`
- **ADD** `RegulatoryDriftAgent` to agent registry pointing to `orchestration.agents.regulatory_drift_agent`
- **GOTCHA**: The registry may map string class names to module paths, to actual `run` functions, or to instantiated objects. Read the existing pattern exactly and mirror it — do NOT guess.
- **VALIDATE**: `PYTHONPATH=. python3 -c "from orchestration.api.dag_executor import get_tool, get_agent; print(get_tool('RegulatoryDriftTool')); print(get_agent('RegulatoryResearchAgent')); print(get_agent('RegulatoryDriftAgent'))"`

### Task 6.1 — ADD `GET /api/data/regulatory-alerts` to `orchestration/api/routes/data.py`

- **VERIFY FIRST**: Read `orchestration/api/routes/data.py` fully — confirm `_DB` path constant, router prefix, and existing endpoint patterns. This file may have changed since the plan was written.
- **ADD** after the last endpoint in `data.py`:
  ```python
  @router.get("/api/data/regulatory-alerts")
  def get_regulatory_alerts():
      conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
      conn.row_factory = sqlite3.Row
      rows = conn.execute("""
          SELECT
              cl.Id, cl.ChangeId, cl.SnapshotDate, cl.IngredientName,
              cl.Route, cl.DosageForm, cl.MaxPotencyPerUnit,
              cl.MaxDailyExposure, cl.MaxDailyExposureUOM, cl.Status,
              cl.CanonicalIngredientId, cl.MatchMethod, cl.MatchScore,
              ic.Name AS canonical_name,
              ic.Grade_Flag AS grade,
              co.Id AS opportunity_id,
              co.Consolidation_Score AS consolidation_score,
              co.regulatory_drift_flag,
              co.regulatory_drift_reason
          FROM FDA_IID_Change_Log cl
          JOIN Ingredient_Canonical ic ON ic.Id = cl.CanonicalIngredientId
          LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = cl.CanonicalIngredientId
          ORDER BY cl.Status ASC, cl.ChangeId ASC
      """).fetchall()
      conn.close()
      # Group by ChangeId for C/R status (before/after pairs)
      alerts = {}
      for r in rows:
          cid = r["ChangeId"]
          if cid not in alerts:
              alerts[cid] = {
                  "change_id": cid,
                  "ingredient_name": r["canonical_name"] or r["IngredientName"],
                  "status": r["Status"],
                  "route": r["Route"],
                  "dosage_form": r["DosageForm"],
                  "canonical_id": str(r["CanonicalIngredientId"]),
                  "grade": r["grade"],
                  "opportunity_id": str(r["opportunity_id"]) if r["opportunity_id"] else None,
                  "consolidation_score": r["consolidation_score"],
                  "regulatory_drift_flag": bool(r["regulatory_drift_flag"]),
                  "regulatory_drift_reason": r["regulatory_drift_reason"],
                  "snapshots": [],
              }
          alerts[cid]["snapshots"].append({
              "snapshot_date": r["SnapshotDate"],
              "max_potency": r["MaxPotencyPerUnit"],
              "max_daily_exposure": r["MaxDailyExposure"],
              "mde_uom": r["MaxDailyExposureUOM"],
          })
      return {"alerts": list(alerts.values()), "count": len(alerts)}
  ```
- **GOTCHA**: `Consolidation_Opportunity` does not have a UNIQUE on CanonicalIngredientId — the LEFT JOIN may return multiple rows per change log entry if there are multiple opportunities for the same canonical. Use `MIN(co.Id)` and `MAX(co.Consolidation_Score)` or just take the first match via Python grouping.
- **VALIDATE**: Start FastAPI server (`PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000`) and `curl -s http://localhost:8000/api/data/regulatory-alerts | python3 -m json.tool | head -30`

### Task 6.2 — UPDATE `orchestration/tools/opportunity_ranker.py`

- **VERIFY FIRST**: Read current `opportunity_ranker.py` fully — confirm schema of `Consolidation_Opportunity` still matches. The `regulatory_drift_flag` and `regulatory_drift_reason` columns must already exist (added in Task 1.1 migration).
- **MODIFY** the SQL query to include:
  ```sql
  co.regulatory_drift_flag,
  co.regulatory_drift_reason
  ```
  in the SELECT clause (after `co.Generated_At`)
- **MODIFY** the returned opportunity dict to include:
  ```python
  "regulatory_drift_flag": bool(r["regulatory_drift_flag"]),
  "regulatory_drift_reason": r["regulatory_drift_reason"],
  ```
- **RATIONALE**: ProactiveAgent receives opportunity dicts via `ctx.get("scan-opportunities")`. With this change, its narrative will include regulatory context without any agent code changes — Gemini will notice the flag and mention it.
- **VALIDATE**: `python3 -c "from orchestration.tools.opportunity_ranker import run; from unittest.mock import MagicMock; ctx=MagicMock(); ctx.enriched_db_path='db_enriched.sqlite'; ctx.trigger_payload={'top_n': 3}; result=run(ctx); print(result['opportunities'][0].keys() if result['opportunities'] else 'no opportunities')"`

### Task 7 — UPDATE `schema/enriched_schema.sql` (documentation only)

- **ADD** `FDA_IID_Change_Log` CREATE TABLE DDL to the schema file in the appropriate location (after `FDA_Inactive_Ingredient`)
- **ADD** `regulatory_drift_flag INTEGER DEFAULT 0` and `regulatory_drift_reason TEXT` columns to the `Consolidation_Opportunity` table definition in the file
- **VALIDATE**: File is documentation only — verify visually that the added DDL matches the actual migration script from Task 1.1

---

## TESTING STRATEGY

This project has no test suite directory (confirm with `find . -name "test_*.py" -o -name "*_test.py" | head -5`). Testing is done via validation commands.

### Unit Tests (via inline validation)

- Migration idempotency: run `db_migrate_iid_changelog.py` twice, assert row count unchanged
- CSV loader: assert 187 rows inserted on first run, 0 on second run (INSERT OR IGNORE)
- Drift tool: assert `has_regulatory_drift` returns True when FDA_IID_Change_Log has matched rows; False when empty
- Condition guard: assert evaluates correctly for both True/False cases

### Integration Tests

- Run full pipeline via API: `curl -X POST http://localhost:8000/pipelines/run/regulatory_drift_alert -H "Content-Type: application/json" -d "{}"` → assert `run_id` returned
- Verify SSE stream: `curl http://localhost:8000/runs/{run_id}/stream` → assert `pipeline_completed` event received
- Verify API endpoint: `GET /api/data/regulatory-alerts` → assert non-empty `alerts` array with correct structure

### Edge Cases

- Empty `FDA_IID_Change_Log` (no matches after CSV load): `scan-drift` returns `drift_alerts: []`, `has_regulatory_drift` returns False, pipeline nodes `find-alternatives` and `write-alerts` are skipped — verify no crash
- Status=D rows (single snapshot, no Q2 pair): drift tool must handle single-row groups without KeyError
- Missing `GOOGLE_API_KEY`: both research and drift agents return `skipped` gracefully — pipeline continues
- MaxDailyExposure values `"NA"` or `""`: severity comparison must not crash — wrap in try/except float conversion
- SupplierAlternativesTool receives `canonical_id: None` (no drift matches): must handle None gracefully — verify tool's input resolution before the pipeline is finalized

---

## VALIDATION COMMANDS

### Level 1: Import Syntax

```bash
PYTHONPATH=. python3 -c "import enrichment.db_migrate_iid_changelog"
PYTHONPATH=. python3 -c "import enrichment.sources.fda_iid_changelog"
PYTHONPATH=. python3 -c "import orchestration.tools.regulatory_drift_tool"
PYTHONPATH=. python3 -c "import orchestration.agents.regulatory_research_agent"
PYTHONPATH=. python3 -c "import orchestration.agents.regulatory_drift_agent"
```

### Level 2: Migration & Ingestion

```bash
# Run once
python enrichment/backfill_iid_changelog.py

# Verify table + row count
python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
total, matched = c.execute('SELECT COUNT(*), SUM(CASE WHEN CanonicalIngredientId IS NOT NULL THEN 1 END) FROM FDA_IID_Change_Log').fetchone()
print(f'Total: {total}, Matched: {matched}')
print('Status breakdown:', dict(c.execute('SELECT Status, COUNT(*) FROM FDA_IID_Change_Log GROUP BY Status').fetchall()))
"

# Idempotency — run again, counts should not change
python enrichment/backfill_iid_changelog.py
```

### Level 3: Tool Smoke Test

```bash
PYTHONPATH=. python3 -c "
from orchestration.tools.regulatory_drift_tool import run
from unittest.mock import MagicMock
ctx = MagicMock()
ctx.enriched_db_path = 'db_enriched.sqlite'
result = run(ctx)
print('Alerts:', result['count'], '| High severity:', result['high_severity_count'])
print('Top canonical_id:', result['canonical_id'])
"
```

### Level 4: Pipeline Integration

```bash
# Start server in background
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000 &
sleep 3

# Trigger pipeline
RUN_ID=$(curl -s -X POST http://localhost:8000/pipelines/run/regulatory_drift_alert \
  -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "Run ID: $RUN_ID"
sleep 10

# Check run status
curl -s http://localhost:8000/runs/$RUN_ID | python3 -m json.tool

# Check alerts endpoint
curl -s http://localhost:8000/api/data/regulatory-alerts | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Alert count:', d['count'])
if d['alerts']:
    print('First alert:', d['alerts'][0])
"

# Kill server
kill %1
```

### Level 5: DB State Verification

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
# Check opportunity flagging
flagged = c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity WHERE regulatory_drift_flag=1').fetchone()[0]
print('Flagged opportunities:', flagged)
# Check opportunity_ranker returns drift flags
from orchestration.tools.opportunity_ranker import run
from unittest.mock import MagicMock
ctx = MagicMock()
ctx.enriched_db_path = 'db_enriched.sqlite'
ctx.trigger_payload = {'top_n': 3}
result = run(ctx)
if result['opportunities']:
    print('Ranker output keys:', list(result['opportunities'][0].keys()))
"
```

---

## ACCEPTANCE CRITERIA

- [ ] `FDA_IID_Change_Log` table created with UNIQUE constraint; 187 rows loaded from CSV
- [ ] Migration is idempotent (second run produces identical DB state)
- [ ] At least some rows have `CanonicalIngredientId` matched (expect 5-20 matches given supplement-focused canonicals vs pharma-focused FDA IID)
- [ ] `regulatory_drift_flag` and `regulatory_drift_reason` columns exist on `Consolidation_Opportunity`
- [ ] `RegulatoryDriftTool` returns correct `drift_alerts` shape with severity, status, and canonical linkage
- [ ] `has_regulatory_drift` condition guard evaluates correctly in both True/False branches
- [ ] `regulatory_drift_alert` pipeline loads via `pipeline_loader.load("regulatory_drift_alert")`
- [ ] Pipeline trigger via `POST /pipelines/run/regulatory_drift_alert` returns run_id and reaches `pipeline_completed` (or all non-agent nodes complete; agent nodes may skip without GOOGLE_API_KEY)
- [ ] `GET /api/data/regulatory-alerts` returns JSON with `alerts` array and correct structure
- [ ] `opportunity_ranker.run()` output includes `regulatory_drift_flag` key for each opportunity
- [ ] All Level 1-5 validation commands pass with no exceptions

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (1.1 → 1.2 → 1.3 → 2.1 → 2.2 → 3.1 → 4.1 → 5.1 → 5.2 → 6.1 → 6.2 → 7)
- [ ] Each task's VALIDATE command ran immediately after implementation
- [ ] Migration idempotency verified
- [ ] Pipeline SSE stream confirmed to terminate with `pipeline_completed`
- [ ] `GET /api/data/regulatory-alerts` returns structurally valid JSON
- [ ] `schema/enriched_schema.sql` updated to reflect new table and columns
- [ ] CLAUDE.md updated with new files and status per self-maintenance rule
- [ ] README.md updated with new endpoint and pipeline per self-maintenance rule

---

## NOTES

### On Match Count Expectations

The FDA IID change log contains pharma excipients (ACETIC ACID, CITRIC ACID MONOHYDRATE, GLYCERIN, MANNITOL, LACTOSE, etc.). Agnes's canonical ingredients are supplement-focused. Expect low but meaningful match overlap — probably 5-20 canonical matches out of 135 unique change IDs. Even low coverage is valuable because any match means a real portfolio ingredient has a regulatory change.

### On SupplierAlternativesTool in Pipeline

Before finalising `regulatory_drift_alert.yaml`, **read `orchestration/tools/supplier_alternatives.py`** to understand how it resolves `canonical_id`. It may look for `ctx.get("find-alternatives", {}).get("canonical_id")` (a naming collision since it IS the `find-alternatives` node) or `ctx.trigger_payload.get("canonical_id")`. If the latter, the pipeline may need to pass the top affected `canonical_id` via `trigger_payload` or the YAML node may need to be replaced with a simpler read from `scan-drift`'s output. The drift tool intentionally returns `canonical_id` at the top level of its output to enable this — verify the tool resolution chain works before finalising.

### On Live FDA Fetch

The FDA IID quarterly change log page at `fda.gov/drugs/drug-approvals-and-databases/quarterly-inactive-ingredient-database-iid-change-log` provides a downloadable CSV. The research agent should search for this URL. If the FDA has changed the format or URL since this plan was written, the agent's search should surface the new URL. The static `Change_Log_Data.csv` provides a baseline regardless of whether the live fetch succeeds.

### On Status Semantics (Confirmed via FDA Research)

- **C (Corrected)**: Record data was corrected; same ChangeId appears in Q1 (before) and Q2 (after); the before/after pair shows what changed. MDE decreases indicate more restrictive limits (HIGH severity).
- **D (Deleted)**: Record was removed from the IID; only Q1 row exists (no Q2). Excipients are rarely fully deleted — this usually reflects route/dosage reclassification, but the net effect is the ingredient+route+form combo is no longer in the IID (HIGH severity).
- **R (Revised)**: MDE replacement — a record from the previous publication was replaced with Maximum Daily Exposure information. Generally expected to be an increase (less restrictive), but verify by parsing numeric values.

### On ProactiveAgent Enhancement

No changes to `proactive_agent.py` are required. By adding `regulatory_drift_flag` and `regulatory_drift_reason` to the opportunity_ranker output, those fields are automatically included in the JSON payload passed to Gemini. Gemini's existing instruction already says "Flag data gaps honestly" — with the drift flag present, it will naturally call out regulatory risk in consolidation proposals.

### Confidence Score

**7/10** — The schema, CSV patterns, and tool/agent patterns are well-understood. The main risk is `SupplierAlternativesTool` canonical_id resolution in the pipeline (see Note above) and the live FDA download (network/format dependency). Both are isolated and have graceful fallbacks. The implementation agent must read all referenced files before writing code — the VERIFY FIRST instructions in each task are not optional.
