# USDA FoodData Central (FDC) Integration Reference

USDA FoodData Central — a free, open government database of food and nutrient composition data. Most useful for food-grade macroingredients (proteins, carbohydrates, fibers). Supplement-specific identity (UNII codes, CAS numbers) is absent; use as a fallback for food-grade ingredients when PubChem and DSLD miss.

---

## What FDC Contains

FDC unifies four distinct datasets under one API. Each has different quality characteristics for supplement ingredients:

| DataType | Records (approx) | Coverage for supplements | Notes |
|---|---|---|---|
| **Foundation** | ~1,200 | Very low | Whole foods only, deeply characterized nutritionally |
| **SR Legacy** | ~7,800 | Low–medium | USDA Standard Reference; whole foods and some raw commodities |
| **Branded** | ~400,000+ | Medium | FDA-registered food products with nutrition labels; includes bulk supplement ingredient powders |
| **Survey (FNDDS)** | ~4,000 | Negligible | Foods from dietary surveys; not relevant for ingredient lookup |

**Key insight from live testing:** For supplement raw material ingredients, `Branded` is the most useful dataType when the ingredient is sold as a stand-alone food/supplement product (e.g., maltodextrin powder, collagen peptides, inulin powder). `SR Legacy` covers food-matrix contexts (e.g., ascorbic acid *as added to applesauce*) but rarely returns pure ingredient records as the top hit.

---

## Auth & Base URL

```
Base URL:  https://api.nal.usda.gov/fdc/v1
Auth:      ?api_key=<FDC_API_KEY>   (query parameter — no header required)
```

API key is free from https://fdc.nal.usda.gov/api-key-signup.html. Store as `FDC_API_KEY` in `.env`.

**Rate limits (free tier):**
- 1,000 requests per hour per API key
- 3,600 requests per day per API key (USDA documentation; actual limits may be higher in practice)
- No enforced per-second limit observed, but add a 0.5–1 second delay between calls to be safe

> **No auth header needed.** Unlike DSLD, FDC uses a query param (`?api_key=`), not a header. Requests without an API key are allowed but rate-limited more aggressively.

---

## Key Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/foods/search` | GET | Full-text search across all datasets |
| `/food/{fdcId}` | GET | Full detail for one food item |
| `/foods` | POST | Batch fetch up to 20 food items by fdcId |
| `/foods/list` | GET | Paginated full-dataset listing |

---

## Verified Response Schemas (live-tested 2026-04-18)

### Search — `GET /foods/search`

```
GET /fdc/v1/foods/search
  ?query=collagen+peptides
  &api_key=<key>
  &dataType=Foundation,SR%20Legacy,Branded
  &pageSize=3
```

**Response envelope:**

```json
{
  "totalHits": 1848,
  "currentPage": 1,
  "totalPages": 616,
  "foods": [ ... ]
}
```

**Search hit fields (Branded example — collagen peptides, fdcId 2587229):**

```json
{
  "fdcId": 2587229,
  "description": "COLLAGEN PEPTIDES",
  "dataType": "Branded",
  "brandOwner": "T.G. Foods, Inc.",
  "brandName": "DIVIDED SUNSET",
  "gtinUpc": "850005606000",
  "ingredients": "INGREDIENTS: COLLAGEN",
  "servingSize": 14.0,
  "servingSizeUnit": "GRM",
  "packageWeight": "8 oz/226 g",
  "marketCountry": "United States",
  "score": 1180.4,
  "publishedDate": "2023-06-29",
  "foodNutrients": [
    { "nutrientId": 1003, "nutrientName": "Protein", "unitName": "G", "value": 85.71 }
  ]
}
```

**Search hit fields (SR Legacy example — whey protein, fdcId 173180):**

```json
{
  "fdcId": 173180,
  "description": "Beverages, Protein powder whey based",
  "dataType": "SR Legacy",
  "ndbNumber": "14219",
  "score": 927.8,
  "foodNutrients": [
    { "nutrientId": 1003, "nutrientName": "Protein", "unitName": "G", "value": 78.13 },
    { "nutrientId": 1008, "nutrientName": "Energy", "unitName": "KCAL", "value": 352.0 }
  ]
}
```

