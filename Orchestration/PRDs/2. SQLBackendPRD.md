# Agnes — SQLite Backend Foundation PRD

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Active — implementation plan for backend stabilization before Phase 4  
**Owner:** timbtz  
**Supersedes:** N/A — companion to `PRD.md` (narrows scope to backend completion)

---

## 1. Executive Summary

Agnes's enrichment pipeline has completed Phases 1 and 2 with a v1.0 schema that is missing critical cross-reference fields required by the rest of the pipeline. The current database holds 854 resolved SKU-to-canonical mappings and 294 BOM quantity rows, but lacks the `SMILES`, `UNII_Code`, and `MatchScore` columns needed for deduplication, Molport commercial lookups, and defensible consolidation scoring. Phase 3 has zero rows.

This document specifies the work required to transform `db_enriched.sqlite` from its current partially-enriched v1.0 state into a stable, fully cross-referenced v1.1 foundation that Phase 4 reasoning can operate over. The work is purely backend: schema migration, backfill passes, data quality fixes, and coverage improvement. No frontend, no agent orchestration.

**MVP goal for this document:** A `db_enriched.sqlite` that satisfies every Phase 1–3 validation query in `PRD.md §11`, has zero duplicate canonical rows for the same UNII, has SMILES populated for ≥ 50% of canonicals, and has `Product_Compliance` populated for ≥ 28 finished goods — all achieved before Phase 4 scoring is run.

---

## 2. Mission

**Get the data right before reasoning over it.** Every Phase 4 proposal is only as trustworthy as the data it reads. A fragmented Vitamin C cluster, missing SMILES, and empty compliance tables would produce proposals with wrong company counts, failed Molport lookups, and undetectable compliance gaps.

### Core Principles

1. **Schema first, data second** — no enrichment pass runs against a column that doesn't exist.
2. **Idempotent always** — every fix, backfill, and re-run must be safe to repeat. `INSERT OR REPLACE` and `ON CONFLICT DO UPDATE` everywhere.
3. **Dedup before scoring** — the consolidation scorer must see merged clusters, not split ones. Vitamin C at 42 companies beats Vitamin C at 25 and l-ascorbic acid at 17.
4. **Cache-first backfill** — Phase 1 backfill (SMILES, UNII) must hit `API_Response_Cache` before making network calls. All 854 PubChem responses are already cached.
5. **Compliance without Molport** — Phase 3 compliance (DSLD claims → `Product_Compliance`) runs entirely on cached data. It does not block on the Molport API key.

---

## 3. Target Users (of this PRD)

### Primary: Pipeline Developer (timbtz)
- Runs each implementation step sequentially
- Needs: precise file paths, function signatures, SQL validation queries, and clear dependency order
- Success: every validation query in §11 returns a passing number

### Secondary: Hackathon Judges (indirect)
- Will query `db_enriched.sqlite` directly during evaluation
- Need: clean canonical rows, populated compliance data, defensible consolidation scores
- Success: a single JOIN view per ingredient shows company count, BOM count, supplier count, price, and compliance in one query

---

## 4. Current State Assessment

### What Exists

| Layer | Current | Target | Gap |
|---|---|---|---|
| Schema version | v1.0 | v1.1 | 15 missing columns across 6 tables |
| `SKU_To_Canonical` rows | 854 | ≥ 657 (≥ 0.65 conf) | ✅ over-target |
| `Ingredient_Canonical` rows | 279 | Correct canonical count | Inflated — UNII duplicates present |
| `Ingredient_Canonical.SMILES` | Column missing | ≥ 50% populated | Column doesn't exist |
| `Ingredient_Canonical.UNII_Code` | Column missing | ≥ 40% populated | Column doesn't exist |
| `BOM_Component_Quantity` rows | 294 | ≥ 400 | 106 short; 19.2% component coverage |
| `Supplier_Commercial` rows | 0 | ≥ 200 | Blocked on Molport API key |
| `Product_Compliance` rows | 0 | ≥ 70 | Not run; DSLD data cached |
| UNII duplicate canonicals | ≥ 2 known (Vitamin C / l-ascorbic acid) | 0 | Dedup pass missing |
| `Ingredient_Substitution` rows | 0 | Seeded from UNII clusters | Blocked on UNII_Code column |

### Known Data Quality Issues

**[CONFIRMED BUG]** Vitamin C (25 companies) and l-ascorbic acid (17 companies) are separate canonical rows sharing UNII `PQ6CK8PD0R`. Unmerged, the true 42-company consolidation opportunity — the largest in the dataset — is invisible to Phase 4.

**[OBSERVED]** Fuzzy matcher surfacing IUPAC display names (e.g. `(2R)-2-[(1S)...`) instead of common names. Cosmetic but affects readability of cluster reports and proposals.

**[PHASE 2 ROOT CAUSE]** Component coverage at 19.2% (294/1528) despite 55 finished goods matched. Primary causes:
1. Token_set_ratio threshold 70 too strict for case variants (`CALCIUM CARBONATE` vs `Calcium Carbonate`)
2. BOM components without `SKU_To_Canonical` entries can't be matched by canonical name
3. DSLD "not provided" (NP) unit values (26 rows) add rows with no useful Amount
4. Brand name synonym gaps (NOW Foods vs NOW, Thorne vs Thorne FX)

**[OBSERVED]** Gelatin and Calcium have no CAS — Gelatin is a protein mixture; Calcium is form-ambiguous. These will not get SMILES from PubChem; their canonical rows need `Grade_Flag='food'` (Gelatin) and Form disambiguation (Calcium).

**[KNOWN LIMIT]** `Sucralose CID 56038-13-2` surfacing in Phase 1 output — likely a parser artifact on a non-ingredient SKU slug. Needs spot-check in `sku_parser.py`.

---

## 5. MVP Scope

### ✅ In Scope

**Schema**
- ✅ Apply all v1.1 DDL changes to `schema/enriched_schema.sql`
- ✅ Re-run `db_bootstrap.py` to migrate `db_enriched.sqlite` to v1.1
- ✅ Verify all 11 Agnes-added tables exist with correct column types

