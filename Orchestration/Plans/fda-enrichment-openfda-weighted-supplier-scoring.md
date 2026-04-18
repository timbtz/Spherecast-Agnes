# Feature: FDA IID Enrichment + openFDA Module + Weighted Supplier Scoring

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to: existing sqlite3 connection patterns (no ORM), the Tool/ToolResult ABC contract in `reasoning/base.py`, the router registration pattern in `orchestration/api/main.py`, and React Query + Zustand state split in the frontend.

## Feature Description

Three coordinated enhancements to Agnes's data and UX layers:

**Phase 1 — FDA IID CSV Import**: Import the FDA Inactive Ingredient Database (IIR_OCOMM.csv, 9,067 rows) into a new `FDA_Inactive_Ingredient` table. Cross-reference by UNII to Agnes's 135 known canonicals (53 match). Surface max-daily-exposure limits per ingredient × route × dosage form via a new API endpoint, and wire a DB-backed safety gate into `compliance_reasoner_tool.py`.

**Phase 2 — openFDA Module**: New `enrichment/sources/openfda.py` with label-search and adverse-event queries. Backfill `openfda_adverse_event_count` on `Ingredient_Canonical`. Expose per-ingredient safety summary via API. API key: `mD6ZQ5YEOVe2jaxtThNUWf6Gsebq28UGHImBavbS` (already added to `.env` as `OPENFDA_API_KEY`).

**Phase 3 — Weighted Supplier Scoring**: User-configurable 1-5 weights for Price, Lead Time, and Quality. Backend scorer reads `Supplier_Commercial`, normalizes three dimensions, returns per-supplier weighted scores. New `Scoring_Config` DB table. New `GET/POST /api/scoring/weights` and `GET /api/scoring/suppliers/{ingredient_id}` endpoints. New "Suppliers" tab in the frontend with weight sliders and a ranked supplier table.

## User Story

As a CPG procurement manager using Agnes  
I want to rank ingredient suppliers by weighted score (price / lead time / quality) using my own priorities, and see FDA-backed safety limits for each ingredient  
So that I can make defensible, data-driven sourcing decisions and flag compliance risks before they reach legal

## Problem Statement

- Agnes's `Supplier_Commercial` table has `Price_USD_Per_KG`, `Lead_Time_Days`, `Purity_Pct`, and `Confidence` — but no scoring or ranking logic exists.
- The FDA IID CSV (already uploaded to `Orchestration/Data/api/`) contains max-daily-exposure limits that would strengthen compliance reasoning but are currently unused.
- The compliance_reasoner uses only hard-coded JURISDICTION_PACKS; no DB-backed FDA exposure limits inform its decisions.
- No UI exists for supplier comparison or weight configuration.

## Solution Statement

Import FDA IID data into a permanent DB table. Augment the compliance reasoner tool to check IID limits as a soft gate. Build an openFDA enrichment source. Add a supplier scoring engine (`reasoning/supplier_scorer.py`) driven by persisted user weights. Wire up three new API endpoints and a new frontend "Suppliers" tab with 1-5 weight selectors.

## Feature Metadata

**Feature Type**: New Capability (Phase 1, 2) + Enhancement (Phase 3)  
**Estimated Complexity**: Medium-High  
**Primary Systems Affected**: DB schema, enrichment pipeline, reasoning tools, orchestration API routes, frontend views/types/API client  
**Dependencies**: `requests` (already in requirements.txt), `python-dotenv` (already), React Query, Zustand, shadcn/ui Slider component (already in @radix-ui/react-slider)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `schema/enriched_schema.sql` — Full schema; FDA_Inactive_Ingredient table goes here as a new section; Scoring_Config table too
- `enrichment/db_migrate_v11.py` — Migration pattern: `_add_col()` idempotent helper, `CREATE TABLE IF NOT EXISTS`, log to `Enrichment_Run_Log`
- `enrichment/sources/pubchem.py` (lines 1-50, 109-160) — Rate-limiting pattern (`_throttle_lock`, `MIN_REQUEST_INTERVAL`), cache pattern (`API_Response_Cache` table, `json.dumps`/`json.loads`)
- `enrichment/sources/molport.py` — Source client pattern: `__init__` reads env key, `lookup_ingredient()` returns `list[dict]`, graceful no-op if key absent
- `enrichment/enrichers/role_classifier.py` — Enricher class pattern: `__init__(db_path)`, `run()` → fetches rows → updates per row → commits per row → logs distribution
- `enrichment/backfill_phase1.py` (lines 1-80) — Backfill script pattern: `load_dotenv()` at top, per-row commit before API call to release locks, `Enrichment_Run_Log` insert per row
- `reasoning/base.py` — `ToolResult`, `Tool(ABC)`, `compound_confidence()` — all reasoning tools use this contract
- `reasoning/compliance_reasoner.py` — `ComplianceReasoner`, `ComplianceInput`, `_JurisdictionVerdict`; **do NOT modify this file**; augment only the orchestration wrapper
- `orchestration/tools/compliance_reasoner_tool.py` — Where FDA IID gate goes: DB query + IID check after ComplianceReasoner._run()
- `orchestration/tools/opportunity_ranker.py` — Simple tool pattern: `run(ctx: AgnesContext) -> dict`, direct sqlite3, `ctx.enriched_db_path`
- `orchestration/api/routes/data.py` — Read-only route pattern: `get_db()` with `mode=ro` URI, `sqlite3.Row` row_factory, WAL pragma
- `orchestration/api/main.py` — Router registration: `app.include_router(router_object)` after imports
- `orchestration/ui/src/types/agnes.ts` — All frontend types; add `ScoringWeights`, `ScoredSupplier`, `FdaLimit` here
- `orchestration/ui/src/lib/agnesApi.ts` — API client; add `scoringWeights()`, `saveScoringWeights()`, `scoredSuppliers()`, `fdaLimits()` methods
- `orchestration/ui/src/components/views/OpportunitiesView.tsx` — Reference for view structure: `useQuery` pattern, grid layout, `ScoreBar`, `GradePill`, `LoadingState`/`ErrorState`/`EmptyState`
- `orchestration/ui/src/components/shared/ScoreBar.tsx` — Reuse directly in SuppliersView for per-supplier weighted scores
- `orchestration/ui/src/components/layout/Sidebar.tsx` — Add "suppliers" tab entry here
- `orchestration/ui/src/pages/Index.tsx` — Add "suppliers" to `TAB_TITLES` and tab render switch

### New Files to Create

**Backend:**
- `enrichment/sources/fda_iid.py` — CSV loader: reads both CSVs, upserts into `FDA_Inactive_Ingredient`
- `enrichment/sources/openfda.py` — openFDA client: `search_labels()`, `adverse_events()`, rate-limited, cached
- `enrichment/backfill_openfda.py` — Backfill script: populates `openfda_adverse_event_count` on all canonicals
- `enrichment/db_migrate_fda_scoring.py` — Idempotent migration: creates `FDA_Inactive_Ingredient` + `Scoring_Config` tables, adds `openfda_adverse_event_count` column
- `reasoning/supplier_scorer.py` — Scoring engine: normalizes price/lead_time/quality, applies user weights, returns ranked list
- `orchestration/api/routes/scoring.py` — New router: GET/POST weights, GET scored suppliers, GET FDA limits

**Frontend:**
- `orchestration/ui/src/components/views/SuppliersView.tsx` — New tab view: weight sliders + supplier table
- `orchestration/ui/src/components/shared/WeightSelector.tsx` — 1-5 dot/segment selector component

### Relevant Documentation

