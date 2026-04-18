# Retailer Scraping Reference

URL patterns, anti-bot levels, and extraction strategies for all finished-good sources in Agnes.

Finished goods in `db.sqlite` span 12 retailers. SKU format: `FG-{retailer}-{id_or_slug}`.

---

## Tier 0: Try DSLD First (Always)

Before scraping any retailer, search DSLD by product name.
If match confidence ≥ 0.85, skip the retailer entirely — DSLD data is more reliable.

```python
from enrichment.sources.dsld import dsld_search, dsld_label

def try_dsld_first(product_name: str) -> dict | None:
    hits = dsld_search(product_name, size=5)
    if not hits:
        return None
    best = hits[0]
    label = dsld_label(best["labelId"])
    return {"source": "dsld", "confidence": 0.9, "data": label}
```

---

## Retailer Profiles

### 1. iHerb (13 products, HIGH anti-bot risk)

**SKU pattern:** `FG-iherb-10421`, `FG-iherb-116514`, `FG-iherb-cen-27493`

**URL pattern:**
```
https://www.iherb.com/pr/{product-name-slug}/{numeric-id}
```
The numeric ID alone is enough to navigate — iHerb redirects to the canonical URL.
```
# Use Google ADK to discover the full URL:
query = f"site:iherb.com {product_id}"
# Or construct directly:
url = f"https://www.iherb.com/pr/product/{product_id}"
```

**Special case — `FG-iherb-cen-27493`:**
The `cen-` prefix indicates a Centrum product on iHerb. Query by brand + ID.

**Supplement facts rendering:** IMAGE-BASED — rendered as a PNG label image embedded in the page. No clean HTML table. Vision extraction required.

**Data available:**
- Product name, brand, description
- Supplement Facts as embedded image (screenshot → Claude Vision)
- Size/count variants via dropdown (60ct, 120ct, etc.)
- Retail pricing per variant
- Certifications as badge icons

**Anti-bot level:** HIGH
- Cloudflare bot management (fingerprinting, IP reputation, challenge pages)
- Standard Playwright headless is often blocked
- JavaScript-heavy React page

**Extraction strategy:**
```python
# 1. Navigate with Playwright in headed or stealth mode
# 2. Take full-page screenshot
# 3. Send to Claude Haiku vision for structured extraction
# (Do NOT attempt BeautifulSoup4 table parsing — no HTML tables exist)
```

**Rate limiting:** 2+ second delay. Max ~30 pages/hour from a single IP.

**Playwright stealth requirement:** See `browser-automation.md` § Stealth Configuration.

---

### 2. Thrive Market (16 products, MEDIUM anti-bot risk)

**SKU patterns:**
- Slug format: `FG-thrive-market-cure-hydration-electrolyte-drink-mix-jar-berry-pomegranate`
- Barcode format: `FG-thrive-market-671635734464` (UPC/EAN-13)
- Numeric format: `FG-thrive-market-6009804424153` (barcode-style)

**URL pattern:**
```
https://thrivemarket.com/p/{product-slug}
```

**For slug-based SKUs:** strip `FG-thrive-market-` prefix → that IS the URL slug.
```python
slug = sku.replace("FG-thrive-market-", "")
url = f"https://thrivemarket.com/p/{slug}"
```

**For barcode-based SKUs:** use Google ADK to resolve.
```python
# Search query:
query = f"site:thrivemarket.com {barcode}"
# Or:
query = f"thrivemarket.com {barcode} supplement"
```

**Data available:**
- Product name, brand, description
- Ingredient list and supplement facts (HTML or image — inspect per product)
- Price (retail, with "member" vs "non-member" tiers)
- Product images

**Anti-bot level:** MEDIUM
- Some Cloudflare protection but less aggressive than iHerb
- Playwright + BeautifulSoup4 often sufficient

**Extraction strategy:**
```python
# 1. Navigate to URL
# 2. Try HTML parsing first (supplement facts may be in DOM)
# 3. Fall back to screenshot + vision if not found
```

---

### 3. Amazon (15 products, MEDIUM-HIGH anti-bot risk)

**SKU pattern:** `FG-amazon-b0002wrqy4`, `FG-amazon-b012t9ga6c`

**URL pattern:**
```python
asin = sku.replace("FG-amazon-", "").upper()  # e.g., "B0002WRQY4"
url = f"https://www.amazon.com/dp/{asin}"
```

**Data available:**
- Product name, brand, features bullets
- Supplement facts often in "Product details" or image gallery
- Size/flavor variants via dropdown
- Pricing

**Anti-bot level:** MEDIUM-HIGH
- Anti-scraping measures enforced; Playwright headless usually blocked
- Consider using the unofficial Amazon Product API (PAAPI — free tier) or search DSLD first

