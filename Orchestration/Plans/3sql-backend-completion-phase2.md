# Feature: SQL Backend Completion — Phase 2

The following plan should be complete, but validate the DB state and codebase patterns before implementing.

Pay special attention to the exact column names in `Consolidation_Opportunity` (v1.1 columns already exist) and the import paths — all modules use `enrichment.*` or `reasoning.*` from the project root.

## Feature Description

Four critical pipeline steps are incomplete despite the codebase being scaffolded. This plan closes the remaining gaps in the Agnes SQLite backend so that Phase 4 proposal generation has correct, complete input data.

**DB state as of plan creation (2026-04-18):**
- `Ingredient_Substitution`: 0 rows (40 rules exist in `Ingredient_Substitution_Rule` — not yet translated)
- `Consolidation_Opportunity`: 0 rows (`ConsolidationScorer` never run)
- `SKU_To_Canonical.MatchScore`: NULL on all 854 rows
- `Ingredient_Canonical.UNII_Code`: 44/260 populated (17%) — target ≥ 40%
- `Supplier_Commercial`: 0 rows — `CommercialEnricher._enrich_pair()` is a stub
- **Formula bug:** `consolidation_scorer.py` uses `compliance_homogeneity` (placeholder 0.5) and `supplier_concentration` (inverted metric) — PRD §13 specifies `fragmentation (sku_count, 0.20)` + `supplier_spread (0.15)`

## User Story

As a pipeline operator,
I want to run three commands to populate Ingredient_Substitution, Consolidation_Opportunity with correct formula scores, and prepare CommercialEnricher for when the Molport key arrives,
So that Phase 4 proposal generation has accurate data and the formula bug doesn't silently corrupt rankings.

## Problem Statement

The scorer formula mismatch is the highest-risk issue: `ConsolidationScorer().run()` can be called today, but it will produce incorrect rankings that will mislead Phase 4 LLM proposals if not fixed first. The `CommercialEnricher._enrich_pair()` TODO stub means Phase 3 commercial enrichment produces zero rows even when `MOLPORT_API_KEY` is available.

## Solution Statement

Fix the consolidation scorer formula, implement `CommercialEnricher._enrich_pair()`, then execute the three no-dependency operations (MatchScore backfill, SubstitutionGraphBuilder, ConsolidationScorer). For DSLD-dependent UNII backfill, provide the command sequence — the agent doesn't run it, but the code is already correct.

## Feature Metadata

**Feature Type**: Bug Fix + Enhancement  
**Estimated Complexity**: Low-Medium  
**Primary Systems Affected**: `reasoning/consolidation_scorer.py`, `enrichment/enrichers/commercial_enricher.py`  
**Dependencies**: No new libraries. Molport key for commercial enrichment (optional, graceful no-op when absent).

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `reasoning/consolidation_scorer.py` (lines 1–163) — full file; fix formula weights, add Unique_SKU_Count stats, write Score_Formula_Component column
- `enrichment/enrichers/commercial_enricher.py` (lines 45–48) — `_enrich_pair` is a TODO stub; wire in MolportClient
- `enrichment/sources/molport.py` (lines 34–141) — `MolportClient.lookup_ingredient()` is implemented; takes dict with `cas_number` and `smiles` keys
- `enrichment/backfill_phase1.py` (lines 94–113) — `backfill_match_scores()` is ready to run, no changes needed
- `reasoning/substitution_graph.py` (lines 13–87) — `SubstitutionGraphBuilder().run()` is ready to run, no changes needed
- `enrichment/run_dedup.py` — already imports `seed_substitutions_from_unii_history`; no changes needed
- `schema/enriched_schema.sql` — reference for column names

### New Files to Create

None — all necessary files exist. This plan is pure bug-fix + wiring.

### Patterns to Follow

**Import pattern (all reasoning/enrichment files):**
```python
ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
```

