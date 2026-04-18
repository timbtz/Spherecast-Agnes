# Feature: Schema v1.1 Migration, Phase 1 Backfill, UNII Dedup, Phase 2+3 Re-Run

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to SQLite's `ALTER TABLE` limitations, existing cache patterns in `pubchem.py` and `dsld.py`, and the exact column names in each enrichment table.

---

## Feature Description

Agnes's `db_enriched.sqlite` is on schema v1.0, which is missing 15 columns across 6 tables
required for Phase 3 commercial lookups, UNII-based deduplication, and defensible Phase 4
scoring. This plan migrates the schema to v1.1 in-place, backfills SMILES and UNII_Code from
already-cached PubChem/DSLD responses, merges duplicate canonical rows sharing a UNII, fixes
Phase 2 ingredient matching (70→55 threshold, UNII exact match, brand synonyms, NP unit
handling), and runs Phase 3 compliance enrichment from DSLD label claims.

## User Story

As a pipeline operator (timbtz),
I want to run a sequence of scripts that migrate the schema, backfill cross-reference fields,
merge duplicate canonicals, and re-run Phases 2 and 3,
So that `db_enriched.sqlite` satisfies every Phase 1–3 validation query and Phase 4 sees
a clean, deduplicated dataset with SMILES, UNII, BOM quantities, and compliance data.

## Problem Statement

- Schema v1.0 is missing `SMILES`, `UNII_Code`, `MatchScore`, and 12 other columns
- Vitamin C (25 co.) and Ascorbic Acid (17 co.) are two canonical rows for the same UNII `PQ6CK8PD0R` — the #1 consolidation candidate (42 co.) is invisible to Phase 4
- Phase 2 BOM coverage is 19.2% (294/1528) — too low for reliable Phase 4 scoring
- Phase 3 compliance has 0 rows despite DSLD label data being cached
- `Supplier_Commercial.Confidence` is stored as TEXT instead of REAL

## Solution Statement

Seven sequential steps: (A) schema migration script, (B) Phase 1 backfill (SMILES + UNII +
MatchScore + display name fix), (C) UNII deduplication merge, (D) Phase 2 threshold/matching
fixes + re-run, (E) Phase 3 compliance re-run with complete cert signal map, (F) Molport
client stub (no-ops if key absent), (G) Ingredient_Substitution seeding from UNII merge log.

## Feature Metadata

**Feature Type**: Enhancement / Bug Fix / Data Migration  
**Estimated Complexity**: High (7 coordinated changes across 12 files)  
**Primary Systems Affected**: `schema/`, `enrichment/`, `reasoning/`  
**Dependencies**: PubChem PUG REST (no key), DSLD v9 (`DSLD_API_KEY`), Molport v3 (`MOLPORT_API_KEY` — optional)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `schema/enriched_schema.sql` (lines 1–170) — v1.0 schema; verify every column name before writing migration DDL
- `enrichment/db_bootstrap.py` (lines 176–259) — bootstrap entry point; add migration call at line 196 after schema apply
- `enrichment/db_bootstrap.py` (lines 189–204) — `bootstrap()` function pattern: `conn.executescript()` → commit → `_validate()` — mirror this for migration
- `enrichment/normalizers/ingredient_normalizer.py` (lines 127–175) — `_upsert_mapping()` and `_get_or_create_canonical()` — the insert at lines 159–174 must also write `MatchScore` after schema migration
- `enrichment/normalizers/ingredient_normalizer.py` (lines 130–136) — `INSERT OR REPLACE INTO SKU_To_Canonical` — the column list here must gain `MatchScore`
- `enrichment/normalizers/fuzzy_matcher.py` (lines 22–52) — `FuzzyMatcher.match()` returns `raw_score` (line 40) — this is the MatchScore value to store
- `enrichment/sources/pubchem.py` (lines 29–77) — `PubChemClient.lookup()` — pattern for cache-first API call to replicate in `get_isomeric_smiles()`
- `enrichment/sources/pubchem.py` (lines 109–138) — `_get_cache()` / `_set_cache()` — exact cache read/write pattern; replicate for SMILES cache key `smiles_{cid}`
- `enrichment/sources/pubchem.py` (lines 143–164) — `_throttle()` and `_get()` — reuse these module-level helpers, do not reimplement
- `enrichment/sources/dsld.py` — `DSLDClient` full file — verify `search_ingredient()` returns dict with `uniiCode` field (or None); confirm cache key pattern
- `enrichment/enrichers/quantity_enricher.py` (lines 175–184) — `_match_ingredient_to_amounts()` — this is the 70-threshold site to lower to 55
- `enrichment/enrichers/quantity_enricher.py` (lines 96–130) — `_fingerprint_match()` — add UNII-based exact match before fuzzy fallback here
- `enrichment/enrichers/quantity_enricher.py` (lines 132–173) — `_store_amounts()` — `INSERT OR REPLACE INTO BOM_Component_Quantity` column list; add `ServingsPerContainer`, `OffMarket` (rename from `Off_Market`), `DSLD_Label_Id` after schema migration
- `enrichment/enrichers/compliance_enricher.py` (lines 18–28) — `CERT_KEYWORDS` dict — replace with full `CERT_SIGNAL_MAP` from PRD §7 Step 5; current dict has only 9 keys, missing `cGMP`, `Halal`, `BSCG` keywords
- `enrichment/enrichers/compliance_enricher.py` (lines 69–98) — `_extract_and_store_certs()` — add `Off_Market_Warning` column write; add `offMarket` gate per PRD §7 Step 5
- `enrichment/parsers/sku_parser.py` (lines 30–31) — `COMPLEX_MARKERS` frozenset — add Sucralose artifact guard here (not in COMPLEX_MARKERS; add separate `KNOWN_NON_INGREDIENTS` set at module top)
- `enrichment/parsers/sku_parser.py` (lines 58–78) — `parse_sku()` — add early return `None` check for `KNOWN_NON_INGREDIENTS`

### New Files to Create

- `enrichment/db_migrate_v11.py` — idempotent v1.0→v1.1 migration; called by `db_bootstrap.py`
- `enrichment/backfill_phase1.py` — SMILES + UNII + MatchScore backfill; cache-first; logs to `Enrichment_Run_Log`
- `enrichment/sources/molport.py` — Molport v3 CAS-first → SMILES fallback client; no-ops if `MOLPORT_API_KEY` absent

### Relevant Documentation — READ BEFORE IMPLEMENTING

- `Orchestration/References/dsld-integration.md` — DSLD v9 API: exact endpoint paths, header name `X-Api-Key`, response shape for ingredient search (field `uniiCode` vs `unii_code`)
- `Orchestration/References/molport-integration.md` — Molport API: Title Case field names with spaces ("Supplier Name", "Molport Id"), response structure, auth pattern
- `Orchestration/References/pubchem-integration.md` — PubChem SMILES endpoint: `GET /rest/pug/compound/cid/{cid}/property/IsomericSMILES/JSON` → `PropertyTable.Properties[0].IsomericSMILES`
- `Orchestration/PRDs/SQLBackendPRD.md` §7 — Full implementation specifications with exact pseudocode for every step
- `Orchestration/PRDs/SQLBackendPRD.md` §10 — Precise success criteria SQL for every validation check

### Patterns to Follow

**Cache read/write pattern** (from `pubchem.py:109–138`):
```python
# Read
row = conn.execute(
    "SELECT Response FROM API_Response_Cache WHERE Source = ? AND Cache_Key = ? "
    "AND (TTL_Days = 0 OR julianday('now') - julianday(Fetched_At) < TTL_Days)",
    (source, key),
).fetchone()
if row is not None:
    return json.loads(row[0]) if row[0] != "null" else None

# Write
conn.execute(
    "INSERT OR REPLACE INTO API_Response_Cache (Source, Cache_Key, Response, TTL_Days) VALUES (?, ?, ?, 0)",
    (source, key, json.dumps(result)),
)
```