---

### Food Detail — `GET /food/{fdcId}`

Returns all fields. Key differences by dataType:

**Branded food detail — top-level keys:**

```
fdcId, description, dataType, publicationDate, modifiedDate, availableDate,
discontinuedDate, brandOwner, brandName, brandedFoodCategory, gtinUpc,
ingredients, servingSize, servingSizeUnit, packageWeight, marketCountry,
foodNutrients, labelNutrients, foodAttributes, foodComponents, foodPortions,
foodUpdateLog, dataSource, foodClass, shortDescription
```

**`labelNutrients` (Branded only) — flat label-as-reported values:**

```json
{
  "fat":           { "value": 0.0 },
  "saturatedFat":  { "value": 0.0 },
  "transFat":      { "value": 0.0 },
  "cholesterol":   { "value": 0.0 },
  "sodium":        { "value": 89.0 },
  "carbohydrates": { "value": 96.0 },
  "fiber":         { "value": 0.0 },
  "sugars":        { "value": 3.6 },
  "protein":       { "value": 0.0 },
  "calories":      { "value": 375.0 }
}
```

**`foodNutrients` (Branded — minimal, label-derived):**

```json
[
  { "nutrient": { "id": 1008, "name": "Energy", "unitName": "kcal" }, "amount": 375.0 },
  { "nutrient": { "id": 1003, "name": "Protein", "unitName": "g" }, "amount": 0.0 },
  { "nutrient": { "id": 1093, "name": "Sodium, Na", "unitName": "mg" }, "amount": 89.0 },
  { "nutrient": { "id": 1004, "name": "Total lipid (fat)", "unitName": "g" }, "amount": 0.0 },
  { "nutrient": { "id": 1005, "name": "Carbohydrate, by difference", "unitName": "g" }, "amount": 96.0 }
]
```

Branded records typically have 5–15 nutrients (label-only). SR Legacy records have 40–80+ nutrients (lab-analyzed). Foundation records have the most complete analytical data including fatty acid profiles and phytochemicals.

**`foodNutrients` (SR Legacy — extensive, lab-analyzed, whey protein 173180 example):**

```json
[
  { "nutrient": { "id": 1003, "name": "Protein", "unitName": "g" }, "amount": 78.13 },
  { "nutrient": { "id": 1004, "name": "Total lipid (fat)", "unitName": "g" }, "amount": 1.56 },
  { "nutrient": { "id": 1005, "name": "Carbohydrate, by difference", "unitName": "g" }, "amount": 6.25 },
  { "nutrient": { "id": 1087, "name": "Calcium, Ca", "unitName": "mg" }, "amount": 469.0 },
  { "nutrient": { "id": 1090, "name": "Magnesium, Mg", "unitName": "mg" }, "amount": 195.0 },
  { "nutrient": { "id": 1095, "name": "Zinc, Zn", "unitName": "mg" }, "amount": 6.18 },
  { "nutrient": { "id": 1165, "name": "Thiamin", "unitName": "mg" }, "amount": 0.609 },
  { "nutrient": { "id": 1166, "name": "Riboflavin", "unitName": "mg" }, "amount": 2.017 },
  { "nutrient": { "id": 1178, "name": "Vitamin B-12", "unitName": "µg" }, "amount": 2.45 }
]
```

**Common nutrient IDs for supplement ingredients:**

| ID | Nutrient | Unit |
|---|---|---|
| 1003 | Protein | g |
| 1004 | Total lipid (fat) | g |
| 1005 | Carbohydrate, by difference | g |
| 1008 | Energy | kcal |
| 1079 | Fiber, total dietary | g |
| 1087 | Calcium, Ca | mg |
| 1089 | Iron, Fe | mg |
| 1090 | Magnesium, Mg | mg |
| 1092 | Potassium, K | mg |
| 1093 | Sodium, Na | mg |
| 1095 | Zinc, Zn | mg |
| 1103 | Selenium, Se | µg |
| 1106 | Vitamin A, RAE | µg |
| 1109 | Vitamin E (alpha-tocopherol) | mg |
| 1114 | Vitamin D (D2 + D3) | µg |
| 1162 | Vitamin C, total ascorbic acid | mg |
| 1165 | Thiamin | mg |
| 1166 | Riboflavin | mg |
| 1167 | Niacin | mg |
| 1175 | Vitamin B-6 | mg |
| 1177 | Folate, total | µg |
| 1178 | Vitamin B-12 | µg |

