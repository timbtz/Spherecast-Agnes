# Free APIs Reference

Reference guide for all external data sources used in the Agnes enrichment pipeline.

---

## Quick Reference

| API | Base URL | Auth | Best For | Rate Limit |
|---|---|---|---|---|
| NIH DSLD v9 | `https://api.ods.od.nih.gov/dsld/v9/` | API key (`X-Api-Key` header) | Supplement label search, ingredient amounts | Undocumented |
| PubChem PUG REST | `https://pubchem.ncbi.nlm.nih.gov/rest/pug/` | None | CAS#, IUPAC name, molecular formula, synonyms | 5/sec, 400/min |
| USDA FoodData Central | `https://api.nal.usda.gov/fdc/v1/` | Free key | Food ingredient nutrient data | 1000/hour |
| RxNorm | `https://rxnav.nlm.nih.gov/REST/` | None | Drug/ingredient name normalization, synonyms | Undocumented |
| openFDA | `https://api.fda.gov/` | Optional key | Label text search, adverse events | Reasonable |
| Molport v3 | `https://www.molport.com/shop/api-documentation-v-3-0` | Free account | Chemical compound supplier pricing | 10k req/month |

---

## 1. NIH DSLD v9 (Dietary Supplement Label Database)

The most important API for Agnes — 58,000+ real supplement labels with exact ingredient amounts.

**Auth:** API key via `X-Api-Key` header (key stored in `.env` as `DSLD_API_KEY`)
**Docs:** https://dsld.od.nih.gov/api-guide

> **Critical notes from live testing:**
> - Use **v9** with `X-Api-Key` header — v9 without key returns 0 hits; v8 works without key but has a different (older) schema
> - Search parameter is `q=`, **not** `query=`
> - `ingredientRows` holds active ingredients with amounts; `otheringredients` holds excipients

### Key Endpoints

```
GET /search-filter?q={name}&size=10    → search by brand/product name
GET /label/{id}                        → full label: amounts, UPC, serving sizes, other ingredients
```

### Verified Response Structure (v9 with key)

**Search hit `_source` fields:**
```json
{
  "brandName": "Nature Made",
  "fullName": "Vitamin D3 2000 IU",
  "physicalState": {"langualCodeDescription": "Softgel Capsule"},
  "netContents": [{"quantity": 320, "unit": "Liquid Softgel(s)", "display": "320 Liquid Softgel(s)"}],
  "allIngredients": [{"name": "Vitamin D3", "category": "vitamin", "ingredientGroup": "Vitamin D"}],
  "offMarket": "0",
  "entryDate": "2013-06-25"
}
```

**Label detail `ingredientRows` (active ingredients with amounts):**
```json
[
  {
    "name": "Vitamin D3",
    "category": "vitamin",
    "ingredientGroup": "Vitamin D",
    "uniiCode": "1C6V77QF41",
    "quantity": [
      {
        "quantity": 2000,
        "unit": "IU",
        "servingSizeUnit": "Softgel(s)",
        "dailyValueTargetGroup": [{"name": "Adults and children 4 or more years of age", "percent": 500}]
      }
    ],
    "nestedRows": [],
    "notes": "Vitamin D3 Note: 50 mcg"
  }
]
```

**Label detail `otheringredients` (excipients/inactive):**
```json
{
  "text": null,
  "ingredients": [
    {"name": "Soybean Oil", "category": "fat"},
    {"name": "Gelatin", "category": "protein"},
    {"name": "Glycerin", "category": "other"}
  ]
}
```

**Additional label fields of interest:**
- `upcSku` — UPC barcode (e.g., `"0 31604 02679 0"`) — useful for retailer matching
- `servingsPerContainer` — total servings
- `servingSizes[].unit` + `minQuantity` — serving size
- `labelRelationships` — links to other package sizes of same product
- `contacts[].contactDetails` — distributor name, address, website

### Python Client

```python
import os
import requests

DSLD_BASE = "https://api.ods.od.nih.gov/dsld/v9"
DSLD_HEADERS = {"X-Api-Key": os.getenv("DSLD_API_KEY", "")}

def dsld_search(product_name: str, size: int = 5) -> list[dict]:
    """Search DSLD by brand/product name. Returns list of hit dicts."""
    r = requests.get(
        f"{DSLD_BASE}/search-filter",
        headers=DSLD_HEADERS,
        params={"q": product_name, "size": size},
        timeout=10
    )
    r.raise_for_status()
    return r.json().get("hits", [])  # list of {_id, _score, _source}

def dsld_label(label_id: str | int) -> dict:
    """Get full label record with ingredientRows, otheringredients, UPC, etc."""
    r = requests.get(
        f"{DSLD_BASE}/label/{label_id}",
        headers=DSLD_HEADERS,
        timeout=10
    )
    r.raise_for_status()
    return r.json()

def dsld_get_ingredient_amounts(product_name: str) -> list[dict]:
    """
    Search by product name → return active ingredient amounts.
    Returns empty list if no match found.
    """
    hits = dsld_search(product_name, size=3)
    if not hits:
        return []

    label_id = hits[0]["_id"]
    label = dsld_label(label_id)

    results = []
    for row in label.get("ingredientRows", []):
        for qty in row.get("quantity", []):
            dv_groups = qty.get("dailyValueTargetGroup", [])
            results.append({
                "name": row["name"],
                "amount": qty.get("quantity"),
                "unit": qty.get("unit"),
                "daily_value_pct": dv_groups[0].get("percent") if dv_groups else None,
                "unii": row.get("uniiCode"),
                "category": row.get("category"),
                "source": "dsld",
                "dsld_id": label_id,
                "confidence": 0.9
            })

    return results

def dsld_get_other_ingredients(label_id: str | int) -> list[str]:
    """Return list of other ingredient (excipient) names from a label."""
    label = dsld_label(label_id)
    other = label.get("otheringredients", {})
    return [i["name"] for i in other.get("ingredients", [])]
```