**Enrichment_Run_Log pattern** (from `ingredient_normalizer.py:177–188`):
```python
conn.execute(
    "INSERT INTO Enrichment_Run_Log (ProductId, Phase, Step, Status, Confidence, Method, Error_Msg) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (product_id, phase_num, step_name, status, confidence, method, error_msg),
)
```

**Idempotent ALTER TABLE** (new pattern for migration):
```python
existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(TableName)")}
if "NewColumn" not in existing_cols:
    conn.execute("ALTER TABLE TableName ADD COLUMN NewColumn TEXT")
```

**INSERT OR REPLACE pattern** (from `quantity_enricher.py:156–169`): Always use `INSERT OR REPLACE` for all enrichment writes; never plain `INSERT`.

**SQLite Supplier_Commercial Confidence fix**: `ALTER TABLE ... MODIFY` does not exist in SQLite. Since `Supplier_Commercial` has 0 rows, use: CREATE new table with correct schema → DROP old → RENAME. Use `PRAGMA table_info()` to detect if `Confidence` is already `REAL` (check column type string).

**Thread-safety**: Each thread opens its own `sqlite3.connect()`. Never share a connection across threads. See `quantity_enricher.py:_store_amounts()` (new connection per call) vs `_fingerprint_match()` (passed connection).

**Logging**: Use `logging.getLogger("agnes.<module>")` at module top. `logger.info()` for progress, `logger.warning()` for soft failures, `logger.error()` for hard failures. No `print()` except in `db_bootstrap.py` and `db_migrate_v11.py` where bootstrap output is expected.

---

## IMPLEMENTATION PLAN

### Phase A — Schema Migration & Bootstrap Integration

Write `db_migrate_v11.py` that applies all v1.1 DDL idempotently. Update `db_bootstrap.py` to call it. Update `schema/enriched_schema.sql` with v1.1 DDL.

**Tasks:**
- Write migration script with PRAGMA-guarded ALTER TABLE for every new column
- Handle `Supplier_Commercial.Confidence` TEXT→REAL via CREATE/DROP/RENAME (0-row table)
- Update `db_bootstrap.py:196` to call `migrate_v11(conn)` after `conn.executescript(schema_sql)`
- Update `schema/enriched_schema.sql` with v1.1 column definitions (for fresh bootstraps)

### Phase B — Phase 1 Backfill

Write `backfill_phase1.py` with three functions: `backfill_smiles()`, `backfill_unii()`, `backfill_match_scores()`. Add `get_isomeric_smiles(cid)` to `pubchem.py`. Fix display name selection in `ingredient_normalizer.py`. Fix Sucralose artifact in `sku_parser.py`.

**Tasks:**
- Add `get_isomeric_smiles(cid)` to `PubChemClient` using cache key `smiles_{cid}`, endpoint `/property/IsomericSMILES/JSON`
- Write `backfill_smiles()`: query canonicals where `PubChem_CID IS NOT NULL AND SMILES IS NULL` → call `get_isomeric_smiles()` → UPDATE → log to `Enrichment_Run_Log` with `Step='smiles_backfill'`
- Write `backfill_unii()`: query canonicals where `UNII_Code IS NULL` → call DSLD `search_ingredient()` → if `uniiCode` in result → UPDATE; add 0.25s sleep for uncached calls
- Write `backfill_match_scores()`: query `SKU_To_Canonical WHERE MatchScore IS NULL AND MatchMethod = 'fuzzy'` → recompute `token_set_ratio` against canonical name → UPDATE (no API calls)
- Fix `ingredient_normalizer.py:_get_or_create_canonical()` INSERT (lines 159–174): pass `MatchScore` value from `result.get("fuzzy_score")` in the `_upsert_mapping` call; update `INSERT OR REPLACE INTO SKU_To_Canonical` column list to include `MatchScore`
- Fix display name in `pubchem.py:_pick_preferred_name()` (lines 175–189): current filter skips IUPAC but still returns them when no short name found; add DSLD preferred name priority if passed as argument
- Fix `ingredient_normalizer.py:_normalize()` (lines 94–125): after PubChem lookup, if DSLD returns a `preferredName`, override the PubChem name via `result["name"] = dsld_preferred` before returning
- Add `KNOWN_NON_INGREDIENTS` guard to `sku_parser.py`: add set at module top, return `None` in `parse_sku()` if slug matches

### Phase C — UNII Deduplication

Add `dedup_by_unii(db_conn)` to `fuzzy_matcher.py`. Return a merge log for substitution seeding.

**Tasks:**
- Add `dedup_by_unii(conn)` function to `fuzzy_matcher.py`: find UNII groups > 1, keep lowest Id, re-point `SKU_To_Canonical.CanonicalId`, re-point both FK columns in `Ingredient_Substitution`, delete duplicates
- Use `UPDATE OR REPLACE` when re-pointing `SKU_To_Canonical` to handle PK conflicts (two merged ingredients appearing in same product)
- Log each merge: `print(f"UNII {unii}: merged {drop_ids} → {keep_id} ({drop_name}→{keep_name})")`
- Return `list[tuple[int, int, str]]` of `(keep_id, drop_id, unii_code)` for use by substitution seeder
- Spot-check: run `SELECT UNII_Code, COUNT(*), GROUP_CONCAT(Name) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1` before and after

### Phase D — Phase 2 Coverage Improvement

Fix `quantity_enricher.py`: lower threshold 70→55, add UNII-based exact match tier, expand brand synonym table, handle NP units as NULL, accept `offMarket=1` labels.

**Tasks:**
- Replace threshold `70` with `55` in `_match_ingredient_to_amounts()` (line 182)
- Add UNII-based match tier before fuzzy in `_match_ingredient_to_amounts()`: if canonical has `UNII_Code` and DSLD ingredient row has matching `uniiCode`, return immediately with confidence 0.95
- Add brand synonym dict `BRAND_SYNONYMS` at module top; in `_parse_fg_sku()` normalize company name via synonym lookup before DSLD search
- In `_store_amounts()`: handle `unit_val == 'NP'` → store `Amount=None, Unit=None` (not 'NP' string)
- Accept `offMarket=1` labels in `_fingerprint_match()` and `_enrich_product()`: no longer filter; set `Off_Market=1` flag in stored row
- After schema migration adds `ServingsPerContainer`: extract `servings_per_container` from DSLD label and store it

### Phase E — Phase 3 Compliance Fix

Replace `CERT_KEYWORDS` in `compliance_enricher.py` with full `CERT_SIGNAL_MAP` from PRD §7. Add source priority tiers. Add `Off_Market_Warning` write. Filter `offMarket=0` labels for compliance only (with warning row if only `offMarket=1` available).

**Tasks:**
- Replace `CERT_KEYWORDS` dict (lines 18–28) with full `CERT_SIGNAL_MAP` covering NSF, USP, InformedSport, BSCG, Organic, NonGMO, GlutenFree, Vegan, Halal, cGMP (10 keys)
- Add two-tier scan: `claims[].langualCodeDescription` (confidence 0.85) then `statements[].text` (confidence 0.65)
- Add `Off_Market_Warning` column write: if label has `offMarket=1`, set `Off_Market_Warning=1` in `Product_Compliance` row
- Gate compliance on `offMarket=0`: prefer on-market labels; if only off-market found, store with `Off_Market_Warning=1`
- Remove `found["none_identified"] = ("not_required", 0.60)` — do not insert placeholder rows for products with no certifications found (pollutes counts)

### Phase F — Molport Client Stub

Create `enrichment/sources/molport.py`. `CommercialEnricher` already exists as stub; wire it to call `MolportClient` when key is present.

**Tasks:**
- Create `MolportClient` class with `lookup_ingredient(canonical)`, `_load_by_cas(cas)`, `_search_by_smiles(smiles)`, `_load_by_molport_id(molport_id)`, `flatten_suppliers(molecule_data)` per PRD §7 Step 6
- Check `MOLPORT_API_KEY` in `.env` at init; if absent, log warning and no-op gracefully
- All Molport field names use Title Case with spaces: `"Supplier Name"`, `"Molport Id"`, `"Price"`, `"Amount"`, `"Measure"`, `"Last Update Date"` — do not assume snake_case
- All rows: `Price_Type='retail_proxy'`, `Grade_Unverified=1`
- Wire `commercial_enricher.py` to call `MolportClient` and store to `Supplier_Commercial` with v1.1 columns

