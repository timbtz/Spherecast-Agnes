# Feature: Phase A — Data Quality Fixes (No-API)

The following plan should be complete, but validate documentation and codebase patterns before implementing.

Pay special attention to actual canonical names in `db_enriched.sqlite` — they differ from the PRD alias table (e.g. `Vitamin D` not `Cholecalciferol`, `Trimagnesium dicitrate` not `Magnesium Citrate`). The alias table in this plan reflects the **verified canonical names from the live DB**.

## Feature Description

Close four data quality gaps in Agnes's enriched SQLite DB to make it demo-ready for hackathon judges:
1. Populate `Grade_Flag` for all 250 canonical ingredients using a no-API heuristic classifier
2. Fix 38/40 substitution rules that silently skip because their `Name_A`/`Name_B` don't match `Ingredient_Canonical.Name`
3. Fix the compliance join in `proposal_generator.py` (status filter uses `confirmed/claimed` but all 126 rows have `implied`)
4. Verify and update the judge query so `certs > 0` for ingredients with compliance data

## User Story

As a hackathon judge querying the knowledge graph,
I want each ingredient to have a Grade_Flag, substitution edges, and visible certification counts,
So that the Agnes demo shows meaningful data across every column in the top-10 query.

## Problem Statement

- `Grade_Flag = 'unknown'` for all 250 canonicals — ingredient category invisible
- 38/40 substitution rules produce no edges — substitution intelligence is zero
- `proposal_generator.py` compliance query filters `Status IN ('confirmed','claimed')` but DB only has `'implied'` — zero compliance context passed to proposals
- Judge query uses wrong join path (direct `ProductId` match instead of BOM chain)

## Solution Statement

Create `grade_classifier.py` (heuristic, no API), `scripts/fix_substitution_rules.py` (SQL UPDATE only), patch two lines in `proposal_generator.py` (status filter + Grade_Flag in context), and verify the judge query. All scripts idempotent and runnable without any API keys.

## Feature Metadata

**Feature Type**: Bug Fix + Enhancement
**Estimated Complexity**: Low-Medium
**Primary Systems Affected**: `enrichment/enrichers/`, `scripts/`, `reasoning/proposal_generator.py`, `reasoning/substitution_graph.py`
**Dependencies**: None (no external API keys required for Phase A)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `enrichment/enrichers/compliance_enricher.py` (lines 1-31) — Why: shows existing enricher class pattern + CERT_SIGNAL_MAP dict; mirror for grade_classifier
- `enrichment/enrichers/commercial_enricher.py` (lines 1-45) — Why: shows class `__init__` + `run()` + per-row sqlite3 pattern with commit
- `enrichment/backfill_phase1.py` (lines 1-42) — Why: shows per-row commit pattern + `load_dotenv()` at top + `Enrichment_Run_Log` insert pattern
- `reasoning/substitution_graph.py` (lines 29-59, 82-86) — Why: shows `_canonical_id()` COLLATE NOCASE lookup; `fix_substitution_rules.py` must mirror this to verify which names resolve
- `reasoning/proposal_generator.py` (lines 38-127) — Why: `_get_top_opportunities` and `_build_context` are the two methods needing patches; TARGET_PROPOSAL_COUNT=10 must become 50; compliance status filter on line 111 must include `'implied'`
- `schema/enriched_schema.sql` (lines 9-25) — Why: `Ingredient_Canonical` columns; `Grade_Flag TEXT DEFAULT 'unknown'`; note: `Source_Grade` and `Confidence_Grade` columns do NOT exist in schema — do not write them
- `enrichment/pipeline.py` — Why: understand how to wire `GradeClassifier` into `run_phase_1()` or as standalone

### New Files to Create

- `enrichment/enrichers/grade_classifier.py` — Heuristic Grade_Flag classifier; standalone runnable
- `scripts/fix_substitution_rules.py` — SQL UPDATE script to fix Name_A/Name_B in Ingredient_Substitution_Rule

### Relevant Documentation

No external docs needed for Phase A — pure heuristic + SQL.

### Patterns to Follow

