# Molport Integration Reference

Molport is a chemical marketplace aggregating supplier offers for commercially available compounds. It is the primary source for **bulk chemical pricing and supplier availability** in Agnes's Phase 3 commercial enrichment.

---

## What Molport Provides

Molport indexes millions of compounds from hundreds of chemical suppliers worldwide. For each compound it covers:

- **Supplier listings** — name, type (stock vs. make-on-demand), country of origin, shipping country
- **Pricing** — per-packing-option prices in USD (or supplier currency), typically at multiple quantity tiers
- **Stock availability** — verified and unverified stock amounts in mg/g, plus last-update date
- **Delivery** — estimated delivery days per supplier offer
- **Minimum order quantity (MOQ)** — minimum purchasable amount per offer
- **Compound identity** — Molport ID, SMILES, canonical SMILES, IUPAC name, molecular formula, molecular weight, synonyms
- **Purity** — returned as a percentage per offer (e.g., ">98%", "98.83") — available via some supplier catalog entries; not guaranteed for all offers

Molport is chemistry-first. It is strongest on CAS-identified pure chemicals and weakest on supplement-specific materials like botanical extracts or proprietary blends. See the Coverage section below.

---

## No API Key Available at Time of Writing — Live Response Examples Pending

**Agnes does not currently have a Molport API key. All response schemas in this document are inferred from official API documentation and third-party wrappers (molharbor, ChemPrice). No live response has been validated against the schemas below.**

**Before writing any parsing code, the first implementor must:**
1. Obtain an API key (registration instructions below)
2. Query a known compound (suggested test cases below)
3. Compare the real JSON response against the documented fields in this guide
4. Update this document with confirmed field names and any discrepancies

Do not assume field names, types, or nesting are exactly as documented here. API responses are the ground truth.

---

## Auth & Base URL

```
Base (v3 REST API):   https://api.molport.com/api/
Base (List Search):   https://api.molport.com/
API Docs:             https://www.molport.com/shop/api-documentation-v-3-0
Swagger UI:           https://api.molport.com/swagger-ui/
Version history:      https://www.molport.com/shop/api-history-of-changes
```

### Getting an API Key

1. Register a free account at `https://www.molport.com/shop/register`
2. Log in and navigate to **Profile → API Keys**
3. Request API access — keys are provisioned for free accounts
4. Store the key in `.env` as `MOLPORT_API_KEY` (already defined in `.env.template`)

Two authentication schemes exist in v3. Use API key — it is the documented preference for institutional/automated access:

```
Query parameter:  ?apikey=<MOLPORT_API_KEY>
  -- OR --
Username/password: ?username=<user>&authenticationcode=<password>
```

Order-tracking endpoints use a different header-based scheme (`MOLPORT-API-ID` / `MOLPORT-API-KEY`) — not needed for Agnes.

---

## Rate Limits (Free Tier)

| Limit | Value |
|---|---|
| Monthly request cap | 10,000 requests (resets at month start) |
| Concurrent chemical searches | 3 simultaneous |
| Concurrent catalog queries | 3 simultaneous |
| Increased limits | Contact sales@molport.com |

> At 10k/month, Agnes can query ~322 compounds per day. With 876 raw material SKUs, a full single-pass enrichment (~1 request per compound for load + 1 for supplier data) costs ~1,750 requests — well within the free tier if cached properly.

---

## Key Endpoints

### 1. Load Molecule by Molport ID

```
GET https://api.molport.com/api/molecule/load
```

**Use when:** You already have a Molport compound ID (from a prior search result).

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `molecule` | Yes | Molport ID string, e.g. `Molport-000-871-563` |
| `apikey` | Yes | Your API key |

**Returns:** Full compound record — identity, stock status, supplier catalog with pricing.

---

### 2. Chemical Structure Search

```
POST https://api.molport.com/api/chemical-search/search
Content-Type: application/json
```

**Use when:** You have a SMILES string for the compound (obtainable from PubChem given a CAS or name).

**Request body:**

```json
{
  "Structure": "CC(=O)Oc1ccccc1C(=O)O",
  "Search Type": 3,
  "Maximum Search Time": 60000,
  "Maximum Result Count": 10,
  "Chemical Similarity Index": 1.0,
  "apikey": "<MOLPORT_API_KEY>"
}
```