### Phase G — Ingredient_Substitution Seeding

Add `seed_substitutions_from_unii_history()` to `reasoning/substitution_graph.py`. Pass the merge log from Phase C.

**Tasks:**
- Add `seed_substitutions_from_unii_history(conn, merge_log)` to `substitution_graph.py`: for each `(keep_id, drop_id, unii)`, INSERT `Ingredient_Substitution` row with `SubstitutionType='identical'`, `Score=1.0`, `Notes='Same UNII: {unii}'`, `Sources='["unii_dedup"]'`
- Curated substitution rules are already seeded in `db_bootstrap.py` (lines 36–173) — do NOT re-insert; verify count via `SELECT COUNT(*) FROM Ingredient_Substitution_Rule` ≥ 38

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order. Each is atomic and independently testable.

---

### TASK 1: UPDATE `schema/enriched_schema.sql`

- **IMPLEMENT**: Add v1.1 column definitions as comments/placeholders in the CREATE TABLE statements so fresh bootstraps include them. Alternatively, add them as separate `ALTER TABLE` blocks at end of file with `IF NOT EXISTS` note — but since SQLite `CREATE TABLE IF NOT EXISTS` won't add new columns to existing tables, the migration script is the real enforcement mechanism. Update the file header comment to `v1.1`.
- **CHANGES**:
  - `Ingredient_Canonical`: add `UNII_Code TEXT`, `Molport_Id TEXT`, `FDC_Id INTEGER`, `RxCUI TEXT`, `SMILES TEXT`, `Grade_Flag TEXT DEFAULT 'unknown'` to the CREATE TABLE definition
  - `SKU_To_Canonical`: add `MatchScore REAL` to CREATE TABLE definition
  - `BOM_Component_Quantity`: add `ServingsPerContainer REAL` to CREATE TABLE (DSLD_Label_Id and Off_Market already present in v1.0 — verify)
  - `Supplier_Commercial`: change `Confidence TEXT` → `Confidence REAL NOT NULL DEFAULT 0.0`; add 7 new columns
  - `Product_Compliance`: add `Off_Market_Warning INTEGER NOT NULL DEFAULT 0`
  - `Consolidation_Opportunity`: add 4 new columns
  - `Ingredient_Substitution`: add `Caveats TEXT`
- **GOTCHA**: `BOM_Component_Quantity` already has `DSLD_Label_Id` and `Off_Market` in v1.0 schema (verified at lines 57–58 of schema file) — do NOT add them again
- **VALIDATE**: `python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.executescript(open('schema/enriched_schema.sql').read()); print([r[1] for r in c.execute(\"PRAGMA table_info('Ingredient_Canonical')\")])"` — verify SMILES, UNII_Code appear

---

### TASK 2: CREATE `enrichment/db_migrate_v11.py`

- **IMPLEMENT**: Idempotent migration script. Reads `PRAGMA table_info()` before each ALTER. Handles Supplier_Commercial Confidence type fix via CREATE/COPY/DROP/RENAME. Writes one `Enrichment_Run_Log` row on completion.
- **IMPORTS**: `sqlite3`, `json`, `logging`; no third-party imports
- **PATTERN**: `db_bootstrap.py:189–204` for conn setup; `PRAGMA table_info()` idempotency pattern described in Patterns section above
- **KEY LOGIC**:
```python
def migrate_v11(conn: sqlite3.Connection) -> None:
    """Apply all v1.0 → v1.1 schema changes idempotently."""
    
    def _add_col(table, col, typedef):
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            print(f"  + {table}.{col}")
    
    # Ingredient_Canonical
    _add_col("Ingredient_Canonical", "UNII_Code", "TEXT")
    _add_col("Ingredient_Canonical", "Molport_Id", "TEXT")
    _add_col("Ingredient_Canonical", "FDC_Id", "INTEGER")
    _add_col("Ingredient_Canonical", "RxCUI", "TEXT")
    _add_col("Ingredient_Canonical", "SMILES", "TEXT")
    _add_col("Ingredient_Canonical", "Grade_Flag", "TEXT DEFAULT 'unknown'")
    
    # SKU_To_Canonical
    _add_col("SKU_To_Canonical", "MatchScore", "REAL")
    
    # BOM_Component_Quantity (ServingsPerContainer only; DSLD_Label_Id + Off_Market already in v1.0)
    _add_col("BOM_Component_Quantity", "ServingsPerContainer", "REAL")
    
    # Supplier_Commercial — fix Confidence type + add 7 new columns
    sc_cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(Supplier_Commercial)")}
    if sc_cols.get("Confidence") == "TEXT":
        # Rebuild table: 0 rows exist so no data migration needed
        conn.executescript("""
            CREATE TABLE Supplier_Commercial_new (
                SupplierId              INTEGER NOT NULL,
                CanonicalIngredientId   INTEGER NOT NULL,
                Price_USD_Per_KG        REAL,
                MOQ_KG                  REAL,
                Lead_Time_Days          INTEGER,
                Country_Origin          TEXT,
                Price_Type              TEXT,
                Price_Source            TEXT,
                Confidence              REAL NOT NULL DEFAULT 0.0,
                Source_URL              TEXT,
                Last_Updated            TEXT,
                Price_Qty_KG            REAL,
                Purity_Pct              REAL,
                Purity_Qualifier        TEXT,
                Grade_Unverified        INTEGER NOT NULL DEFAULT 1,
                Molport_Catalog_Id      TEXT,
                Data_Freshness_Days     INTEGER,
                Country_Shipping        TEXT,
                PRIMARY KEY (SupplierId, CanonicalIngredientId),
                FOREIGN KEY (SupplierId) REFERENCES Supplier(Id),
                FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
            );
            INSERT INTO Supplier_Commercial_new SELECT *, NULL, NULL, NULL, 1, NULL, NULL, NULL FROM Supplier_Commercial;
            DROP TABLE Supplier_Commercial;
            ALTER TABLE Supplier_Commercial_new RENAME TO Supplier_Commercial;
        """)
        print("  ✓ Supplier_Commercial rebuilt with Confidence REAL")
    else:
        # Already rebuilt; just add any missing columns
        for col, typedef in [
            ("Price_Qty_KG", "REAL"), ("Purity_Pct", "REAL"),
            ("Purity_Qualifier", "TEXT"), ("Grade_Unverified", "INTEGER NOT NULL DEFAULT 1"),
            ("Molport_Catalog_Id", "TEXT"), ("Data_Freshness_Days", "INTEGER"),
            ("Country_Shipping", "TEXT"),
        ]:
            _add_col("Supplier_Commercial", col, typedef)
    
    # Product_Compliance
    _add_col("Product_Compliance", "Off_Market_Warning", "INTEGER NOT NULL DEFAULT 0")
    
    # Consolidation_Opportunity
    _add_col("Consolidation_Opportunity", "Unique_SKU_Count", "INTEGER DEFAULT 0")
    _add_col("Consolidation_Opportunity", "Score_Formula_Component", "REAL")
    _add_col("Consolidation_Opportunity", "Score_LLM_Adjustment", "REAL")
    _add_col("Consolidation_Opportunity", "Compliance_Feasible", "INTEGER")
    
    # Ingredient_Substitution
    _add_col("Ingredient_Substitution", "Caveats", "TEXT")
    
    conn.commit()
    # Log migration
    try:
        conn.execute(
            "INSERT INTO Enrichment_Run_Log (ProductId, Phase, Step, Status, Confidence, Method) VALUES (NULL, 0, 'schema_migration_v11', 'success', 1.0, 'migration')"
        )
        conn.commit()
    except Exception:
        pass
    print("Schema v1.1 migration complete.")
```
- **GOTCHA**: The `INSERT INTO Supplier_Commercial_new SELECT *, NULL, NULL, NULL, 1, NULL, NULL, NULL FROM Supplier_Commercial` — the NULL count must exactly match the 7 new columns being added. Verify column count in original CREATE TABLE (10 data columns + 2 PK = 12 total → +7 new = 19 total).
- **VALIDATE**: `python enrichment/db_migrate_v11.py` should print all `+` lines and "migration complete" with no errors