**Class pattern (mirror compliance_enricher.py):**
```python
class GradeClassifier:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT Id, Name, SMILES FROM Ingredient_Canonical").fetchall()
        conn.close()
        for canonical_id, name, smiles in rows:
            grade, confidence = classify_grade(name, smiles)
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE Ingredient_Canonical SET Grade_Flag = ? WHERE Id = ?",
                (grade, canonical_id)
            )
            conn.commit()
            conn.close()
```

**Standalone run pattern (all new scripts):**
```python
if __name__ == "__main__":
    import sys
    from pathlib import Path
    ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    GradeClassifier().run()
```

**DB path pattern:**
```python
ROOT = Path(__file__).parent.parent   # for files in enrichment/enrichers/
ENRICHED_DB = ROOT / "db_enriched.sqlite"
```
For `scripts/` (one level deeper): `ROOT = Path(__file__).parent.parent`

**Idempotency pattern:** For grade classifier, always overwrite `Grade_Flag` (safe to re-run; heuristic is deterministic). For substitution rule fix, `UPDATE` is idempotent since it sets the same value.

---

## VERIFIED ALIAS MAPPING (from live DB)

Built by querying actual `Ingredient_Canonical.Name` values. These are the exact canonical names in the DB:

| Rule Name_A or Name_B | Canonical Name in DB | Action |
|---|---|---|
| Ascorbic Acid | Vitamin C | UPDATE |
| Cholecalciferol | Vitamin D | UPDATE |
| d-Alpha Tocopherol | Tocopherols | UPDATE |
| dl-Alpha Tocopherol | Tocopherols | UPDATE |
| Mixed Tocopherols | Tocopherols | UPDATE |
| Methylfolate | Folate | UPDATE |
| 5-MTHF | Folate | UPDATE |
| Cyanocobalamin | vitamin B12 | UPDATE |
| Magnesium Oxide | Magnesia | UPDATE |
| Magnesium Citrate | Trimagnesium dicitrate | UPDATE |
| Hydroxypropyl Methylcellulose | Hypromellose | UPDATE |
| HPMC | Hypromellose | UPDATE |
| Dextrose | D-Glucopyranose | UPDATE |
| Glucose | D-Glucopyranose | UPDATE |
| CoQ10 | Coenzyme Q10 | UPDATE |
| Potassium Citrate | potassium citrate monohydrate | UPDATE |
| Vegetarian Capsule | Vegan Capsule | UPDATE |
| Silicon Dioxide (rule) | SILICON DIOXIDE (canonical) | COLLATE NOCASE — no UPDATE needed |
| Magnesium Glycinate (rule) | MAGNESIUM GLYCINATE | COLLATE NOCASE — no UPDATE needed |
| Magnesium Malate (rule) | Magnesium malate | COLLATE NOCASE — no UPDATE needed |
| Ferrous Fumarate (rule) | Ferrous fumarate | COLLATE NOCASE — no UPDATE needed |
| Ergocalciferol | No canonical match | LOG UNRESOLVED, skip |
| Magnesium Ascorbate | No canonical match | LOG UNRESOLVED, skip |
| Methylcobalamin | No canonical match | LOG UNRESOLVED, skip |
| Adenosylcobalamin | No canonical match | LOG UNRESOLVED, skip |
| Calcium Phosphate | No canonical match | LOG UNRESOLVED, skip |
| Zinc Oxide | No canonical match | LOG UNRESOLVED, skip |
| Zinc Citrate | No canonical match | LOG UNRESOLVED, skip |
| Zinc Gluconate | No canonical match | LOG UNRESOLVED, skip |
| Zinc Picolinate | No canonical match | LOG UNRESOLVED, skip |
| Ferrous Sulfate | No canonical match | LOG UNRESOLVED, skip |
| Ferric Pyrophosphate | No canonical match | LOG UNRESOLVED, skip |
| Fish Oil | No canonical match | LOG UNRESOLVED, skip |
| Algal Oil | No canonical match | LOG UNRESOLVED, skip |
| Krill Oil | No canonical match | LOG UNRESOLVED, skip |
| Silica | No canonical match | LOG UNRESOLVED, skip |
| Microcrystalline Cellulose | No canonical match | LOG UNRESOLVED, skip |
| MCC | No canonical match | LOG UNRESOLVED, skip |
| FOS | No canonical match | LOG UNRESOLVED, skip |
| Fructooligosaccharides | No canonical match | LOG UNRESOLVED, skip |
| Ubiquinol | No canonical match | LOG UNRESOLVED, skip |
| Curcumin | No canonical match | LOG UNRESOLVED, skip |
| Curcuma Longa Extract | No canonical match | LOG UNRESOLVED, skip |
| Turmeric Extract | No canonical match | LOG UNRESOLVED, skip |
| Bovine Gelatin | No canonical match | LOG UNRESOLVED, skip |
| Porcine Gelatin | No canonical match | LOG UNRESOLVED, skip |