**Phase 1 Backfill**
- ✅ Backfill `SMILES` for all `Ingredient_Canonical` rows with `PubChem_CID`
- ✅ Backfill `UNII_Code` for canonicals via DSLD name search (cache-first)
- ✅ Backfill `MatchScore` in `SKU_To_Canonical` (raw similarity score before calibration)
- ✅ Fix display name selection: prefer DSLD preferred name over IUPAC in `ingredient_normalizer.py`

**UNII Deduplication**
- ✅ Identify all `Ingredient_Canonical` rows sharing a `UNII_Code`
- ✅ Merge duplicate rows: keep oldest, re-point all `SKU_To_Canonical.CanonicalId` references
- ✅ Delete merged duplicate canonical rows
- ✅ Spot-check Sucralose artifact in `sku_parser.py`

**Phase 2 Coverage Improvement**
- ✅ Lower ingredient match threshold 70 → 55 in `quantity_enricher.py`
- ✅ Add UNII-based matching: if BOM component's canonical has `UNII_Code`, search DSLD `ingredientRows` by UNII (exact, no fuzzy)
- ✅ Expand brand name synonym table in `quantity_enricher.py`
- ✅ Accept `offMarket=1` labels with `OffMarket=1` flag (PRD §8 explicitly permits)
- ✅ Filter out `Unit='NP'` rows or replace with `NULL`
- ✅ Re-run Phase 2; target ≥ 500 rows and ≥ 60% component coverage on matched products

**Phase 3 Compliance (no Molport needed)**
- ✅ Run `compliance_enricher.py` against cached DSLD label data
- ✅ Parse `claims[].langualCodeDescription` → `CERT_SIGNAL_MAP` → `Product_Compliance`
- ✅ Parse `statements[].text` via pattern matching for cert keywords
- ✅ Filter `offMarket=0` labels only for compliance
- ✅ Set `Off_Market_Warning=1` where label is `offMarket=1`
- ✅ Target ≥ 28 `Product_Compliance` rows (50% of 55 matched finished goods)

**Phase 3 Commercial (Molport — when key available)**
- ✅ Implement `enrichment/sources/molport.py` (CAS-first → SMILES fallback)
- ✅ Run `commercial_enricher.py` → `Supplier_Commercial`
- ✅ Tag all prices `Price_Type='retail_proxy'`, `Grade_Unverified=1`
- ✅ Target ≥ 200 `Supplier_Commercial` rows

**Ingredient_Substitution Seeding**
- ✅ From UNII clusters: pairs sharing UNII get `SubstitutionType='identical'`
- ✅ Seed 6–10 curated `Ingredient_Substitution_Rule` rows for common supplement form variants
- ✅ Populate `Ingredient_Substitution` from rules + UNII cluster inference

### ❌ Out of Scope for This Document

- ❌ Phase 4 reasoning, scoring, or proposal generation
- ❌ FDC integration (food macros only — 5 SKUs; low impact)
- ❌ RxNorm integration (drug-class only; narrow applicability in this dataset)
- ❌ Retailer scraping fallback (iHerb, Vitacost)
- ❌ Certification registry scraping (NSF, USP, Informed Sport)
- ❌ Google ADK agents
- ❌ Frontend / API layer
- ❌ `Discovered_Supplier` or `Supplier_Alternative` tables

---

## 6. User Stories

### US-B1: Schema Migration
**As a pipeline operator**, I want to run `python enrichment/db_bootstrap.py` and get a v1.1 schema with all new columns, so that subsequent phases can write SMILES, UNII codes, and confidence types correctly.

*Validation:* `PRAGMA table_info(Ingredient_Canonical)` returns `SMILES`, `UNII_Code`, `Grade_Flag` columns.

### US-B2: SMILES Backfill
**As a pipeline operator**, I want every `Ingredient_Canonical` row with a `PubChem_CID` to have its `SMILES` populated without re-fetching already-cached responses, so that Phase 3 Molport lookups have their primary search key ready.

*Validation:* `SELECT COUNT(*) FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL` returns 0.

### US-B3: UNII Deduplication
**As a sourcing analyst**, I want Agnes to show Vitamin C purchased by 42 companies as one row, not as "Vitamin C (25 co.)" and "l-ascorbic acid (17 co.)" split across two rows, so that the true consolidation opportunity is visible.

*Validation:* `SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1` returns 0 rows.

### US-B4: Phase 2 Coverage
**As a pipeline operator**, I want Phase 2 to populate `BOM_Component_Quantity` for ≥ 60% of matched BOM components, so that Phase 4 scoring has sufficient BOM count signal to rank consolidation candidates accurately.

*Validation:* `SELECT COUNT(*) FROM BOM_Component_Quantity` ≥ 500; `Unit != 'NP'` on all rows with an Amount value.

### US-B5: Compliance Population
**As a sourcing analyst**, I want to see which certifications (NSF, Kosher, GlutenFree, Organic) each matched finished good claims, so that Phase 4 can flag compliance gaps when recommending a supplier switch.

*Validation:* `SELECT COUNT(*) FROM Product_Compliance` ≥ 28.

### US-B6: Substitution Seeding
**As a sourcing analyst**, I want Agnes to know that Vitamin C and Ascorbic Acid are identical, and that Magnesium Citrate and Magnesium Oxide are equivalent with bioavailability caveats, so that consolidation proposals include substitution feasibility context.

*Validation:* `SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType = 'identical'` ≥ number of merged UNII pairs; curated rules for top-6 form variants present.

### US-B7: Audit Trail
**As a hackathon judge**, I want to query `Enrichment_Run_Log` and see a record for every Phase 1 backfill attempt (success, cache_hit, or no_match), so that I can verify no silent failures occurred during the migration.

*Validation:* After backfill, `SELECT COUNT(*) FROM Enrichment_Run_Log WHERE Phase = 1 AND Step = 'smiles_backfill'` = number of PubChem_CID-bearing canonical rows.

---

## 7. Detailed Implementation Specifications

### Step 1 — Schema v1.1 Upgrade

**File:** `schema/enriched_schema.sql`

Apply the following DDL additions. The file must be idempotent (`IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` with `IF NOT EXISTS` guard via Python migration script).