**DB connection pattern (per-write, avoid locks):**
```python
conn = sqlite3.connect(self.db_path)
# ...work...
conn.commit()
conn.close()
```

**INSERT OR REPLACE pattern:**
```python
conn.execute(
    "INSERT OR REPLACE INTO Consolidation_Opportunity (...) VALUES (...)",
    (values,)
)
```

**Molport no-op pattern (when key absent):**
```python
if not self.api_key:
    return []
```
MolportClient already handles this — `lookup_ingredient()` returns `[]` when no key.

---

## IMPLEMENTATION PLAN

### Phase 1: Fix ConsolidationScorer Formula

The existing formula uses wrong metrics. Fix before running — running with the broken formula wastes time and produces misleading output.

**What's wrong:**
- `W_SUPPLIER_CONCENTRATION = 0.20` uses `1 - (supplier_count/company_count)` — gives high score when FEW suppliers serve many companies, but that means the ingredient is ALREADY consolidated. We want high score for HIGH fragmentation.
- `W_COMPLIANCE_HOMOGENEITY = 0.15` uses placeholder `0.5` for all ingredients — useless signal.

**What PRD §13 specifies (from CLAUDE.md design decision):**
- `company_score`: 0.40 — `company_count / max_companies`
- `bom_score`: 0.25 — `bom_count / max_boms`
- `fragmentation`: 0.20 — `unique_sku_count / max_unique_skus` (Unique_SKU_Count column)
- `supplier_spread`: 0.15 — `supplier_count / max_supplier_count`

### Phase 2: Wire CommercialEnricher

`_enrich_pair` is a logger.debug stub. The MolportClient is fully implemented in `enrichment/sources/molport.py`. Wire them together:
1. Query `Ingredient_Canonical` for `CAS_Number` and `SMILES` for the given `canonical_id`
2. Call `MolportClient(self.db_path).lookup_ingredient({"cas_number": cas, "smiles": smiles})`
3. For each supplier row returned, insert into `Supplier_Commercial`

### Phase 3: Execute the No-Dependency Operations

In order:
1. Run `backfill_match_scores()` — pure local computation, no API calls
2. Run `SubstitutionGraphBuilder().run()` — translates 40 `Ingredient_Substitution_Rule` rows into edges
3. Run `ConsolidationScorer().run()` — populate `Consolidation_Opportunity`

### Phase 4: UNII Backfill (DSLD key required)

Only 44/260 canonicals have UNII codes. This affects Phase 4 signal quality but doesn't block the above three steps.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom.

---

### Task 1: UPDATE `reasoning/consolidation_scorer.py` — Fix formula weights

- **PATTERN**: `reasoning/consolidation_scorer.py:1-20` — existing weight constants block
- **CHANGE**: Replace the four weight constants and update `_get_stats` + `_compute_score` + `_upsert_opportunity`

**Replace the weight constants (lines 13-16):**

```python
# OLD:
W_COMPANY_COUNT = 0.40
W_BOM_COUNT = 0.25
W_SUPPLIER_CONCENTRATION = 0.20
W_COMPLIANCE_HOMOGENEITY = 0.15

# NEW:
W_COMPANY_SCORE = 0.40
W_BOM_SCORE = 0.25
W_FRAGMENTATION = 0.20    # unique_sku_count / max
W_SUPPLIER_SPREAD = 0.15  # distinct_supplier_count / max
```

**Add `max_unique_skus` denominator to `run()` (after `max_boms` query, ~line 42):**

```python
max_unique_skus = conn.execute(
    """SELECT MAX(c) FROM (
       SELECT COUNT(DISTINCT stc.ProductId) AS c
       FROM SKU_To_Canonical stc
       GROUP BY stc.CanonicalId)"""
).fetchone()[0] or 1

max_supplier_count = conn.execute(
    """SELECT MAX(c) FROM (
       SELECT COUNT(DISTINCT sp.SupplierId) AS c
       FROM SKU_To_Canonical stc
       JOIN Supplier_Product sp ON sp.ProductId = stc.ProductId
       GROUP BY stc.CanonicalId)"""
).fetchone()[0] or 1
```