**Supplement facts:** Mixed — sometimes HTML table in "Technical Specifications", sometimes image-only.

**Extraction strategy:**
```python
# Priority: DSLD first (Amazon supplements are almost all in DSLD)
# If DSLD misses: try Amazon page with stealth Playwright
# Last resort: Google ADK → find manufacturer or iHerb page for same product
```

---

### 4. Target (20 products, MEDIUM anti-bot risk)

**SKU pattern:** `FG-target-a-10996455`, `FG-target-a-14161820`, `FG-target-a-50284728`

**URL pattern:**
```python
item_id = sku.replace("FG-target-", "")  # e.g., "a-10996455"
url = f"https://www.target.com/p/-/{item_id}"
```

**Data available:**
- Product name, brand, description
- Supplement facts (usually image-based in "Specifications" section)
- Multiple sizes listed
- Pricing

**Anti-bot level:** MEDIUM
- Target uses standard Akamai bot protection
- Playwright with realistic delays often sufficient
- Supplement facts may be in `<div data-content="specifications">` or image

**Extraction strategy:**
```python
# Try BeautifulSoup4 for the specifications section
# Look for table or description block containing "Supplement Facts"
# Fall back to screenshot + vision
```

---

### 5. Walmart (18 products, MEDIUM anti-bot risk)

**SKU pattern:** `FG-walmart-8053802024`, `FG-walmart-17338669408`

**URL pattern:**
```python
item_id = sku.replace("FG-walmart-", "")  # e.g., "8053802024"
url = f"https://www.walmart.com/ip/{item_id}"
```

**Data available:**
- Product name, brand, description
- Supplement facts (usually in "Specifications" section as HTML or image)
- Multiple sizes listed
- Pricing

**Anti-bot level:** MEDIUM
- Akamai bot protection; stealth Playwright usually works
- JavaScript-heavy — use `wait_for_load_state("networkidle")` plus 2s extra delay

**Extraction strategy:**
```python
# 1. Navigate with Playwright
# 2. Try: soup.find("div", {"data-automation-id": "product-overview"})
# 3. Search for "Supplement Facts" or "Ingredients" in page text
# 4. Vision fallback if no structured data
```

---

### 6. Vitamin Shoppe (15 products, LOW-MEDIUM anti-bot risk)

**SKU pattern:** `FG-the-vitamin-shoppe-vs-2750`, `FG-the-vitamin-shoppe-ye-7038`

**URL pattern:**
```python
item_code = sku.replace("FG-the-vitamin-shoppe-", "")  # e.g., "vs-2750" or "ye-7038"
url = f"https://www.vitaminshoppe.com/p/{item_code}"
```

**Data available:**
- Product name, brand, full ingredient list
- Supplement facts usually available as HTML text (easy to parse)
- Size/count variants
- Pricing

**Anti-bot level:** LOW-MEDIUM
- Standard e-commerce protection; Playwright often works cleanly
- Good candidate for BeautifulSoup4 HTML extraction first

---

### 7. Walgreens (14 products, MEDIUM anti-bot risk)

**SKU pattern:** `FG-walgreens-prod6083374`, `FG-walgreens-prod6063885`

**URL pattern:**
```python
item_id = sku.replace("FG-walgreens-", "")  # e.g., "prod6083374"
url = f"https://www.walgreens.com/store/c/productDetail.jsp?ID={item_id}"
```

**Data available:**
- Product name, brand, description
- Drug Facts / Supplement Facts (HTML table often present)
- Pricing

**Anti-bot level:** MEDIUM
- Playwright with delays usually sufficient

---

### 8. Vitacost (12 products, LOW-MEDIUM anti-bot risk)

**SKU pattern:** `FG-vitacost-vitacost-magnesium`, `FG-vitacost-vitacost-vitamin-d3-as-cholecalciferol-25-mcg-1000-iu-300-capsules`

**URL pattern:**
```python
slug = sku.replace("FG-vitacost-", "")  # e.g., "vitacost-magnesium"
url = f"https://www.vitacost.com/vitacost-{slug}"
# OR via search:
url = f"https://www.vitacost.com/{slug}"
```

**Note:** Vitacost slugs are verbose product names. The slug in the SKU may include size. Strip redundant prefix:
```python
slug = sku.replace("FG-vitacost-vitacost-", "")
url = f"https://www.vitacost.com/vitacost-{slug}"
```

**Data available:**
- Full supplement facts in HTML (Vitacost is notably clean for HTML parsing)
- Multiple sizes listed clearly
- Pricing with Vitacost member discount

**Anti-bot level:** LOW-MEDIUM
- Standard protection; Playwright usually works
- Vitacost is a good test site for HTML parsing patterns

---

### 9. CVS (10 products, LOW-MEDIUM anti-bot risk)

**SKU pattern:** `FG-cvs-704167`, `FG-cvs-342300`