#### `Ingredient_Canonical` — add 6 columns

```sql
ALTER TABLE Ingredient_Canonical ADD COLUMN UNII_Code TEXT;
ALTER TABLE Ingredient_Canonical ADD COLUMN Molport_Id TEXT;
ALTER TABLE Ingredient_Canonical ADD COLUMN FDC_Id INTEGER;
ALTER TABLE Ingredient_Canonical ADD COLUMN RxCUI TEXT;
ALTER TABLE Ingredient_Canonical ADD COLUMN SMILES TEXT;
ALTER TABLE Ingredient_Canonical ADD COLUMN Grade_Flag TEXT DEFAULT 'unknown';
```

`SMILES` is critical for Molport's SMILES-based search. Must be populated in Phase 1 backfill alongside `PubChem_CID` — do not defer to Phase 3.

`UNII_Code` is the deduplication key. FDA's authoritative cross-reference resolves name variants ("silicon-dioxide" vs "silica") via the same UNII `ETJ7Z6XBU4`.

#### `SKU_To_Canonical` — add 1 column

```sql
ALTER TABLE SKU_To_Canonical ADD COLUMN MatchScore REAL;
```

Raw similarity score before calibration. Enables post-hoc confidence tuning without re-running the full Phase 1 enrichment.

#### `BOM_Component_Quantity` — add 3 columns

```sql
ALTER TABLE BOM_Component_Quantity ADD COLUMN ServingsPerContainer REAL;
ALTER TABLE BOM_Component_Quantity ADD COLUMN OffMarket INTEGER DEFAULT 0;
ALTER TABLE BOM_Component_Quantity ADD COLUMN DSLD_Label_Id TEXT;
```

`DSLD_Label_Id` enables re-fetching a specific label without re-searching by brand. `OffMarket` gates compliance use (Phase 3 compliance must filter `OffMarket=0`).

#### `Supplier_Commercial` — fix type + add 7 columns

```sql
-- Cannot ALTER type in SQLite; requires table recreation
-- Migration script must: CREATE new table, copy data, DROP old, RENAME new
-- New Confidence column: REAL NOT NULL DEFAULT 0.0 (was TEXT in v1.0)
ALTER TABLE Supplier_Commercial ADD COLUMN Price_Qty_KG REAL;
ALTER TABLE Supplier_Commercial ADD COLUMN Purity_Pct REAL;
ALTER TABLE Supplier_Commercial ADD COLUMN Purity_Qualifier TEXT;
ALTER TABLE Supplier_Commercial ADD COLUMN Grade_Unverified INTEGER NOT NULL DEFAULT 1;
ALTER TABLE Supplier_Commercial ADD COLUMN Molport_Catalog_Id TEXT;
ALTER TABLE Supplier_Commercial ADD COLUMN Data_Freshness_Days INTEGER;
ALTER TABLE Supplier_Commercial ADD COLUMN Country_Shipping TEXT;
```

**SQLite constraint:** `ALTER TABLE ... MODIFY COLUMN` does not exist. The `Confidence TEXT → REAL` fix requires creating a new table with the corrected schema, copying all rows, dropping the old table, and renaming. Since `Supplier_Commercial` currently has 0 rows, this is a DROP + CREATE with no data migration cost.

#### `Product_Compliance` — add 1 column

```sql
ALTER TABLE Product_Compliance ADD COLUMN Off_Market_Warning INTEGER NOT NULL DEFAULT 0;
```

#### `Consolidation_Opportunity` — add 4 columns

```sql
ALTER TABLE Consolidation_Opportunity ADD COLUMN Unique_SKU_Count INTEGER DEFAULT 0;
ALTER TABLE Consolidation_Opportunity ADD COLUMN Score_Formula_Component REAL;
ALTER TABLE Consolidation_Opportunity ADD COLUMN Score_LLM_Adjustment REAL;
ALTER TABLE Consolidation_Opportunity ADD COLUMN Compliance_Feasible INTEGER;
```

**Implementation:** Write `enrichment/db_migrate_v11.py` that runs all migrations idempotently using `PRAGMA table_info()` checks before each `ALTER TABLE`. Call this from `db_bootstrap.py` when schema version is detected as v1.0.

---

### Step 2 — Phase 1 Backfill (SMILES + UNII_Code + MatchScore)

**File:** `enrichment/normalizers/ingredient_normalizer.py` (add backfill mode)  
**New file:** `enrichment/backfill_phase1.py`

#### SMILES Backfill Logic

```python
def backfill_smiles(db_conn):
    """Populate SMILES for all canonicals with PubChem_CID, cache-first."""
    cur = db_conn.cursor()
    cur.execute("""
        SELECT Id, PubChem_CID FROM Ingredient_Canonical
        WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL
    """)
    rows = cur.fetchall()
    
    for canonical_id, cid in rows:
        # Check API_Response_Cache first
        cache_key = f"smiles_{cid}"
        cached = get_cached_response(db_conn, 'pubchem', cache_key)
        
        if cached is None:
            smiles = pubchem_client.get_isomeric_smiles(cid)  # rate-limited
            cache_response(db_conn, 'pubchem', cache_key, smiles)
        else:
            smiles = cached
        
        cur.execute(
            "UPDATE Ingredient_Canonical SET SMILES = ? WHERE Id = ?",
            (smiles, canonical_id)
        )
        log_enrichment(db_conn, None, 1, 'smiles_backfill',
                      'cache_hit' if cached else 'success', 0.97)
```

The PubChem PUG REST endpoint for SMILES:
```
GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/IsomericSMILES/JSON
```

Respect rate limit: 4.5 req/sec. All Phase 1 CID lookups are already cached, so SMILES fetches are the only new network calls.

#### UNII_Code Backfill Logic