---

### Batch Fetch — `POST /foods`

Fetch up to 20 records in one call. More efficient than individual `/food/{id}` calls when you have a list of known fdcIds.

```python
payload = {
    "fdcIds": [2534810, 2587229, 173180],
    "format": "abridged"   # "abridged" or "full"
}
r = requests.post(f"{BASE}/foods", params={"api_key": API_KEY}, json=payload)
# Returns list of food objects, same schema as /food/{fdcId}
```

---

## Coverage by Ingredient Type

Results from live testing against 24 representative supplement ingredient slugs:

| Ingredient type | Search hits (typical) | Useful results? | Notes |
|---|---|---|---|
| **Macronutrient proteins** (whey, collagen, pea protein) | 1,800–126,000 | **Yes** — SR Legacy and Branded both return relevant records | Whey protein has SR Legacy record (173180) with full nutrient profile; collagen peptides have Branded records |
| **Food-grade carbs** (maltodextrin, inulin, sucrose) | 46,000–128,000 | **Yes** for Branded | Swanson inulin (2372957) and CYTOSPORT maltodextrin (2534810) are clean stand-alone ingredient records |
| **B-vitamins as food context** (riboflavin, folic acid, thiamine) | 68,000–207,000 | **Partially** | Hits are foods fortified with the vitamin, not the pure ingredient. High hit count is misleading; top results are irrelevant foods |
| **Isolated supplement vitamins** (cholecalciferol, cyanocobalamin) | 0 (Foundation/SR Legacy), ~59,000 (Branded) | **Poor** | Branded hits are fortified food products, not pure ingredient records. No direct match for pure supplement chemical |
| **Minerals as food context** (calcium carbonate, zinc, magnesium citrate) | 8,000–131,000 | **Poor–medium** | Top results are foods containing the mineral, not the pure compound. Exception: some Branded records for supplement products |
| **Botanicals** (green tea extract, rhodiola, hesperidin) | 23–114,000 | **Poor** | High hit counts are false positives (name overlap with unrelated foods). Coenzyme Q10 and hesperidin had small hit sets with more targeted results, but still branded food products |
| **Amino acids** (leucine, taurine) | 221,000–268,000 | **Poor** | Hits are foods containing the amino acid, not pure amino acid. Top results are protein powder products |
| **Excipients** (magnesium stearate, silicon dioxide, croscarmellose sodium) | 123–27,000 | **Poor** | No direct records for pharmaceutical/food excipients. Results are unrelated foods that happen to contain these ingredients |

**Summary hit-rate table (live-tested, 2026-04-18):**

| Slug | Total hits | Top result type | Top result relevant? |
|---|---|---|---|
| collagen-peptides | 1,848 | Branded | Yes |
| coenzyme-q10 | 111 | Branded | Yes |
| hesperidin-complex | 653 | SR Legacy | Partial |
| inulin | 115,447 | Branded | Yes (Swanson inulin powder top 2) |
| maltodextrin | 128,617 | Branded | Yes (pure maltodextrin powder top 1) |
| whey-protein-concentrate | 125,842 | SR Legacy | Yes |
| ascorbic-acid | 207,391 | SR Legacy | No (applesauce top 1) |
| vitamin-d3 | 58,612 | Branded | No (vitamin D3 milk top 1) |
| riboflavin | 107,454 | SR Legacy | No (energy drink top 1) |
| zinc | 10,026 | SR Legacy | No |
| magnesium-stearate | 8,580 | SR Legacy | No |
| silicon-dioxide | 27,129 | Branded | No (smoked bacon top 1) |
| green-tea-extract | 114,433 | SR Legacy | No (vanilla extract top 1) |
| rhodiola-rosea | 91,007 | SR Legacy | No (vanilla extract top 1) |
| l-leucine | 221,192 | SR Legacy | No |
| microcrystalline-cellulose | 122,280 | SR Legacy | No |
| croscarmellose-sodium | 123,057 | SR Legacy | No |