**Search type codes:**

| Code | Type | Agnes use |
|---|---|---|
| 1 | Substructure | Rarely needed |
| 2 | Superstructure | Rarely needed |
| 3 | Exact | Default — match the exact compound |
| 4 | Similarity | Fallback for approximate matches; pair with `Chemical Similarity Index` ≥ 0.90 |
| 5 | Perfect | Stricter than exact; use when tautomers/stereochemistry matter |
| 6 | Exact Fragment | Default per docs — confirm behavior vs. type 3 once key is obtained |

**Response fields per result (inferred from docs):**

| Field | Type | Description |
|---|---|---|
| `Id` | int | Internal compound ID |
| `Molport Id` | string | E.g. `"Molport-000-871-563"` |
| `SMILES` | string | Input SMILES |
| `Canonical SMILES` | string | Normalized SMILES |
| `Verified Amount` | float | Stock in mg (verified by supplier) |
| `Unverified Amount` | float | Stock in mg (unverified/estimated) |
| `Similarity Index` | float | 0.0–1.0; present for similarity search type only |

Chemical search returns summary records only — call `/molecule/load` to get full supplier + pricing data for a hit.

---

### 3. List Search API (Batch)

```
POST https://api.molport.com/
```

Separate REST API for batch lookups (up to 10,000 compounds per job). Accepts SMILES, SD format, or Molport IDs. Returns availability, pricing, lead times, and supplier details in bulk. Full schema is defined in the OpenAPI spec at `https://api.molport.com/swagger-ui/` — retrieve and document it when the key is obtained.

---

## Expected Response Schema — Molecule/Load

The following is inferred from Molport's v3 API documentation and third-party wrappers. **Not live-validated.**

```json
{
  "Molecule": {
    "Id": 871563,
    "Molport Id": "Molport-000-871-563",
    "SMILES": "...",
    "Canonical SMILES": "...",
    "IUPAC": "magnesium stearate",
    "Formula": "C36H70MgO4",
    "Molecular Weight": 591.27,
    "Status": "shop",
    "Type": "stock",
    "Largest Stock": 500000,
    "Stock Measure": "g",
    "Synonyms": ["magnesium distearate", "octadecanoic acid, magnesium salt"],
    "Suppliers": [
      {
        "Supplier Name": "Acme Chem",
        "Supplier Id": 1234,
        "Supplier Type": "stock",
        "Origin Country Name": "China",
        "Origin Country ISO": "CN",
        "Shipping Country Name": "United States",
        "Shipping Country ISO": "US",
        "Minimum Order": 100,
        "Currency": "USD",
        "Catalogue": [
          {
            "Catalog Id": 567890,
            "Catalog Number": "ACM-12345",
            "Stock Amount": 500000,
            "Stock Measure": "g",
            "Last Update Date": "2024-01-12",
            "Purity": ">98%",
            "Packings": [
              {
                "Amount": 100,
                "Measure": "g",
                "Price": 45.00,
                "Currency": "USD",
                "Delivery Days": 5
              },
              {
                "Amount": 1000,
                "Measure": "g",
                "Price": 320.00,
                "Currency": "USD",
                "Delivery Days": 5
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Agnes-relevant fields:**

| Field path | Agnes use |
|---|---|
| `Molport Id` | Primary Molport cross-reference key; store in `Supplier_Commercial` |
| `Synonyms[]` | Supplement fuzzy matching fallback |
| `Suppliers[].Supplier Name` | Maps to Agnes `Supplier.Name` (fuzzy match needed) |
| `Suppliers[].Origin Country ISO` | Supply chain provenance |
| `Suppliers[].Minimum Order` | MOQ — key for Phase 3 commercial enrichment |
| `Suppliers[].Currency` | Normalize to USD for comparison |
| `Catalogue[].Purity` | Grade indicator; flag "food grade" vs "reagent grade" manually |
| `Catalogue[].Packings[].Amount` + `Measure` | Quantity tier |
| `Catalogue[].Packings[].Price` | Price at that tier |
| `Catalogue[].Packings[].Delivery Days` | Lead time proxy |
| `Catalogue[].Stock Amount` + `Stock Measure` | Current availability |
| `Catalogue[].Last Update Date` | Data freshness signal |

> **Purity caveat:** Molport pricing is typically for lab/research quantities (mg to kg scale). "98% purity" in a research catalog does not guarantee food-grade, cGMP, or pharmaceutical-grade specification. Flag all Molport purity values as `grade_unverified` until confirmed by a COA or supplier contact.

---

## Search Strategy for Agnes (CAS → SMILES → Molport)

Molport's primary search interface is **SMILES-based**, not CAS-based. The correct lookup chain is:

```
Ingredient slug  →  canonical name (Phase 1)
    ↓