```python
def backfill_unii(db_conn):
    """Populate UNII_Code via DSLD ingredient search, cache-first."""
    cur = db_conn.cursor()
    cur.execute("""
        SELECT Id, Name FROM Ingredient_Canonical
        WHERE UNII_Code IS NULL
    """)
    rows = cur.fetchall()
    
    for canonical_id, name in rows:
        cache_key = f"unii_{name.lower()}"
        cached = get_cached_response(db_conn, 'dsld', cache_key)
        
        if cached is None:
            result = dsld_client.search_ingredient(name)
            cache_response(db_conn, 'dsld', cache_key, result)
        else:
            result = cached
        
        if result and result.get('uniiCode'):
            cur.execute(
                "UPDATE Ingredient_Canonical SET UNII_Code = ? WHERE Id = ?",
                (result['uniiCode'], canonical_id)
            )
```

DSLD ingredient search endpoint (from `dsld-integration.md`):
```
GET https://api.ods.od.nih.gov/dsld/v9/ingredient?name={name}
Headers: X-Api-Key: {DSLD_API_KEY}
```

#### Display Name Fix

In `ingredient_normalizer.py`, `_select_best_name()` currently returns IUPAC when no preferred name is set. Fix:

```python
def _select_best_name(pubchem_data, dsld_data, extracted_name):
    # Priority: DSLD preferred name > PubChem IUPACName if short (< 40 chars)
    # > extracted slug name > IUPAC (fallback only)
    if dsld_data and dsld_data.get('preferredName'):
        return dsld_data['preferredName']
    iupac = pubchem_data.get('IUPACName', '')
    if iupac and len(iupac) < 40:
        return iupac
    return extracted_name or iupac
```

---

### Step 3 — UNII Deduplication Merge

**File:** `enrichment/normalizers/fuzzy_matcher.py` (add `dedup_by_unii()` function)

#### Algorithm

```python
def dedup_by_unii(db_conn):
    """
    Find Ingredient_Canonical rows sharing a UNII_Code.
    Keep oldest (lowest Id). Re-point all SKU_To_Canonical rows.
    Delete duplicates.
    """
    cur = db_conn.cursor()
    
    # Find UNII groups with > 1 canonical
    cur.execute("""
        SELECT UNII_Code, MIN(Id) AS keep_id, GROUP_CONCAT(Id) AS all_ids
        FROM Ingredient_Canonical
        WHERE UNII_Code IS NOT NULL
        GROUP BY UNII_Code
        HAVING COUNT(*) > 1
    """)
    groups = cur.fetchall()
    
    for unii, keep_id, all_ids_str in groups:
        all_ids = [int(x) for x in all_ids_str.split(',')]
        drop_ids = [i for i in all_ids if i != keep_id]
        
        # Re-point SKU_To_Canonical
        for drop_id in drop_ids:
            cur.execute("""
                UPDATE OR REPLACE SKU_To_Canonical
                SET CanonicalId = ?
                WHERE CanonicalId = ?
            """, (keep_id, drop_id))
        
        # Re-point Ingredient_Substitution
        for drop_id in drop_ids:
            cur.execute(
                "UPDATE Ingredient_Substitution SET IngredientAId = ? WHERE IngredientAId = ?",
                (keep_id, drop_id)
            )
            cur.execute(
                "UPDATE Ingredient_Substitution SET IngredientBId = ? WHERE IngredientBId = ?",
                (keep_id, drop_id)
            )
        
        # Delete duplicates
        for drop_id in drop_ids:
            cur.execute("DELETE FROM Ingredient_Canonical WHERE Id = ?", (drop_id,))
        
        print(f"UNII {unii}: merged {drop_ids} → {keep_id}")
    
    db_conn.commit()
```

#### Expected Outcome

Post-dedup cluster report for Vitamin C:
- `Name`: Vitamin C (or l-ascorbic acid, whichever has lower Id)
- `Company_Count`: 42 (was split 25/17)
- `BOM_Count`: 89 (was split 52/37)

This is the single highest-impact data quality fix. It costs zero API calls and transforms the #1 consolidation candidate from invisible to dominant.

#### Sucralose Artifact Spot-Check

```python
# In sku_parser.py, add guard:
KNOWN_NON_INGREDIENTS = {'sucralose-cid-56038-13-2', 'prop-65-warning'}
if normalized_slug in KNOWN_NON_INGREDIENTS:
    return None  # skip, not an ingredient SKU
```

---

### Step 4 — Phase 2 Coverage Improvement

**File:** `enrichment/enrichers/quantity_enricher.py`

#### Root Cause Analysis (from Phase 2 output)

The 19.2% component match rate (294/1528) has four causes:

| Cause | Fix |
|---|---|
| Threshold 70 too strict for case variants | Lower to 55; DSLD names are clean so FP rate stays low |
| BOM components without `SKU_To_Canonical` | Match by canonical name after dedup (Step 3 enlarges clusters) |
| DSLD NP units (26 rows) | Store `Amount=NULL, Unit=NULL` instead of `Unit='NP'` |
| Brand name synonym gaps | Expand synonym table |

#### Threshold and Matching Changes

```python
# Before:
score = fuzz.token_set_ratio(canonical_name, dsld_ingredient_name)
if score >= 70:
    match = True

# After:
# 1. Try exact UNII match first (highest confidence)
if canonical.unii_code and dsld_row.get('uniiCode') == canonical.unii_code:
    match = True
    confidence = 0.95
    
# 2. Try case-insensitive exact match
elif canonical_name.lower() == dsld_ingredient_name.lower():
    match = True
    confidence = 0.90

# 3. Fuzzy fallback
else:
    score = fuzz.token_set_ratio(canonical_name, dsld_ingredient_name)
    if score >= 55:
        match = True
        confidence = 0.65 + (score - 55) / 100  # 0.65–0.80 range
```

#### Brand Name Synonym Table

```python
BRAND_SYNONYMS = {
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
```

#### NP Unit Handling

```python
# In quantity_enricher.py:
amount_raw = ingredient_row.get('amount', {})
amount_val = amount_raw.get('quantity')
unit_val = amount_raw.get('unit', {}).get('abbreviation')

# NP = "not provided" — store as NULL, still record the row
if unit_val == 'NP':
    amount_val = None
    unit_val = None
```

#### offMarket=1 Acceptance

```python
# Accept offMarket=1 labels; set OffMarket flag
off_market = 1 if label.get('offMarket', False) else 0
# PRD §8: "OffMarket=1 labels are valid for Phase 2 quantity enrichment"
# Do NOT use for compliance (Phase 3)
```