### Matching Strategy for Agnes Finished Goods

```python
def find_dsld_match(sku: str, product_name: str, brand: str = "") -> dict | None:
    """
    Try to find the right DSLD label for a finished-good SKU.
    Returns the best label dict or None if no confident match.
    """
    # Try brand + product name together for precision
    query = f"{brand} {product_name}".strip() if brand else product_name
    hits = dsld_search(query, size=5)

    for hit in hits:
        src = hit["_source"]
        hit_brand = src.get("brandName", "").lower()
        hit_name = src.get("fullName", "").lower()

        # Fuzzy brand match
        from rapidfuzz import fuzz
        brand_score = fuzz.partial_ratio(brand.lower(), hit_brand)
        name_score = fuzz.token_set_ratio(product_name.lower(), hit_name)

        if brand_score >= 70 and name_score >= 70:
            return {"dsld_id": hit["_id"], "confidence": min(brand_score, name_score) / 100, **src}

    return None
```

---

## 2. PubChem PUG REST API

Authoritative source for chemical identity — CAS numbers, IUPAC names, synonyms, molecular formulas.

**Docs:** https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest

**Rate limit: 5 req/sec, 400 req/min** — implement backoff.

### Key Query Patterns

```
GET /compound/name/{name}/JSON          → full compound record by name
GET /compound/name/{name}/property/MolecularFormula,InChIKey/JSON  → specific properties
GET /compound/cid/{cid}/synonyms/JSON   → all synonyms (includes CAS)
GET /compound/name/{name}/cids/JSON     → just the CID(s) for a name
```

### Python Client

```python
import requests
import time

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"

def pubchem_lookup(name: str) -> dict:
    """
    Look up a chemical by name.
    Returns: {cid, cas, iupac_name, molecular_formula, synonyms, confidence}
    Never trust the CAS from LLMs — this is the authoritative source.
    """
    try:
        r = requests.get(f"{PUBCHEM_BASE}/name/{name}/JSON", timeout=10)
        if r.status_code == 404:
            return {"confidence": 0.0, "error": "not_found"}
        r.raise_for_status()
        compound = r.json()["PC_Compounds"][0]
        cid = compound["id"]["id"]["cid"]

        # Extract properties from props list
        props = {
            p["urn"].get("label"): p["value"].get("sval")
            for p in compound.get("props", [])
            if p["value"].get("sval")
        }

        time.sleep(0.2)  # respect rate limit

        # Fetch synonyms to extract CAS
        syn_r = requests.get(f"{PUBCHEM_BASE}/cid/{cid}/synonyms/JSON", timeout=10)
        synonyms = []
        cas = None
        if syn_r.status_code == 200:
            synonyms = syn_r.json()["InformationList"]["Information"][0]["Synonym"]
            # CAS numbers match pattern: digits-digits-digits
            import re
            for s in synonyms:
                if re.match(r"^\d{2,7}-\d{2}-\d$", s):
                    cas = s
                    break

        return {
            "cid": cid,
            "cas": cas,
            "iupac_name": props.get("IUPAC Name"),
            "molecular_formula": props.get("Molecular Formula"),
            "synonyms": synonyms[:20],
            "source": "pubchem",
            "confidence": 0.97 if cas else 0.80
        }

    except (requests.RequestException, KeyError, IndexError) as e:
        return {"confidence": 0.0, "error": str(e)}

def pubchem_with_backoff(name: str, max_retries: int = 3) -> dict:
    """Wrapper with exponential backoff for rate limits."""
    for attempt in range(max_retries):
        result = pubchem_lookup(name)
        if result.get("error") != "rate_limited":
            return result
        time.sleep(2 ** attempt)
    return {"confidence": 0.0, "error": "rate_limited_exhausted"}
```

---

## 3. USDA FoodData Central (FDC)

Secondary source — useful for common food-grade ingredients. Requires a free API key.

**Sign up:** https://fdc.nal.usda.gov/api-key-signup/  
**Docs:** https://fdc.nal.usda.gov/api-guide/  
**Rate limit:** 1000 req/hour