**Practical coverage rate for supplement raw materials: ~15–25%.** FDC is useful primarily for macronutrient ingredients (proteins, fibers, food-grade carbohydrates). It is not useful for vitamin/mineral pure compounds, amino acids, excipients, or botanical extracts.

---

## Limitations

**What FDC does not provide:**
- UNII codes, CAS numbers, or InChI strings — no chemical identity data
- Supplement-specific ingredient forms (e.g., "magnesium glycinate" vs. "magnesium oxide")
- Supplier data, pricing, MOQ, or lead times
- Certification or compliance data (organic, NSF, Kosher)
- Ingredient amounts per serving for finished supplement products — use DSLD for that

**Search quality issues:**
- The `query` parameter is full-text across description, ingredients list, and brand name. A search for "riboflavin" returns 107,000+ hits because it matches any food that lists riboflavin in its ingredient declaration. Relevance ranking (`score` field) is not calibrated for ingredient-purity lookups.
- High `totalHits` does not mean relevant hits. Filter by checking whether the `description` or `ingredients` field matches the pure ingredient name.
- DataType filtering (`dataType=Foundation,SR Legacy`) can reduce noise but dramatically reduces hit counts — many useful Branded records are excluded.

**Branded data quality:**
- Branded records are submitted by food manufacturers and are not systematically validated.
- `discontinuedDate` is often empty even for discontinued products; `modifiedDate` and `availableDate` are available but don't indicate current market availability.
- `ingredients` field is a raw ingredients list string (e.g., `"MALTODEXTRIN"`) — useful for confirming purity but not structured.
- Branded nutrient counts are sparse (5–15 nutrients, label-declared only). Do not use for comprehensive nutrient profiling.

**No substitute for chemical databases:**
For chemical identity of supplement ingredients (CAS, IUPAC name, synonyms, InChI), use PubChem. For supplement-specific UNII codes and ingredient forms, use DSLD. FDC does not overlap with either.

---

## Python Client