---

### TASK 3: UPDATE `enrichment/db_bootstrap.py`

- **IMPLEMENT**: Import and call `migrate_v11` after schema apply; add `if __name__ == "__main__"` guard calls it too.
- **CHANGES** at lines 193–196:
```python
schema_sql = SCHEMA_FILE.read_text()
conn.executescript(schema_sql)
conn.commit()
print("Enriched schema applied.")

# NEW: apply v1.1 migration (idempotent — safe on fresh and existing DBs)
from enrichment.db_migrate_v11 import migrate_v11
migrate_v11(conn)
```
- **GOTCHA**: `migrate_v11` must be importable from `enrichment/db_migrate_v11.py` — verify no circular imports (it should only import `sqlite3`, `json`, `logging`)
- **VALIDATE**: `python enrichment/db_bootstrap.py --force` — verify "Schema v1.1 migration complete." in output; then `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print([r[1] for r in c.execute(\"PRAGMA table_info('Ingredient_Canonical')\")])"` shows `SMILES`, `UNII_Code`

---

### TASK 4: ADD `get_isomeric_smiles()` to `enrichment/sources/pubchem.py`

- **IMPLEMENT**: New method on `PubChemClient` that fetches IsomericSMILES for a CID. Cache key: `smiles_{cid}`. Endpoint: `GET /rest/pug/compound/cid/{cid}/property/IsomericSMILES/JSON`.
- **PATTERN**: `pubchem.py:33–77` (`lookup()` method) — identical cache-first structure
- **ADD after line 139** (end of `_set_cache` method):
```python
def get_isomeric_smiles(self, cid: int) -> str | None:
    """Return IsomericSMILES for a PubChem CID. Cache-first, permanent TTL."""
    cache_key = f"smiles_{cid}"
    in_cache, cached = self._get_cache(cache_key)
    if in_cache:
        return cached  # may be None (confirmed no SMILES for this CID)
    _throttle()
    url = f"{PUBCHEM_BASE}/cid/{cid}/property/IsomericSMILES/JSON"
    resp = _get(url)
    smiles = None
    if resp is not None:
        props = resp.json().get("PropertyTable", {}).get("Properties", [{}])
        smiles = props[0].get("IsomericSMILES") if props else None
    self._set_cache(cache_key, smiles)
    return smiles
```
- **GOTCHA**: `_get_cache` / `_set_cache` store JSON: `json.dumps(None)` → `"null"`, and `_get_cache` returns `None` for `"null"` strings (line 121). Returning `None` for a cached no-SMILES is correct — do not re-fetch.
- **VALIDATE**: `python -c "import sys; sys.path.insert(0,''); from enrichment.sources.pubchem import PubChemClient; c=PubChemClient(); print(c.get_isomeric_smiles(5280795))"` — should return ascorbic acid SMILES string

---

### TASK 5: CREATE `enrichment/backfill_phase1.py`

- **IMPLEMENT**: Three public functions: `backfill_smiles(db_path)`, `backfill_unii(db_path)`, `backfill_match_scores(db_path)`. `main()` entry point runs all three.
- **PATTERN**: `pubchem.py:109–138` for cache reads; `ingredient_normalizer.py:177–188` for log writes
- **STRUCTURE**:
```python
"""Phase 1 backfill: populate SMILES, UNII_Code, MatchScore on existing canonical rows."""
import json, logging, sqlite3, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_phase1")

def backfill_smiles(db_path=ENRICHED_DB):
    from enrichment.sources.pubchem import PubChemClient
    client = PubChemClient(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT Id, PubChem_CID FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL"
    ).fetchall()
    logger.info(f"SMILES backfill: {len(rows)} canonicals to process")
    for canonical_id, cid in rows:
        smiles = client.get_isomeric_smiles(cid)
        conn.execute("UPDATE Ingredient_Canonical SET SMILES = ? WHERE Id = ?", (smiles, canonical_id))
        status = "success" if smiles else "no_match"
        conn.execute(
            "INSERT INTO Enrichment_Run_Log (ProductId, Phase, Step, Status, Confidence, Method) VALUES (NULL, 1, 'smiles_backfill', ?, 0.97, 'pubchem')",
            (status,)
        )
    conn.commit()
    conn.close()
    logger.info(f"SMILES backfill complete: {len(rows)} rows processed")

def backfill_unii(db_path=ENRICHED_DB):
    from enrichment.sources.dsld import DSLDClient
    client = DSLDClient(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT Id, Name FROM Ingredient_Canonical WHERE UNII_Code IS NULL"
    ).fetchall()
    logger.info(f"UNII backfill: {len(rows)} canonicals to process")
    updated = 0
    for canonical_id, name in rows:
        result = client.search_ingredient(name)
        if result and result.get("uniiCode"):
            conn.execute("UPDATE Ingredient_Canonical SET UNII_Code = ? WHERE Id = ?",
                        (result["uniiCode"], canonical_id))
            updated += 1
        # Respect DSLD rate limit for uncached calls
        time.sleep(0.25)
    conn.commit()
    conn.close()
    logger.info(f"UNII backfill: {updated}/{len(rows)} rows populated")

def backfill_match_scores(db_path=ENRICHED_DB):
    """Re-compute MatchScore for fuzzy-matched SKU_To_Canonical rows (no API calls)."""
    from rapidfuzz import fuzz
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT stc.ProductId, stc.ExtractedName, ic.Name
        FROM SKU_To_Canonical stc
        JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
        WHERE stc.MatchScore IS NULL AND stc.MatchMethod = 'fuzzy'
    """).fetchall()
    logger.info(f"MatchScore backfill: {len(rows)} fuzzy rows to score")
    for product_id, extracted, canonical_name in rows:
        score = fuzz.token_set_ratio(extracted, canonical_name) if extracted else None
        conn.execute("UPDATE SKU_To_Canonical SET MatchScore = ? WHERE ProductId = ?",
                    (score, product_id))
    conn.commit()
    conn.close()
    logger.info("MatchScore backfill complete")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    backfill_smiles()
    backfill_unii()
    backfill_match_scores()
```
- **GOTCHA**: `backfill_unii()` uses `time.sleep(0.25)` unconditionally — DSLD client caches responses so cached calls return instantly. The sleep wastes time on cache hits but is safe. Optionally check if result was from cache (no sleep needed) vs fresh API call (sleep 0.25s) — but uniform sleep is simpler and safe.
- **GOTCHA**: Verify the DSLD `search_ingredient()` response dict key for UNII — it may be `"uniiCode"` or `"unii_code"` depending on DSLD v9 response shape. Check `dsld-integration.md` before assuming field name.
- **VALIDATE**: 
  - `python enrichment/backfill_phase1.py`
  - `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL').fetchone())"` → must be `(0,)`
  - `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL').fetchone())"` → must be ≥ 112

---

### TASK 6: FIX display name in `enrichment/normalizers/ingredient_normalizer.py`

