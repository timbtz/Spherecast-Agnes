# Feature: Phase 1 Naming Fix + Phase 2 DSLD Quantity Enrichment

The following plan should be complete, but validate documentation and codebase patterns before implementing. Pay special attention to field names in DSLD API responses — there are two different schemas: `search-filter` endpoint uses `allIngredients[].name`, while `label/{id}` endpoint uses `ingredientRows[].name` with nested `quantity[]` array.

## Feature Description

Two coordinated improvements:

1. **Phase 1 Naming Fix** — Replace IUPAC chemical names (e.g., "magnesium bis(octadecanoate)") with human-readable preferred names (e.g., "Magnesium Stearate") in `Ingredient_Canonical.Name`. The IUPAC name is preserved in the existing `IUPAC_Name` column.

2. **Phase 2 DSLD Quantity Enrichment Rewrite** — Replace the broken `QuantityEnricher` (which extracts useless numeric IDs as product names) with a working implementation that: (a) extracts product names from slug-based SKUs, (b) uses ingredient-fingerprint matching for numeric-ID SKUs, (c) correctly parses DSLD label `ingredientRows`, and (d) stores mg/serving quantities in `BOM_Component_Quantity`. No browser scraper needed for the DSLD-covered fraction (~55–65% of 149 finished goods).

## User Story

As Agnes (the supply chain AI),  
I want to resolve BOM component quantities from DSLD supplement labels using human-readable ingredient names,  
So that consolidation proposals cite real mg/serving data and the cluster report shows ingredient names buyers recognize.

## Problem Statement

**Naming:** `PubChemClient.lookup()` sets `result["name"] = props.get("IUPACName", name)`. This IUPAC string is then written to `Ingredient_Canonical.Name`, making the cluster report unreadable. PubChem's synonym list always has the preferred commercial name at index 0.

**Phase 2 – product name extraction:** `_sku_to_product_name("FG-iherb-10421")` returns `"10421"` — a numeric iHerb product ID that DSLD cannot search. DSLD has never been called for Phase 2; `BOM_Component_Quantity` has 0 rows.

**Phase 2 – ingredient amount extraction:** `DSLDClient.extract_ingredient_amounts()` reads `row.get("ingredientName")` but the DSLD label schema uses `row.get("name")`, and quantities are nested in `row["quantity"][]` (array), not a scalar. This method would produce empty results even if a label were found.

**Phase 2 – ingredient matching:** `_store_amounts()` matches DSLD ingredient names to `Ingredient_Canonical.Name` using simple `in` substring logic against IUPAC names — which will never match "Vitamin D3" to "magnesium bis(octadecanoate)". Must match against human-readable preferred names after the naming fix.

## Solution Statement

1. **Naming fix**: In `PubChemClient.lookup()`, derive `preferred_name` from `synonyms[0]` (filter to ASCII, ≤ 60 chars, not all-caps) and set `result["name"] = preferred_name`. IUPAC_Name stays in its own field. Re-run Phase 1 (fast from cache) to backfill `Ingredient_Canonical.Name`.

2. **Phase 2 rewrite**: 
   - Add `dsld.find_label(brand, product_name)` (from reference doc pattern) with brand+name fuzzy scoring.
   - Add `dsld.extract_label_ingredients(label_id)` that correctly reads `ingredientRows[].name` + `ingredientRows[].quantity[]`.
   - Rewrite `QuantityEnricher._enrich_product()` with a two-path strategy:
     - **Slug path**: extract product name from Thrive Market / readable SKUs → DSLD brand+name search
     - **Numeric-ID path**: use BOM ingredient fingerprinting — fetch all DSLD labels for the company, score by ingredient overlap, accept if ≥ 3 ingredients match
   - Add `DSLD_Label_Id` column to `BOM_Component_Quantity` for audit trail.
   - Use `FuzzyMatcher.match()` (after naming fix) for ingredient-to-canonical matching rather than substring logic.
   - Add `ThreadPoolExecutor` for concurrent finished-good processing.

## Feature Metadata