```python
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FDC_BASE = "https://api.nal.usda.gov/fdc/v1"

def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

_session = _make_session()
_FDC_API_KEY = os.environ.get("FDC_API_KEY", "")


def fdc_search(
    query: str,
    data_types: list[str] | None = None,
    page_size: int = 5,
) -> list[dict]:
    """
    Search FDC by ingredient name. Returns list of food objects.

    data_types: subset of ["Foundation", "SR Legacy", "Branded", "Survey (FNDDS)"]
    Default: all four types (broadest search).
    For supplement ingredient lookup, try ["Branded"] first for pure ingredient powders,
    then ["Foundation", "SR Legacy"] for nutrient profiling of food-grade ingredients.
    """
    params = {
        "query": query,
        "api_key": _FDC_API_KEY,
        "pageSize": page_size,
    }
    if data_types:
        params["dataType"] = ",".join(data_types)

    r = _session.get(f"{FDC_BASE}/foods/search", params=params, timeout=15)
    r.raise_for_status()
    time.sleep(0.5)  # polite delay
    return r.json().get("foods", [])


def fdc_food(fdc_id: int) -> dict:
    """Fetch full detail for a single food item."""
    r = _session.get(
        f"{FDC_BASE}/food/{fdc_id}",
        params={"api_key": _FDC_API_KEY},
        timeout=15,
    )
    r.raise_for_status()
    time.sleep(0.5)
    return r.json()


def fdc_foods_batch(fdc_ids: list[int], abridged: bool = True) -> list[dict]:
    """
    Fetch up to 20 food items by fdcId in one call.
    Use abridged=True for id/description/nutrients only.
    """
    r = _session.post(
        f"{FDC_BASE}/foods",
        params={"api_key": _FDC_API_KEY},
        json={"fdcIds": fdc_ids, "format": "abridged" if abridged else "full"},
        timeout=15,
    )
    r.raise_for_status()
    time.sleep(0.5)
    return r.json()


def fdc_find_ingredient(ingredient_name: str) -> dict | None:
    """
    Attempt to find a pure ingredient record in FDC.
    Strategy: try Branded first (most likely to have pure ingredient powders),
    then fall back to SR Legacy for food-matrix context.

    Returns best match dict with fdcId, description, dataType, and nutrient summary,
    or None if no relevant hit found.
    """
    # Try Branded for pure ingredient powders
    hits = fdc_search(ingredient_name, data_types=["Branded"], page_size=5)
    for hit in hits:
        desc = hit.get("description", "").lower()
        ingredients_field = hit.get("ingredients", "").lower()
        query_words = ingredient_name.lower().split()
        # Simple relevance check: ingredient name words appear in description
        if sum(1 for w in query_words if w in desc) >= max(1, len(query_words) // 2):
            return {
                "fdc_id": hit["fdcId"],
                "description": hit["description"],
                "data_type": hit["dataType"],
                "brand_owner": hit.get("brandOwner"),
                "gtin_upc": hit.get("gtinUpc"),
                "ingredients": hit.get("ingredients"),
                "serving_size": hit.get("servingSize"),
                "serving_size_unit": hit.get("servingSizeUnit"),
                "source": "fdc",
                "confidence": 0.65,  # FDC Branded is a proxy; not a definitive identity match
            }

    # Fall back to SR Legacy for food-grade ingredient context
    hits = fdc_search(ingredient_name, data_types=["Foundation", "SR Legacy"], page_size=5)
    for hit in hits:
        desc = hit.get("description", "").lower()
        query_words = ingredient_name.lower().split()
        if sum(1 for w in query_words if w in desc) >= len(query_words):
            return {
                "fdc_id": hit["fdcId"],
                "description": hit["description"],
                "data_type": hit["dataType"],
                "source": "fdc",
                "confidence": 0.55,
            }

    return None


def fdc_get_nutrients(fdc_id: int) -> list[dict]:
    """
    Fetch nutrient profile for a food item. Returns list of
    {nutrient_id, name, unit, amount} dicts.
    """
    food = fdc_food(fdc_id)
    result = []
    for fn in food.get("foodNutrients", []):
        nut = fn.get("nutrient", {})
        amt = fn.get("amount")
        if amt is not None:
            result.append({
                "nutrient_id": nut.get("id"),
                "name": nut.get("name"),
                "unit": nut.get("unitName"),
                "amount": amt,
            })
    return result
```

---

## Caching

FDC responses are stable (USDA updates datasets quarterly, not daily). Cache aggressively — a 30-day TTL is appropriate for most use cases.

```python
# Suggested SQLite cache table:
# CREATE TABLE IF NOT EXISTS FDC_Cache (
#     cache_key  TEXT PRIMARY KEY,   -- "search:{query}:{dataType}" or "food:{fdcId}"
#     response   TEXT NOT NULL,      -- JSON-encoded response
#     fetched_at TEXT NOT NULL       -- ISO 8601 UTC timestamp
# );

import json
from datetime import datetime, timezone

def cached_fdc_search(query: str, data_types: list[str], db_conn) -> list[dict]:
    key = f"search:{query}:{','.join(sorted(data_types or []))}"
    row = db_conn.execute(
        "SELECT response FROM FDC_Cache WHERE cache_key = ?", (key,)
    ).fetchone()
    if row:
        return json.loads(row[0])

    data = fdc_search(query, data_types=data_types)
    db_conn.execute(
        "INSERT OR REPLACE INTO FDC_Cache VALUES (?, ?, ?)",
        (key, json.dumps(data), datetime.now(timezone.utc).isoformat()),
    )
    db_conn.commit()
    return data


def cached_fdc_food(fdc_id: int, db_conn) -> dict:
    key = f"food:{fdc_id}"
    row = db_conn.execute(
        "SELECT response FROM FDC_Cache WHERE cache_key = ?", (key,)
    ).fetchone()
    if row:
        return json.loads(row[0])

    data = fdc_food(fdc_id)
    db_conn.execute(
        "INSERT OR REPLACE INTO FDC_Cache VALUES (?, ?, ?)",
        (key, json.dumps(data), datetime.now(timezone.utc).isoformat()),
    )
    db_conn.commit()
    return data
```