**Pass them to `_compute_score` and `_upsert_opportunity` (update the for-loop call, ~line 53):**

```python
score = self._compute_score(stats, max_companies, max_boms, max_unique_skus, max_supplier_count)
self._upsert_opportunity(conn, canonical_id, stats, score)
```

**Add `unique_sku_count` to `_get_stats` (after `bom_count` query, ~line 82):**

```python
unique_sku_count = conn.execute(
    """SELECT COUNT(DISTINCT stc.ProductId)
       FROM SKU_To_Canonical stc
       WHERE stc.CanonicalId = ?""",
    (canonical_id,),
).fetchone()[0]
```

**Add it to the stats return dict (~line 101):**

```python
return {
    "company_count": company_count,
    "bom_count": bom_count,
    "unique_sku_count": unique_sku_count,   # ADD THIS
    "supplier_count": supplier_count,
    "best_supplier_id": best_supplier[0] if best_supplier else None,
    "best_supplier_coverage": best_supplier[1] if best_supplier else 0,
}
```

**Replace `_compute_score` entirely (~lines 108-127):**

```python
def _compute_score(self, stats: dict, max_companies: int, max_boms: int,
                   max_unique_skus: int, max_supplier_count: int) -> float:
    company_score = stats["company_count"] / max_companies
    bom_score = stats["bom_count"] / max_boms
    fragmentation_score = stats["unique_sku_count"] / max_unique_skus
    supplier_spread_score = stats["supplier_count"] / max(max_supplier_count, 1)

    return (
        W_COMPANY_SCORE * company_score
        + W_BOM_SCORE * bom_score
        + W_FRAGMENTATION * fragmentation_score
        + W_SUPPLIER_SPREAD * supplier_spread_score
    )
```

**Update `_upsert_opportunity` to write v1.1 columns (~lines 129-144):**

```python
def _upsert_opportunity(self, conn: sqlite3.Connection, canonical_id: int,
                         stats: dict, score: float) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO Consolidation_Opportunity
           (CanonicalIngredientId, Company_Count, BOM_Count, Current_Supplier_Count,
            Unique_SKU_Count, Score_Formula_Component, Consolidation_Score, Recommended_SupplierId)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            canonical_id,
            stats["company_count"],
            stats["bom_count"],
            stats["supplier_count"],
            stats["unique_sku_count"],
            round(score, 4),    # Score_Formula_Component stores the pure formula score
            round(score, 4),    # Consolidation_Score = formula score until LLM adjustment applied
            stats["best_supplier_id"],
        ),
    )
```

- **VALIDATE**: `python3 -c "from reasoning.consolidation_scorer import ConsolidationScorer; print('import OK')"`

---

### Task 2: UPDATE `enrichment/enrichers/commercial_enricher.py` — Implement `_enrich_pair`

- **PATTERN**: `enrichment/sources/molport.py:34-55` — `MolportClient.lookup_ingredient()` takes a dict with `cas_number` and `smiles` keys, returns list of row dicts
- **IMPORTS**: `from enrichment.sources.molport import MolportClient`
- **GOTCHA**: Molport's `lookup_ingredient` returns `[]` when `MOLPORT_API_KEY` is absent — always check `if not rows: return` before DB writes
- **GOTCHA**: `Supplier_Commercial` primary key is `(SupplierId, CanonicalIngredientId)`. For Molport suppliers (not in `Supplier` table), use `INSERT OR IGNORE` and create a stub supplier row first.

**Replace `_enrich_pair` (lines 45-48) with:**