- **IMPLEMENT**: In `_normalize()` (lines 94–125), after PubChem returns a result with IUPAC name, check if DSLD has a better `preferredName` and override. In `_upsert_mapping()` (lines 127–139), pass `fuzzy_score` to SKU_To_Canonical insert.
- **CHANGES at lines 99–109** (Tier 1 block):
```python
result = pubchem.lookup(name)
if result and result["confidence"] >= CONFIDENCE_THRESHOLD:
    # Override name with DSLD preferred name if available
    dsld_check = dsld.search_ingredient(name)
    if dsld_check and dsld_check.get("preferredName"):
        result["name"] = dsld_check["preferredName"]
    logger.debug(f"PubChem hit for '{name}' (conf={result['confidence']:.2f})")
    return result
```
- **CHANGES at lines 130–136** (`_upsert_mapping` INSERT):
```python
conn.execute(
    """INSERT OR REPLACE INTO SKU_To_Canonical
       (ProductId, CanonicalId, ExtractedName, MatchMethod, Confidence, MatchScore)
       VALUES (?, ?, ?, ?, ?, ?)""",
    (product_id, canonical_id, extracted_name,
     result.get("method", "unknown"), result.get("confidence", 0.0),
     result.get("fuzzy_score")),  # None for non-fuzzy methods
)
```
- **GOTCHA**: Adding the DSLD check in Tier 1 adds a DSLD API call for every PubChem hit. This is mitigated by DSLD's 30-day cache — but the backfill in Task 5 will have already populated most UNII responses. Only ~50 uncached calls expected. If DSLD rate-limiting becomes an issue, make this check opt-in via a flag.
- **GOTCHA**: `DSLDClient.search_ingredient()` may not return a `"preferredName"` key — check the actual return dict in `dsld.py` before assuming the key name
- **VALIDATE**: `python enrichment/pipeline.py --phase 1` (with a few test ingredients) — inspect cluster report; Ascorbic Acid should show common name not IUPAC

---

### TASK 7: FIX Sucralose artifact in `enrichment/parsers/sku_parser.py`

- **IMPLEMENT**: Add `KNOWN_NON_INGREDIENTS` set at module top; guard in `parse_sku()`.
- **ADD at line 31** (after `COMPLEX_MARKERS`):
```python
# SKU slugs that pattern-match as ingredients but are not (parser artifacts)
KNOWN_NON_INGREDIENTS: frozenset[str] = frozenset([
    "sucralose-cid-56038-13-2",
    "prop-65-warning",
])
```
- **CHANGE `parse_sku()` at line 58** (after regex match, before slug processing):
```python
slug = m.group(2)
if slug.lower() in KNOWN_NON_INGREDIENTS:
    logger.debug(f"Skipping known non-ingredient SKU slug: {slug}")
    return None
```
- **VALIDATE**: `python -c "from enrichment.parsers.sku_parser import parse_sku; print(parse_sku('RM-C30-sucralose-cid-56038-13-2-201fdf47', 1))"` → must print `None`

---

### TASK 8: ADD `dedup_by_unii()` to `enrichment/normalizers/fuzzy_matcher.py`

- **IMPLEMENT**: New standalone function (not a method) that takes a `sqlite3.Connection` and returns `list[tuple[int, int, str]]` merge log.
- **ADD at end of `fuzzy_matcher.py`** (after `FuzzyMatcher` class):
```python
def dedup_by_unii(conn: sqlite3.Connection) -> list[tuple[int, int, str]]:
    """
    Merge Ingredient_Canonical rows sharing a UNII_Code.
    Keeps the row with the lowest Id (earliest resolved). Re-points all FK references.
    Returns: list of (keep_id, drop_id, unii_code) for substitution seeding.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT UNII_Code, MIN(Id) AS keep_id, GROUP_CONCAT(Id) AS all_ids,
               GROUP_CONCAT(Name, '|||') AS all_names
        FROM Ingredient_Canonical
        WHERE UNII_Code IS NOT NULL
        GROUP BY UNII_Code
        HAVING COUNT(*) > 1
    """)
    groups = cur.fetchall()
    merge_log: list[tuple[int, int, str]] = []

    for unii, keep_id, all_ids_str, all_names_str in groups:
        all_ids = [int(x) for x in all_ids_str.split(",")]
        drop_ids = [i for i in all_ids if i != keep_id]
        all_names = all_names_str.split("|||")
        drop_names = [n for i, n in zip(all_ids, all_names) if i != keep_id]

        for drop_id, drop_name in zip(drop_ids, drop_names):
            # Re-point SKU_To_Canonical (PK on ProductId — use OR IGNORE to drop conflicts)
            cur.execute("""
                UPDATE OR IGNORE SKU_To_Canonical SET CanonicalId = ? WHERE CanonicalId = ?
            """, (keep_id, drop_id))
            # Delete any SKU_To_Canonical rows that couldn't be re-pointed (duplicate product)
            cur.execute("DELETE FROM SKU_To_Canonical WHERE CanonicalId = ?", (drop_id,))
            # Re-point Ingredient_Substitution FKs
            cur.execute("UPDATE OR IGNORE Ingredient_Substitution SET IngredientAId = ? WHERE IngredientAId = ?", (keep_id, drop_id))
            cur.execute("UPDATE OR IGNORE Ingredient_Substitution SET IngredientBId = ? WHERE IngredientBId = ?", (keep_id, drop_id))
            # Delete orphaned substitution rows (self-referencing after merge)
            cur.execute("DELETE FROM Ingredient_Substitution WHERE IngredientAId = IngredientBId")
            # Delete the duplicate canonical
            cur.execute("DELETE FROM Ingredient_Canonical WHERE Id = ?", (drop_id,))
            merge_log.append((keep_id, drop_id, unii))
            logger.info(f"UNII {unii}: merged {drop_name!r} (Id={drop_id}) → {keep_id!r} (Id={keep_id})")

    conn.commit()
    logger.info(f"UNII dedup complete: {len(merge_log)} canonical rows merged")
    return merge_log
```
- **GOTCHA**: `UPDATE OR REPLACE` on `SKU_To_Canonical` would delete the existing row with `keep_id` for the same `ProductId` (since PK is `ProductId`). Use `UPDATE OR IGNORE` + explicit DELETE of remaining rows instead to avoid silent data loss.
- **VALIDATE**:
  - `python -c "import sqlite3, sys; sys.path.insert(0,''); from enrichment.normalizers.fuzzy_matcher import dedup_by_unii; c=sqlite3.connect('db_enriched.sqlite'); log=dedup_by_unii(c); print(f'Merged: {len(log)} rows'); c.close()"`
  - Then: `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); r=c.execute('SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1').fetchall(); print(f\"Remaining dupes: {len(r)}\")"`  → must be `0`

---

### TASK 9: FIX `enrichment/enrichers/quantity_enricher.py`

Four changes: threshold 70→55, UNII exact match, brand synonyms, NP unit handling.

- **CHANGE 1 — Threshold at line 182**:
```python
# Before:
if best and best[1] >= 70:
# After:
if best and best[1] >= 55:
```

- **CHANGE 2 — UNII match in `_match_ingredient_to_amounts()`** (add before fuzzy, lines 175–184):
```python
def _match_ingredient_to_amounts(self, canonical_name: str, amounts: list[dict],
                                  unii_code: str | None = None) -> dict | None:
    # Tier 1: UNII exact match (highest confidence; no fuzzy needed)
    if unii_code:
        for amt in amounts:
            if amt.get("uniiCode") == unii_code:
                amt["confidence"] = 0.95
                return amt
    # Tier 2: Case-insensitive exact name match
    for amt in amounts:
        if canonical_name.lower() == amt["ingredient_name"].lower():
            amt["confidence"] = 0.90
            return amt
    # Tier 3: Fuzzy (token_set_ratio, threshold 55)
    from rapidfuzz import fuzz, process as fuzz_process
    dsld_names = [a["ingredient_name"] for a in amounts]
    best = fuzz_process.extractOne(canonical_name, dsld_names, scorer=fuzz.token_set_ratio)
    if best and best[1] >= 55:
        idx = dsld_names.index(best[0])
        return amounts[idx]
    return None
```

- **CHANGE 3 — Pass UNII to match call in `_store_amounts()`** (line 152 area): Fetch `UNII_Code` from `Ingredient_Canonical` alongside `Name`; pass to `_match_ingredient_to_amounts()`.
```python
canonical = conn.execute("""
    SELECT ic.Id, ic.Name, ic.UNII_Code FROM Ingredient_Canonical ic
    JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
    WHERE stc.ProductId = ?
""", (consumed_id,)).fetchone()
if not canonical:
    continue
_, canonical_name, unii_code = canonical
best_amt = self._match_ingredient_to_amounts(canonical_name, ingredients, unii_code)
```

- **CHANGE 4 — Brand synonyms and offMarket handling**: Add `BRAND_SYNONYMS` dict at module top. In `_parse_fg_sku()`, normalize company name via reverse lookup through synonyms. In `_fingerprint_match()` and `_enrich_product()`, remove any `offMarket` filter — all labels accepted, `off_market` flag is set in stored row.

