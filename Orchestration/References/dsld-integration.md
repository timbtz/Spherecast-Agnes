# DSLD Integration Reference

NIH Dietary Supplement Label Database — 58,000+ real supplement labels with exact ingredient amounts.

---

## Why DSLD Matters for Agnes

The DB has 143 ingredient slugs shared by 2+ companies, 51 shared by 5+ companies. But slug matching alone is too fragile. Example:

```
silicon-dioxide  → 10 companies
silica           →  7 companies   ← same ingredient (SiO2), different slug
```

Without enrichment these look like two separate purchasing categories. DSLD resolves this via **UNII codes** — FDA's authoritative ingredient identifiers. Both slugs map to UNII `ETJ7Z6XBU4`, revealing 17 companies buying the same thing independently. That's a consolidation opportunity pure text matching misses entirely.

### The enrichment chain

DSLD doesn't enrich raw material SKUs directly — they have no labeled records. The path is indirect:

```
RM slug  →  ingredient name  →  DSLD search  →  UNII code  →  Ingredient_Canonical
                                     ↑
FG product  →  DSLD label  →  ingredientRows (UNII + amounts)  →  BOM_Component_Quantity
```

DSLD serves Agnes at two levels: **identity** (UNII codes linking different slugs to the same canonical) and **quantity** (serving amounts for BOM enrichment).

### Reliability by ingredient type

| Ingredient type | Reliability | Notes |
|---|---|---|
| Common vitamins (D3, C, A, E) | High | UNII consistent, well-indexed |
| Minerals (Mg, Zn, K) | High | Same |
| Excipients (MCC, Mg stearate, silica) | Medium | Often in `otheringredients` with no UNII — fall back to PubChem |
| Proteins (whey, collagen) | Medium | In DSLD but form variants make matching harder |
| Complex botanicals / blends | Low | Multi-component; won't resolve to one UNII |
| DTC brands (Liquid I.V., SALTWTR) | Not covered | Go straight to retailer scraping |

**Expected DSLD coverage for Agnes 149 finished goods: ~55–65%.** Established brands (NOW, Jarrow, Thorne, Solgar) are well-covered but often `offMarket=1`. That's fine for identity and quantities — see Off-Market section.

### What DSLD cannot do

- Supplier pricing, MOQ, lead time — that's Molport + browser scraping
- Spec equivalence — UNII confirms ingredient *class*, not grade (food vs. pharma-grade)
- Proprietary blend amounts hidden behind "Proprietary Blend" labels
- Quantities are inferred from finished-good labels, not supplier COAs — confidence ceiling ~0.90

---

## Auth & Base URL

```
Base:    https://api.ods.od.nih.gov/dsld/v9
Header:  X-Api-Key: <DSLD_API_KEY>   ← key in .env
```

> **Critical:** Use v9 + `X-Api-Key` header. v9 without key returns 0 hits. v8 works without key but has a different schema. Search param is `q=`, not `query=`.

---

## Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /search-filter?q={name}&size=N` | Search by brand or product name |
| `GET /label/{id}` | Full label: ingredient amounts, UPC, servings, contacts |

---

## Verified Response Schemas (live-tested 2026-04-18)

### Search hit `_source` fields

```json
{
  "brandName": "Jarrow Formulas",
  "fullName": "Vitamin D3 5000 IU",
  "offMarket": "1",
  "entryDate": "2014-03-12",
  "physicalState": {"langualCodeDescription": "Softgel Capsule"},
  "netContents": [{"quantity": 100, "unit": "Softgel(s)"}],
  "allIngredients": [{"name": "Vitamin D3", "category": "vitamin", "ingredientGroup": "Vitamin D"}],
  "productType": {"langualCodeDescription": "Other Combinations"},
  "claims": [{"langualCodeDescription": "Nutrient"}]
}
```

### `ingredientRows` — active ingredients (fully verified)

```json
{
  "order": 1,
  "ingredientId": 280374,
  "name": "Vitamin D3",
  "category": "vitamin",
  "ingredientGroup": "Vitamin D",
  "uniiCode": "1C6V77QF41",
  "notes": "Vitamin D3 (Alt. Name: Cholecalciferol) Note: 200 IU",
  "alternateNames": [],
  "forms": [{"name": "Cholecalciferol", "uniiCode": "1C6V77QF41"}],
  "nestedRows": [],
  "quantity": [{
    "servingSizeOrder": 1,
    "quantity": 125,
    "unit": "mcg",
    "servingSizeUnit": "Softgel(s)",
    "dailyValueTargetGroup": [{"name": "Adults 4+", "percent": 625}]
  }]
}
```