PubChem CID + CAS (Phase 1, already enriched)
    ↓
PubChem: GET https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/IsomericSMILES/JSON
    ↓
SMILES  →  Molport chemical-search (exact, type 3)
    ↓
Molport Id  →  molecule/load  →  suppliers + pricing
```

Molport does also accept CAS numbers and IUPAC names via its web search interface and reportedly via the List Search API — but this is not clearly documented in the v3 REST API spec. When the key is obtained, test both:

```
# Test: does the API accept CAS directly?
GET https://api.molport.com/api/molecule/load?molecule=557-04-0&apikey=...
# (557-04-0 is magnesium stearate)
```

If CAS-based lookup works, it eliminates the PubChem SMILES step and simplifies the pipeline considerably.

---

## Coverage by Ingredient Type

| Ingredient type | Molport coverage | Notes |
|---|---|---|
| Pure vitamins (ascorbic acid, cholecalciferol, riboflavin) | High | CAS-identified; many suppliers, multiple tiers |
| Minerals (zinc citrate, magnesium stearate, calcium carbonate) | High | Well-indexed; pricing at g–kg scale |
| Excipients (silicon dioxide, microcrystalline cellulose) | High | Common industrial chemicals |
| Amino acids (L-glutamine, L-carnitine) | High | Standard chemicals |
| Simple botanicals (caffeine, quercetin, resveratrol) | Medium-High | Isolated compounds work; plant-sourced vs. synthetic not distinguished |
| Botanical extracts ("ashwagandha extract 5% withanolides") | Low | Non-CAS identifiable; search returns the isolated active, not the extract blend |
| Proprietary blends ("Curcumin C3 Complex") | None | Brand-trademarked forms — Molport does not index these |
| Proteins (whey protein concentrate, collagen peptides) | None | Not small molecules; outside Molport's database scope |

**Rule of thumb:** If Phase 1 returned a valid CAS number and PubChem CID, Molport will likely have at least one supplier listing. If Phase 1 flagged the ingredient as `manual_review` or `complex_botanical`, skip Molport — go directly to browser scraping of PureBulk or BulkSupplements.

### Agnes test cases (use these first when key is obtained)

| Ingredient | CAS | Why useful |
|---|---|---|
| Ascorbic acid | 50-81-7 | Very common; should have 20+ supplier listings |
| Cholecalciferol | 67-97-0 | Key vitamin D3 form; moderate supplier count |
| Zinc citrate | 5990-32-9 | Mineral salt; tests salt-form lookup |
| Magnesium stearate | 557-04-0 | Ubiquitous excipient; should be cheap and abundant |
| Silicon dioxide | 7631-86-9 | Fumed silica; test for industrial-grade excipient |

---

## Practical Limitations

1. **Research-scale pricing ≠ industrial bulk pricing.** Molport aggregates lab-chemical and research-reagent suppliers. Pricing at 1 kg differs substantially from contract manufacturing quantities (1 MT+). Flag all Molport prices as `"retail_proxy"` until a supplier quotes at actual production volumes.

2. **No food/pharma grade filter.** Molport does not tag listings by regulatory grade (food, pharmaceutical, USP, FCC). Purity percentage alone is insufficient to confirm grade. Phase 3 compliance must separately verify grade from supplier COA or certification databases.

3. **Supplier overlap with Agnes's existing suppliers is unknown.** Agnes's `Supplier` table has 40 known entities — it is not known which of these appear in Molport's catalog. Fuzzy-match `Supplier.Name` against `Suppliers[].Supplier Name` to find overlaps; store unmatched Molport suppliers as new commercial data points.

4. **Prices in mixed currencies.** Suppliers quote in their local currency. Normalize to USD using a daily exchange rate fetch (or a fixed rate with a stale-data flag) before inserting into `Supplier_Commercial`.

5. **Stock data freshness varies.** `Last Update Date` can be months or years old. Treat stock amounts as indicative, not real-time. Flag any record where `Last Update Date` is > 180 days old.

6. **SMILES round-trips through PubChem add latency and a failure point.** If PubChem is unavailable, the Molport lookup chain stalls. Cache SMILES in `db_enriched.sqlite` alongside PubChem results in Phase 1 — never re-fetch for Phase 3.

---

## Minimal Python Client

```python
import os
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MOLPORT_BASE = "https://api.molport.com/api"
MOLPORT_API_KEY = os.environ["MOLPORT_API_KEY"]