- **CHANGE 5 — NP unit handling** in extracted DSLD ingredients (in `dsld.py::extract_label_ingredients()` or in `_store_amounts()`):
```python
unit_val = best_amt.get("unit")
amount_val = best_amt.get("amount")
if unit_val == "NP":
    unit_val = None
    amount_val = None
```

- **ADD `BRAND_SYNONYMS` at module top** (after imports):
```python
BRAND_SYNONYMS: dict[str, list[str]] = {
    "NOW Foods": ["NOW", "Now Foods", "Now"],
    "Thorne": ["Thorne FX", "Thorne Research"],
    "Garden of Life": ["Garden Of Life", "GOL"],
    "Nature Made": ["NatureMade", "Nature's Made"],
    "Jarrow Formulas": ["Jarrow"],
    "Life Extension": ["LEF", "Life Ext"],
    "Solgar": ["Solgar Inc"],
    "MegaFood": ["Mega Food"],
    "Rainbow Light": ["Rainbow Light Nutritional"],
    "New Chapter": ["New Chapter Inc"],
}
# Reverse map: variant → canonical
_BRAND_REVERSE: dict[str, str] = {
    v: k for k, vs in BRAND_SYNONYMS.items() for v in vs
}
```

- **GOTCHA**: The `_match_ingredient_to_amounts()` signature change adds `unii_code` parameter — update all call sites in `_store_amounts()`.
- **VALIDATE**:
  - `python enrichment/pipeline.py --phase 2`
  - `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*) FROM BOM_Component_Quantity').fetchone(), c.execute(\"SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Unit='NP'\").fetchone())"` → count ≥ 500; NP count = 0

---

### TASK 10: FIX `enrichment/enrichers/compliance_enricher.py`

Replace `CERT_KEYWORDS` with full `CERT_SIGNAL_MAP`, add two-tier scan, add `Off_Market_Warning`, remove placeholder rows.

- **REPLACE lines 18–28** entirely:
```python
CERT_SIGNAL_MAP: dict[str, str] = {
    "nsf": "NSF", "nsf certified": "NSF", "nsf international": "NSF", "nsf/ansi": "NSF",
    "usp verified": "USP", "usp dietary supplement": "USP", "usp": "USP",
    "informed sport": "InformedSport", "informed-sport": "InformedSport", "informed choice": "InformedSport",
    "bscg": "BSCG", "certified for sport": "BSCG", "banned substance": "BSCG",
    "organic": "Organic", "usda organic": "Organic", "certified organic": "Organic",
    "non-gmo": "NonGMO", "non gmo": "NonGMO", "non-gmo project": "NonGMO",
    "gluten-free": "GlutenFree", "gluten free": "GlutenFree", "gluten-free certified": "GlutenFree",
    "vegan": "Vegan", "certified vegan": "Vegan", "vegan society": "Vegan",
    "halal": "Halal",
    "cgmp": "cGMP", "gmp": "cGMP", "current good manufacturing": "cGMP",
    "kosher": "Kosher", "kosher certified": "Kosher",
}
```

- **REPLACE `_extract_and_store_certs()` (lines 69–98)**:
```python
def _extract_and_store_certs(self, product_id: int, label: dict) -> None:
    off_market = 1 if label.get("offMarket") == "1" or label.get("offMarket") is True else 0
    found: dict[str, tuple[str, float, int]] = {}  # cert → (status, confidence, off_market_warning)

    # Tier 1: claims[].langualCodeDescription (confidence 0.85)
    for claim in label.get("claims", []):
        desc = str(claim.get("langualCodeDescription", claim) if isinstance(claim, dict) else claim).lower()
        for signal, cert in CERT_SIGNAL_MAP.items():
            if signal in desc and cert not in found:
                found[cert] = ("claimed", 0.85, off_market)

    # Tier 2: statements[].text (confidence 0.65)
    for stmt in label.get("statements", []):
        text = str(stmt.get("text", "") if isinstance(stmt, dict) else stmt).lower()
        for signal, cert in CERT_SIGNAL_MAP.items():
            if signal in text and cert not in found:
                found[cert] = ("implied", 0.65, off_market)

    if not found:
        return  # No certs found — do not insert placeholder rows

    conn = sqlite3.connect(self.db_path)
    for cert, (status, confidence, off_mkt_warning) in found.items():
        conn.execute(
            """INSERT OR REPLACE INTO Product_Compliance
               (ProductId, Certification, Status, Source, Confidence, Off_Market_Warning)
               VALUES (?, ?, ?, 'dsld', ?, ?)""",
            (product_id, cert, status, confidence, off_mkt_warning),
        )
    conn.commit()
    conn.close()
```

- **GOTCHA**: The DSLD `claims[]` structure varies — some DSLD labels return claims as plain strings, others as dicts with `langualCodeDescription`. The `isinstance(claim, dict)` check handles both.
- **VALIDATE**:
  - `python enrichment/pipeline.py --phase 3`
  - `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute('SELECT COUNT(*), COUNT(DISTINCT ProductId), COUNT(DISTINCT Certification) FROM Product_Compliance').fetchone())"` → rows ≥ 28, products ≥ 20, certs ≥ 4

---

### TASK 11: CREATE `enrichment/sources/molport.py`

- **IMPLEMENT**: `MolportClient` with graceful no-op if key absent. Full lookup chain per PRD §7 Step 6.
- **PATTERN**: `pubchem.py:29–77` — identical class structure; use `SESSION` module-level requests.Session
- **STRUCTURE** (abbreviated):
```python
"""Molport v3 API client — CAS-first → SMILES fallback → supplier price rows.

WARNING: Molport API returns Title Case field names with spaces.
Use: data["Supplier Name"], data["Molport Id"], data["Price"], data["Amount"], data["Measure"]
Do NOT assume snake_case field names.

All prices are research/lab scale. Always set Price_Type='retail_proxy', Grade_Unverified=1.
"""
import json, logging, os, time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent.parent.parent
MOLPORT_BASE = "https://api.molport.com/api"
logger = logging.getLogger("agnes.molport")

class MolportClient:
    def __init__(self, db_path=None):
        self.api_key = os.getenv("MOLPORT_API_KEY")
        self.db_path = str(db_path) if db_path else None
        if not self.api_key:
            logger.warning("MOLPORT_API_KEY not set — MolportClient will no-op")

    def lookup_ingredient(self, canonical: dict) -> list[dict]:
        """CAS-first → SMILES fallback. Returns list of supplier rows or []."""
        if not self.api_key:
            return []
        result = None
        if canonical.get("cas_number"):
            result = self._load_by_cas(canonical["cas_number"])
        if not result and canonical.get("smiles"):
            molport_id = self._search_by_smiles(canonical["smiles"])
            if molport_id:
                result = self._load_by_molport_id(molport_id)
        if not result:
            return []
        return self.flatten_suppliers(result)

    def _load_by_cas(self, cas: str) -> dict | None:
        """POST to molecule/load endpoint. Returns molecule data dict or None."""
        url = f"{MOLPORT_BASE}/molecule/load"
        try:
            resp = requests.post(url, json={"molecule": cas, "apikey": self.api_key}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Data", {}).get("Molecule")
        except Exception as e:
            logger.warning(f"Molport CAS lookup failed for {cas}: {e}")
            return None

    def _search_by_smiles(self, smiles: str) -> str | None:
        url = f"{MOLPORT_BASE}/chemical-search/search"
        try:
            resp = requests.post(url, json={"Structure": smiles, "Search Type": 1, "apikey": self.api_key}, timeout=15)
            resp.raise_for_status()
            molecules = resp.json().get("Data", {}).get("Molecules", [])
            return molecules[0].get("Molport Id") if molecules else None
        except Exception as e:
            logger.warning(f"Molport SMILES search failed: {e}")
            return None

    def _load_by_molport_id(self, molport_id: str) -> dict | None:
        url = f"{MOLPORT_BASE}/molecule/load"
        try:
            resp = requests.post(url, json={"molportId": molport_id, "apikey": self.api_key}, timeout=15)
            resp.raise_for_status()
            return resp.json().get("Data", {}).get("Molecule")
        except Exception as e:
            logger.warning(f"Molport ID load failed for {molport_id}: {e}")
            return None

    def flatten_suppliers(self, molecule_data: dict) -> list[dict]:
        """Flatten Suppliers[].Catalogue[].Packings[] into row dicts.
        FIELD NAMES ARE TITLE CASE WITH SPACES — this is Molport's API convention."""
        rows = []
        for supplier in molecule_data.get("Suppliers", []):
            for catalogue in supplier.get("Catalogue", []):
                for packing in catalogue.get("Packings", []):
                    rows.append({
                        "supplier_name": supplier.get("Supplier Name"),
                        "price_usd": packing.get("Price"),
                        "amount_raw": packing.get("Amount"),
                        "measure": packing.get("Measure"),
                        "delivery_days": supplier.get("Delivery Days"),
                        "molport_catalog_id": catalogue.get("Molport Catalog Id"),
                        "last_update_date": catalogue.get("Last Update Date"),
                        "purity": catalogue.get("Purity"),
                        "price_type": "retail_proxy",
                        "grade_unverified": 1,
                    })
        return rows
```
- **GOTCHA**: Verify actual Molport v3 endpoint paths against `Orchestration/References/molport-integration.md` before finalizing — field names and endpoint URLs confirmed in that doc
- **VALIDATE**: `python -c "from enrichment.sources.molport import MolportClient; c=MolportClient(); print('no-op:', c.lookup_ingredient({'cas_number': '50-81-7'}))"` → prints `no-op: []` (key absent) without error