**Feature Type**: Enhancement + Bug Fix  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `enrichment/sources/pubchem.py`, `enrichment/sources/dsld.py`, `enrichment/enrichers/quantity_enricher.py`, `enrichment/normalizers/fuzzy_matcher.py`, `schema/enriched_schema.sql`  
**Dependencies**: `rapidfuzz`, `requests` (already installed), `sqlite3` (stdlib)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `enrichment/sources/pubchem.py` (lines 57–76) — `lookup()` currently sets `"name": props.get("IUPACName", name)` and stores `synonyms[:20]` in result but never uses them for naming. Fix is here.
- `enrichment/sources/pubchem.py` (lines 87–95) — `_get_synonyms(cid)` already returns the full list. `synonyms[0]` is the preferred name.
- `enrichment/sources/dsld.py` (lines 36–65) — `search_ingredient()` — already fixed to read `allIngredients[].name`. Use same pattern for Phase 2 label search.
- `enrichment/sources/dsld.py` (lines 97–114) — `extract_ingredient_amounts()` — BROKEN: reads `ingredientName` (wrong) and `row.get("quantity")` as scalar (wrong). Must be replaced.
- `enrichment/enrichers/quantity_enricher.py` (lines 38–75) — `_enrich_product()` — broken product-name extraction and no real DSLD matching. Full rewrite needed.
- `enrichment/enrichers/quantity_enricher.py` (lines 77–120) — `_store_amounts()` — substring matching against IUPAC names. Replace with `FuzzyMatcher.match()`.
- `enrichment/normalizers/fuzzy_matcher.py` (lines 22–52) — `match()` returns `canonical_id` in result dict; use this in `_store_amounts()` to skip the name-matching step entirely.
- `enrichment/normalizers/ingredient_normalizer.py` (lines 95–143) — `_upsert_mapping()` / `_get_or_create_canonical()` — must pass `preferred_name` separately from `iupac_name` after pubchem fix.
- `schema/enriched_schema.sql` (lines 49–63) — `BOM_Component_Quantity` columns. Add `DSLD_Label_Id INTEGER` and `Off_Market INTEGER` (0/1).

### New Files to Create

None — all changes are in existing files.

### Relevant Documentation — READ BEFORE IMPLEMENTING

- `Orchestration/References/dsld-integration.md` (lines 90–135) — **CRITICAL**: verified DSLD label schema showing `ingredientRows[].name`, `ingredientRows[].quantity[]` array with `quantity`, `unit`, `servingSizeQuantity`, `servingSizeUnit`. Also contains `score_dsld_hit()` reference implementation (lines 161–169) and `dsld_find_label()` / `dsld_extract_ingredients()` reference implementations (lines 243–282).
- `Orchestration/References/dsld-integration.md` (lines 149–175) — brand name mapping table (NOW Foods → NOW, Thorne → Thorne FX) and confidence thresholds (≥ 0.85 accept, 0.65–0.84 flag, < 0.65 skip).
- `Orchestration/References/dsld-integration.md` (lines 326–336) — gotchas: unit inconsistency (IU vs mcg for Vitamin D), multiple serving sizes (use `servingSizeOrder: 1`), nested blends in `nestedRows`, `offMarket` handling.

### Patterns to Follow

**Caching pattern** (pubchem.py lines 106–136, dsld.py lines 134–163):
```python
def _get_cache(self, key: str) -> tuple[bool, dict | None]:
    conn = sqlite3.connect(self.db_path)
    row = conn.execute(
        "SELECT Response FROM API_Response_Cache WHERE Source = ? AND Cache_Key = ? ...",
        (source, key),
    ).fetchone()
    conn.close()
    return (True, json.loads(row[0])) if row else (False, None)
```

**Throttle lock pattern** (pubchem.py — thread-safe, already in place):
```python
with _throttle_lock:
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()
```

**Concurrency pattern** (ingredient_normalizer.py — established in this session):
```python
with ThreadPoolExecutor(max_workers=8) as pool:
    futures = {pool.submit(_resolve, (i, item)): item for i, item in enumerate(items, 1)}
    for future in as_completed(futures):
        key, result = future.result()
        results[key] = result
```

**Provenance pattern** — every enriched field must carry source + confidence:
```python
{"amount": 125, "unit": "mcg", "source": "dsld", "confidence": 0.88, "dsld_label_id": 20581}
```

**Idempotent upsert** — always use `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE`.

---

## IMPLEMENTATION PLAN

### Part A: Phase 1 Naming Fix

#### Task A1 — FIX `pubchem.py`: derive preferred name from synonyms

**File:** `enrichment/sources/pubchem.py`  
**Change:** In `lookup()`, after fetching synonyms, compute `preferred_name` from `synonyms[0]` with a quality filter, then set `result["name"] = preferred_name`.

```python
# After: synonyms = self._get_synonyms(cid)
preferred = _pick_preferred_name(synonyms, fallback=name)

# Replace the result dict construction:
result = {
    "name": preferred,                  # ← was: props.get("IUPACName", name)
    "iupac_name": props.get("IUPACName"),
    "cas_number": cas,
    "pubchem_cid": cid,
    "molecular_formula": props.get("MolecularFormula"),
    "synonyms": synonyms[:20],
    "confidence": 0.97 if cas else 0.80,
    "method": "pubchem",
    "sources": ["pubchem"],
}
```

Add helper function at module level:
```python
def _pick_preferred_name(synonyms: list[str], fallback: str) -> str:
    """Return the first synonym that looks like a human-readable name (not all-caps, not IUPAC)."""
    for syn in synonyms:
        # Skip registry IDs, IUPAC-style names, and all-caps abbreviations
        if re.match(r'^[A-Z0-9\-]+$', syn):  # all-caps / registry ID
            continue
        if len(syn) > 80:  # IUPAC names are long
            continue
        if syn.count('(') > 2:  # IUPAC nesting
            continue
        return syn.strip()
    return fallback
```