def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

_session = _make_session()


def molport_load(molport_id: str) -> dict:
    """Fetch full compound record by Molport ID."""
    r = _session.get(
        f"{MOLPORT_BASE}/molecule/load",
        params={"molecule": molport_id, "apikey": MOLPORT_API_KEY},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def molport_search_smiles(smiles: str, max_results: int = 5) -> list[dict]:
    """Search by SMILES (exact match). Returns list of summary hits."""
    payload = {
        "Structure": smiles,
        "Search Type": 3,          # Exact
        "Maximum Search Time": 60000,
        "Maximum Result Count": max_results,
        "Chemical Similarity Index": 1.0,
        "apikey": MOLPORT_API_KEY,
    }
    r = _session.post(
        f"{MOLPORT_BASE}/chemical-search/search",
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # NOTE: validate actual response structure once a key is obtained —
    # the exact key name for the hits array is unconfirmed.
    return data.get("Molecules", data.get("molecules", []))


def molport_lookup_by_cas(cas_number: str) -> dict | None:
    """
    Attempt CAS-based lookup. Not officially documented for the REST API
    but worth testing — pass CAS as the 'molecule' parameter.
    Returns None if unsupported (non-200 or empty result).
    """
    try:
        r = _session.get(
            f"{MOLPORT_BASE}/molecule/load",
            params={"molecule": cas_number, "apikey": MOLPORT_API_KEY},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("Molecule"):
                return data
    except Exception:
        pass
    return None


def molport_get_suppliers(molport_id: str) -> list[dict]:
    """
    Load a compound and return a flat list of supplier offer dicts,
    normalized for storage in Supplier_Commercial.

    NOTE: Field names below are inferred — validate against real response.
    """
    data = molport_load(molport_id)
    molecule = data.get("Molecule", {})
    results = []

    for supplier in molecule.get("Suppliers", []):
        for catalog in supplier.get("Catalogue", []):
            for packing in catalog.get("Packings", []):
                results.append({
                    "molport_id":       molport_id,
                    "supplier_name":    supplier.get("Supplier Name"),
                    "supplier_country": supplier.get("Shipping Country ISO"),
                    "origin_country":   supplier.get("Origin Country ISO"),
                    "catalog_number":   catalog.get("Catalog Number"),
                    "purity":           catalog.get("Purity"),
                    "stock_amount":     catalog.get("Stock Amount"),
                    "stock_measure":    catalog.get("Stock Measure"),
                    "last_update":      catalog.get("Last Update Date"),
                    "min_order":        supplier.get("Minimum Order"),
                    "amount":           packing.get("Amount"),
                    "measure":          packing.get("Measure"),
                    "price":            packing.get("Price"),
                    "currency":         packing.get("Currency"),
                    "delivery_days":    packing.get("Delivery Days"),
                    "source":           "molport",
                    "confidence":       0.80,   # lower than DSLD/PubChem — pricing is indicative
                })
    return results
```

---

## Caching

All Molport responses must be cached. At 10k requests/month, re-fetching the same compound wastes quota and risks hitting the monthly cap during pipeline re-runs.

```python
import json
import sqlite3
from datetime import datetime, timezone

# DDL (add to schema/enriched_schema.sql):
# CREATE TABLE IF NOT EXISTS Molport_Cache (
#     molport_id   TEXT NOT NULL,
#     query_type   TEXT NOT NULL,   -- 'load' | 'search_smiles'
#     query_key    TEXT NOT NULL,   -- molport_id or smiles
#     response     TEXT NOT NULL,   -- JSON blob
#     fetched_at   TEXT NOT NULL,
#     PRIMARY KEY (query_type, query_key)
# );

def cached_molport_load(molport_id: str, db_conn: sqlite3.Connection) -> dict:
    row = db_conn.execute(
        "SELECT response FROM Molport_Cache WHERE query_type='load' AND query_key=?",
        (molport_id,),
    ).fetchone()
    if row:
        return json.loads(row[0])

    time.sleep(0.5)   # be polite; Molport has no documented per-second rate limit
    data = molport_load(molport_id)
    db_conn.execute(
        "INSERT OR REPLACE INTO Molport_Cache VALUES (?,?,?,?,?)",
        ("load", molport_id, molport_id, json.dumps(data),
         datetime.now(timezone.utc).isoformat()),
    )
    db_conn.commit()
    return data


def cached_molport_search(smiles: str, db_conn: sqlite3.Connection) -> list[dict]:
    row = db_conn.execute(
        "SELECT response FROM Molport_Cache WHERE query_type='search_smiles' AND query_key=?",
        (smiles,),
    ).fetchone()
    if row:
        return json.loads(row[0])

    time.sleep(0.5)
    results = molport_search_smiles(smiles)
    db_conn.execute(
        "INSERT OR REPLACE INTO Molport_Cache VALUES (?,?,?,?,?)",
        ("search_smiles", smiles, smiles, json.dumps(results),
         datetime.now(timezone.utc).isoformat()),
    )
    db_conn.commit()
    return results
```

Cache expiry policy: Molport pricing changes infrequently for bulk chemicals. A 30-day TTL is reasonable. Add a `WHERE fetched_at < datetime('now', '-30 days')` filter to invalidate stale entries.

---

## Pipeline Integration — Phase 3

Molport is the **primary source** for `Supplier_Commercial` enrichment. It is called after Phase 1 has populated `Ingredient_Canonical` with CAS numbers and PubChem SMILES.

Lookup order per raw material:
1. Check `Molport_Cache` — if fresh hit exists, use it
2. Try CAS-based load (undocumented, worth testing once key available)
3. Fetch SMILES from `Ingredient_Canonical.smiles` (populated by PubChem in Phase 1)
4. Call `molport_search_smiles()` → get first Molport ID
5. Call `cached_molport_load()` → get full supplier + pricing data
6. Flatten to `Supplier_Commercial` rows via `molport_get_suppliers()`
7. If no hits: store `NULL` with `confidence = 0.0`, flag as `molport_no_match`

---

## Gotchas

- **Field names may use title case with spaces** — the official docs show `"Supplier Name"`, `"Delivery Days"` etc. The molharbor wrapper converts these to snake_case. Use the raw API's conventions when parsing directly; do not assume snake_case without validating against a real response.
- **"Verified" vs "Unverified" stock** — prefer `Verified Amount` for availability confidence; `Unverified Amount` is self-reported by the supplier and unconfirmed.
- **Empty `Suppliers` array** — can mean the compound exists in Molport's database but has no current offers. Store `Molport Id` but leave pricing fields as `NULL`.
- **`Status: "made-on-demand"` vs `"stock"`** — made-on-demand compounds have longer lead times (weeks to months) and variable pricing. Tag them separately in `Supplier_Commercial`.
- **Multiple currency types** — convert all prices to USD at time of fetch; store `original_currency` and `original_price` alongside for auditability.
- **Concurrent search limit** — if running Phase 3 in parallel threads, enforce a semaphore capping at 3 concurrent Molport API calls. Exceeding this returns HTTP 429.
- **SMILES canonicalization** — different tools produce different SMILES for the same molecule. If a Molport search on PubChem SMILES returns 0 hits, try the canonical SMILES from RDKit or OPSIN before concluding no match.