**Expected improvement:** Accepting `offMarket=1` and lowering threshold to 55 should increase from 294 → 450–600 rows. UNII-based matching adds highest-confidence rows for well-resolved canonicals.

---

### Step 5 — Phase 3 Compliance (DSLD Claims)

**File:** `enrichment/enrichers/compliance_enricher.py`

This enricher already exists. Verify it implements the full certification signal map and runs against cached responses only.

#### Certification Signal Map (complete)

```python
CERT_SIGNAL_MAP = {
    "nsf": "NSF",
    "nsf certified": "NSF",
    "usp verified": "USP",
    "usp": "USP",
    "informed sport": "InformedSport",
    "informed choice": "InformedSport",
    "informed-sport": "InformedSport",
    "bscg": "BSCG",
    "certified for sport": "BSCG",
    "organic": "Organic",
    "usda organic": "Organic",
    "certified organic": "Organic",
    "non-gmo": "NonGMO",
    "non gmo": "NonGMO",
    "gluten-free": "GlutenFree",
    "gluten free": "GlutenFree",
    "vegan": "Vegan",
    "certified vegan": "Vegan",
    "halal": "Halal",
    "cgmp": "cGMP",
    "gmp": "cGMP",
    "current good manufacturing": "cGMP",
    "kosher": "Kosher",
}
```

#### Source Priority

```python
def extract_certifications(label_json):
    """
    Source priority: dsld_claims > dsld_statements > (manual: not automated)
    Returns list of (certification, status, source, confidence) tuples.
    """
    found = {}
    
    # Tier 1: claims[].langualCodeDescription
    for claim in label_json.get('claims', []):
        desc = claim.get('langualCodeDescription', '').lower()
        for signal, cert_name in CERT_SIGNAL_MAP.items():
            if signal in desc:
                found[cert_name] = ('claimed', 'dsld_claims', 0.85)
    
    # Tier 2: statements[].text (pattern match)
    for stmt in label_json.get('statements', []):
        text = stmt.get('text', '').lower()
        for signal, cert_name in CERT_SIGNAL_MAP.items():
            if signal in text and cert_name not in found:
                found[cert_name] = ('implied', 'dsld_statements', 0.65)
    
    return found
```

#### offMarket Gate

```python
# Only use offMarket=0 labels for compliance
# If only offMarket=1 label available: store with Off_Market_Warning=1, Status='claimed'
# This mirrors PRD §8: "offMarket=1 labels may have lapsed certifications"
```

---

### Step 6 — Molport Integration (Phase 3 Commercial)

**File to create:** `enrichment/sources/molport.py`

**Status:** Blocked on `MOLPORT_API_KEY` in `.env`. Implement the module now; commercial_enricher will no-op gracefully if key is absent.

#### Lookup Chain

```python
class MolportClient:
    BASE = "https://api.molport.com/api"
    
    def lookup_ingredient(self, canonical):
        """CAS-first → SMILES fallback → return supplier list."""
        
        # Step 1: Try CAS-based molecule load
        if canonical.cas_number:
            result = self._load_by_cas(canonical.cas_number)
            if result:
                return result
        
        # Step 2: Try SMILES-based search
        if canonical.smiles:
            molport_id = self._search_by_smiles(canonical.smiles)
            if molport_id:
                return self._load_by_molport_id(molport_id)
        
        return None
    
    def _load_by_cas(self, cas):
        url = f"{self.BASE}/molecule/load"
        params = {"molecule": cas, "apikey": self.api_key}
        # Response: {"Data": {"Molecule": {"Molport Id": ..., "Suppliers": [...]}}}
        # NOTE: Molport uses Title Case field names with spaces
        
    def _search_by_smiles(self, smiles):
        url = f"{self.BASE}/chemical-search/search"
        payload = {"Structure": smiles, "Search Type": 1, "apikey": self.api_key}
        # POST JSON; returns {"Data": {"Molecules": [{"Molport Id": ...}]}}
    
    def flatten_suppliers(self, molecule_data):
        """
        Flatten Suppliers[].Catalogue[].Packings[] into Supplier_Commercial rows.
        NOTE: Molport field names use Title Case with spaces:
        - "Supplier Name", "Delivery Days", "Last Update Date"
        - "Price", "Amount", "Measure"
        """
        rows = []
        for supplier in molecule_data.get('Suppliers', []):
            for catalogue_entry in supplier.get('Catalogue', []):
                for packing in catalogue_entry.get('Packings', []):
                    rows.append({
                        'supplier_name': supplier.get('Supplier Name'),
                        'price_usd': packing.get('Price'),
                        'amount_kg': self._normalize_to_kg(
                            packing.get('Amount'), packing.get('Measure')
                        ),
                        'delivery_days': supplier.get('Delivery Days'),
                        'molport_catalog_id': catalogue_entry.get('Molport Catalog Id'),
                        'last_update_date': catalogue_entry.get('Last Update Date'),
                        'purity': self._parse_purity(catalogue_entry.get('Purity')),
                    })
        return rows
```

**Field name warning:** Molport API returns Title Case field names with spaces ("Supplier Name", not "supplier_name"). This is confirmed in `Orchestration/References/molport-integration.md`. Do not assume snake_case.

**Price disclaimer:** All Molport prices are research/lab scale. Always set `Price_Type='retail_proxy'`. Any `Proposal_Text` that references pricing must include: *"pricing is indicative at research/lab quantities — production-volume pricing requires direct supplier negotiation."*

---

### Step 7 — Ingredient_Substitution Seeding

**File:** `reasoning/substitution_graph.py`

#### Seeding from UNII Clusters

After dedup, pairs that were merged share a UNII (they are chemically identical by definition):

```python
def seed_substitutions_from_unii_history(db_conn, merge_log):
    """
    merge_log: list of (keep_id, drop_id, unii) tuples from dedup pass.
    Each pair gets SubstitutionType='identical', Score=1.0.
    """
    for keep_id, drop_id, unii in merge_log:
        db_conn.execute("""
            INSERT OR REPLACE INTO Ingredient_Substitution
            (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
            VALUES (?, ?, 'identical', 1.0, 'Same UNII: ' || ?, '["unii_dedup"]')
        """, (keep_id, drop_id, unii))
```