Note: COLLATE NOCASE entries need no UPDATE — `substitution_graph.py:82-86` already uses COLLATE NOCASE lookup. Only aliases mapping to a **different** canonical name need UPDATE.

---

## COMPLIANCE JOIN ROOT CAUSE (verified against live DB)

**Problem 1 — Status filter:** `proposal_generator.py:111` filters `AND pc.Status IN ('confirmed', 'claimed')` but all 126 `Product_Compliance` rows have `Status = 'implied'`. Zero compliance rows are returned.

**Problem 2 — Judge query join path:** The PRD's §3 judge query placeholder uses a subquery. The verified correct join path (confirmed working, returns `certs=8` for Vitamin C):
```sql
LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
    SELECT DISTINCT b.ProducedProductId
    FROM BOM b
    JOIN BOM_Component bc ON bc.BOMId = b.Id
    JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
    WHERE stc.CanonicalId = ic.Id
)
```

**Problem 3 — proposal_generator.py already uses the correct BOM join path** (lines 101-113). Only the status filter needs fixing there.

---

## IMPLEMENTATION PLAN

### Phase 1: Grade Classifier (no API, ~30 min)

Create `enrichment/enrichers/grade_classifier.py` with heuristic rules, run it, verify.

### Phase 2: Substitution Rule Fix (~20 min)

Create `scripts/fix_substitution_rules.py` using the verified alias table above, run it, re-run substitution graph.

### Phase 3: Compliance Fix (~10 min)

Patch two lines in `proposal_generator.py`:
- Status filter: add `'implied'` 
- Grade_Flag: add to context-building query and prompt

### Phase 4: Verify judge query (~10 min)

Run the verified judge query and confirm `certs > 0` for top-10.

---

## STEP-BY-STEP TASKS

### TASK 1: CREATE `enrichment/enrichers/grade_classifier.py`

- **IMPLEMENT**: Module-level `classify_grade(name, smiles)` function + `GradeClassifier` class with `run()` method
- **PATTERN**: Mirror `compliance_enricher.py:1-50` for class structure; `backfill_phase1.py:1-9` for `load_dotenv` + ROOT path
- **IMPORTS**: `import logging, sqlite3; from pathlib import Path; from dotenv import load_dotenv`
- **DB WRITE**: `UPDATE Ingredient_Canonical SET Grade_Flag = ? WHERE Id = ?` — only `Grade_Flag`, no `Source_Grade`/`Confidence_Grade` (columns do not exist in schema)
- **GOTCHA**: The `Grade_Flag` column schema comment says `food|pharma|reagent|unknown` but the PRD specifies `supplement|excipient|food|sweetener|flavor|unknown`. Use the PRD values — they're the intended ones.
- **GOTCHA**: Run order matters — `flavor` and `sweetener` rules must be checked before `supplement` to avoid Sucralose being classified as supplement
- **GOTCHA**: Names in DB are inconsistently cased (`nicotinamide`, `VITAMIN E`, `Vitamin C`). Use `name.lower()` for all keyword matching.