**URL pattern:**
```python
item_id = sku.replace("FG-cvs-", "")  # e.g., "704167"
url = f"https://www.cvs.com/shop/product-detail/{item_id}"
```

**Data available:**
- Product name, brand, description
- Supplement facts (often HTML table or structured text)
- Pricing

**Anti-bot level:** LOW-MEDIUM

---

### 10. Costco (9 products, LOW anti-bot risk)

**SKU pattern:** `FG-costco-11467951`, `FG-costco-100494097`

**URL pattern:**
```python
item_id = sku.replace("FG-costco-", "")
url = f"https://www.costco.com/product-{item_id}.product.{item_id}.html"
# Or simpler:
url = f"https://www.costco.com/.product.{item_id}.html"
```

**Data available:**
- Product name, brand, description
- Supplement facts in structured HTML (Costco pages are relatively clean)
- Warehouse-sized pricing (useful for volume benchmarking)
- Unit price calculations

**Anti-bot level:** LOW
- Minimal anti-bot protection; Playwright works easily

---

### 11. Sam's Club (5 products, LOW-MEDIUM anti-bot risk)

**SKU pattern:** `FG-sams-club-prod15990273`, `FG-sams-club-p03010993`

**URL pattern:**
```python
item_id = sku.replace("FG-sams-club-", "")  # e.g., "prod15990273" or "p03010993"
url = f"https://www.samsclub.com/p/{item_id}"
```

**Anti-bot level:** LOW-MEDIUM (similar to Walmart)

---

### 12. GNC (2 products)

**SKU pattern:** (only 2 products — low priority)
Use Google ADK to discover URL for each.

---

## Unified Product Discovery Strategy

When a direct URL construction fails or returns 404, fall back to Google ADK search:

```python
async def discover_product_url(sku: str, product_name: str) -> str | None:
    retailer = extract_retailer(sku)
    query = f"site:{RETAILER_DOMAINS[retailer]} {product_name}"
    results = await google_search(query)
    # Return first result URL matching the retailer domain
    for r in results:
        if RETAILER_DOMAINS[retailer] in r["url"]:
            return r["url"]
    return None

RETAILER_DOMAINS = {
    "iherb": "iherb.com",
    "thrive-market": "thrivemarket.com",
    "amazon": "amazon.com",
    "target": "target.com",
    "walmart": "walmart.com",
    "the-vitamin-shoppe": "vitaminshoppe.com",
    "walgreens": "walgreens.com",
    "vitacost": "vitacost.com",
    "cvs": "cvs.com",
    "costco": "costco.com",
    "sams-club": "samsclub.com",
    "gnc": "gnc.com",
}
```

---

## Extraction Priority by Retailer

| Retailer | Supplement Facts Format | Best Method |
|---|---|---|
| iHerb | Image-based | Screenshot → Claude Vision |
| Thrive Market | Mixed | BeautifulSoup4 → Vision fallback |
| Amazon | Mixed | DSLD first → Vision fallback |
| Target | Image/structured | BeautifulSoup4 → Vision fallback |
| Walmart | Structured HTML | BeautifulSoup4 |
| Vitamin Shoppe | HTML text | BeautifulSoup4 |
| Walgreens | HTML table | BeautifulSoup4 |
| Vitacost | HTML table (clean) | BeautifulSoup4 |
| CVS | HTML table | BeautifulSoup4 |
| Costco | HTML structured | BeautifulSoup4 |
| Sam's Club | Mixed | BeautifulSoup4 → Vision fallback |
| GNC | Mixed | Google ADK discovery first |

---

## Size Variant Extraction

Many products come in multiple sizes (60ct vs 120ct, 500g vs 1kg). Extract all variants when available:

```python
def extract_size_variants(soup: BeautifulSoup) -> list[dict]:
    """Extract all size/count options with their prices."""
    variants = []
    # Most retailers use <select> dropdown or radio buttons for size
    for option in soup.find_all("option"):
        text = option.get_text(strip=True)
        if any(unit in text.lower() for unit in ["ct", "mg", "g", "kg", "lb", "oz", "fl oz", "ml"]):
            variants.append({
                "label": text,
                "value": option.get("value"),
                "price": extract_price_from_nearby_element(option)
            })
    return variants

# Store in Supplier_Commercial:
# {size_label: "120 ct", price_usd: 18.99, price_per_unit: 0.158}
```

---

## Rate Limiting by Retailer

| Retailer | Min Delay | Max Req/Hour |
|---|---|---|
| iHerb | 3s | 20 |
| Amazon | 3s | 20 |
| Walmart | 2s | 30 |
| Target | 2s | 30 |
| Vitacost | 1.5s | 40 |
| Costco | 1s | 60 |
| Others | 2s | 30 |