**Agnes-relevant fields:**
- `uniiCode` — FDA UNII; the canonical cross-reference key
- `forms[]` — chemical forms (e.g., Cholecalciferol); critical for Phase 1 identity
- `alternateNames[]` + `notes` — synonym sources for fuzzy matching
- `nestedRows[]` — sub-ingredients in blends; iterate recursively
- `quantity[].unit` — "mg", "mcg", "IU", "g", "%", "{Calories}"

### `otheringredients` — excipients

Same shape as `ingredientRows` but `uniiCode` is usually null. Use for cross-company excipient identification, not chemical identity.

### Other useful label fields

```
upcSku              — barcode for retailer matching
servingsPerContainer
servingSizes[].unit + minQuantity — serving size
claims[].langualCodeDescription  — certification signals (Organic, Kosher, NSF)
statements[].text                — usage/directions, often contains cert text
```

---

## Off-Market Products

**~70–80% of DSLD hits are `offMarket: "1"`** (observed across test queries). Policy:

- **Phase 1 (identity):** fully valid — UNII codes and forms don't expire
- **Phase 2 (quantities):** use freely; supplement formulations rarely change significantly; prefer `offMarket: "0"` when available
- **Phase 3 (compliance):** filter to `offMarket: "0"` — certifications may have lapsed

Always store the `offMarket` value alongside the enrichment record.

---

## Matching Strategy for Agnes Finished Goods

SKU slugs contain no product name — they come from retailer page slugs. **Brand names in our DB often differ from DSLD's `brandName`:**

| Our DB | DSLD |
|---|---|
| NOW Foods | NOW |
| Thorne | Thorne FX |
| 21st Century | 21st Century |

Use `fuzz.partial_ratio` for brand (handles prefix variants) and `fuzz.token_set_ratio` for product name (handles word-order differences).

```python
from rapidfuzz import fuzz

def score_dsld_hit(our_brand: str, our_product: str, hit_source: dict) -> float:
    brand_score = fuzz.partial_ratio(our_brand.lower(), hit_source.get("brandName", "").lower()) / 100
    name_score = fuzz.token_set_ratio(our_product.lower(), hit_source.get("fullName", "").lower()) / 100
    if brand_score < 0.60 or name_score < 0.60:
        return 0.0
    return (brand_score * 0.4) + (name_score * 0.6)
```

Confidence thresholds:
- ≥ 0.85 → accept, `source="dsld"`
- 0.65–0.84 → store with `flag="low_confidence_dsld"`
- < 0.65 → skip, fall back to retailer scraping

---

## Pipeline Integration — Phase by Phase

### Phase 1: Ingredient Identity → `SKU_To_Canonical` + `Ingredient_Canonical`

DSLD is **Tier 2** (after PubChem, before RapidFuzz). Use it when PubChem confidence < 0.85 — especially for supplement-specific names and botanical extracts that PubChem misses.

Search the ingredient name directly (not a finished-good product name):

```python
hits = dsld_search("vitamin d3 cholecalciferol", size=3)
# Extract from first hit's _source.allIngredients or from label ingredientRows
# Key output: uniiCode, forms[].name → Ingredient_Canonical
```

### Phase 2: BOM Quantity Enrichment → `BOM_Component_Quantity`

DSLD is the **primary source** — always try before browser automation. Match via finished-good brand + product name, then extract `ingredientRows`.

```python
# Target columns from ingredientRow.quantity[0]:
{
    "Amount":      qty["quantity"],
    "Unit":        qty["unit"],           # mg / mcg / IU / g
    "PerServing":  qty["servingSizeQuantity"],
    "ServingUnit": qty["servingSizeUnit"],
    "Source":      "dsld",
    "Confidence":  match_score            # from score_dsld_hit()
}
```

### Phase 3: Compliance → `Product_Compliance`

Parse `claims[].langualCodeDescription` for cert signals (Organic, Kosher, Gluten-Free, NSF Certified for Sport). For unlisted certs, pass `statements[].text` to Claude for extraction.

---

## Python Client