**classify_grade logic (priority order, check `name.lower()`):**
```python
FLAVOR_KEYWORDS = ["flavor", "flavour", "artificial flavor", "natural flavor"]
SWEETENER_NAMES = ["sucralose", "erythritol", "sorbitol", "stevia", "monk fruit",
                   "sucrose", "xylitol", "maltitol", "saccharin", "aspartame",
                   "rebaudioside", "coconut sugar", "tapioca syrup"]
EXCIPIENT_KEYWORDS = ["cellulose", "silicon dioxide", "magnesium stearate", "croscarmellose",
                      "hpmc", "hypromellose", "methylcellulose", "talc", "silica",
                      "hydroxypropyl", "carrageenan", "carnauba", "shellac",
                      "titanium dioxide", "rice flour", "polyethylene glycol",
                      "crospovidone", "stearic acid", "starch", "polydextrose",
                      "pharmaceutical glaze", "sodium benzoate", "sorbic acid",
                      "alginate", "sodium alginate", "citric acid"]  # citric acid = acidulant/excipient
FOOD_KEYWORDS = ["protein", "gelatin", "collagen", "maltodextrin", "inulin",
                 "lecithin", "pectin", "xanthan", "guar gum", "sunflower oil",
                 "coconut oil", "mct", "medium chain triglycerides", "cocoa", "whey",
                 "casein", "rice bran", "flax", "pumpkin", "hemp"]
SUPPLEMENT_KEYWORDS = ["vitamin", "zinc", "magnesium", "calcium", "iron", "potassium",
                       "selenium", "chromium", "copper", "manganese", "iodine",
                       "cobalamin", "folate", "biotin", "niacin", "thiamin", "riboflavin",
                       "pantothenic", "folic acid"]
AMINO_ACID_NAMES = ["glycine", "lysine", "leucine", "isoleucine", "valine", "methionine",
                    "phenylalanine", "tryptophan", "threonine", "histidine", "arginine",
                    "glutamine", "taurine", "carnitine", "creatine", "beta-alanine",
                    "citrulline", "l-leucine", "l-valine", "l-isoleucine"]

def classify_grade(name: str, smiles: str | None) -> tuple[str, float]:
    n = name.lower()
    if any(kw in n for kw in FLAVOR_KEYWORDS):
        return "flavor", 0.9
    if any(kw in n for kw in SWEETENER_NAMES):
        return "sweetener", 0.9
    if any(kw in n for kw in EXCIPIENT_KEYWORDS):
        return "excipient", 0.9
    if any(kw in n for kw in FOOD_KEYWORDS):
        return "food", 0.9
    if any(kw in n for kw in SUPPLEMENT_KEYWORDS):
        return "supplement", 0.9
    if any(kw in n for kw in AMINO_ACID_NAMES):
        return "supplement", 0.9
    if smiles is not None:
        return "supplement", 0.7  # has SMILES → likely bioactive
    return "unknown", 0.0
```

- **VALIDATE**: 
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python enrichment/enrichers/grade_classifier.py
```
```sql
-- Run in Python: sqlite3.connect("db_enriched.sqlite").execute("SELECT Grade_Flag, COUNT(*) cnt FROM Ingredient_Canonical GROUP BY Grade_Flag ORDER BY cnt DESC").fetchall()
-- Expect: unknown < 50
```

---

### TASK 2: CREATE `scripts/fix_substitution_rules.py`

- **IMPLEMENT**: Script queries all canonical names, applies the verified alias table from this plan, runs UPDATE statements for matched aliases, logs unresolved names
- **PATTERN**: Standalone script with `ROOT = Path(__file__).parent.parent` and `sys.path.insert(0, str(ROOT))`
- **IMPORTS**: `import logging, sqlite3, sys; from pathlib import Path`
- **GOTCHA**: Do NOT update rules where COLLATE NOCASE already handles the match — only update rules where the canonical name is genuinely different (see alias table above). If a rule name already matches via COLLATE NOCASE, skip it and print "already correct".
- **GOTCHA**: Some rule rows have the same name in multiple rules (e.g. 'Ascorbic Acid' appears in rules 1, 2, 3). Update ALL rules sharing that Name_A/Name_B, not just the first.
- **GOTCHA**: Only update `Name_A` or `Name_B` when they are the unresolved side; don't touch the other side if it already matches.

**Core logic:**
```python
ALIAS_TABLE = {
    "ascorbic acid": "Vitamin C",
    "cholecalciferol": "Vitamin D",
    "d-alpha tocopherol": "Tocopherols",
    "dl-alpha tocopherol": "Tocopherols",
    "mixed tocopherols": "Tocopherols",
    "methylfolate": "Folate",
    "5-mthf": "Folate",
    "cyanocobalamin": "vitamin B12",
    "magnesium oxide": "Magnesia",
    "magnesium citrate": "Trimagnesium dicitrate",
    "hydroxypropyl methylcellulose": "Hypromellose",
    "hpmc": "Hypromellose",
    "dextrose": "D-Glucopyranose",
    "glucose": "D-Glucopyranose",
    "coq10": "Coenzyme Q10",
    "potassium citrate": "potassium citrate monohydrate",
    "vegetarian capsule": "Vegan Capsule",
}