#### Curated Substitution Rules

Seed `Ingredient_Substitution_Rule` with high-value supplement form variants:

```sql
INSERT INTO Ingredient_Substitution_Rule 
(Name_A, Name_B, Rule_Type, Confidence, Justification, Caveats, Source)
VALUES
('Vitamin C', 'Sodium Ascorbate', 'equivalent', 0.85,
 'Same antioxidant function; sodium form is buffered', 
 'Sodium content ~12%; not suitable for sodium-restricted formulations', 'curated'),

('Ascorbic Acid', 'Calcium Ascorbate', 'equivalent', 0.80,
 'Same antioxidant function; calcium form is buffered',
 'Calcium contributes to DV; label disclosure required', 'curated'),

('Magnesium Citrate', 'Magnesium Oxide', 'equivalent', 0.70,
 'Same mineral; bioavailability differs (~25% vs ~60%)',
 'Oxide has lower absorption; dose adjustment required for equivalent effect', 'curated'),

('Magnesium Citrate', 'Magnesium Glycinate', 'equivalent', 0.80,
 'Same mineral; glycinate has highest absorption',
 'Cost premium ~3x; suitable drop-in if budget allows', 'curated'),

('Cholecalciferol', 'Ergocalciferol', 'equivalent', 0.75,
 'D3 vs D2; both raise serum 25(OH)D',
 'D3 more potent per IU for sustained elevation; vegan products may specify D2', 'curated'),

('Gelatin', 'Collagen Peptides', 'partial', 0.50,
 'Both are collagen-derived proteins; Gelatin gels, peptides dissolve',
 'Functional difference in applications requiring gelling; not always interchangeable', 'curated'),

('Calcium Carbonate', 'Calcium Citrate', 'equivalent', 0.75,
 'Same mineral; citrate absorbs without food, carbonate requires acid',
 'Patients on proton pump inhibitors should use citrate', 'curated')
;
```

---

## 8. Technology Stack

| Component | Library | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.11+ | All pipeline phases |
| Database | SQLite | stdlib | `db_enriched.sqlite` |
| HTTP | `requests` | ≥ 2.31 | PubChem, DSLD, Molport |
| Rate limiting | `time.sleep` + token bucket | stdlib | PubChem 4.5 req/sec |
| Fuzzy matching | `rapidfuzz` | ≥ 3.0 | Ingredient name matching |
| Env | `python-dotenv` | ≥ 1.0 | `.env` loading |
| LLM (Phase 4 only) | `anthropic` SDK | latest | Proposal generation |

### External APIs Used in This Scope

| API | Auth | Used for | Rate limit |
|---|---|---|---|
| PubChem PUG REST | None | SMILES backfill | 5/sec, 400/min |
| NIH DSLD v9 | `DSLD_API_KEY` | UNII backfill, compliance | Undocumented |
| Molport v3 | `MOLPORT_API_KEY` | Supplier commercial | 10k/month |

---

## 9. Security & Configuration

### Environment Variables Required

```bash
# Already in use
DSLD_API_KEY=...        # Required for UNII backfill (Step 2)

# Required for Step 6
MOLPORT_API_KEY=...     # Pending receipt; molport.py no-ops if absent
ANTHROPIC_API_KEY=...   # Phase 4 only; not required for backend completion
```

### Safe Migration Pattern

The `db_migrate_v11.py` migration script must:
1. Read `PRAGMA table_info(table_name)` before each `ALTER TABLE`
2. Skip the `ALTER TABLE` if the column already exists
3. Handle `Supplier_Commercial.Confidence` TYPE fix via CREATE/COPY/DROP/RENAME (no data loss since 0 rows exist)
4. Write a migration log entry to `Enrichment_Run_Log` on completion

---

## 10. Success Criteria

### Backend Completion Definition

A backend is considered complete when a single JOIN view per ingredient returns:
- Canonical name, CAS, UNII, SMILES, Grade_Flag
- Company count and BOM count from `SKU_To_Canonical`
- At least one `BOM_Component_Quantity` row (for ~55% of ingredients used in finished goods)
- At least one `Supplier_Commercial` row (for CAS-identified ingredients)
- At least one `Product_Compliance` row (for matched finished goods)
- Zero duplicate UNII rows in `Ingredient_Canonical`

### Functional Requirements

**Step 1 — Schema**
- ✅ `PRAGMA table_info(Ingredient_Canonical)` includes `SMILES`, `UNII_Code`, `Grade_Flag`
- ✅ `PRAGMA table_info(SKU_To_Canonical)` includes `MatchScore`
- ✅ `PRAGMA table_info(Supplier_Commercial)` shows `Confidence` as `REAL` (not `TEXT`)
- ✅ All 11 Agnes enrichment tables present

**Step 2 — Backfill**
- ✅ `SELECT COUNT(*) FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL` = 0
- ✅ `SELECT COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL` ≥ 112 (≥ 40% of 279)
- ✅ `SELECT COUNT(*) FROM Enrichment_Run_Log WHERE Step = 'smiles_backfill'` = rows with PubChem_CID

**Step 3 — UNII Dedup**
- ✅ `SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1` = 0 rows
- ✅ Vitamin C cluster company count ≥ 35 (merged)
- ✅ `SELECT COUNT(*) FROM Ingredient_Canonical` decreases by number of merged duplicates

**Step 4 — Phase 2**
- ✅ `SELECT COUNT(*) FROM BOM_Component_Quantity` ≥ 500
- ✅ `SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Unit = 'NP'` = 0
- ✅ `SELECT COUNT(DISTINCT BOMId) FROM BOM_Component_Quantity` ≥ 60

**Step 5 — Compliance**
- ✅ `SELECT COUNT(*) FROM Product_Compliance` ≥ 28
- ✅ `SELECT COUNT(DISTINCT ProductId) FROM Product_Compliance` ≥ 20
- ✅ `SELECT DISTINCT Certification FROM Product_Compliance` includes ≥ 4 distinct values