```python
def _enrich_pair(self, supplier_id: int, canonical_id: int, ingredient_name: str) -> None:
    conn = sqlite3.connect(self.db_path)
    canonical = conn.execute(
        "SELECT CAS_Number, SMILES FROM Ingredient_Canonical WHERE Id = ?",
        (canonical_id,)
    ).fetchone()
    conn.close()

    if not canonical:
        return

    cas, smiles = canonical
    molport = MolportClient(self.db_path)
    rows = molport.lookup_ingredient({"cas_number": cas, "smiles": smiles})

    if not rows:
        return

    conn = sqlite3.connect(self.db_path)
    for row in rows:
        supplier_name = row.get("supplier_name")
        if not supplier_name:
            continue

        # Get or create a stub Supplier row for this Molport supplier
        existing = conn.execute(
            "SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)
        ).fetchone()
        if existing:
            molport_supplier_id = existing[0]
        else:
            cur = conn.execute(
                "INSERT OR IGNORE INTO Supplier (Name, Country) VALUES (?, ?)",
                (supplier_name, row.get("country_origin"))
            )
            molport_supplier_id = cur.lastrowid or conn.execute(
                "SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)
            ).fetchone()[0]

        conn.execute(
            """INSERT OR REPLACE INTO Supplier_Commercial
               (SupplierId, CanonicalIngredientId,
                Price_USD_Per_KG, Price_Qty_KG, MOQ_KG,
                Lead_Time_Days, Country_Origin, Country_Shipping,
                Price_Type, Price_Source, Confidence,
                Grade_Unverified, Molport_Catalog_Id, Data_Freshness_Days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                molport_supplier_id, canonical_id,
                row.get("price_usd"), row.get("price_qty_kg"), None,
                row.get("delivery_days"), row.get("country_origin"), row.get("country_shipping"),
                "retail_proxy", "molport", 0.70,
                1, row.get("molport_catalog_id"), None,
            )
        )

    conn.commit()
    conn.close()
    logger.info(f"Commercial: {len(rows)} Molport rows stored for canonical_id={canonical_id} ({ingredient_name})")
```

- **VALIDATE**: `python3 -c "from enrichment.enrichers.commercial_enricher import CommercialEnricher; print('import OK')"`

---

### Task 3: RUN `backfill_match_scores` — Populate MatchScore for all 854 fuzzy rows

No code changes. The function in `enrichment/backfill_phase1.py:94-113` is complete.

- **VALIDATE before running**: `python3 -c "import sqlite3; conn = sqlite3.connect('db_enriched.sqlite'); print(conn.execute('SELECT COUNT(*) FROM SKU_To_Canonical WHERE MatchScore IS NULL').fetchone()[0], 'rows need MatchScore')"`
- **RUN**: `cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sys; sys.path.insert(0, '.')
from enrichment.backfill_phase1 import backfill_match_scores
backfill_match_scores()
"`
- **VALIDATE after**: `SELECT COUNT(*) FROM SKU_To_Canonical WHERE MatchScore IS NULL AND MatchMethod = 'fuzzy'` → must return 0

---

### Task 4: RUN `SubstitutionGraphBuilder` — Translate 40 rules into edges

No code changes. `reasoning/substitution_graph.py:13-87` is fully implemented.