def fix_name(name: str, canonical_set: set[str]) -> tuple[str, str]:
    """Returns (new_name, status) where status is 'updated'|'already_correct'|'unresolved'."""
    if name.lower() in canonical_set:
        return name, "already_correct"   # COLLATE NOCASE will match
    alias = ALIAS_TABLE.get(name.lower())
    if alias and alias.lower() in canonical_set:
        return alias, "updated"
    return name, "unresolved"
```

- **VALIDATE**:
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python scripts/fix_substitution_rules.py
# Expect: ~17 rules updated, ~23 rules already correct or unresolved
```

---

### TASK 3: RE-RUN SUBSTITUTION GRAPH

After running Task 2, re-run the substitution graph builder to generate new edges.

- **IMPLEMENT**: Run existing `SubstitutionGraphBuilder().run()` via pipeline
- **VALIDATE**:
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python -c "
import sys; sys.path.insert(0, '.')
from reasoning.substitution_graph import SubstitutionGraphBuilder
SubstitutionGraphBuilder().run()
"
```
```python
# Verify edge count
import sqlite3
conn = sqlite3.connect("db_enriched.sqlite")
print(conn.execute("SELECT COUNT(*) FROM Ingredient_Substitution").fetchone())
# Expect: >= 10 (was 4 before fix; should reach 30+ after aliases resolve ~15 rule pairs)
```

---

### TASK 4: PATCH `reasoning/proposal_generator.py`

Two targeted patches:

**Patch 4a — Fix compliance status filter (line 111):**
- **IMPLEMENT**: Change `AND pc.Status IN ('confirmed', 'claimed')` → `AND pc.Status IN ('confirmed', 'claimed', 'implied')`
- **PATTERN**: `reasoning/proposal_generator.py:101-113` — `_build_context` compliance query
- **GOTCHA**: All 126 compliance rows have `Status='implied'` — without this fix, proposals get zero compliance context

**Patch 4b — Add Grade_Flag to opportunity fetch (line 41):**
- **IMPLEMENT**: Add `ic.Grade_Flag, ic.SMILES` to the SELECT in `_get_top_opportunities()` and pass them through to `_build_context`
- **PATTERN**: `reasoning/proposal_generator.py:38-64` — `_get_top_opportunities` query
- **IMPLEMENT**: Update `_build_context` dict return at line 116 to include `"grade": opp["grade"], "smiles_available": opp["smiles"] is not None`
- **IMPLEMENT**: Change `TARGET_PROPOSAL_COUNT = 10` → `TARGET_PROPOSAL_COUNT = 50`
- **IMPLEMENT**: Add `ANTHROPIC_API_KEY` guard at start of `run()`:
```python
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    logger.error("ANTHROPIC_API_KEY not set — proposal generation requires this key. Exiting.")
    return