**GOTCHA:** `synonyms[0]` is usually correct, but for some compounds PubChem puts registry IDs first. The filter above skips those. Test with "magnesium stearate" (expected: "Magnesium Stearate"), "ascorbic acid" (expected: "Ascorbic acid" or "Vitamin C"), "cholecalciferol" (expected: "Cholecalciferol").

**VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
from enrichment.sources.pubchem import PubChemClient
c = PubChemClient(':memory:')
for name in ['magnesium stearate', 'ascorbic acid', 'cholecalciferol', 'zinc']:
    r = c.lookup(name)
    print(f'{name} → {r[\"name\"]} (iupac: {r.get(\"iupac_name\",\"N/A\")[:40]})')
"
```

---

#### Task A2 — FIX `ingredient_normalizer.py`: pass iupac_name separately to canonical

**File:** `enrichment/normalizers/ingredient_normalizer.py`  
**Change:** In `_get_or_create_canonical()`, use `result.get("iupac_name")` for the `IUPAC_Name` column instead of duplicating `name`. The `Name` column now holds the preferred name from PubChem or the DSLD name.

```python
# In _get_or_create_canonical(), INSERT statement — update IUPAC_Name binding:
cursor = conn.execute(
    """INSERT INTO Ingredient_Canonical
       (Name, CAS_Number, PubChem_CID, IUPAC_Name, Molecular_Formula,
        Function, Confidence, Sources)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        name,
        cas,
        result.get("pubchem_cid"),
        result.get("iupac_name"),      # ← was result.get("iupac_name") via old "name" — now explicit
        result.get("molecular_formula"),
        result.get("function"),
        result.get("confidence", 0.0),
        json.dumps(result.get("sources", [])),
    ),
)
```

No logic change needed — just ensuring the separation is clean after the PubChem fix.

**VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sqlite3, json
conn = sqlite3.connect('db_enriched.sqlite')
rows = conn.execute('SELECT Name, IUPAC_Name, CAS_Number FROM Ingredient_Canonical WHERE CAS_Number IS NOT NULL LIMIT 10').fetchall()
for r in rows: print(r)
"
```

---

#### Task A3 — RE-RUN Phase 1 to backfill preferred names

**Note:** Existing `Ingredient_Canonical` rows must be updated. The simplest approach is `--bootstrap` (force re-clone + re-run) since all API responses are cached — it will be fast.

```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 enrichment/pipeline.py --bootstrap --phase 1 2>&1
```

**GOTCHA:** `--bootstrap` deletes `db_enriched.sqlite` and re-clones from `db.sqlite`. All Phase 1 API responses are cached in `API_Response_Cache` — but that table lives in `db_enriched.sqlite`. After `--bootstrap`, the cache is lost and all API calls are re-made.

**Better approach** — update in-place instead of re-bootstrapping:
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 -c "
import sqlite3, json
from enrichment.sources.pubchem import PubChemClient
conn = sqlite3.connect('db_enriched.sqlite')
client = PubChemClient('db_enriched.sqlite')
rows = conn.execute('SELECT Id, Name, PubChem_CID FROM Ingredient_Canonical WHERE PubChem_CID IS NOT NULL').fetchall()
for id_, current_name, cid in rows:
    result = client.lookup(current_name)  # served from cache
    if result and result['name'] != current_name:
        conn.execute('UPDATE Ingredient_Canonical SET Name=?, IUPAC_Name=? WHERE Id=?',
                     (result['name'], result.get('iupac_name'), id_))
        print(f'Updated: {current_name!r} → {result[\"name\"]!r}')
conn.commit()
conn.close()
"
```

**VALIDATE:** Cluster report should now show "Magnesium Stearate" instead of "magnesium bis(octadecanoate)". Run:
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 enrichment/pipeline.py --phase 1 2>&1 | grep -A 30 "Top Consol"
```

---

### Part B: Phase 2 DSLD Quantity Enrichment

#### Task B1 — FIX `dsld.py`: add `find_label()` + fix `extract_label_ingredients()`

**File:** `enrichment/sources/dsld.py`

**Add method `find_label()`** — replaces the broken `search_product()` usage. Based exactly on `dsld_find_label()` reference implementation in `Orchestration/References/dsld-integration.md` lines 243–258:

```python
def find_label(self, brand: str, product_name: str,
               min_confidence: float = 0.65) -> dict | None:
    """Search DSLD for a finished product; return best match metadata or None."""
    from rapidfuzz import fuzz
    query = f"{brand} {product_name}".strip()
    data = self._search({"q": query, "size": 5})
    if not data or not data.get("hits"):
        return None

    best, best_score = None, 0.0
    for hit in data["hits"]:
        src = hit.get("_source", {})
        b = fuzz.partial_ratio(brand.lower(), src.get("brandName", "").lower()) / 100
        n = fuzz.token_set_ratio(product_name.lower(), src.get("fullName", "").lower()) / 100
        if b < 0.60 or n < 0.60:
            continue
        score = round((b * 0.4) + (n * 0.6), 3)
        if score > best_score:
            best_score = score
            best = {
                "dsld_id": hit["_id"],
                "confidence": score,
                "off_market": src.get("offMarket", "1"),
                "brand_name": src.get("brandName"),
                "full_name": src.get("fullName"),
            }
    return best if best and best_score >= min_confidence else None
```

**Add method `extract_label_ingredients()`** — replaces the broken `extract_ingredient_amounts()`. Based on reference implementation `dsld_extract_ingredients()` in `Orchestration/References/dsld-integration.md` lines 261–282:

```python
def extract_label_ingredients(self, label_id: str | int) -> list[dict]:
    """Fetch label and return structured ingredient list with amounts.
    
    Reads ingredientRows[].name and ingredientRows[].quantity[] (array, not scalar).
    Also recurses into nestedRows for proprietary blends.
    """
    label = self.get_label(label_id)
    if not label:
        return []

    results = []

    def _parse_rows(rows: list[dict]) -> None:
        for row in rows:
            name = row.get("name", "").strip()
            if not name or name in ("Calories", "Calories from Fat"):
                continue
            for qty in row.get("quantity", []):
                if qty.get("servingSizeOrder", 1) != 1:
                    continue  # use primary serving size only
                results.append({
                    "ingredient_name": name,
                    "unii_code": row.get("uniiCode"),
                    "category": row.get("category"),
                    "ingredient_group": row.get("ingredientGroup"),
                    "forms": [f["name"] for f in row.get("forms", [])],
                    "amount": qty.get("quantity"),
                    "unit": qty.get("unit"),
                    "per_serving": qty.get("servingSizeQuantity"),
                    "serving_unit": qty.get("servingSizeUnit"),
                    "source": "dsld",
                    "confidence": 0.90,
                    "dsld_label_id": label_id,
                })
            # Recurse into nested blend rows
            for nested in row.get("nestedRows", []):
                _parse_rows([nested])

    _parse_rows(label.get("ingredientRows", []))
    return results
```

**Keep `extract_ingredient_amounts()` as a deprecated alias** pointing to the new method for backward compat:
```python
def extract_ingredient_amounts(self, label_data: dict) -> list[dict]:
    # Deprecated: use extract_label_ingredients(label_id) instead
    label_id = label_data.get("id") or label_data.get("_id")
    if label_id:
        return self.extract_label_ingredients(label_id)
    return []
```

**VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 -c "
from enrichment.sources.dsld import DSLDClient
d = DSLDClient('db_enriched.sqlite')
# Find a known label
match = d.find_label('NOW Foods', 'Vitamin D3')
print('Match:', match)
if match:
    ings = d.extract_label_ingredients(match['dsld_id'])
    print(f'Ingredients ({len(ings)}):')
    for i in ings[:5]: print(' ', i)
"
```

---

#### Task B2 — ADD schema column: `DSLD_Label_Id` in `BOM_Component_Quantity`

**File:** `schema/enriched_schema.sql` — update the DDL:
```sql
CREATE TABLE IF NOT EXISTS BOM_Component_Quantity (
    BOMId               INTEGER NOT NULL,
    ConsumedProductId   INTEGER NOT NULL,
    Amount              REAL,
    Unit                TEXT,
    PerServing          REAL,
    ServingUnit         TEXT,
    DSLD_Label_Id       TEXT,            -- ← ADD: DSLD label ID used as source
    Off_Market          INTEGER,         -- ← ADD: 0=current, 1=off-market label
    Source              TEXT,
    Source_URL          TEXT,
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (BOMId, ConsumedProductId),
    FOREIGN KEY (BOMId)             REFERENCES BOM(Id),
    FOREIGN KEY (ConsumedProductId) REFERENCES Product(Id)
);
```

**Apply to existing DB** (non-destructive ALTER):
```python
# In quantity_enricher.py __init__ or a one-time migration:
conn = sqlite3.connect(self.db_path)
for col, typedef in [("DSLD_Label_Id", "TEXT"), ("Off_Market", "INTEGER")]:
    try:
        conn.execute(f"ALTER TABLE BOM_Component_Quantity ADD COLUMN {col} {typedef}")
    except Exception:
        pass  # column already exists
conn.commit()
conn.close()
```

**VALIDATE:**
```bash
python3 -c "import sqlite3; conn = sqlite3.connect('db_enriched.sqlite'); print([r[1] for r in conn.execute('PRAGMA table_info(BOM_Component_Quantity)').fetchall()])"
```

---

#### Task B3 — REWRITE `quantity_enricher.py`

**File:** `enrichment/enrichers/quantity_enricher.py`

Full rewrite. Key design decisions:

**A. SKU → (brand, product_name) extraction:**

```python
def _parse_fg_sku(self, sku: str, company_name: str) -> tuple[str, str | None]:
    """Return (brand, product_name_or_None) for DSLD search.
    
    Slug-based SKUs contain product name; numeric-ID SKUs return None → fingerprint path.
    """
    # Strip FG- prefix
    if not sku.startswith("FG-"):
        return company_name, None
    rest = sku[3:]  # "iherb-10421" or "thrive-market-thorne-vitamin-d-5-000"

    # Identify retailer prefix
    for prefix in ("iherb-", "walmart-", "amazon-", "target-", "vitacost-",
                   "vitamin-shoppe-", "walgreens-", "cvs-", "costco-",
                   "sams-club-", "gnc-", "thrive-market-"):
        if rest.startswith(prefix):
            slug = rest[len(prefix):]
            # Numeric-only = no product name extractable
            if re.match(r'^\d+$', slug) or re.match(r'^[A-Z0-9\-]+$', slug):
                return company_name, None
            # Slug contains brand prefix (e.g. "thorne-vitamin-d-5-000") — strip brand if it matches
            product_name = slug.replace("-", " ").strip()
            return company_name, product_name
    return company_name, None
```

**B. Ingredient fingerprint fallback** for numeric-ID SKUs:

```python
def _fingerprint_match(self, conn, company_name: str, bom_id: int) -> dict | None:
    """Match a finished good to DSLD by ingredient overlap when product name is unknown."""
    from rapidfuzz import fuzz as rfuzz
    
    # Get BOM ingredient names
    bom_ingredients = conn.execute("""
        SELECT ic.Name FROM Ingredient_Canonical ic
        JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
        JOIN BOM_Component bc ON bc.ConsumedProductId = stc.ProductId
        WHERE bc.BOMId = ?
    """, (bom_id,)).fetchall()
    
    if not bom_ingredients:
        return None
    
    bom_names = {r[0].lower() for r in bom_ingredients}
    
    # Search DSLD by brand only (size=10)
    data = self._dsld._search({"q": company_name, "size": 10})
    if not data or not data.get("hits"):
        return None
    
    best, best_overlap = None, 0
    for hit in data["hits"]:
        src = hit.get("_source", {})
        dsld_ingredients = {i["name"].lower() for i in src.get("allIngredients", [])}
        overlap = len(bom_names & dsld_ingredients)
        if overlap > best_overlap:
            best_overlap = overlap
            best = {"dsld_id": hit["_id"], "confidence": min(0.65 + overlap * 0.05, 0.85),
                    "off_market": src.get("offMarket", "1"),
                    "brand_name": src.get("brandName"), "full_name": src.get("fullName")}
    
    return best if best_overlap >= 3 else None  # require ≥ 3 matching ingredients
```

**C. Full `run()` and `_enrich_product()` structure:**

```python
class QuantityEnricher:
    def __init__(self, db_path=ENRICHED_DB):
        self.db_path = str(db_path)
        self._dsld = DSLDClient(self.db_path)
        self._fuzzy = FuzzyMatcher(self.db_path)
        self._apply_schema_migrations()

    def run(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT p.Id, p.SKU, c.Name AS company_name
            FROM Product p
            JOIN Company c ON c.Id = p.CompanyId
            WHERE p.Type = 'finished-good'
        """).fetchall()
        conn.close()
        logger.info(f"Enriching BOM quantities for {len(rows)} finished goods")

        # Instantiate clients once, then process concurrently
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda r: self._enrich_product(*r), rows))

        self._report()

    def _enrich_product(self, product_id, sku, company_name):
        brand, product_name = self._parse_fg_sku(sku, company_name)
        
        conn = sqlite3.connect(self.db_path)
        boms = conn.execute("SELECT Id FROM BOM WHERE ProducedProductId=?", (product_id,)).fetchall()
        conn.close()
        
        if not boms:
            return

        match = None
        if product_name:
            match = self._dsld.find_label(brand, product_name)
        if not match:
            # Fingerprint fallback using first BOM
            bom_id = boms[0][0]
            conn2 = sqlite3.connect(self.db_path)
            match = self._fingerprint_match(conn2, company_name, bom_id)
            conn2.close()

        if not match:
            self._log_skip(product_id, f"No DSLD match for '{brand} {product_name}'")
            return

        ingredients = self._dsld.extract_label_ingredients(match["dsld_id"])
        if not ingredients:
            self._log_skip(product_id, f"Empty ingredients for DSLD label {match['dsld_id']}")
            return

        self._store_amounts(product_id, boms, ingredients, match)

    def _store_amounts(self, product_id, boms, ingredients, match):
        conn = sqlite3.connect(self.db_path)
        stored = 0
        for bom_row in boms:
            bom_id = bom_row[0]
            components = conn.execute(
                "SELECT ConsumedProductId FROM BOM_Component WHERE BOMId=?", (bom_id,)
            ).fetchall()
            for comp_row in components:
                consumed_id = comp_row[0]
                canonical = conn.execute("""
                    SELECT ic.Id, ic.Name FROM Ingredient_Canonical ic
                    JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
                    WHERE stc.ProductId = ?
                """, (consumed_id,)).fetchone()
                if not canonical:
                    continue
                canonical_id, canonical_name = canonical

                # Use FuzzyMatcher to find best ingredient match by name
                best_amt = self._match_ingredient_to_amounts(canonical_name, ingredients)
                if not best_amt:
                    continue

                conn.execute("""
                    INSERT OR REPLACE INTO BOM_Component_Quantity
                    (BOMId, ConsumedProductId, Amount, Unit, PerServing, ServingUnit,
                     DSLD_Label_Id, Off_Market, Source, Confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bom_id, consumed_id,
                    best_amt.get("amount"), best_amt.get("unit"),
                    best_amt.get("per_serving"), best_amt.get("serving_unit"),
                    str(match["dsld_id"]),
                    1 if match.get("off_market") == "1" else 0,
                    "dsld", best_amt.get("confidence", match["confidence"]),
                ))
                stored += 1

        conn.commit()
        conn.close()
        logger.info(f"product_id={product_id} → stored {stored} quantities from DSLD label {match['dsld_id']}")

    def _match_ingredient_to_amounts(self, canonical_name: str, amounts: list[dict]) -> dict | None:
        """Use rapidfuzz to find best-matching ingredient in DSLD amounts list."""
        from rapidfuzz import fuzz, process as fuzz_process
        dsld_names = [a["ingredient_name"] for a in amounts]
        best = fuzz_process.extractOne(canonical_name, dsld_names, scorer=fuzz.token_set_ratio)
        if best and best[1] >= 70:  # lower threshold: DSLD uses "Vitamin D3", canonical might be "Cholecalciferol"
            idx = dsld_names.index(best[0])
            return amounts[idx]
        return None
```

**GOTCHA:** Thread safety — each call to `_store_amounts` opens its own `sqlite3.connect()`. SQLite supports multiple readers; writes are serialized by SQLite's WAL mode. Enable WAL in `__init__`:
```python
conn = sqlite3.connect(self.db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.close()
```

**VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 enrichment/pipeline.py --phase 2 2>&1 | tail -30
```

Then check results:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
total = conn.execute('SELECT COUNT(*) FROM BOM_Component_Quantity').fetchone()[0]
by_unit = conn.execute('SELECT Unit, COUNT(*) FROM BOM_Component_Quantity GROUP BY Unit ORDER BY 2 DESC').fetchall()
print(f'Total quantities: {total}')
print('By unit:', by_unit)
"
```

---

#### Task B4 — FIX `fuzzy_matcher.py`: also match against `ExtractedName`

**File:** `enrichment/normalizers/fuzzy_matcher.py`

After the naming fix, `Ingredient_Canonical.Name` holds preferred names. But for Phase 2 ingredient matching against DSLD ingredient names, we also want to match against `SKU_To_Canonical.ExtractedName` (the original slug-parsed name like "magnesium stearate").

Add overloaded search in `_load_canonicals()`:

```python
def _load_canonicals(self) -> list[tuple[int, str]]:
    if self._cache is not None:
        return self._cache
    try:
        conn = sqlite3.connect(self.db_path)
        # Include ExtractedName variants for broader matching surface
        rows = conn.execute("""
            SELECT DISTINCT ic.Id, ic.Name
            FROM Ingredient_Canonical ic
            UNION
            SELECT ic.Id, stc.ExtractedName
            FROM Ingredient_Canonical ic
            JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
            WHERE stc.ExtractedName IS NOT NULL
        """).fetchall()
        conn.close()
        self._cache = rows
        return rows
    except Exception as e:
        logger.error(f"Failed to load canonicals: {e}")
        return []
```

**VALIDATE:**
```bash
python3 -c "
from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher
fm = FuzzyMatcher('db_enriched.sqlite')
for name in ['Vitamin D3', 'Cholecalciferol', 'magnesium stearate', 'Ascorbic Acid']:
    r = fm.match(name)
    print(f'{name} → {r}')
"
```

---

## STEP-BY-STEP TASKS (ordered by dependency)

### TASK 1 — UPDATE `enrichment/sources/pubchem.py`
- **ADD** `_pick_preferred_name()` helper function at module level (after `_extract_cas`)
- **UPDATE** `lookup()`: after `synonyms = self._get_synonyms(cid)`, compute `preferred = _pick_preferred_name(synonyms, fallback=name)`
- **UPDATE** result dict: `"name": preferred`, add `"iupac_name": props.get("IUPACName")`
- **VALIDATE:** `python3 -c "from enrichment.sources.pubchem import PubChemClient; r = PubChemClient(':memory:').lookup('magnesium stearate'); print(r['name'], r.get('iupac_name'))"`

### TASK 2 — UPDATE `enrichment/normalizers/ingredient_normalizer.py`
- **VERIFY** `_get_or_create_canonical()` already passes `result.get("iupac_name")` to the `IUPAC_Name` column (line 133). If it still uses `result.get("name")` there, that's a bug — it should be `result.get("iupac_name")`.
- **NO OTHER CHANGE** needed here — `Name` column gets `result.get("name")` which is now the preferred name.
- **VALIDATE:** `python3 -c "from enrichment.normalizers.ingredient_normalizer import IngredientNormalizer"` — no import errors.

### TASK 3 — RUN in-place name update (backfill existing Ingredient_Canonical rows)
- **RUN** the UPDATE script from Task A3 (in-place update, not re-bootstrap)
- **VALIDATE:** `python3 enrichment/pipeline.py --phase 1 2>&1 | grep -A 25 "Top Consol"` — confirm "Magnesium Stearate" not "magnesium bis(octadecanoate)"

### TASK 4 — UPDATE `schema/enriched_schema.sql`
- **ADD** `DSLD_Label_Id TEXT` and `Off_Market INTEGER` columns to `BOM_Component_Quantity` DDL
- **VALIDATE:** DDL is syntactically correct (no runtime test needed — it's DDL only)

### TASK 5 — UPDATE `enrichment/sources/dsld.py`
- **ADD** `find_label(brand, product_name, min_confidence=0.65)` method
- **ADD** `extract_label_ingredients(label_id)` method with `_parse_rows()` inner function for nestedRows
- **DEPRECATE** `extract_ingredient_amounts()` — redirect to new method
- **KEEP** all existing Phase 1 methods (`search_ingredient`, `search_product`, `get_label`) unchanged
- **VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 -c "
from enrichment.sources.dsld import DSLDClient
d = DSLDClient('db_enriched.sqlite')
m = d.find_label('NOW Foods', 'Vitamin D3')
print('Match:', m)
if m: print('Ingredients:', d.extract_label_ingredients(m['dsld_id'])[:3])
"
```

### TASK 6 — UPDATE `enrichment/normalizers/fuzzy_matcher.py`
- **UPDATE** `_load_canonicals()` to UNION with `SKU_To_Canonical.ExtractedName`
- **INVALIDATE** in-memory cache after schema migration: `self._cache = None`
- **VALIDATE:**
```bash
python3 -c "
from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher
fm = FuzzyMatcher('db_enriched.sqlite')
r = fm.match('Vitamin D3')
print(r)
"
```

### TASK 7 — REWRITE `enrichment/enrichers/quantity_enricher.py`
- **ADD** imports: `from concurrent.futures import ThreadPoolExecutor`, `from enrichment.sources.dsld import DSLDClient`, `from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher`, `import re`
- **ADD** `_apply_schema_migrations()` method (ALTER TABLE for new columns)
- **ADD** `_parse_fg_sku()` method
- **ADD** `_fingerprint_match()` method
- **REWRITE** `run()` with `ThreadPoolExecutor(max_workers=6)`
- **REWRITE** `_enrich_product()` with two-path strategy
- **REWRITE** `_store_amounts()` using `_match_ingredient_to_amounts()`
- **ADD** `_match_ingredient_to_amounts()` method
- **ADD** `_report()` method: logs coverage stats
- **VALIDATE:**
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 enrichment/pipeline.py --phase 2 2>&1 | tail -20
python3 -c "import sqlite3; conn=sqlite3.connect('db_enriched.sqlite'); print('Quantities:', conn.execute('SELECT COUNT(*) FROM BOM_Component_Quantity').fetchone()[0])"
```

---

## TESTING STRATEGY

### Unit Tests (manual validation scripts — no pytest framework required)

**Test A: Preferred name extraction**
```bash
python3 -c "
from enrichment.sources.pubchem import PubChemClient, _pick_preferred_name
tests = [
    (['Magnesium Stearate', '557-04-0', 'magnesium bis(octadecanoate)'], 'Magnesium Stearate'),
    (['Ascorbic acid', '50-81-7', '(2R)-2-[(1S)-1,2...'], 'Ascorbic acid'),
    (['7440-66-6', 'Zinc', 'zinc'], 'Zinc'),
]
for synonyms, expected in tests:
    result = _pick_preferred_name(synonyms, 'fallback')
    status = '✓' if result == expected else f'✗ got {result}'
    print(f'{expected}: {status}')
"
```

**Test B: DSLD label extraction**
```bash
python3 -c "
from enrichment.sources.dsld import DSLDClient
d = DSLDClient('db_enriched.sqlite')
# Test extract_label_ingredients with a known label ID
ings = d.extract_label_ingredients('20581')  # Known Vitamin D label
print(f'{len(ings)} ingredients extracted')
assert all('amount' in i and 'unit' in i for i in ings), 'Missing fields'
print('All fields present ✓')
"
```

**Test C: SKU parsing**
```bash
python3 -c "
# Test _parse_fg_sku logic
test_cases = [
    ('FG-iherb-10421', 'NOW Foods', ('NOW Foods', None)),
    ('FG-thrive-market-thorne-vitamin-d-5-000', 'Thorne', ('Thorne', 'thorne vitamin d 5 000')),
    ('FG-thrive-market-671635734464', 'Wellmade', ('Wellmade', None)),
]
print('Add _parse_fg_sku tests after implementation')
"
```

### Edge Cases

- iHerb numeric-only SKUs (e.g., `FG-iherb-10421`) → fingerprint path with ≥ 3 ingredient overlap requirement
- Thrive Market barcode SKUs (`671635734464`) → fingerprint path
- Products with 0 BOMs → skip cleanly with log
- DSLD label with `nestedRows` (proprietary blend) → recurse into nestedRows
- `offMarket: "1"` labels → accepted for Phase 2, stored with `Off_Market=1`
- `servingSizeOrder: 2` quantities → skip, use only primary serving size
- IU vs mcg for same ingredient → store as-is, don't convert (Phase 4 handles normalization)

---

## VALIDATION COMMANDS

### Level 1: Import sanity
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
from enrichment.sources.pubchem import PubChemClient
from enrichment.sources.dsld import DSLDClient
from enrichment.enrichers.quantity_enricher import QuantityEnricher
from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher
print('All imports OK')
"
```

### Level 2: Naming fix validation
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
# Should NOT see IUPAC-style names in Name column
iupac_names = conn.execute(
    \"SELECT Name FROM Ingredient_Canonical WHERE Name LIKE '%(%)%' OR Name LIKE '%yl%' LIMIT 10\"
).fetchall()
print('Remaining IUPAC-style names:', iupac_names)
"
```

### Level 3: Phase 2 coverage
```bash
cd "/home/developer/Projects/Spherecast Agnes" && python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
total_bom = conn.execute('SELECT COUNT(*) FROM BOM_Component').fetchone()[0]
enriched = conn.execute('SELECT COUNT(*) FROM BOM_Component_Quantity').fetchone()[0]
fg_total = conn.execute(\"SELECT COUNT(*) FROM Product WHERE Type='finished-good'\").fetchone()[0]
fg_enriched = conn.execute('SELECT COUNT(DISTINCT b.ProducedProductId) FROM BOM b JOIN BOM_Component_Quantity bcq ON bcq.BOMId = b.Id').fetchone()[0]
print(f'BOM components enriched: {enriched}/{total_bom} ({enriched/total_bom*100:.1f}%)')
print(f'Finished goods covered: {fg_enriched}/{fg_total} ({fg_enriched/fg_total*100:.1f}%)')
print(f'Target: ≥70% components, ≥55% finished goods')
"
```

### Level 4: Full pipeline re-run
```bash
cd "/home/developer/Projects/Spherecast Agnes" && set -a && source .env && set +a && python3 enrichment/pipeline.py --phase 2 2>&1
```

---

## ACCEPTANCE CRITERIA

- [ ] `Ingredient_Canonical.Name` shows human-readable names ("Magnesium Stearate", "Vitamin C", "Cholecalciferol") — no IUPAC strings in top-20 cluster report
- [ ] `BOM_Component_Quantity` has ≥ 400 rows after Phase 2 (target: ~55% of 1,528 BOM_Component rows via DSLD)
- [ ] ≥ 55 of 149 finished goods have at least one enriched quantity row
- [ ] All Phase 2 rows have non-null `Amount`, `Unit`, `DSLD_Label_Id`
- [ ] `find_label("NOW Foods", "Vitamin D3")` returns a match with `confidence ≥ 0.65`
- [ ] `extract_label_ingredients(label_id)` returns items with `amount` and `unit` fields populated
- [ ] No import errors or regressions in Phase 1 pipeline
- [ ] Phase 2 completes in < 15 minutes (6 concurrent workers × 149 finished goods × ~5s avg)

---

## NOTES

**Why no web scraper for Phase 2:** DSLD covers ~55–65% of finished goods (established brands: NOW, Thorne, Jarrow, Solgar, Natural Factors, Optimum Nutrition, etc.). The fingerprint fallback adds a few more. DTC brands (Liquid I.V., Cure Hydration, SALTWTR) are not in DSLD and will require browser scraping — but that's post-MVP. For the hackathon goal of ≥ 10 consolidation proposals, DSLD coverage is sufficient.

**Why `max_workers=6` not 8 for Phase 2:** Phase 2 makes heavier DSLD calls (search + label fetch = 2 cached API calls per finished good). 6 workers avoids hammering DSLD while still giving ~5× speedup over sequential.

**Schema migration approach:** `ALTER TABLE ... ADD COLUMN` is non-destructive and idempotent (wrapped in try/except). No re-bootstrap needed.

**Ingredient matching threshold 70 vs 85:** Phase 2 ingredient matching uses `token_set_ratio ≥ 70` (lower than Phase 1's 85) because DSLD uses "Vitamin D3" while our canonical might be "Cholecalciferol" — they're the same ingredient but textually different. The lower threshold captures these chemical-name vs common-name pairs.

**Confidence Score: 8/10** — All patterns are established in the codebase or directly in reference docs. Main risk is DSLD label schema variations (some labels may have unusual structures), but the `_parse_rows` recursion handles nesting.