**Step 6 — Molport (when key available)**
- ✅ `SELECT COUNT(*) FROM Supplier_Commercial` ≥ 200
- ✅ `SELECT COUNT(*) FROM Supplier_Commercial WHERE Price_Type != 'retail_proxy'` = 0
- ✅ `SELECT COUNT(*) FROM Supplier_Commercial WHERE Grade_Unverified != 1` = 0

**Step 7 — Substitution**
- ✅ `SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType = 'identical'` ≥ 1
- ✅ `SELECT COUNT(*) FROM Ingredient_Substitution_Rule` ≥ 6

### Quality Indicators

- Pipeline runtime (warm cache): Steps 1–3 < 5 min, Step 2 backfill < 10 min (rate-limited)
- `Enrichment_Run_Log`: no `Status='error'` rows without corresponding investigation note
- `Confidence` distribution: < 10% of `SKU_To_Canonical` rows with Confidence < 0.50

---

## 11. Implementation Phases (Execution Order)

### Phase A — Schema Migration & Backfill (Day 1, ~2 hours)

**Goal:** v1.1 schema live; SMILES and UNII populated on all existing canonicals.

**Deliverables:**
- ✅ `enrichment/db_migrate_v11.py` — idempotent migration script
- ✅ Update `schema/enriched_schema.sql` to v1.1 spec
- ✅ Update `enrichment/db_bootstrap.py` to call migration
- ✅ `enrichment/backfill_phase1.py` — SMILES + UNII backfill (cache-first)
- ✅ Fix display name selection in `ingredient_normalizer.py`

**Validation:**
```sql
SELECT COUNT(*) FROM Ingredient_Canonical WHERE SMILES IS NULL AND PubChem_CID IS NOT NULL;
-- Must return 0
```

---

### Phase B — Deduplication & Data Quality (Day 1, ~1 hour)

**Goal:** Zero UNII duplicates; Vitamin C cluster unified; Sucralose artifact removed.

**Deliverables:**
- ✅ `dedup_by_unii()` function in `fuzzy_matcher.py`
- ✅ Sucralose guard in `sku_parser.py`
- ✅ Run dedup; verify cluster report shows merged Vitamin C

**Validation:**
```sql
SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical
WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1;
-- Must return 0 rows
```

---

### Phase C — Phase 2 Re-Run & Phase 3 Compliance (Day 1–2, ~3 hours)

**Goal:** BOM coverage ≥ 500 rows; Product_Compliance ≥ 28 rows.

**Deliverables:**
- ✅ Threshold + UNII matching + synonym table in `quantity_enricher.py`
- ✅ NP unit handling fix
- ✅ Re-run Phase 2: `python enrichment/pipeline.py --phase 2`
- ✅ Run Phase 3 compliance: `python enrichment/pipeline.py --phase 3`

**Validation:**
```sql
SELECT COUNT(*) FROM BOM_Component_Quantity;    -- ≥ 500
SELECT COUNT(*) FROM Product_Compliance;         -- ≥ 28
```

---

### Phase D — Molport Commercial & Substitution Seeding (Day 2, ~3 hours)

**Goal:** Supplier_Commercial ≥ 200 rows; Ingredient_Substitution seeded.

**Deliverables:**
- ✅ `enrichment/sources/molport.py` implemented
- ✅ Run Phase 3 commercial: `python enrichment/pipeline.py --phase 3` (when key available)
- ✅ Curated `Ingredient_Substitution_Rule` rows inserted
- ✅ `reasoning/substitution_graph.py` seeding function

**Validation:**
```sql
SELECT COUNT(*) FROM Supplier_Commercial;        -- ≥ 200 (when key available)
SELECT COUNT(*) FROM Ingredient_Substitution;    -- ≥ 1
SELECT COUNT(*) FROM Ingredient_Substitution_Rule; -- ≥ 6
```

---

## 12. Critical SQL Verification Queries

```sql
-- Full backend health check (run after all steps)

-- 1. Schema version check
SELECT COUNT(*) FROM pragma_table_info('Ingredient_Canonical')
WHERE name IN ('SMILES', 'UNII_Code', 'Grade_Flag', 'Molport_Id');
-- Expect: 4

-- 2. Phase 1 coverage
SELECT
    COUNT(*) AS total_rm,
    SUM(CASE WHEN stc.Confidence >= 0.65 THEN 1 END) AS resolved,
    ROUND(100.0 * SUM(CASE WHEN stc.Confidence >= 0.65 THEN 1 END) / COUNT(*), 1) AS pct
FROM Product p LEFT JOIN SKU_To_Canonical stc ON stc.ProductId = p.Id
WHERE p.Type = 'raw-material';
-- Expect: resolved ≥ 657 (75%)

-- 3. SMILES coverage
SELECT COUNT(*) AS with_smiles,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Ingredient_Canonical), 1) AS pct
FROM Ingredient_Canonical WHERE SMILES IS NOT NULL;
-- Expect: ≥ 50%

-- 4. UNII dedup clean
SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical
WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1;
-- Expect: 0 rows

-- 5. Top consolidation candidates (post-dedup)
SELECT ic.Name, COUNT(DISTINCT p.CompanyId) AS companies,
       COUNT(DISTINCT bc.BOMId) AS boms
FROM Ingredient_Canonical ic
JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
JOIN Product p ON p.Id = stc.ProductId
LEFT JOIN BOM_Component bc ON bc.ConsumedProductId = p.Id
GROUP BY ic.Id ORDER BY companies DESC LIMIT 5;
-- Vitamin C (merged) should appear at ≥ 35 companies

-- 6. Phase 2 quality
SELECT COUNT(*) AS bom_rows,
    SUM(CASE WHEN Unit IS NULL OR Unit = 'NP' THEN 1 ELSE 0 END) AS null_unit_rows
FROM BOM_Component_Quantity;
-- bom_rows ≥ 500; null_unit_rows = 0 (NP converted to NULL)

-- 7. Phase 3 compliance
SELECT COUNT(*) AS compliance_rows,
    COUNT(DISTINCT ProductId) AS products_covered,
    COUNT(DISTINCT Certification) AS cert_types
FROM Product_Compliance;
-- ≥ 28 rows, ≥ 20 products, ≥ 4 cert types

-- 8. Supplier commercial (post-Molport)
SELECT COUNT(*) AS sc_rows,
    SUM(CASE WHEN Price_Type != 'retail_proxy' THEN 1 ELSE 0 END) AS bad_price_type
FROM Supplier_Commercial;
-- sc_rows ≥ 200; bad_price_type = 0
```