---

## Integration Notes

FDC is best used as a **late fallback** for food-grade ingredients when chemical databases (PubChem) and supplement-specific databases (DSLD) produce no match. It is not a primary source for supplement ingredient identity.

**Where FDC adds value:**
- **Macronutrient profiling** — whey protein, collagen, pea protein, casein. SR Legacy records have full amino acid, vitamin, and mineral profiles. This is useful for validating ingredient claims.
- **Food-grade carbohydrate ingredients** — maltodextrin, inulin, dextrose, sucrose, tapioca starch. Branded records for bulk ingredient suppliers (CYTOSPORT, Swanson Health Products) provide serving size, GTIN/UPC, and basic nutrient data.
- **UPC cross-reference** — Branded records have `gtinUpc`. If you have a product barcode, FDC can confirm ingredient identity for food-grade ingredients.
- **Confirming ingredient purity via the `ingredients` field** — e.g., `"INGREDIENTS: COLLAGEN"` or `"MALTODEXTRIN"` confirms it is a single-ingredient product.

**Where FDC does not add value:**
- Vitamin/mineral pure compounds (cholecalciferol, cyanocobalamin, zinc oxide) — FDC has no pure ingredient records; only fortified food products
- Botanical extracts (green tea extract, rhodiola rosea, hesperidin) — FDC results are false positives; unrelated foods dominate
- Amino acids (leucine, taurine, glycine) — FDC results are foods containing the amino acid, not the pure compound
- Pharmaceutical excipients (magnesium stearate, silicon dioxide, croscarmellose sodium) — not represented

**Confidence ceiling:** Because FDC Branded records are self-reported by food manufacturers and not chemically verified, confidence for ingredient identity should not exceed 0.70 even for a strong name match. Use the `ingredients` field text to confirm purity (single-ingredient record) before assigning confidence above 0.65.

**Suggested source priority for food-grade ingredients:**
1. PubChem — chemical identity (CAS, IUPAC, InChI)
2. DSLD — supplement-specific identity (UNII, forms, amounts)
3. **FDC** — food-grade macroingredient nutrient profiling and UPC cross-reference
4. Browser scraping — pricing, MOQ, availability

---

## Gotchas

- **High `totalHits` is meaningless without relevance filtering.** A search for "riboflavin" returns 107,000+ results; most are fortified foods. Always check the `description` field of top results before using the data.
- **`dataType` filter is critical.** Without it, `Branded` dominates and low-relevance branded food products overwhelm results. Specify `dataType=Branded` when looking for pure ingredient powders; specify `Foundation,SR Legacy` for whole-food nutrient profiles.
- **`score` field is not calibrated for ingredient purity.** A food that merely lists the ingredient in its ingredient declaration can score higher than a pure ingredient powder. Do not rely on score alone.
- **Branded nutrient data is label-declared, not analytically verified.** Branded records have 5–15 nutrients; SR Legacy and Foundation have 40–80+. Use SR Legacy for nutritional claims validation.
- **`discontinuedDate`** is often empty even for old records. Do not assume an empty `discontinuedDate` means the product is current.
- **GTIN/UPC coverage is incomplete.** Many Branded records have a `gtinUpc` field, but not all barcodes are present. Do not use FDC as a barcode-to-ingredient resolver for supplement SKUs — use DSLD instead.
- **No pagination in batch `/foods` endpoint.** Maximum 20 fdcIds per POST request. Chunk larger lists accordingly.
- **Rate limits are per API key, per hour.** If running batch enrichment across hundreds of ingredients, implement a rate limiter that stays well below 1,000 requests/hour. At 1 request per 4 seconds, you can safely process ~900 ingredients per hour.