client = anthropic.Anthropic(api_key=api_key)
```
- **IMPLEMENT**: Add `Score_LLM_Adjustment` write in `_store_proposal()` — update the `UPDATE` statement to include `Score_LLM_Adjustment = ?` and pass `proposal.get("llm_adjustment", 0.0)` (clamped to [-0.10, 0.10])
- **GOTCHA**: `Score_LLM_Adjustment` column exists in schema (`schema/enriched_schema.sql:135`). Add it to the UPDATE statement in `_store_proposal`.
- **GOTCHA**: The user_prompt currently references `opp.get('function', 'Unknown')`. Add grade: `f"- Grade: {opp.get('grade', 'unknown')}"` to the prompt

- **VALIDATE**:
```python
# Quick verify: check the patched query returns compliance for Vitamin C
import sqlite3
conn = sqlite3.connect("db_enriched.sqlite")
result = conn.execute('''
    SELECT COUNT(DISTINCT pc.Certification) FROM Product_Compliance pc
    JOIN Product p ON p.Id = pc.ProductId
    JOIN BOM b ON b.ProducedProductId = p.Id
    JOIN BOM_Component bc ON bc.BOMId = b.Id
    JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
    JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
    WHERE ic.Name = "Vitamin C" COLLATE NOCASE
    AND pc.Status IN ("confirmed", "claimed", "implied")
''').fetchone()
print("Certs for Vitamin C:", result)
# Expect: 8
```

---

### TASK 5: VERIFY JUDGE QUERY

Document and verify the corrected judge query returns meaningful data.

- **IMPLEMENT**: Run the verified judge query (confirmed working in pre-plan diagnosis):
```python
import sqlite3
conn = sqlite3.connect("/home/developer/Projects/Spherecast Agnes/db_enriched.sqlite")
rows = conn.execute('''
    SELECT ic.Name, ic.Grade_Flag, ic.SMILES IS NOT NULL as has_smiles,
           co.Company_Count, co.Consolidation_Score,
           co.Proposal_Text IS NOT NULL as has_proposal,
           COUNT(DISTINCT sc.SupplierId) as priced_suppliers,
           COUNT(DISTINCT pc.Certification) as certs
    FROM Ingredient_Canonical ic
    LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
    LEFT JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
    LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
        SELECT DISTINCT b.ProducedProductId
        FROM BOM b
        JOIN BOM_Component bc ON bc.BOMId = b.Id
        JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
        WHERE stc.CanonicalId = ic.Id
    )
    GROUP BY ic.Id ORDER BY co.Consolidation_Score DESC LIMIT 10
''').fetchall()
for r in rows: print(r)
```
Expected output post-Phase A:
- `Grade_Flag` = 'supplement' / 'excipient' / 'food' etc. (not 'unknown')  
- `certs` >= 3 for Vitamin C, Vitamin D, Cellulose
- `Proposal_Text` = 0 (Phase B not run yet — that's expected)

---

### TASK 6: UPDATE `CLAUDE.md` 

- **IMPLEMENT**: Update the Current State table and add arc entries for the completed fixes
- **PATTERN**: Self-maintenance rule at top of `CLAUDE.md` — max 3 lines per entry

---

## TESTING STRATEGY

### Manual Validation (primary)
This is a data pipeline, not a service. Testing = running validation queries against the DB.

### Unit-testable function
`classify_grade()` is a pure function and can be spot-checked inline:
```python
assert classify_grade("Vitamin C", "OC[C@H]...")[0] == "supplement"
assert classify_grade("MAGNESIUM STEARATE", None)[0] == "excipient"
assert classify_grade("Sucralose", None)[0] == "sweetener"
assert classify_grade("natural Vanilla flavor", None)[0] == "flavor"
assert classify_grade("Gelatin", None)[0] == "food"
```

### Edge Cases to Verify
- `classify_grade("Protein", None)` → `"food"` (contains "protein" keyword)
- `classify_grade("organic Turmeric", None)` → `"food"` or `"unknown"` (no keyword hit — acceptable)
- `classify_grade("TITANIUM DIOXIDE", None)` → `"excipient"` (lowercase match on "titanium dioxide")
- `classify_grade("an inositol", "OC1...")[0]` → `"supplement"` (SMILES present fallback)
- All-caps names handled via `name.lower()`

---

## VALIDATION COMMANDS

### Level 1: Syntax Check
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python -c "import enrichment.enrichers.grade_classifier; import scripts.fix_substitution_rules" 2>&1
```

### Level 2: Grade Classifier
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python enrichment/enrichers/grade_classifier.py
```
```python
import sqlite3
conn = sqlite3.connect("db_enriched.sqlite")
print(conn.execute("SELECT Grade_Flag, COUNT(*) FROM Ingredient_Canonical GROUP BY Grade_Flag ORDER BY 2 DESC").fetchall())
# Expect: unknown < 50
```

### Level 3: Substitution Fix + Re-run
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python scripts/fix_substitution_rules.py
cd "/home/developer/Projects/Spherecast Agnes" && python -c "
import sys; sys.path.insert(0, '.')
from reasoning.substitution_graph import SubstitutionGraphBuilder
SubstitutionGraphBuilder().run()
import sqlite3
print(sqlite3.connect('db_enriched.sqlite').execute('SELECT COUNT(*) FROM Ingredient_Substitution').fetchone())
"
# Expect: >= 10
```