- [openFDA API Authentication](https://open.fda.gov/apis/authentication/)
  - Key passed as `?api_key=` query param
  - Rate: 240 req/min without key, 12,000 req/hr with key
  - Why: Backfill script must pass key for acceptable throughput
- [openFDA Drug Label Endpoint](https://open.fda.gov/apis/drug/label/)
  - `GET https://api.fda.gov/drug/label.json?search=inactive_ingredient:"ascorbic acid"&limit=5`
  - Why: Use `inactive_ingredient` field to count appearances; `results[].openfda.unii` for cross-ref
- [openFDA Drug Event (FAERS)](https://open.fda.gov/apis/drug/event/)
  - `GET https://api.fda.gov/drug/event.json?search=patient.drug.openfda.unii:"PQ6CK8PD0R"&count=patient.drug.openfda.unii.exact&limit=1`
  - Why: Count adverse event reports per UNII — stored as `openfda_adverse_event_count`
- [FDA Inactive Ingredient Database](https://www.fda.gov/drugs/drug-approvals-and-databases/inactive-ingredient-database-search)
  - CSV column mapping: `INGREDIENT_NAME`, `ROUTE`, `DOSAGE_FORM`, `CAS_NUMBER`, `UNII`, `POTENCY_AMOUNT`, `POTENCY_UNIT`, `MAXIMUM_DAILY_EXPOSURE`, `MAXIMUM_DAILY_EXPOSURE_UNIT`, `RECORD_UPDATED`
  - CSV has BOM (`\ufeff`) — open with `encoding='utf-8-sig'`
  - Why: Both CSVs already downloaded to `Orchestration/Data/api/`
- [shadcn/ui Slider](https://ui.shadcn.com/docs/components/slider)
  - `<Slider min={1} max={5} step={1} value={[n]} onValueChange={([v]) => ...} />`
  - Already available via `@radix-ui/react-slider` (in package.json)
  - Why: Used for weight input in WeightSelector component

### Patterns to Follow

**DB Connection (write-capable):**
```python
import sqlite3
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
conn.row_factory = sqlite3.Row
# ... operations ...
conn.commit()
conn.close()
```

**DB Connection (read-only, routes):**
```python
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"

def get_db():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

**Idempotent migration helper (mirror `enrichment/db_migrate_v11.py` lines 10-18):**
```python
def _add_col(conn, table: str, col: str, typedef: str) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        print(f"  + {table}.{col}")
```

**Rate-limiting (mirror `enrichment/sources/pubchem.py` lines 18-26):**
```python
import threading, time
_MIN_INTERVAL = 0.25   # openFDA: 240/min = 0.25s minimum
_last_req: float = 0.0
_lock = threading.Lock()

def _throttle() -> None:
    global _last_req
    with _lock:
        elapsed = time.monotonic() - _last_req
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_req = time.monotonic()
```

**Cache pattern (mirror `enrichment/sources/pubchem.py` lines 109-138):**
```python
def _get_cache(self, key: str) -> tuple[bool, dict | None]:
    try:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT Response FROM API_Response_Cache WHERE Source = ? AND Cache_Key = ?",
            ("openfda", key)
        ).fetchone()
        conn.close()
        if row:
            val = json.loads(row[0])
            return True, val
    except Exception:
        pass
    return False, None

def _set_cache(self, key: str, result: dict | None) -> None:
    try:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO API_Response_Cache (Source, Cache_Key, Response, TTL_Days) VALUES (?, ?, ?, 7)",
            ("openfda", key, json.dumps(result))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
```

**New route file (mirror `orchestration/api/routes/data.py` lines 1-18):**
```python
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/scoring", tags=["scoring"])
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"

def get_db_rw():
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn
```

**React Query fetch pattern (mirror `OpportunitiesView.tsx`):**
```typescript
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ["scored-suppliers", selectedIngredientId],
  queryFn: () => agnesApi.scoredSuppliers(selectedIngredientId!),
  enabled: !!selectedIngredientId,
});
```

**Zustand store access (from `useAgnes.ts`):**
```typescript
const { setOrbState } = useAgnesStore();
```

**API client method (mirror `agnesApi.ts`):**
```typescript
async scoringWeights(): Promise<ScoringWeights> {
  const r = await safeFetch(`${API_URL}/api/scoring/weights`);
  return r.json();
},
```

**Naming conventions:**
- Python: `snake_case` functions, `PascalCase` classes, `UPPER_CASE` constants
- TypeScript: `camelCase` functions/vars, `PascalCase` components/interfaces, `kebab-case` file names
- DB tables: `PascalCase_With_Underscores`
- Route prefixes: `/api/data/...` (read), `/api/scoring/...` (scoring config)
- Logger names: `"agnes.module_name"` (e.g. `"agnes.openfda"`)

---

## IMPLEMENTATION PLAN

### Phase 1: FDA IID Import + Compliance Gate

Foundation for FDA-backed compliance decisions. Two new DB tables, CSV import script, and a compliance_reasoner_tool augmentation.

**Tasks:**
1. Add `FDA_Inactive_Ingredient` and `Scoring_Config` to schema + migration
2. Write `enrichment/sources/fda_iid.py` loader
3. Augment `compliance_reasoner_tool.py` with IID exposure check
4. Add `GET /api/data/fda-limits/{ingredient_id}` endpoint

### Phase 2: openFDA Adverse Events

New enrichment source, backfill script, schema column, API endpoint.

**Tasks:**
5. Write `enrichment/sources/openfda.py`
6. Write `enrichment/backfill_openfda.py`
7. Add `GET /api/data/ingredients/{ingredient_id}/safety` endpoint

### Phase 3: Weighted Supplier Scoring

Backend scorer + config endpoints + frontend tab.

**Tasks:**
8. Write `reasoning/supplier_scorer.py`
9. Write `orchestration/api/routes/scoring.py`
10. Register scoring router in `main.py`
11. Add types to `agnes.ts`
12. Add API methods to `agnesApi.ts`
13. Create `WeightSelector.tsx` component
14. Create `SuppliersView.tsx`
15. Add "suppliers" tab to Sidebar + Index

### Phase 4: Integration & Validation

**Tasks:**
16. Run migration script to create all new tables
17. Run `fda_iid.py` loader to populate `FDA_Inactive_Ingredient`
18. Smoke-test all API endpoints
19. Build frontend (`npm run build` in `orchestration/ui/`)
20. Manual validation of UI

---

## STEP-BY-STEP TASKS

### TASK 1: UPDATE `schema/enriched_schema.sql`

- **ADD** two new table definitions at the end of the file (after `Certification_Registry`):

```sql
-- FDA Inactive Ingredient Database (IID) — max daily exposure limits per route/form
CREATE TABLE IF NOT EXISTS FDA_Inactive_Ingredient (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    IngredientName          TEXT NOT NULL,
    UNII                    TEXT,
    CAS_Number              TEXT,
    Route                   TEXT NOT NULL,
    DosageForm              TEXT NOT NULL,
    MaxPotencyAmount        REAL,
    MaxPotencyUnit          TEXT,
    MaxDailyExposure        REAL,
    MaxDailyExposureUnit    TEXT,
    RecordUpdated           TEXT,
    CanonicalIngredientId   INTEGER,
    Source                  TEXT DEFAULT 'fda_iid_csv',
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);
CREATE INDEX IF NOT EXISTS idx_fda_iid_unii       ON FDA_Inactive_Ingredient(UNII);
CREATE INDEX IF NOT EXISTS idx_fda_iid_canonical  ON FDA_Inactive_Ingredient(CanonicalIngredientId);

-- Scoring configuration — user-adjustable weights for supplier ranking
CREATE TABLE IF NOT EXISTS Scoring_Config (
    Key     TEXT PRIMARY KEY,
    Value   REAL NOT NULL
);
-- Default rows inserted by migration script
```

- **VALIDATE**: `grep -n "FDA_Inactive_Ingredient\|Scoring_Config" "schema/enriched_schema.sql"`

---

### TASK 2: CREATE `enrichment/db_migrate_fda_scoring.py`

- **IMPLEMENT**: Idempotent migration creating both new tables, inserting default Scoring_Config rows, adding `openfda_adverse_event_count` column to `Ingredient_Canonical`
- **PATTERN**: Mirror `enrichment/db_migrate_v11.py` — `_add_col()` helper, `CREATE TABLE IF NOT EXISTS`, log to `Enrichment_Run_Log`
- **IMPORTS**: `import sqlite3, logging; from pathlib import Path; from dotenv import load_dotenv; load_dotenv()`

```python
"""Idempotent migration: FDA_Inactive_Ingredient table, Scoring_Config table,
openfda_adverse_event_count column on Ingredient_Canonical."""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_fda_scoring")


def _add_col(conn, table: str, col: str, typedef: str) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        logger.info(f"  + {table}.{col}")


def migrate(conn: sqlite3.Connection) -> None:
    # 1. FDA_Inactive_Ingredient table
    conn.execute("""CREATE TABLE IF NOT EXISTS FDA_Inactive_Ingredient (
        Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        IngredientName          TEXT NOT NULL,
        UNII                    TEXT,
        CAS_Number              TEXT,
        Route                   TEXT NOT NULL,
        DosageForm              TEXT NOT NULL,
        MaxPotencyAmount        REAL,
        MaxPotencyUnit          TEXT,
        MaxDailyExposure        REAL,
        MaxDailyExposureUnit    TEXT,
        RecordUpdated           TEXT,
        CanonicalIngredientId   INTEGER,
        Source                  TEXT DEFAULT 'fda_iid_csv',
        FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fda_iid_unii ON FDA_Inactive_Ingredient(UNII)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fda_iid_canonical ON FDA_Inactive_Ingredient(CanonicalIngredientId)")

    # 2. Scoring_Config table with defaults
    conn.execute("""CREATE TABLE IF NOT EXISTS Scoring_Config (
        Key   TEXT PRIMARY KEY,
        Value REAL NOT NULL
    )""")
    for key, default in [("weight_price", 3.0), ("weight_lead_time", 3.0), ("weight_quality", 3.0)]:
        conn.execute("INSERT OR IGNORE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, default))

    # 3. New column on Ingredient_Canonical
    _add_col(conn, "Ingredient_Canonical", "openfda_adverse_event_count", "INTEGER")

    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_fda_scoring', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python enrichment/db_migrate_fda_scoring.py`
- **CHECK**: `sqlite3 db_enriched.sqlite ".tables"` — should include `FDA_Inactive_Ingredient` and `Scoring_Config`

---

### TASK 3: CREATE `enrichment/sources/fda_iid.py`

- **IMPLEMENT**: CSV loader that reads `IIR_OCOMM.csv` and `Change_Log_Data.csv`, UNII-matches to `Ingredient_Canonical`, upserts into `FDA_Inactive_Ingredient`
- **GOTCHA**: CSV has BOM — use `encoding='utf-8-sig'` not `'utf-8'`
- **GOTCHA**: `UNII` column in CSV may have leading/trailing whitespace — `.strip()`
- **GOTCHA**: `MAXIMUM_DAILY_EXPOSURE` may be empty string — convert to `None` if empty
- **IMPORTS**: `import csv, sqlite3, logging; from pathlib import Path; from dotenv import load_dotenv`

```python
"""Load FDA Inactive Ingredient Database CSVs into FDA_Inactive_Ingredient table."""
import csv
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
CSV_DIR = ROOT / "Orchestration" / "Data" / "api"
IIR_CSV = CSV_DIR / "IIR_OCOMM.csv"
CHANGELOG_CSV = CSV_DIR / "Change_Log_Data.csv"

logger = logging.getLogger("agnes.fda_iid")


def _float_or_none(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_iir(db_path=ENRICHED_DB) -> int:
    """Load IIR_OCOMM.csv into FDA_Inactive_Ingredient. Returns row count inserted."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Build UNII → CanonicalIngredientId lookup from existing canonicals
    unii_map: dict[str, int] = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT UNII_Code, Id FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL"
        ).fetchall()
    }
    logger.info(f"UNII map: {len(unii_map)} known canonicals")

    inserted = 0
    with open(IIR_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            unii = row.get("UNII", "").strip() or None
            canonical_id = unii_map.get(unii) if unii else None
            conn.execute(
                """INSERT OR IGNORE INTO FDA_Inactive_Ingredient
                   (IngredientName, UNII, CAS_Number, Route, DosageForm,
                    MaxPotencyAmount, MaxPotencyUnit, MaxDailyExposure,
                    MaxDailyExposureUnit, RecordUpdated, CanonicalIngredientId)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["INGREDIENT_NAME"].strip(),
                    unii,
                    row.get("CAS_NUMBER", "").strip() or None,
                    row["ROUTE"].strip(),
                    row["DOSAGE_FORM"].strip(),
                    _float_or_none(row.get("POTENCY_AMOUNT", "")),
                    row.get("POTENCY_UNIT", "").strip() or None,
                    _float_or_none(row.get("MAXIMUM_DAILY_EXPOSURE", "")),
                    row.get("MAXIMUM_DAILY_EXPOSURE_UNIT", "").strip() or None,
                    row.get("RECORD_UPDATED", "").strip() or None,
                    canonical_id,
                ),
            )
            inserted += 1
    conn.commit()

    matched = conn.execute(
        "SELECT COUNT(*) FROM FDA_Inactive_Ingredient WHERE CanonicalIngredientId IS NOT NULL"
    ).fetchone()[0]
    logger.info(f"Inserted {inserted} IIR rows; {matched} matched to canonical ingredients")
    conn.execute(
        """INSERT INTO Enrichment_Run_Log
           (ProductId, Phase, Step, Status, Confidence, Method)
           VALUES (NULL, 1, 'fda_iid_load', 'success', 1.0, 'csv_import')"""
    )
    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = load_iir()
    print(f"Loaded {n} IIR rows.")
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python enrichment/sources/fda_iid.py`
- **CHECK**: `sqlite3 db_enriched.sqlite "SELECT COUNT(*) FROM FDA_Inactive_Ingredient; SELECT COUNT(*) FROM FDA_Inactive_Ingredient WHERE CanonicalIngredientId IS NOT NULL;"`

---

### TASK 4: UPDATE `orchestration/tools/compliance_reasoner_tool.py`

- **ADD** FDA IID max-daily-exposure check AFTER the existing `ComplianceReasoner` call (around line 85, before the return statement)
- **PATTERN**: Same `sqlite3.connect(str(ctx.enriched_db_path))` pattern used on line ~65 of existing file
- **IMPLEMENT**: Query `FDA_Inactive_Ingredient` for the resolved canonical's UNII, find any `ORAL` rows with `MaxDailyExposure IS NOT NULL`, return the minimum as a reference limit
- **GOTCHA**: Do NOT modify `reasoning/compliance_reasoner.py` — add the DB check only in the orchestration tool wrapper
- **ADD** these fields to the existing return dict:
  ```python
  "fda_iid_max_daily_mg": float | None,   # minimum MaxDailyExposure found (ORAL), None if no data
  "fda_iid_routes": list[str],             # list of routes for which IID data exists
  "fda_iid_data_available": bool,
  ```
- **INSERT** the following block before the final `return` in `run()`:
  ```python
  # FDA IID max-daily-exposure lookup
  fda_max = None
  fda_routes: list[str] = []
  try:
      iid_conn = sqlite3.connect(str(ctx.enriched_db_path))
      iid_conn.row_factory = sqlite3.Row
      unii_row = iid_conn.execute(
          "SELECT UNII_Code FROM Ingredient_Canonical WHERE Id = ?", (canonical_id,)
      ).fetchone()
      if unii_row and unii_row["UNII_Code"]:
          iid_rows = iid_conn.execute(
              """SELECT Route, MIN(MaxDailyExposure) as min_exp
                 FROM FDA_Inactive_Ingredient
                 WHERE UNII = ? AND MaxDailyExposure IS NOT NULL
                 GROUP BY Route""",
              (unii_row["UNII_Code"],)
          ).fetchall()
          fda_routes = [r["Route"] for r in iid_rows]
          oral_rows = [r for r in iid_rows if r["Route"] == "ORAL"]
          if oral_rows:
              fda_max = oral_rows[0]["min_exp"]
      iid_conn.close()
  except Exception as e:
      logger.warning(f"FDA IID lookup failed for canonical {canonical_id}: {e}")
  ```
  Then add to return dict:
  ```python
  "fda_iid_max_daily_mg": fda_max,
  "fda_iid_routes": fda_routes,
  "fda_iid_data_available": len(fda_routes) > 0,
  ```
- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python -c "from orchestration.tools.compliance_reasoner_tool import run; print('import ok')"`

---

### TASK 5: ADD `GET /api/data/fda-limits/{ingredient_id}` to `orchestration/api/routes/data.py`

- **ADD** new endpoint after the existing `proposals()` endpoint (line 88):

```python
@router.get("/fda-limits/{ingredient_id}")
def fda_limits(ingredient_id: int):
    with get_db() as db:
        rows = db.execute(
            """SELECT Route, DosageForm, MaxPotencyAmount, MaxPotencyUnit,
                      MaxDailyExposure, MaxDailyExposureUnit, RecordUpdated
               FROM FDA_Inactive_Ingredient
               WHERE CanonicalIngredientId = ?
               ORDER BY Route, DosageForm""",
            (ingredient_id,),
        ).fetchall()
    return {"ingredient_id": ingredient_id, "limits": [dict(r) for r in rows], "count": len(rows)}
```

- **VALIDATE**: After server start: `curl -s http://localhost:8000/api/data/fda-limits/1 | python3 -m json.tool`

---

### TASK 6: CREATE `enrichment/sources/openfda.py`

- **IMPLEMENT**: openFDA client with label search and adverse event count query; rate-limited at 0.25s/req; cache with 7-day TTL; loads API key from env
- **PATTERN**: Mirror `enrichment/sources/pubchem.py` structure — session-level throttle, `API_Response_Cache`, per-method cache keys
- **IMPORTS**: `import requests, json, sqlite3, os, time, threading, logging; from pathlib import Path; from dotenv import load_dotenv; load_dotenv()`

```python
"""openFDA client: drug label search and adverse event counts.

API key at OPENFDA_API_KEY env var (240 req/min without, 12k req/hr with).
"""
import json
import logging
import os
import sqlite3
import threading
import time

import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
_BASE_URL = "https://api.fda.gov"
_MIN_INTERVAL = 0.26  # ~230 req/min — stay under 240/min limit
_last_req: float = 0.0
_lock = threading.Lock()
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Agnes/1.0 (supply-chain-agent)"

logger = logging.getLogger("agnes.openfda")


def _throttle() -> None:
    global _last_req
    with _lock:
        elapsed = time.monotonic() - _last_req
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_req = time.monotonic()


class OpenFDAClient:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self.api_key = os.getenv("OPENFDA_API_KEY", "")

    def _build_url(self, path: str, params: dict) -> str:
        if self.api_key:
            params["api_key"] = self.api_key
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{_BASE_URL}{path}?{qs}"

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT Response FROM API_Response_Cache WHERE Source = 'openfda' AND Cache_Key = ?",
                (key,),
            ).fetchone()
            conn.close()
            if row:
                return True, json.loads(row[0])
        except Exception:
            pass
        return False, None

    def _set_cache(self, key: str, result: dict | None) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES ('openfda', ?, ?, 7)""",
                (key, json.dumps(result)),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def adverse_event_count(self, unii: str) -> int:
        """Return total adverse event reports mentioning this UNII code."""
        cache_key = f"ae_count:{unii}"
        hit, cached = self._get_cache(cache_key)
        if hit:
            return cached.get("count", 0) if cached else 0

        url = self._build_url(
            "/drug/event.json",
            {
                "search": f'patient.drug.openfda.unii:"{unii}"',
                "limit": "1",
            },
        )
        _throttle()
        try:
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code == 404:
                # No results — valid response
                self._set_cache(cache_key, {"count": 0})
                return 0
            resp.raise_for_status()
            data = resp.json()
            total = data.get("meta", {}).get("results", {}).get("total", 0)
            self._set_cache(cache_key, {"count": total})
            return total
        except Exception as e:
            logger.warning(f"openFDA adverse_event_count({unii}) failed: {e}")
            return 0

    def search_labels(self, ingredient_name: str, limit: int = 5) -> list[dict]:
        """Search drug labels for ingredient in inactive_ingredient field."""
        cache_key = f"label:{ingredient_name.lower()}:{limit}"
        hit, cached = self._get_cache(cache_key)
        if hit:
            return cached or []

        url = self._build_url(
            "/drug/label.json",
            {
                "search": f'inactive_ingredient:"{ingredient_name}"',
                "limit": str(limit),
            },
        )
        _throttle()
        try:
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code == 404:
                self._set_cache(cache_key, [])
                return []
            resp.raise_for_status()
            results = resp.json().get("results", [])
            simplified = [
                {
                    "brand_name": r.get("openfda", {}).get("brand_name", [None])[0],
                    "manufacturer": r.get("openfda", {}).get("manufacturer_name", [None])[0],
                    "route": r.get("openfda", {}).get("route", [None])[0],
                    "inactive_ingredient": r.get("inactive_ingredient", [""]),
                }
                for r in results
            ]
            self._set_cache(cache_key, simplified)
            return simplified
        except Exception as e:
            logger.warning(f"openFDA search_labels({ingredient_name!r}) failed: {e}")
            return []
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python -c "from enrichment.sources.openfda import OpenFDAClient; c=OpenFDAClient(); print(c.adverse_event_count('PQ6CK8PD0R'))"`
  - Expected: non-zero integer (Vitamin C UNII)

---

### TASK 7: CREATE `enrichment/backfill_openfda.py`

- **IMPLEMENT**: Backfill `openfda_adverse_event_count` on all `Ingredient_Canonical` rows that have a `UNII_Code`
- **PATTERN**: Mirror `enrichment/backfill_phase1.py` — `load_dotenv()`, per-row commit, `Enrichment_Run_Log` insert, progress logging

```python
"""Backfill openfda_adverse_event_count on all UNII-bearing canonical ingredients."""
import logging
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_openfda")


def backfill_adverse_events(db_path=ENRICHED_DB) -> None:
    from enrichment.sources.openfda import OpenFDAClient
    client = OpenFDAClient(db_path)

    with sqlite3.connect(str(db_path), timeout=30) as _r:
        rows = _r.execute(
            """SELECT Id, Name, UNII_Code FROM Ingredient_Canonical
               WHERE UNII_Code IS NOT NULL AND openfda_adverse_event_count IS NULL"""
        ).fetchall()

    logger.info(f"Adverse event backfill: {len(rows)} canonicals to process")
    for canonical_id, name, unii in rows:
        count = client.adverse_event_count(unii)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE Ingredient_Canonical SET openfda_adverse_event_count = ? WHERE Id = ?",
            (count, canonical_id),
        )
        conn.execute(
            """INSERT INTO Enrichment_Run_Log
               (ProductId, Phase, Step, Status, Confidence, Method)
               VALUES (NULL, 2, 'openfda_ae_backfill', 'success', 0.95, 'openfda')"""
        )
        conn.commit()
        conn.close()
        logger.info(f"  {name} ({unii}): {count} adverse events")

    logger.info("Adverse event backfill complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill_adverse_events()
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python enrichment/backfill_openfda.py`
- **CHECK**: `sqlite3 db_enriched.sqlite "SELECT Name, openfda_adverse_event_count FROM Ingredient_Canonical WHERE openfda_adverse_event_count IS NOT NULL LIMIT 10;"`

---

### TASK 8: ADD `GET /api/data/ingredients/{ingredient_id}/safety` endpoint to `data.py`

- **ADD** after the `fda-limits` endpoint:

```python
@router.get("/ingredients/{ingredient_id}/safety")
def ingredient_safety(ingredient_id: int):
    with get_db() as db:
        ic = db.execute(
            """SELECT Name, Grade_Flag, openfda_adverse_event_count
               FROM Ingredient_Canonical WHERE Id = ?""",
            (ingredient_id,),
        ).fetchone()
        if not ic:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Ingredient not found")
        limits = db.execute(
            """SELECT Route, DosageForm, MaxDailyExposure, MaxDailyExposureUnit
               FROM FDA_Inactive_Ingredient
               WHERE CanonicalIngredientId = ? AND MaxDailyExposure IS NOT NULL
               ORDER BY Route""",
            (ingredient_id,),
        ).fetchall()
    return {
        "ingredient_id": ingredient_id,
        "name": ic["Name"],
        "grade": ic["Grade_Flag"],
        "adverse_event_count": ic["openfda_adverse_event_count"],
        "fda_limits": [dict(r) for r in limits],
    }
```

- **VALIDATE**: `curl -s http://localhost:8000/api/data/ingredients/1/safety | python3 -m json.tool`

---

### TASK 9: CREATE `reasoning/supplier_scorer.py`

- **IMPLEMENT**: Normalizes Price, Lead Time, and Quality across all suppliers for a given ingredient; applies user weights; returns ranked list
- **PATTERN**: Class with `__init__(db_path)`, direct sqlite3, returns `list[dict]`
- **IMPORTS**: `import sqlite3, logging; from pathlib import Path`

**Scoring formulas:**
- `price_score = 1 - (price - min_price) / (max_price - min_price)` — lower price = higher score; if min == max → 0.5
- `lead_time_score = 1 - (lead_time - min_lt) / (max_lt - min_lt)` — lower days = higher score; if min == max → 0.5
- `quality_score = mean(purity_pct/100 [if not None else 0.5], 1-grade_unverified [0 or 1], confidence [0-1])`
- `weighted_score = (P * price_score + L * lt_score + Q * quality_score) / (P + L + Q)`

```python
"""Supplier scoring engine — normalizes price/lead_time/quality and applies user weights."""
import sqlite3
import logging
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.supplier_scorer")

_DEFAULT_WEIGHTS = {"weight_price": 3.0, "weight_lead_time": 3.0, "weight_quality": 3.0}


def _safe_mean(vals: list[float]) -> float:
    return mean(vals) if vals else 0.5


class SupplierScorer:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def get_weights(self) -> dict[str, float]:
        """Load weights from Scoring_Config; return defaults if table empty."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT Key, Value FROM Scoring_Config").fetchall()
            conn.close()
            cfg = {r[0]: r[1] for r in rows}
            return {k: cfg.get(k, v) for k, v in _DEFAULT_WEIGHTS.items()}
        except Exception:
            return dict(_DEFAULT_WEIGHTS)

    def save_weights(self, price: float, lead_time: float, quality: float) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        for key, val in [("weight_price", price), ("weight_lead_time", lead_time), ("weight_quality", quality)]:
            conn.execute("INSERT OR REPLACE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()

    def score_suppliers(self, canonical_ingredient_id: int) -> list[dict]:
        """Return suppliers for this ingredient, ranked by weighted score."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT sc.SupplierId, s.Name as supplier_name,
                      sc.Price_USD_Per_KG, sc.Lead_Time_Days, sc.MOQ_KG,
                      sc.Purity_Pct, sc.Grade_Unverified, sc.Confidence,
                      sc.Country_Origin, sc.Country_Shipping,
                      sc.Price_Source, sc.Price_Type,
                      sc.Purity_Qualifier, sc.Last_Updated
               FROM Supplier_Commercial sc
               JOIN Supplier s ON s.Id = sc.SupplierId
               WHERE sc.CanonicalIngredientId = ?""",
            (canonical_ingredient_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return []

        weights = self.get_weights()
        W_P = weights["weight_price"]
        W_L = weights["weight_lead_time"]
        W_Q = weights["weight_quality"]
        W_total = W_P + W_L + W_Q

        # Extract raw values, substituting None with sentinel for normalization
        prices = [r["Price_USD_Per_KG"] for r in rows if r["Price_USD_Per_KG"] is not None]
        lead_times = [r["Lead_Time_Days"] for r in rows if r["Lead_Time_Days"] is not None]
        min_p, max_p = (min(prices), max(prices)) if prices else (0, 1)
        min_l, max_l = (min(lead_times), max(lead_times)) if lead_times else (0, 1)

        def _norm(val, lo, hi) -> float:
            if lo == hi:
                return 0.5
            return (val - lo) / (hi - lo)

        results = []
        for r in rows:
            d = dict(r)

            # price score (lower price = better)
            p_score = (1.0 - _norm(r["Price_USD_Per_KG"], min_p, max_p)) if r["Price_USD_Per_KG"] is not None else 0.5

            # lead time score (fewer days = better)
            l_score = (1.0 - _norm(r["Lead_Time_Days"], min_l, max_l)) if r["Lead_Time_Days"] is not None else 0.5

            # quality score
            q_parts = []
            if r["Purity_Pct"] is not None:
                q_parts.append(min(r["Purity_Pct"] / 100.0, 1.0))
            q_parts.append(0.0 if r["Grade_Unverified"] else 1.0)
            if r["Confidence"] is not None:
                q_parts.append(float(r["Confidence"]))
            q_score = _safe_mean(q_parts)

            weighted = (W_P * p_score + W_L * l_score + W_Q * q_score) / W_total

            d["price_score"] = round(p_score, 4)
            d["lead_time_score"] = round(l_score, 4)
            d["quality_score"] = round(q_score, 4)
            d["weighted_score"] = round(weighted, 4)
            results.append(d)

        results.sort(key=lambda x: x["weighted_score"], reverse=True)
        return results
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python -c "from reasoning.supplier_scorer import SupplierScorer; s=SupplierScorer(); print(s.get_weights())"`

---

### TASK 10: CREATE `orchestration/api/routes/scoring.py`

- **IMPLEMENT**: Three endpoints — GET weights, POST weights, GET scored suppliers
- **PATTERN**: Mirror `orchestration/api/routes/data.py` — `APIRouter`, `_DB` path, `sqlite3.Row`, `HTTPException`
- **NOTE**: Use RW connection for POST (not `mode=ro`)

```python
"""Scoring configuration and supplier ranking endpoints."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, confloat

router = APIRouter(prefix="/api/scoring", tags=["scoring"])
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"


class WeightsPayload(BaseModel):
    price: confloat(ge=1.0, le=5.0)
    lead_time: confloat(ge=1.0, le=5.0)
    quality: confloat(ge=1.0, le=5.0)


@router.get("/weights")
def get_weights():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT Key, Value FROM Scoring_Config").fetchall()
    conn.close()
    cfg = {r["Key"]: r["Value"] for r in rows}
    return {
        "price": cfg.get("weight_price", 3.0),
        "lead_time": cfg.get("weight_lead_time", 3.0),
        "quality": cfg.get("weight_quality", 3.0),
    }


@router.post("/weights")
def save_weights(payload: WeightsPayload):
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    for key, val in [
        ("weight_price", payload.price),
        ("weight_lead_time", payload.lead_time),
        ("weight_quality", payload.quality),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, val)
        )
    conn.commit()
    conn.close()
    return {"status": "saved", "price": payload.price, "lead_time": payload.lead_time, "quality": payload.quality}


@router.get("/suppliers/{ingredient_id}")
def scored_suppliers(ingredient_id: int):
    from reasoning.supplier_scorer import SupplierScorer
    scorer = SupplierScorer(_DB)
    results = scorer.score_suppliers(ingredient_id)
    if not results and not _ingredient_exists(ingredient_id):
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return {
        "ingredient_id": ingredient_id,
        "weights": scorer.get_weights(),
        "suppliers": results,
        "count": len(results),
    }


def _ingredient_exists(ingredient_id: int) -> bool:
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    row = conn.execute("SELECT Id FROM Ingredient_Canonical WHERE Id = ?", (ingredient_id,)).fetchone()
    conn.close()
    return row is not None
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python -c "from orchestration.api.routes.scoring import router; print([r.path for r in router.routes])"`

---

### TASK 11: REGISTER scoring router in `orchestration/api/main.py`

- **ADD** import and `app.include_router()` call, mirroring the existing pattern (lines 8-15, 40-43)

```python
# Add to imports section (after existing route imports):
from orchestration.api.routes import chat, pipelines, data_update, data, scoring

# Add after app.include_router(data.router):
app.include_router(scoring.router)
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes" && PYTHONPATH=. python -c "from orchestration.api.main import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'scoring' in r])"`

---

### TASK 12: UPDATE `orchestration/ui/src/types/agnes.ts`

- **ADD** new type definitions at the end of the file:

```typescript
export interface ScoringWeights {
  price: number;       // 1-5
  lead_time: number;   // 1-5
  quality: number;     // 1-5
}

export interface ScoredSupplier {
  SupplierId: number;
  supplier_name: string;
  Price_USD_Per_KG: number | null;
  Lead_Time_Days: number | null;
  MOQ_KG: number | null;
  Purity_Pct: number | null;
  Purity_Qualifier: string | null;
  Grade_Unverified: number;        // 0 = verified, 1 = unverified
  Confidence: number | null;
  Country_Origin: string | null;
  Country_Shipping: string | null;
  Price_Source: string | null;
  Price_Type: string | null;
  Last_Updated: string | null;
  price_score: number;             // 0..1
  lead_time_score: number;         // 0..1
  quality_score: number;           // 0..1
  weighted_score: number;          // 0..1
}

export interface FdaLimit {
  Route: string;
  DosageForm: string;
  MaxDailyExposure: number | null;
  MaxDailyExposureUnit: string | null;
}
```

- **VALIDATE**: `cd "/home/developer/Projects/Spherecast Agnes/orchestration/ui" && npm run build 2>&1 | tail -5`

---

### TASK 13: UPDATE `orchestration/ui/src/lib/agnesApi.ts`

- **ADD** four new methods inside the `agnesApi` object, after the existing `proposals()` method:

```typescript
async scoringWeights(): Promise<ScoringWeights> {
  const r = await safeFetch(`${API_URL}/api/scoring/weights`);
  return r.json();
},

async saveScoringWeights(weights: ScoringWeights): Promise<ScoringWeights> {
  const r = await safeFetch(`${API_URL}/api/scoring/weights`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      price: weights.price,
      lead_time: weights.lead_time,
      quality: weights.quality,
    }),
  });
  return r.json();
},

async scoredSuppliers(ingredientId: number): Promise<{ ingredient_id: number; weights: ScoringWeights; suppliers: ScoredSupplier[]; count: number }> {
  const r = await safeFetch(`${API_URL}/api/scoring/suppliers/${ingredientId}`);
  return r.json();
},

async fdaLimits(ingredientId: number): Promise<{ ingredient_id: number; limits: FdaLimit[]; count: number }> {
  const r = await safeFetch(`${API_URL}/api/data/fda-limits/${ingredientId}`);
  return r.json();
},
```

- **GOTCHA**: Import the new types: add `ScoringWeights, ScoredSupplier, FdaLimit` to the import from `../types/agnes` at the top of the file
- **VALIDATE**: `cd orchestration/ui && npm run build 2>&1 | grep -E "error|Error" | head -10`

---

### TASK 14: CREATE `orchestration/ui/src/components/shared/WeightSelector.tsx`

- **IMPLEMENT**: A 1-5 segment selector (5 clickable dots/boxes) for a single weight dimension
- **PATTERN**: Inline Tailwind, no external state — controlled component via `value` + `onChange`
- **USE**: `cn()` from `lib/utils`, lucide-react icons

```typescript
import { cn } from "@/lib/utils";

interface WeightSelectorProps {
  label: string;
  description: string;
  value: number;             // 1-5
  onChange: (v: number) => void;
  icon?: React.ReactNode;
}

export function WeightSelector({ label, description, value, onChange, icon }: WeightSelectorProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        {icon && <span className="text-muted-foreground">{icon}</span>}
        <span className="text-[13px] font-medium">{label}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{description}</p>
      <div className="flex gap-1.5 mt-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={cn(
              "h-7 w-9 rounded text-[11px] font-mono border transition-colors",
              n <= value
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted text-muted-foreground border-border hover:bg-surface-hover"
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- **VALIDATE**: Component renders without TS errors — `npm run build` passes

---

### TASK 15: CREATE `orchestration/ui/src/components/views/SuppliersView.tsx`

- **IMPLEMENT**: New tab view with:
  1. Left panel: ingredient selector (dropdown from `agnesApi.ingredients()`) + three `WeightSelector` components + "Apply Weights" button
  2. Right panel: ranked supplier table with `ScoreBar` per supplier + detail columns
- **PATTERN**: `useQuery` for data, `useMutation`-style `useState` for pending weight edits, `LoadingState`/`ErrorState`/`EmptyState` from `components/shared/States`
- **USE**: shadcn `Select` for ingredient picker, `Button` for apply, `ScoreBar` for scores, `GradePill` for ingredient grade
- **STATE**: Local `pendingWeights` state (not saved until user clicks Apply); saved weights fetched via `useQuery(["scoring-weights"])`

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign, Clock, Star, ChevronDown } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import { ScoringWeights, ScoredSupplier } from "@/types/agnes";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { WeightSelector } from "@/components/shared/WeightSelector";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SuppliersView() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pendingWeights, setPendingWeights] = useState<ScoringWeights>({ price: 3, lead_time: 3, quality: 3 });

  const { data: ingredients } = useQuery({
    queryKey: ["ingredients"],
    queryFn: () => agnesApi.ingredients(),
  });

  const { data: savedWeights } = useQuery({
    queryKey: ["scoring-weights"],
    queryFn: () => agnesApi.scoringWeights(),
    onSuccess: (w) => setPendingWeights(w),  // sync local state once loaded
  });

  const { data: suppliersData, isLoading, error } = useQuery({
    queryKey: ["scored-suppliers", selectedId, savedWeights],
    queryFn: () => agnesApi.scoredSuppliers(selectedId!),
    enabled: !!selectedId,
  });

  const saveMutation = useMutation({
    mutationFn: (w: ScoringWeights) => agnesApi.saveScoringWeights(w),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scoring-weights"] });
      qc.invalidateQueries({ queryKey: ["scored-suppliers"] });
    },
  });

  const handleApply = () => saveMutation.mutate(pendingWeights);

  return (
    <div className="flex gap-6 p-5 h-full">
      {/* Left: Config panel */}
      <div className="w-64 shrink-0 flex flex-col gap-5">
        <div>
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">Ingredient</p>
          <Select onValueChange={(v) => setSelectedId(Number(v))}>
            <SelectTrigger className="w-full text-[13px]">
              <SelectValue placeholder="Select ingredient…" />
            </SelectTrigger>
            <SelectContent>
              {(ingredients ?? []).map((ing) => (
                <SelectItem key={ing.id} value={String(ing.id)}>
                  {ing.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="border-t border-border pt-4">
          <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide mb-3">Scoring Weights</p>
          <div className="flex flex-col gap-4">
            <WeightSelector
              label="Price"
              description="$/kg importance"
              value={pendingWeights.price}
              onChange={(v) => setPendingWeights((w) => ({ ...w, price: v }))}
              icon={<DollarSign size={13} />}
            />
            <WeightSelector
              label="Lead Time"
              description="Days to delivery"
              value={pendingWeights.lead_time}
              onChange={(v) => setPendingWeights((w) => ({ ...w, lead_time: v }))}
              icon={<Clock size={13} />}
            />
            <WeightSelector
              label="Quality"
              description="Purity, grade, confidence"
              value={pendingWeights.quality}
              onChange={(v) => setPendingWeights((w) => ({ ...w, quality: v }))}
              icon={<Star size={13} />}
            />
          </div>
          <Button
            size="sm"
            className="w-full mt-4 text-[12px]"
            onClick={handleApply}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? "Saving…" : "Apply Weights"}
          </Button>
        </div>
      </div>

      {/* Right: Supplier table */}
      <div className="flex-1 min-w-0">
        {!selectedId ? (
          <EmptyState title="No ingredient selected" body="Choose an ingredient from the left panel to see ranked suppliers." />
        ) : isLoading ? (
          <LoadingState label="Loading suppliers…" />
        ) : error ? (
          <ErrorState message="Failed to load supplier data." />
        ) : !suppliersData?.suppliers?.length ? (
          <EmptyState title="No supplier data" body="No commercial data yet for this ingredient. Run the Molport enrichment to populate." />
        ) : (
          <div className="flex flex-col gap-2">
            <div
              className="grid gap-x-3 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide px-3 pb-1"
              style={{ gridTemplateColumns: "1.8fr 80px 80px 80px 80px 2fr" }}
            >
              <span>Supplier</span>
              <span>Price/kg</span>
              <span>Lead Time</span>
              <span>Purity</span>
              <span>Country</span>
              <span>Weighted Score</span>
            </div>
            {suppliersData.suppliers.map((sup) => (
              <SupplierRow key={sup.SupplierId} supplier={sup} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SupplierRow({ supplier: s }: { supplier: ScoredSupplier }) {
  return (
    <div
      className="grid gap-x-3 items-center px-3 py-2.5 rounded-lg border border-border bg-background hover:bg-surface-hover/60 transition-colors text-[13px]"
      style={{ gridTemplateColumns: "1.8fr 80px 80px 80px 80px 2fr" }}
    >
      <span className="font-medium truncate">{s.supplier_name}</span>
      <span className="font-mono text-[12px]">
        {s.Price_USD_Per_KG != null ? `$${s.Price_USD_Per_KG.toFixed(2)}` : "—"}
      </span>
      <span className="font-mono text-[12px]">
        {s.Lead_Time_Days != null ? `${s.Lead_Time_Days}d` : "—"}
      </span>
      <span className="font-mono text-[12px]">
        {s.Purity_Pct != null ? `${s.Purity_Pct}%` : "—"}
      </span>
      <span className="text-[12px] text-muted-foreground">{s.Country_Origin ?? "—"}</span>
      <ScoreBar score={s.weighted_score} />
    </div>
  );
}
```

- **VALIDATE**: `npm run build` in orchestration/ui — zero TypeScript errors

---

### TASK 16: UPDATE `orchestration/ui/src/components/layout/Sidebar.tsx`

- **ADD** "suppliers" entry to the `ITEMS` array:

```typescript
// Add this import at the top (with other lucide imports):
import { Package } from "lucide-react";

// Add to ITEMS array after the "compliance" entry:
{ key: "suppliers" as TabKey, label: "Suppliers", icon: Package },
```

- **GOTCHA**: `TabKey` type is defined inline in `Sidebar.tsx` — also add `"suppliers"` to the union type
- **VALIDATE**: Sidebar renders with new tab visible

---

### TASK 17: UPDATE `orchestration/ui/src/pages/Index.tsx`

- **ADD** "suppliers" to `TAB_TITLES`, the render switch, and import `SuppliersView`:

```typescript
// Add to imports:
import { SuppliersView } from "@/components/views/SuppliersView";

// Add to TAB_TITLES:
suppliers: { title: "Supplier Scoring", subtitle: "Rank suppliers by price, lead time, and quality — adjustable weights." },

// Add to tab render switch (before the default/else):
{tab === "suppliers" && <SuppliersView />}
```

- **GOTCHA**: `TabKey` type must also include `"suppliers"` — add it to the union in both `Index.tsx` and `Sidebar.tsx`
- **VALIDATE**: `npm run build` — zero errors; `npm run dev` in orchestration/ui, navigate to Suppliers tab

---

### TASK 18: RUN MIGRATION + DATA LOAD

Execute in order:
```bash
cd "/home/developer/Projects/Spherecast Agnes"

# 1. Run migration (creates FDA_Inactive_Ingredient, Scoring_Config, adds openfda_adverse_event_count)
PYTHONPATH=. python enrichment/db_migrate_fda_scoring.py

# 2. Load FDA IID CSV (9,067 rows → ~53 canonical matches)
PYTHONPATH=. python enrichment/sources/fda_iid.py

# 3. Run openFDA adverse event backfill (~135 UNII-bearing canonicals, ~35s)
PYTHONPATH=. python enrichment/backfill_openfda.py

# 4. Build frontend
cd orchestration/ui && npm run build && cd ../..

# 5. Start API server
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
```

---

## TESTING STRATEGY

### Unit Tests

No formal test framework found in the project (no `tests/` directory, no pytest config). Validate via direct Python import + print assertions and curl smoke tests.

### Integration Checks (Manual)

After server is running at `http://localhost:8000`:

```bash
# Check new tables exist
sqlite3 db_enriched.sqlite ".tables" | tr ' ' '\n' | sort

# FDA IID data loaded
sqlite3 db_enriched.sqlite "SELECT COUNT(*) FROM FDA_Inactive_Ingredient;"
# Expected: 9067

# Matches to canonicals
sqlite3 db_enriched.sqlite "SELECT COUNT(*) FROM FDA_Inactive_Ingredient WHERE CanonicalIngredientId IS NOT NULL;"
# Expected: ~1150 (multiple routes per ingredient)

# Scoring_Config defaults
sqlite3 db_enriched.sqlite "SELECT * FROM Scoring_Config;"
# Expected: weight_price=3.0, weight_lead_time=3.0, weight_quality=3.0

# openFDA adverse events
sqlite3 db_enriched.sqlite "SELECT Name, openfda_adverse_event_count FROM Ingredient_Canonical WHERE openfda_adverse_event_count IS NOT NULL LIMIT 5;"
```

### Edge Cases

- **Supplier_Commercial is empty** (currently 0 rows): `scored_suppliers` endpoint returns `{ suppliers: [], count: 0 }` — not a 404. SuppliersView shows EmptyState.
- **Ingredient with no UNII**: `fda_iid.py` skips UNII matching but still inserts row with `CanonicalIngredientId=NULL`
- **openFDA 404**: `adverse_event_count()` returns 0 and caches the miss — prevents re-querying
- **Weight inputs**: Backend uses `confloat(ge=1.0, le=5.0)` — validation rejects out-of-range; frontend sliders enforce 1-5 visually
- **Single supplier** (min==max for normalization): `_norm()` returns 0.5 — score is quality-only effectively; correct behavior

---

## VALIDATION COMMANDS

### Level 1: Python imports

```bash
cd "/home/developer/Projects/Spherecast Agnes"
PYTHONPATH=. python -c "from enrichment.sources.fda_iid import load_iir; print('fda_iid ok')"
PYTHONPATH=. python -c "from enrichment.sources.openfda import OpenFDAClient; print('openfda ok')"
PYTHONPATH=. python -c "from reasoning.supplier_scorer import SupplierScorer; print(SupplierScorer().get_weights())"
PYTHONPATH=. python -c "from orchestration.api.routes.scoring import router; print('scoring router ok')"
PYTHONPATH=. python -c "from orchestration.api.main import app; print([r.path for r in app.routes if 'scoring' in r.path])"
```

### Level 2: Frontend build

```bash
cd "/home/developer/Projects/Spherecast Agnes/orchestration/ui"
npm run build 2>&1 | tail -10
# Expected: "built in X.XXs" with zero errors
```

### Level 3: API endpoints (server must be running)

```bash
# Scoring weights
curl -s http://localhost:8000/api/scoring/weights | python3 -m json.tool
# Expected: {"price": 3.0, "lead_time": 3.0, "quality": 3.0}

# Save weights
curl -s -X POST http://localhost:8000/api/scoring/weights \
  -H "Content-Type: application/json" \
  -d '{"price": 5, "lead_time": 4, "quality": 3}' | python3 -m json.tool
# Expected: {"status": "saved", ...}

# Get weights back (verify persistence)
curl -s http://localhost:8000/api/scoring/weights | python3 -m json.tool
# Expected: {"price": 5.0, "lead_time": 4.0, "quality": 3.0}

# Scored suppliers (will be empty until Molport data populated)
curl -s http://localhost:8000/api/scoring/suppliers/1 | python3 -m json.tool

# FDA limits
curl -s http://localhost:8000/api/data/fda-limits/1 | python3 -m json.tool

# Ingredient safety
curl -s http://localhost:8000/api/data/ingredients/1/safety | python3 -m json.tool

# Health check (regression)
curl -s http://localhost:8000/health
```

### Level 4: Manual UI validation

1. Start server + serve frontend: `PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000`
2. Navigate to `http://localhost:8000`
3. Click "Suppliers" tab — verify it loads without error
4. Select any ingredient from dropdown
5. Adjust weight sliders → click "Apply Weights"
6. Refresh — verify weights persist (should reload same values)
7. Navigate to another tab and back — no visual regression

---

## ACCEPTANCE CRITERIA

- [ ] `FDA_Inactive_Ingredient` table created with 9,067 rows loaded
- [ ] 53 canonical ingredients matched to IID data by UNII
- [ ] `Scoring_Config` table created with default weights (3.0, 3.0, 3.0)
- [ ] `openfda_adverse_event_count` column added to `Ingredient_Canonical`
- [ ] openFDA adverse events backfilled for all UNII-bearing canonicals
- [ ] `compliance_reasoner_tool.py` returns `fda_iid_max_daily_mg` and `fda_iid_data_available` fields
- [ ] `GET /api/scoring/weights` returns current weights
- [ ] `POST /api/scoring/weights` persists new weights; verified by re-fetch
- [ ] `GET /api/scoring/suppliers/{id}` returns scored+ranked list (empty list when no Molport data — not 404)
- [ ] `GET /api/data/fda-limits/{id}` returns IID route/form limits for matched ingredient
- [ ] `GET /api/data/ingredients/{id}/safety` returns AE count + FDA limits
- [ ] Frontend builds with zero TypeScript errors
- [ ] "Suppliers" tab visible in sidebar and renders `SuppliersView`
- [ ] Weight selectors persist via `POST /api/scoring/weights` on "Apply Weights" click
- [ ] No regressions in existing tabs (Opportunities, Proposals, Compliance, Ingredients, Runs)

---

## COMPLETION CHECKLIST

- [ ] Tasks 1-2: Schema + migration created and run
- [ ] Task 3: FDA IID CSV loader created and run
- [ ] Task 4: compliance_reasoner_tool.py augmented
- [ ] Task 5: /api/data/fda-limits/{id} endpoint added
- [ ] Tasks 6-7: openFDA client + backfill created and run
- [ ] Task 8: /api/data/ingredients/{id}/safety endpoint added
- [ ] Task 9: supplier_scorer.py created
- [ ] Tasks 10-11: scoring.py router created + registered in main.py
- [ ] Tasks 12-13: Frontend types + API client updated
- [ ] Task 14: WeightSelector component created
- [ ] Task 15: SuppliersView created
- [ ] Tasks 16-17: Sidebar + Index updated with new tab
- [ ] Task 18: All data loaded, frontend built, server running
- [ ] All Level 1-4 validation commands pass

---

## NOTES

**Supplier_Commercial is currently empty** — `scored_suppliers` will return empty lists until Molport FTP bulk download is imported or manual data is entered. The scoring engine is correct and will activate as soon as rows exist.

**openFDA rate limiting**: With the API key (240 req/min), the full backfill of ~135 UNII-bearing canonicals takes ~35 seconds. Without key: same throttle applies but daily cap is lower. Key is already in `.env`.

**Change_Log_Data.csv**: The `load_iir()` function currently only loads `IIR_OCOMM.csv` (the full current snapshot). The changelog CSV tracks quarterly updates. Recommend a future job that applies changelog diffs to keep IID data current — not in scope for this plan.

**Weight normalization**: User inputs are 1-5 integers. The scorer treats them as raw weights in a weighted average (not percentages). A weight of 5 vs 1 means 5x more influence, not 500%. This is intentional — the UI labels (1=low, 5=high priority) communicate the relative scale naturally.

**ComplianceReasoner is not modified**: The `reasoning/compliance_reasoner.py` JURISDICTION_PACKS are hand-curated and tested. The FDA IID gate is added only in `orchestration/tools/compliance_reasoner_tool.py` (the DAG wrapper), keeping the core reasoner clean and testable independently.

**Frontend package manager**: CLAUDE.md says `bun run build` for the UI; `package.json` uses standard npm scripts. The `pull-ui.sh` script uses bun. Use `npm run build` for local development builds; use `bun run build` if running via `pull-ui.sh`. Both work — bun is faster.