---

### TASK 12: ADD substitution seeding to `reasoning/substitution_graph.py`

- **IMPLEMENT**: Add `seed_substitutions_from_unii_history()` function. Call from a new entry point script or integrate into the dedup workflow.
- **PATTERN**: Existing `_seed_substitution_rules()` in `db_bootstrap.py:208–220` — `INSERT OR REPLACE` pattern
- **ADD to `substitution_graph.py`**:
```python
def seed_substitutions_from_unii_history(conn: sqlite3.Connection, merge_log: list[tuple[int, int, str]]) -> None:
    """Seed Ingredient_Substitution rows for pairs merged during UNII dedup.
    merge_log: list of (keep_id, drop_id, unii_code) from dedup_by_unii()."""
    inserted = 0
    for keep_id, drop_id, unii in merge_log:
        conn.execute("""
            INSERT OR REPLACE INTO Ingredient_Substitution
            (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
            VALUES (?, ?, 'identical', 1.0, ?, '["unii_dedup"]')
        """, (keep_id, drop_id, f"Same UNII: {unii}"))
        # Bidirectional edge
        conn.execute("""
            INSERT OR REPLACE INTO Ingredient_Substitution
            (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
            VALUES (?, ?, 'identical', 1.0, ?, '["unii_dedup"]')
        """, (drop_id, keep_id, f"Same UNII: {unii}"))
        inserted += 2
    conn.commit()
    logger.info(f"Seeded {inserted} substitution edges from UNII dedup merge log")
```
- **VALIDATE**: `python -c "import sqlite3; c=sqlite3.connect('db_enriched.sqlite'); print(c.execute(\"SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType='identical'\").fetchone())"` → ≥ 1

---

### TASK 13: WIRE dedup + substitution seeding into a runnable script

- **CREATE** `enrichment/run_dedup.py` (or add to `pipeline.py` as `--dedup` flag):
```python
"""Run UNII dedup and seed substitutions. Safe to re-run (idempotent)."""
import sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from enrichment.normalizers.fuzzy_matcher import dedup_by_unii
from reasoning.substitution_graph import seed_substitutions_from_unii_history

conn = sqlite3.connect(ROOT / "db_enriched.sqlite")
merge_log = dedup_by_unii(conn)
seed_substitutions_from_unii_history(conn, merge_log)
conn.close()
print(f"Done. Merged {len(merge_log)} canonical pairs.")
```
- **VALIDATE**: `python enrichment/run_dedup.py`

---

## TESTING STRATEGY

### Unit Tests

No formal test suite exists in this project. Validation is SQL-query-based (see Validation Commands).

### Integration Tests

Run the full pipeline after all changes and verify every SQL check in PRD §10 and §12.

### Edge Cases

- **Vitamin C merge**: After dedup, cluster report must show merged entry with company_count ≥ 35
- **SMILES NULL for Gelatin/Calcium**: These have no PubChem CID — `backfill_smiles()` skips them correctly (WHERE PubChem_CID IS NOT NULL)
- **NP units**: Phase 2 re-run must produce 0 rows with `Unit='NP'`
- **Compliance off-market**: Products with only `offMarket=1` labels should get compliance rows with `Off_Market_Warning=1`
- **Migration idempotency**: Running `db_migrate_v11.py` twice must produce no errors and no duplicate columns

---

## VALIDATION COMMANDS

### Level 1: Schema Check

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')

# Ingredient_Canonical v1.1 columns
ic_cols = {r[1] for r in c.execute('PRAGMA table_info(Ingredient_Canonical)')}
assert 'SMILES' in ic_cols, 'MISSING: Ingredient_Canonical.SMILES'
assert 'UNII_Code' in ic_cols, 'MISSING: Ingredient_Canonical.UNII_Code'
assert 'Grade_Flag' in ic_cols, 'MISSING: Ingredient_Canonical.Grade_Flag'
assert 'Molport_Id' in ic_cols, 'MISSING: Ingredient_Canonical.Molport_Id'

# SKU_To_Canonical.MatchScore
stc_cols = {r[1] for r in c.execute('PRAGMA table_info(SKU_To_Canonical)')}
assert 'MatchScore' in stc_cols, 'MISSING: SKU_To_Canonical.MatchScore'

# Supplier_Commercial.Confidence type = REAL
sc_info = {r[1]: r[2] for r in c.execute('PRAGMA table_info(Supplier_Commercial)')}
assert sc_info.get('Confidence') == 'REAL', f'Confidence type wrong: {sc_info.get(\"Confidence\")}'

# Product_Compliance.Off_Market_Warning
pc_cols = {r[1] for r in c.execute('PRAGMA table_info(Product_Compliance)')}
assert 'Off_Market_Warning' in pc_cols, 'MISSING: Product_Compliance.Off_Market_Warning'

print('PASS: All schema checks passed')
c.close()
"
```

### Level 2: Phase 1 Backfill Check

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
smiles_missing = c.execute('SELECT COUNT(*) FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL').fetchone()[0]
unii_count = c.execute('SELECT COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL').fetchone()[0]
smiles_log = c.execute(\"SELECT COUNT(*) FROM Enrichment_Run_Log WHERE Step='smiles_backfill'\").fetchone()[0]
print(f'SMILES missing (must be 0): {smiles_missing}')
print(f'UNII populated (must be ≥112): {unii_count}')
print(f'SMILES log entries: {smiles_log}')
assert smiles_missing == 0, 'FAIL: Some canonicals with PubChem_CID still missing SMILES'
assert unii_count >= 112, f'FAIL: UNII coverage too low ({unii_count}/279)'
c.close()
"
```