### Level 4: Compliance Patch Verification
```python
import sqlite3
conn = sqlite3.connect("db_enriched.sqlite")
# Vitamin C should have 8 distinct certs
result = conn.execute("""
    SELECT COUNT(DISTINCT pc.Certification) FROM Product_Compliance pc
    JOIN Product p ON p.Id = pc.ProductId
    JOIN BOM b ON b.ProducedProductId = p.Id
    JOIN BOM_Component bc ON bc.BOMId = b.Id
    JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
    JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
    WHERE ic.Name = "Vitamin C" COLLATE NOCASE
    AND pc.Status IN ("confirmed", "claimed", "implied")
""").fetchone()[0]
assert result >= 8, f"Expected >= 8 certs for Vitamin C, got {result}"
print(f"OK: {result} certs for Vitamin C")
```

### Level 5: Full Judge Query
```python
import sqlite3
conn = sqlite3.connect("db_enriched.sqlite")
rows = conn.execute('''
    SELECT ic.Name, ic.Grade_Flag, ic.SMILES IS NOT NULL as has_smiles,
           co.Company_Count, co.Consolidation_Score,
           COUNT(DISTINCT sc.SupplierId) as priced_suppliers,
           COUNT(DISTINCT pc.Certification) as certs
    FROM Ingredient_Canonical ic
    LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
    LEFT JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
    LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
        SELECT DISTINCT b.ProducedProductId
        FROM BOM b
        JOIN BOM_Component bc ON bc.BOMId = b.Id
        JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
        WHERE stc.CanonicalId = ic.Id
    )
    GROUP BY ic.Id ORDER BY co.Consolidation_Score DESC LIMIT 10
''').fetchall()
for r in rows: print(r)
# Vitamin C row: Grade_Flag != 'unknown', certs >= 3
assert rows[0][1] != 'unknown', "Vitamin C Grade_Flag still unknown"
assert rows[0][6] >= 3, "Vitamin C certs too low"
```

---

## ACCEPTANCE CRITERIA

- [ ] `Grade_Flag != 'unknown'` for >= 200 of 250 canonicals (80%+)
- [ ] `Ingredient_Substitution` has >= 10 edges (up from 4)
- [ ] Judge query returns `certs >= 3` for Vitamin C
- [ ] `proposal_generator.py` compliance query returns > 0 rows for Vitamin C (post-patch)
- [ ] All scripts run without errors from project root
- [ ] `fix_substitution_rules.py` reports <= 25 unresolved rules (most skipped are valid mismatches)
- [ ] No API key needed for any Phase A script

---

## COMPLETION CHECKLIST

- [ ] Task 1: `grade_classifier.py` created and run — Grade_Flag populated
- [ ] Task 2: `fix_substitution_rules.py` created and run — rules updated
- [ ] Task 3: Substitution graph re-run — edge count >= 10
- [ ] Task 4: `proposal_generator.py` patched — status filter, Grade_Flag in context, TARGET=50, API key guard, Score_LLM_Adjustment write
- [ ] Task 5: Judge query verified — certs > 0 for top ingredients
- [ ] Task 6: CLAUDE.md updated with new state
- [ ] All validation commands passed

---

## NOTES

**Why `Magnesia` for `Magnesium Oxide`:** PubChem CID 14791 for MgO resolves to "Magnesia" as the preferred name in this DB. The rule uses "Magnesium Oxide" but the canonical is stored as "Magnesia". Both refer to the same compound.

**Why all compliance rows are `implied`:** The compliance enricher (`compliance_enricher.py`) sets Status from DSLD label claims — these are all DSLD-implied certifications (not formally verified). The status `'implied'` is the intended value; the proposal generator's filter was just over-restrictive.

**Why COLLATE NOCASE doesn't need alias updates for all-caps names:** `substitution_graph.py:84` uses `WHERE Name = ? COLLATE NOCASE` which treats `VITAMIN E` and `Vitamin E` as equal. The ALIAS_TABLE only needs entries where the names are genuinely different strings (e.g. "Ascorbic Acid" ≠ "Vitamin C").

**Phase B prerequisite:** Grade_Flag must be populated before running `proposal_generator.py` so proposals include grade in context. Run Phase A Tasks 1-4 before attempting Phase B.

**`scripts/` directory:** Does not exist yet. Create it as a plain directory (no `__init__.py` needed since scripts run standalone via `python scripts/fix_substitution_rules.py` from project root).