---

## 13. Future Considerations

### Immediately After Backend Completion → Phase 4

With the backend stabilized, Phase 4 can run:
1. `consolidation_scorer.py` — formula score using `company_count`, `bom_count`, `sku_count`, `supplier_count` (weights: 0.40/0.25/0.20/0.15)
2. LLM adjustment for top-50 (requires `ANTHROPIC_API_KEY`)
3. `proposal_generator.py` — structured JSON + markdown narrative for top-10

The formula score does not require `Supplier_Commercial` data — it uses existing `Supplier_Product` from `db.sqlite`. Phase 4 can start even before Molport commercial data is available.

### Phase 2 Fallback (if re-run doesn't hit 500 rows)

If DSLD re-run + threshold tuning still misses target:
1. Run iHerb/Vitacost scraper for the ~30 unmatched products (Playwright, see `browser-automation.md`)
2. Only for brands with no DSLD presence; DSLD is primary source

### FDC Integration (low priority)

5 food-grade SKUs (whey, collagen, maltodextrin, gelatin, inulin) benefit from FDC `fdcId`. Implement after Phase 4 proposals are running — these SKUs have lower consolidation priority than vitamins and minerals.

### RxNorm (very low priority)

After Phase 1 coverage report: if unresolved SKUs include drug-class ingredients (CoQ10-drug-form, melatonin), RxNorm adds value. Current dataset appears supplement-dominated.

---

## 14. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Molport API key not yet received; Phase 3 commercial blocked | High | Implement `molport.py` now; `commercial_enricher.py` no-ops gracefully if `MOLPORT_API_KEY` absent. Phase 4 formula scoring runs without commercial data — uses `Supplier_Product` from `db.sqlite` for supplier count. |
| UNII dedup merges incorrect rows (false UNII match from DSLD) | Medium | After dedup, run cluster spot-check for top-10 merged groups. If company count jumps implausibly (e.g., > 50 for a narrow ingredient), investigate the UNII. Log all merges with full detail. |
| Phase 2 re-run still below 500 rows after threshold tuning | Medium | Lower threshold further to 45 for case-insensitive exact stem matches only. Accept `offMarket=1` with flag (PRD-approved). If still below 400: browser scraper for top 20 unmatched brands (Playwright). |
| DSLD API rate limiting during UNII backfill (279 name lookups) | Low | UNII backfill checks `API_Response_Cache` first. Most names were already searched in Phase 1 — expect < 50 new network calls. Add 0.25s delay between uncached calls. |
| SQLite `ALTER TABLE` missing `IF NOT EXISTS` causes migration failure on re-run | Low | `db_migrate_v11.py` reads `PRAGMA table_info()` before every `ALTER TABLE`. Skips if column already present. Migration is fully idempotent. |

---

## 15. Appendix

### Related Documents

| Document | Purpose |
|---|---|
| `Orchestration/PRDs/PRD.md` | Full Agnes PRD (schema spec, all phases, success criteria) |
| `Orchestration/PRDs/meta-workflow.md` | Stage-by-stage implementation workflow |
| `Orchestration/References/dsld-integration.md` | DSLD v9 API guide (live-tested) |
| `Orchestration/References/molport-integration.md` | Molport v3 guide (validate field names on first real call) |
| `Orchestration/References/pubchem-integration.md` | PubChem PUG REST guide |
| `Orchestration/Plans/phase1-naming-fix-and-phase2-dsld-quantity.md` | Prior plan for Phase 1+2 naming fixes |

### File Map for This PRD's Scope

```
Agnes/
├── enrichment/
│   ├── db_bootstrap.py          — call db_migrate_v11.py
│   ├── db_migrate_v11.py        — NEW: idempotent v1.0→v1.1 migration
│   ├── backfill_phase1.py       — NEW: SMILES + UNII backfill
│   ├── normalizers/
│   │   ├── ingredient_normalizer.py  — FIX: display name selection
│   │   └── fuzzy_matcher.py          — ADD: dedup_by_unii()
│   ├── parsers/
│   │   └── sku_parser.py             — FIX: Sucralose artifact guard
│   ├── sources/
│   │   ├── pubchem.py           — ADD: get_isomeric_smiles(cid)
│   │   ├── dsld.py              — ADD: search_ingredient_by_name()
│   │   └── molport.py           — NEW: CAS/SMILES lookup + flatten
│   └── enrichers/
│       ├── quantity_enricher.py — FIX: threshold, UNII match, synonyms, NP units
│       ├── commercial_enricher.py — FIX: Molport field names (Title Case)
│       └── compliance_enricher.py — FIX: full CERT_SIGNAL_MAP, Off_Market_Warning
├── reasoning/
│   └── substitution_graph.py   — ADD: seed_from_unii_history(), curated rules
└── schema/
    └── enriched_schema.sql      — UPDATE: v1.1 DDL
```

### Phase 2 Diagnosis Summary

From the Phase 2 run (294 rows, 19.2% coverage):
- Root cause 1: `token_set_ratio` threshold 70 failing on case variants (`CALCIUM CARBONATE` vs `Calcium Carbonate`) — fix: lower to 55, add case-insensitive exact match tier
- Root cause 2: BOM components without `SKU_To_Canonical` entries can't be bridged — fix: UNII-based exact match (after Step 2 backfill)
- Root cause 3: 26 rows with `Unit='NP'` inflating row count without usable amount — fix: store as `NULL`
- Root cause 4: Brand name variants causing DSLD label miss — fix: synonym table expansion
- Root cause 5: `offMarket=1` labels excluded — fix: accept with `OffMarket=1` flag (PRD §8 permits)

Expected improvement from fixes: 294 → 500–700 rows; 55 → 70–90 finished goods covered.