### Level 3: UNII Dedup Check

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
dupes = c.execute('SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1').fetchall()
print(f'UNII duplicates remaining (must be 0): {len(dupes)}')
if dupes: print('DUPES:', dupes)
vc_row = c.execute(\"SELECT ic.Name, COUNT(DISTINCT p.CompanyId) FROM Ingredient_Canonical ic JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id JOIN Product p ON p.Id = stc.ProductId WHERE ic.UNII_Code = 'PQ6CK8PD0R' GROUP BY ic.Id\").fetchone()
print(f'Vitamin C company count (must be ≥35): {vc_row}')
assert len(dupes) == 0, 'FAIL: UNII duplicates remain'
c.close()
"
```

### Level 4: Phase 2 Coverage Check

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
bom_total = c.execute('SELECT COUNT(*) FROM BOM_Component_Quantity').fetchone()[0]
np_rows = c.execute(\"SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Unit = 'NP'\").fetchone()[0]
distinct_fg = c.execute('SELECT COUNT(DISTINCT BOMId) FROM BOM_Component_Quantity').fetchone()[0]
print(f'BOM rows (must be ≥500): {bom_total}')
print(f'NP unit rows (must be 0): {np_rows}')
print(f'Distinct BOMs covered: {distinct_fg}')
assert bom_total >= 500, f'FAIL: BOM coverage too low ({bom_total})'
assert np_rows == 0, f'FAIL: NP unit rows present ({np_rows})'
c.close()
"
```

### Level 5: Phase 3 Compliance Check

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
r = c.execute('SELECT COUNT(*), COUNT(DISTINCT ProductId), COUNT(DISTINCT Certification) FROM Product_Compliance').fetchone()
print(f'Compliance rows (must be ≥28): {r[0]}, Products (≥20): {r[1]}, Cert types (≥4): {r[2]}')
certs = c.execute('SELECT DISTINCT Certification FROM Product_Compliance').fetchall()
print('Cert types found:', [r[0] for r in certs])
assert r[0] >= 28, f'FAIL: compliance rows too low ({r[0]})'
assert r[1] >= 20, f'FAIL: products covered too low ({r[1]})'
assert r[2] >= 4, f'FAIL: cert types too few ({r[2]})'
c.close()
"
```

### Level 6: Full Health Check (PRD §12)

```bash
python -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')

# 1. Schema version
n = c.execute(\"SELECT COUNT(*) FROM pragma_table_info('Ingredient_Canonical') WHERE name IN ('SMILES','UNII_Code','Grade_Flag','Molport_Id')\").fetchone()[0]
print(f'v1.1 cols in Ingredient_Canonical (must be 4): {n}')

# 2. Phase 1 coverage
r = c.execute(\"SELECT COUNT(*), SUM(CASE WHEN stc.Confidence >= 0.65 THEN 1 END) FROM Product p LEFT JOIN SKU_To_Canonical stc ON stc.ProductId = p.Id WHERE p.Type = 'raw-material'\").fetchone()
print(f'Phase 1: {r[1]}/{r[0]} resolved (must be ≥657)')

# 3. SMILES coverage
r2 = c.execute('SELECT COUNT(*), ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM Ingredient_Canonical),1) FROM Ingredient_Canonical WHERE SMILES IS NOT NULL').fetchone()
print(f'SMILES coverage: {r2[0]} rows ({r2[1]}%, must be ≥50%)')

# 4. Top 5 consolidation candidates
rows = c.execute(\"SELECT ic.Name, COUNT(DISTINCT p.CompanyId) AS companies FROM Ingredient_Canonical ic JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id JOIN Product p ON p.Id = stc.ProductId GROUP BY ic.Id ORDER BY companies DESC LIMIT 5\").fetchall()
print('Top 5:'); [print(f'  {r}') for r in rows]

c.close()
print('Health check complete.')
"
```

### Level 7: Run Full Re-Extraction

```bash
# After all code changes are implemented:
python enrichment/db_bootstrap.py --force   # Fresh start with v1.1 schema
python enrichment/pipeline.py --phase 1     # Phase 1 ingredient identity
python enrichment/backfill_phase1.py        # SMILES + UNII backfill
python enrichment/run_dedup.py              # UNII dedup + substitution seeding
python enrichment/pipeline.py --phase 2     # Phase 2 BOM quantities (improved)
python enrichment/pipeline.py --phase 3     # Phase 3 compliance
```

---

## ACCEPTANCE CRITERIA

- [ ] `PRAGMA table_info(Ingredient_Canonical)` includes `SMILES`, `UNII_Code`, `Grade_Flag`, `Molport_Id`
- [ ] `PRAGMA table_info(SKU_To_Canonical)` includes `MatchScore`
- [ ] `PRAGMA table_info(Supplier_Commercial)` shows `Confidence` as `REAL` (not `TEXT`)
- [ ] `SELECT COUNT(*) FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL` = 0
- [ ] `SELECT COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL` ≥ 112
- [ ] `SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1` = 0 rows
- [ ] Vitamin C cluster company count ≥ 35 after dedup merge
- [ ] `SELECT COUNT(*) FROM BOM_Component_Quantity` ≥ 500
- [ ] `SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Unit = 'NP'` = 0
- [ ] `SELECT COUNT(*) FROM Product_Compliance` ≥ 28
- [ ] `SELECT COUNT(DISTINCT Certification) FROM Product_Compliance` ≥ 4
- [ ] `SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType = 'identical'` ≥ 1
- [ ] `MolportClient().lookup_ingredient({'cas_number': '50-81-7'})` returns `[]` without error when key absent
- [ ] `parse_sku('RM-C30-sucralose-cid-56038-13-2-201fdf47', 1)` returns `None`
- [ ] All migration and backfill scripts are idempotent (safe to run twice)

---

## COMPLETION CHECKLIST

- [ ] Task 1: `schema/enriched_schema.sql` updated to v1.1
- [ ] Task 2: `enrichment/db_migrate_v11.py` created and tested
- [ ] Task 3: `enrichment/db_bootstrap.py` calls `migrate_v11()`
- [ ] Task 4: `PubChemClient.get_isomeric_smiles()` added
- [ ] Task 5: `enrichment/backfill_phase1.py` created and run
- [ ] Task 6: Display name fix in `ingredient_normalizer.py`
- [ ] Task 7: Sucralose guard in `sku_parser.py`
- [ ] Task 8: `dedup_by_unii()` added to `fuzzy_matcher.py`
- [ ] Task 9: `quantity_enricher.py` threshold + UNII + synonyms + NP unit fixes
- [ ] Task 10: `compliance_enricher.py` CERT_SIGNAL_MAP + Off_Market_Warning fix
- [ ] Task 11: `enrichment/sources/molport.py` created (graceful no-op)
- [ ] Task 12: `seed_substitutions_from_unii_history()` added to `substitution_graph.py`
- [ ] Task 13: `enrichment/run_dedup.py` wiring script created
- [ ] All Level 1–6 validation commands pass
- [ ] Level 7 full re-extraction run produces target numbers

---

## NOTES

**Execution Order is Critical**: Migration (Tasks 1–3) must run before backfill (Tasks 4–5), which must run before dedup (Task 8), which must run before Phase 2 (Task 9) because UNII matching requires UNII_Code to be populated.

**Re-bootstrap or Migrate In-Place?**: Prefer running `db_bootstrap.py --force` (Tasks 1–3) to get a clean v1.1 schema, then re-run Phase 1, then backfill. This is cleaner than migrating the existing Phase 1 output in-place, because Phase 1 was run before display name fix and Sucralose guard. However, Phase 1 takes ~7 min and has 854 cache hits — warm cache re-run is fast. The PRD §4 Core Principle 4 ("cache-first backfill") ensures this is efficient.

**DSLD `preferredName` key**: Before implementing Task 6, read `enrichment/sources/dsld.py::search_ingredient()` carefully to confirm the exact key name returned for the preferred/common name. If it doesn't return `preferredName`, the Task 6 logic needs adjustment.

**Supplier_Commercial rebuild risk**: The CREATE/DROP/RENAME for Supplier_Commercial (Task 2) is only safe because the table has 0 rows. The migration script must verify this (`SELECT COUNT(*) FROM Supplier_Commercial` = 0) before proceeding with the rebuild.

**Molport key timing**: Task 11 (Molport) is low-risk to implement now — it no-ops cleanly without the key. When the key arrives, running `python enrichment/pipeline.py --phase 3` will automatically invoke CommercialEnricher which should be wired to MolportClient.

**Confidence Score**: 7.5/10 — High confidence because all code patterns are established, all cache infrastructure exists, and the hardest logic (dedup merge, UNII backfill) has exact pseudocode in PRD §7. Risk factors: DSLD `preferredName` field name uncertainty (easy to check), Molport field name verification needed against reference doc.