```python
import os, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DSLD_BASE = "https://api.ods.od.nih.gov/dsld/v9"

def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["X-Api-Key"] = os.environ["DSLD_API_KEY"]
    return s

_session = _make_session()

def dsld_search(query: str, size: int = 5) -> list[dict]:
    r = _session.get(f"{DSLD_BASE}/search-filter", params={"q": query, "size": size}, timeout=15)
    r.raise_for_status()
    return r.json().get("hits", [])

def dsld_label(label_id: int | str) -> dict:
    r = _session.get(f"{DSLD_BASE}/label/{label_id}", timeout=15)
    r.raise_for_status()
    return r.json()

def dsld_find_label(brand: str, product_name: str, min_confidence: float = 0.65) -> dict | None:
    from rapidfuzz import fuzz
    hits = dsld_search(f"{brand} {product_name}".strip(), size=5)
    best, best_score = None, 0.0
    for hit in hits:
        src = hit["_source"]
        b = fuzz.partial_ratio(brand.lower(), src.get("brandName", "").lower()) / 100
        n = fuzz.token_set_ratio(product_name.lower(), src.get("fullName", "").lower()) / 100
        if b < 0.60 or n < 0.60:
            continue
        score = (b * 0.4) + (n * 0.6)
        if score > best_score:
            best_score = score
            best = {"dsld_id": hit["_id"], "confidence": round(score, 3),
                    "off_market": src.get("offMarket"), "brand_name": src.get("brandName"),
                    "full_name": src.get("fullName")}
    return best if best and best_score >= min_confidence else None

def dsld_extract_ingredients(label_id: int | str) -> list[dict]:
    label = dsld_label(label_id)
    results = []
    for row in label.get("ingredientRows", []):
        if row["name"] in ("Calories", "Calories from Fat"):
            continue
        for qty in row.get("quantity", []):
            dv = qty.get("dailyValueTargetGroup", [])
            results.append({
                "name": row["name"], "unii": row.get("uniiCode"),
                "category": row.get("category"), "ingredient_group": row.get("ingredientGroup"),
                "forms": [f["name"] for f in row.get("forms", [])],
                "alternate_names": [n["name"] for n in row.get("alternateNames", [])],
                "amount": qty.get("quantity"), "unit": qty.get("unit"),
                "serving_size_qty": qty.get("servingSizeQuantity"),
                "serving_size_unit": qty.get("servingSizeUnit"),
                "daily_value_pct": dv[0].get("percent") if dv else None,
                "notes": row.get("notes"), "dsld_id": label_id,
                "dsld_ingredient_id": row.get("ingredientId"),
                "source": "dsld", "confidence": 0.90,
            })
    return results

def dsld_extract_excipients(label_id: int | str) -> list[str]:
    label = dsld_label(label_id)
    return [i["name"] for i in label.get("otheringredients", {}).get("ingredients", [])]
```

---

## Caching

```python
# DSLD_Cache table in db_enriched.sqlite:
# CREATE TABLE IF NOT EXISTS DSLD_Cache (
#     query TEXT PRIMARY KEY,   -- "label:{id}" or "search:{q}"
#     response TEXT NOT NULL,
#     fetched_at TEXT NOT NULL
# );

def cached_dsld_label(label_id: int, db_conn) -> dict:
    import json
    from datetime import datetime, timezone
    key = f"label:{label_id}"
    row = db_conn.execute("SELECT response FROM DSLD_Cache WHERE query=?", (key,)).fetchone()
    if row:
        return json.loads(row[0])
    data = dsld_label(label_id)
    db_conn.execute("INSERT OR REPLACE INTO DSLD_Cache VALUES (?,?,?)",
                    (key, json.dumps(data), datetime.now(timezone.utc).isoformat()))
    db_conn.commit()
    return data
```

---

## Coverage & Fallback

**~55–65% of Agnes's 149 finished goods will have a DSLD match.** Established brands (NOW, Jarrow, Thorne, Solgar, Nature Made) are well-covered; newer DTC brands (Cure Hydration, Liquid I.V., SALTWTR) are not.

For the gap, fall back in order:
1. USDA FDC — food-grade ingredients (whey, collagen, maltodextrin)
2. Retailer scraping — per `Orchestration/References/retailer-scraping.md`; `FG-iherb-*` → iHerb, `FG-thrive-market-*` → Thrive Market (barcode reverse lookup for numeric SKUs)

DSLD is always first for Phase 2 — never invoke browser automation until DSLD returns no usable match.

---

## Gotchas

- **Brand name mismatch:** "NOW Foods" → "NOW", "Thorne" → "Thorne FX". Use `partial_ratio`.
- **Unit inconsistency:** IU and mcg both appear for Vitamin D. Check `notes` for the alternate value.
- **Multiple serving sizes:** Use `servingSizeOrder: 1` as primary; log others.
- **Nested blends:** `nestedRows` holds sub-ingredients — iterate recursively for proprietary blends.
- **UNII null on excipients:** Fall back to PubChem for chemical identity of excipients.
- **`total` count unreliable:** `/search-filter` does not reliably return `total.value`. Use `hits` array length only.