```python
import requests

FDC_BASE = "https://api.nal.usda.gov/fdc/v1"
FDC_API_KEY = "YOUR_FREE_KEY"   # from fdc.nal.usda.gov

def fdc_search(ingredient_name: str, limit: int = 5) -> list[dict]:
    r = requests.get(
        f"{FDC_BASE}/foods/search",
        params={"query": ingredient_name, "pageSize": limit, "api_key": FDC_API_KEY},
        timeout=10
    )
    r.raise_for_status()
    return r.json().get("foods", [])

def fdc_get_nutrients(fdc_id: int) -> dict:
    r = requests.get(
        f"{FDC_BASE}/food/{fdc_id}",
        params={"api_key": FDC_API_KEY},
        timeout=10
    )
    r.raise_for_status()
    food = r.json()
    return {
        "name": food["description"],
        "nutrients": {
            n["nutrient"]["name"]: {"value": n["value"], "unit": n["nutrient"]["unitName"]}
            for n in food.get("foodNutrients", [])
        }
    }
```

---

## 4. RxNorm API

Useful for normalizing drug/supplement ingredient names to standardized identities and extracting synonyms.

**Docs:** https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html

### Append `.json` to all endpoints for JSON output.

```python
import requests

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"

def rxnorm_find_rxcui(name: str, search_type: int = 1) -> list[str]:
    """
    Find RxCUI identifiers for a drug/ingredient name.
    search_type: 0=exact, 1=normalized (ignores word order/punctuation), 9=approximate
    """
    r = requests.get(
        f"{RXNORM_BASE}/rxcui.json",
        params={"name": name, "search": search_type, "allsrc": 1},
        timeout=10
    )
    r.raise_for_status()
    rxcuis = r.json().get("rxNormdata", {}).get("idGroup", {}).get("rxnormId", [])
    return rxcuis if isinstance(rxcuis, list) else ([rxcuis] if rxcuis else [])

def rxnorm_get_synonyms(rxcui: str) -> dict:
    r = requests.get(f"{RXNORM_BASE}/rxcui/{rxcui}/properties.json", timeout=10)
    r.raise_for_status()
    props = r.json().get("rxNormdata", {}).get("properties", [])
    if not props:
        return {}
    return {
        "rxcui": rxcui,
        "name": props[0].get("name"),
        "synonyms": props[0].get("synonym", [])
    }

def rxnorm_normalize(name: str) -> dict:
    """Normalize ingredient name → RxCUI + synonyms."""
    rxcuis = rxnorm_find_rxcui(name)
    if not rxcuis:
        return {"confidence": 0.0, "error": "not_found"}
    props = rxnorm_get_synonyms(rxcuis[0])
    return {**props, "source": "rxnorm", "confidence": 0.85}
```

---

## 5. openFDA API

Search FDA label databases and adverse event reports.

**Docs:** https://open.fda.gov/apis/

```python
import requests

OPENFDA_BASE = "https://api.fda.gov"

def openfda_search_labels(ingredient_name: str, limit: int = 5) -> list[dict]:
    """Search supplement/drug labels by ingredient name."""
    r = requests.get(
        f"{OPENFDA_BASE}/drug/label.json",
        params={"search": f"ingredients:{ingredient_name}", "limit": limit},
        timeout=10
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("results", [])
```

---

## Recommended Normalization Pipeline

Tier order for ingredient identity resolution:

```python
def resolve_ingredient_identity(name: str) -> dict:
    """
    Try sources in priority order. Stop at confidence >= 0.85.
    Returns enriched identity with source + confidence.
    """
    THRESHOLD = 0.85

    # Tier 1: PubChem — authoritative for chemical identity
    result = pubchem_lookup(name)
    if result.get("confidence", 0) >= THRESHOLD:
        return result

    # Tier 2: DSLD — supplement-specific naming (UNII codes)
    dsld_hits = dsld_search(name, size=3)
    if dsld_hits:
        # Extract UNII from first matching ingredient row
        for row in dsld_hits[0].get("ingredientRows", []):
            if similar_name(row["ingredientName"], name) and row.get("uniiFda"):
                return {
                    "unii": row["uniiFda"],
                    "name": row["ingredientName"],
                    "source": "dsld",
                    "confidence": 0.88
                }

    # Tier 3: RxNorm — drug-type ingredients
    rxnorm_result = rxnorm_normalize(name)
    if rxnorm_result.get("confidence", 0) >= THRESHOLD:
        return rxnorm_result

    # Tier 4: RapidFuzz against already-resolved canonicals
    from rapidfuzz import fuzz
    # ... fuzzy match against db_enriched.sqlite Ingredient_Canonical table

    # Tier 5: Manual review flag
    return {"name": name, "confidence": 0.3, "flag": "manual_review", "source": "none"}
```

---

## Error Handling Best Practice

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session(max_retries: int = 3) -> requests.Session:
    """Create a session with automatic retry on 429/5xx errors."""
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

session = make_session()
# Use session.get() instead of requests.get() throughout the pipeline
```