- **VALIDATE before**: `python3 -c "import sqlite3; conn = sqlite3.connect('db_enriched.sqlite'); print('Rules:', conn.execute('SELECT COUNT(*) FROM Ingredient_Substitution_Rule').fetchone()[0], '| Edges:', conn.execute('SELECT COUNT(*) FROM Ingredient_Substitution').fetchone()[0])"`
- **RUN**: `cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sys; sys.path.insert(0, '.')
from reasoning.substitution_graph import SubstitutionGraphBuilder
SubstitutionGraphBuilder().run()
"`
- **VALIDATE after**: `SELECT COUNT(*) FROM Ingredient_Substitution` — expect ≥ 40 (each rule creates 2 edges; some rules may not resolve if ingredient names don't match canonicals exactly)

**GOTCHA**: `_canonical_id()` uses exact `COLLATE NOCASE` match against `Ingredient_Canonical.Name`. If a rule uses "Vitamin C" but the canonical is "Ascorbic Acid", the edge won't be created. Check the log output for "Skipping rule" lines and note any unresolved pairs.

---

### Task 5: RUN `ConsolidationScorer` — Score all candidates (after Task 1 fix)

Must run Task 1 first to apply the formula fix.

- **VALIDATE before**: `python3 -c "import sqlite3; conn = sqlite3.connect('db_enriched.sqlite'); print('CO rows:', conn.execute('SELECT COUNT(*) FROM Consolidation_Opportunity').fetchone()[0])"`
- **RUN**: `cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sys; sys.path.insert(0, '.'); import logging; logging.basicConfig(level=logging.INFO)
from reasoning.consolidation_scorer import ConsolidationScorer
ConsolidationScorer().run()
"`
- **VALIDATE after**:
  ```sql
  SELECT ic.Name, co.Company_Count, co.Unique_SKU_Count, co.Score_Formula_Component, co.Consolidation_Score
  FROM Consolidation_Opportunity co
  JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
  ORDER BY co.Consolidation_Score DESC LIMIT 10;
  ```
  — Expect Vitamin D3/Cholecalciferol near top (17 companies); Vitamin C (13 companies after dedup); no Score_Formula_Component = NULL

---

### Task 6: UNII Backfill (requires DSLD_API_KEY in .env)

The code in `enrichment/backfill_phase1.py:44-91` is correct and ready. Only 44/260 canonicals have UNII codes. Running this should reach ≥ 112 (40% target).

- **PRE-CHECK**: Verify DSLD_API_KEY is set: `python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Key set:', bool(os.getenv('DSLD_API_KEY')))"`
- **RUN (only if key is present)**:
  ```bash
  cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
  import sys; sys.path.insert(0, '.'); import logging; logging.basicConfig(level=logging.INFO)
  from enrichment.backfill_phase1 import backfill_unii
  backfill_unii()
  "
  ```
- **VALIDATE**: `SELECT COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL` → target ≥ 112
- **THEN run dedup again**: `python3 enrichment/run_dedup.py` — catches any new UNII matches
- **THEN re-run scorer**: Task 5 command above (re-scores with improved UNII-merged clusters)

---

### Task 7: Commercial Enrichment (requires MOLPORT_API_KEY in .env)

After Task 2 code change is applied. No-ops gracefully when key is absent.

- **PRE-CHECK**: `python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Molport key:', bool(os.getenv('MOLPORT_API_KEY')))"`
- **RUN**: `cd "/home/developer/Projects/Spherecast Agnes" && python3 enrichment/pipeline.py --phase 3`
- **VALIDATE**: `SELECT COUNT(*) FROM Supplier_Commercial` → target ≥ 200 (when key present)
- **VALIDATE**: `SELECT COUNT(*) FROM Supplier_Commercial WHERE Price_Type != 'retail_proxy'` → must be 0
- **VALIDATE**: `SELECT COUNT(*) FROM Supplier_Commercial WHERE Grade_Unverified != 1` → must be 0

---

### Task 8: Phase 4 Proposals (requires ANTHROPIC_API_KEY)

After Tasks 1–5 are complete. `reasoning/proposal_generator.py` is fully implemented — no changes needed.

- **PRE-CHECK**: `python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('Anthropic key:', bool(os.getenv('ANTHROPIC_API_KEY')))"`
- **PRE-CHECK**: `SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Consolidation_Score >= 0.30` → must be ≥ 10
- **RUN**: `cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sys; sys.path.insert(0, '.'); import logging; logging.basicConfig(level=logging.INFO)
from reasoning.proposal_generator import ProposalGenerator
ProposalGenerator().run()
"`
- **VALIDATE**: `SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL` → ≥ 10

---

## TESTING STRATEGY

### Unit Tests

No existing test framework — validate inline with SQL queries after each step.

### Edge Cases to Verify

1. **Substitution rules where ingredient name doesn't match canonical**: `SubstitutionGraphBuilder` logs "Skipping rule" — check the count and verify it's not skipping all 40 rules due to naming mismatch. If > 20 rules skip, check canonical names in DB:  
   `SELECT Name FROM Ingredient_Canonical WHERE Name LIKE '%Vitamin C%' OR Name LIKE '%Ascorbic%'`

2. **ConsolidationScorer with 0 BOM rows for some ingredients**: `_get_stats` returns bom_count=0 → bom_score=0 → that's correct behavior; those ingredients still get company/sku/supplier scores.

3. **CommercialEnricher Supplier table INSERT conflict**: Using `INSERT OR IGNORE` + lookup for Molport supplier names. Test with: after running commercial enrichment, `SELECT COUNT(*) FROM Supplier` should increase by the number of new Molport suppliers found.

4. **Consolidation_Opportunity `INSERT OR REPLACE`**: If scorer is re-run after UNII backfill, it overwrites existing rows cleanly. `Score_Formula_Component` and `Consolidation_Score` will update correctly.

---

## VALIDATION COMMANDS

### Level 1: Import checks (run before each task)

```bash
cd "/home/developer/Projects/Spherecast Agnes"
python3 -c "
import sys; sys.path.insert(0, '.')
from reasoning.consolidation_scorer import ConsolidationScorer
from enrichment.enrichers.commercial_enricher import CommercialEnricher
from reasoning.substitution_graph import SubstitutionGraphBuilder
from enrichment.backfill_phase1 import backfill_match_scores
print('All imports OK')
"
```

### Level 2: Full backend health check (run after all tasks)

```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')

checks = [
    ('IC total/SMILES/UNII', 'SELECT COUNT(*), SUM(CASE WHEN SMILES IS NOT NULL THEN 1 END), SUM(CASE WHEN UNII_Code IS NOT NULL THEN 1 END) FROM Ingredient_Canonical'),
    ('MatchScore NULL (fuzzy rows)', \"SELECT COUNT(*) FROM SKU_To_Canonical WHERE MatchScore IS NULL AND MatchMethod = 'fuzzy'\"),
    ('BOM rows', 'SELECT COUNT(*) FROM BOM_Component_Quantity'),
    ('Compliance rows/products/certs', 'SELECT COUNT(*), COUNT(DISTINCT ProductId), COUNT(DISTINCT Certification) FROM Product_Compliance'),
    ('Substitution edges', 'SELECT COUNT(*) FROM Ingredient_Substitution'),
    ('Substitution rules', 'SELECT COUNT(*) FROM Ingredient_Substitution_Rule'),
    ('CO rows/with_formula', 'SELECT COUNT(*), SUM(CASE WHEN Score_Formula_Component IS NOT NULL THEN 1 END) FROM Consolidation_Opportunity'),
    ('UNII duplicates', 'SELECT COUNT(*) FROM (SELECT UNII_Code FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1)'),
    ('Supplier_Commercial', 'SELECT COUNT(*) FROM Supplier_Commercial'),
    ('Proposals', \"SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL AND Proposal_Text != ''\"),
]

for name, q in checks:
    r = conn.execute(q).fetchone()
    print(f'{name}: {r}')
conn.close()
"
```

### Level 3: Consolidation top-10 spot-check

```sql
SELECT ic.Name, co.Company_Count, co.BOM_Count, co.Unique_SKU_Count, 
       co.Current_Supplier_Count, co.Score_Formula_Component, co.Consolidation_Score
FROM Consolidation_Opportunity co
JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
ORDER BY co.Consolidation_Score DESC LIMIT 10;
```

Expect: Cholecalciferol (17 companies), Vitamin C variants (13 companies), Citric Acid (12 companies), Magnesium Stearate (11 companies) in top positions.

---

## ACCEPTANCE CRITERIA

- [ ] `ConsolidationScorer` formula uses `fragmentation (sku_count, W=0.20)` and `supplier_spread (W=0.15)`, not `compliance_homogeneity` or inverted supplier concentration
- [ ] `Consolidation_Opportunity` has ≥ 50 rows (ingredients with ≥ 2 companies)
- [ ] All rows have `Score_Formula_Component` populated (not NULL)
- [ ] `Consolidation_Opportunity.Unique_SKU_Count` populated on every row
- [ ] `SKU_To_Canonical.MatchScore` NULL count = 0 for `MatchMethod = 'fuzzy'` rows
- [ ] `Ingredient_Substitution` ≥ 1 row (ideally ≥ 40; at least the rules that resolve)
- [ ] `CommercialEnricher._enrich_pair()` no longer a stub; verified by import test
- [ ] No regression in Phase 2 (BOM rows ≥ 515) or compliance (≥ 126 rows)

---

## COMPLETION CHECKLIST

- [ ] Task 1: `consolidation_scorer.py` formula fix applied + import OK
- [ ] Task 2: `commercial_enricher.py` `_enrich_pair` implemented + import OK
- [ ] Task 3: `backfill_match_scores()` run — MatchScore NULL = 0 for fuzzy rows
- [ ] Task 4: `SubstitutionGraphBuilder().run()` — edges > 0; check log for skip ratio
- [ ] Task 5: `ConsolidationScorer().run()` — Consolidation_Opportunity ≥ 50 rows; top-10 spot-check passes
- [ ] Level 2 validation script passes (all checks show expected values)
- [ ] Task 6: UNII backfill queued for when DSLD key available (or run if key present)
- [ ] Task 7: Commercial enrichment run if MOLPORT_API_KEY present
- [ ] Task 8: Proposals run if ANTHROPIC_API_KEY present
- [ ] CLAUDE.md updated: mark Phase 4 formula scoring as ✅; mark substitution graph as ✅; update formula mismatch arc to [FIXED]

---

## NOTES

### Formula Design Decision Rationale

The original code used `supplier_concentration = 1 - (supplier_count/company_count)` which scores HIGH when few suppliers serve many companies — i.e., the ingredient is **already consolidated**. This is backwards for finding consolidation **opportunities** (where the goal is to identify fragmented purchasing).

The corrected formula:
- `fragmentation (0.20)` = `unique_sku_count / max_unique_skus`: more raw material SKUs mapped to this canonical = more distinct purchase points = more opportunity
- `supplier_spread (0.15)` = `supplier_count / max_supplier_count`: more distinct suppliers = more fragmented sourcing = more opportunity

Both metrics now reward fragmentation, which is the correct signal for consolidation candidates.

### CommercialEnricher Supplier Table Note

The `Supplier` table in `db_enriched.sqlite` contains rows from `db.sqlite` (read-only source). New Molport-sourced supplier names must be inserted into `db_enriched.sqlite`'s `Supplier` table. The `INSERT OR IGNORE` + lookup pattern handles this without duplicates.

### ProposalGenerator Uses Compliance Data

`ProposalGenerator._build_context()` queries `Product_Compliance` — the existing 126 rows (66 products, 9 cert types) are ready. No additional work needed before running proposals once the API key is available.

### Substitution Rule Name Matching

`SubstitutionGraphBuilder._canonical_id()` uses exact `COLLATE NOCASE` on `Ingredient_Canonical.Name`. The 40 rules use names like "Ascorbic Acid", "Cholecalciferol", "Magnesium Citrate". If the canonical's Name was normalized differently (e.g. "magnesium citrate" lowercase or "l-ascorbic acid" as an alias), rules will silently skip. After running, check:
```sql
SELECT COUNT(*) FROM Ingredient_Substitution;
-- If significantly less than 80 (40 rules × 2 edges), investigate name mismatches
SELECT Name FROM Ingredient_Canonical WHERE Name LIKE '%Ascorbic%' OR Name LIKE '%Magnesium%';
```
