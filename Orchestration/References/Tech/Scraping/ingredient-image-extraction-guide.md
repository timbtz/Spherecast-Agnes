# Ingredient Image Extraction Reference

How to extract structured ingredient data from product images and label photographs.

Applies to: supplement facts panels, ingredient lists, product label images, bulk ingredient spec sheets.

---

## When to Use Image Extraction

Image extraction is required when:
- The supplement facts panel is rendered as a PNG/JPG on the product page (iHerb, Amazon)
- The product label image is the only source of ingredient amounts
- HTML table parsing returns no structured data
- A PDF spec sheet or CoA needs ingredient data extracted

For HTML-parseable pages (Vitacost, Walgreens, Walmart), use BeautifulSoup4 directly — skip image extraction.

---

## Strategy 1: Supplement Facts Panel from Product Page

### Step 1 — Locate and Download the Image

Most retailers embed a supplement facts image directly in the product page.

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

def find_supplement_facts_image_url(html: str) -> str | None:
    """Find URL of the supplement facts image embedded in a product page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Strategy A: alt text matching
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").lower()
        src = img.get("src") or img.get("data-src") or ""
        if any(kw in alt for kw in ["supplement facts", "nutrition facts", "drug facts", "supplement panel"]):
            return src
    
    # Strategy B: src path matching (iHerb stores label images in /assets/)
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if any(kw in src.lower() for kw in ["label", "supplement", "nutrition", "facts"]):
            return src
    
    # Strategy C: find in lazy-loaded data attributes
    for img in soup.find_all("img"):
        for attr in ["data-src", "data-lazy", "data-original", "srcset"]:
            val = img.get(attr) or ""
            if "label" in val.lower() or "supplement" in val.lower():
                return val.split(",")[0].strip().split(" ")[0]
    
    return None

def download_image(url: str, session) -> bytes | None:
    """Download image bytes from URL."""
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r.content
    except Exception:
        return None
```

### Step 2 — Send Image to Claude Vision

```python
import base64
import json
from anthropic import Anthropic

client = Anthropic()

SUPPLEMENT_FACTS_PROMPT = """Extract all data from this Supplement Facts / Nutrition Facts label.

Return JSON only (no markdown):
{
  "product_name": null,
  "serving_size": null,
  "servings_per_container": null,
  "calories_per_serving": null,
  "ingredients": [
    {
      "name": "Vitamin D3 (as Cholecalciferol)",
      "amount": 50.0,
      "unit": "mcg",
      "daily_value_pct": 250.0
    }
  ],
  "other_ingredients": ["Gelatin", "Rice Flour"],
  "allergen_statement": null,
  "confidence": 0.0
}

Rules:
- amount: numeric value only (no units in this field)
- unit: mg | mcg | IU | g | % | CFU | billion CFU (normalize to these)
- daily_value_pct: numeric only, null if not shown
- Set confidence: 0.9 if table is clearly readable, 0.6 if partially obscured, 0.3 if very unclear
- Include ALL ingredients visible, including subdoses/blends with parent names"""

def extract_supplement_facts_from_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Send image to Claude Haiku for supplement facts extraction.
    Returns structured JSON with confidence score.
    """
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(image_bytes).decode()
                    }
                },
                {"type": "text", "text": SUPPLEMENT_FACTS_PROMPT}
            ]
        }]
    )
    
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json\n").strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"confidence": 0.0, "error": "vision_parse_failed", "raw": text[:500]}
```

---

## Strategy 2: Full Page Screenshot (iHerb Primary Strategy)

When the supplement facts image URL can't be isolated, screenshot the entire product page and let Claude Vision find and extract the relevant section.

```python
from playwright.sync_api import sync_playwright
import time

def screenshot_and_extract(url: str) -> dict:
    """
    Capture full-page screenshot of a product page and extract supplement facts via vision.
    Best for iHerb where supplement facts are image-rendered in a page section.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        )
        
        page = context.new_page()
        
        # Remove webdriver flag
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2.0)  # extra delay for JS rendering
            
            # Try to find and scroll to supplement facts section first
            # iHerb: click on "Supplement Facts" tab if present
            try:
                page.click('text="Supplement Facts"', timeout=3000)
                time.sleep(1.0)
            except Exception:
                pass
            
            screenshot_bytes = page.screenshot(full_page=True)
        except Exception as e:
            browser.close()
            return {"confidence": 0.0, "error": str(e)}
        
        browser.close()
    
    return extract_supplement_facts_from_image(screenshot_bytes, "image/png")
```

---

## Strategy 3: Targeted Region Screenshot

If a specific DOM element contains the supplement facts, screenshot just that element — smaller image, cheaper Vision call, better accuracy.

```python
def screenshot_element_and_extract(url: str, selector: str) -> dict:
    """
    Screenshot a specific DOM element (e.g., the supplement facts section).
    Much cheaper than full-page screenshot.
    
    Common selectors:
    - Vitacost: 'div.supplement-facts'
    - Walgreens: 'div[data-id="supplement-facts"]'
    - Target: 'div[data-test="item-details-spec"]'
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        
        try:
            element = page.query_selector(selector)
            if element:
                screenshot_bytes = element.screenshot()
            else:
                screenshot_bytes = page.screenshot()
        except Exception:
            screenshot_bytes = page.screenshot()
        
        browser.close()
    
    return extract_supplement_facts_from_image(screenshot_bytes, "image/png")
```

---

## Strategy 4: PDF Label Extraction

For manufacturer spec sheets, certificates of analysis (CoA), or NDI spreadsheets.

```python
import pdfplumber
import requests
import tempfile
import os

def extract_from_pdf_url(pdf_url: str) -> dict:
    """Download and extract supplement facts from a PDF spec sheet."""
    r = requests.get(pdf_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(r.content)
        tmp_path = f.name
    
    try:
        return extract_from_pdf_file(tmp_path)
    finally:
        os.unlink(tmp_path)

def extract_from_pdf_file(pdf_path: str) -> dict:
    """Extract supplement facts table from a local PDF file."""
    all_text = []
    all_tables = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text.append(text)
            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines"
            })
            if tables:
                all_tables.extend(tables)
    
    full_text = "\n".join(all_text)
    
    # If clean tables found, try structured parse
    if all_tables:
        facts = _parse_supplement_facts_table(all_tables)
        if facts:
            return {"source": "pdf_table", "confidence": 0.85, "ingredients": facts}
    
    # Fall back to LLM text extraction
    return _extract_from_raw_text(full_text[:8000])

def _parse_supplement_facts_table(tables: list) -> list[dict] | None:
    """Try to parse structured supplement facts from extracted PDF tables."""
    for table in tables:
        if not table:
            continue
        # Check if this is a supplement facts table
        flat = " ".join(str(cell) for row in table for cell in row if cell).lower()
        if "supplement facts" not in flat and "serving size" not in flat:
            continue
        
        ingredients = []
        for row in table[1:]:  # skip header
            if len(row) >= 2 and row[0] and row[1]:
                ingredients.append({
                    "name": str(row[0]).strip(),
                    "amount": _parse_amount(str(row[1])),
                    "unit": _parse_unit(str(row[1]))
                })
        
        if ingredients:
            return ingredients
    
    return None

def _parse_amount(raw: str) -> float | None:
    import re
    m = re.search(r"([\d,]+\.?\d*)", raw.replace(",", ""))
    return float(m.group(1)) if m else None

def _parse_unit(raw: str) -> str | None:
    import re
    m = re.search(r"(mg|mcg|g|IU|µg|%|CFU|billion|oz|ml)", raw, re.IGNORECASE)
    return m.group(1) if m else None

def _extract_from_raw_text(text: str) -> dict:
    """Use Claude to extract supplement facts from raw PDF text."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"Extract supplement facts from this PDF text:\n\n{text}\n\n" + SUPPLEMENT_FACTS_PROMPT
        }]
    )
    try:
        return json.loads(response.content[0].text)
    except Exception:
        return {"confidence": 0.0, "error": "pdf_extract_failed"}
```

---

## Confidence Calibration

| Situation | Confidence |
|---|---|
| Clean HTML table, all fields present | 0.95 |
| DSLD API exact match | 0.90 |
| Clear supplement facts image, full table visible | 0.85–0.90 |
| Screenshot of full page (supplement facts section visible) | 0.70–0.80 |
| Partial image (some text cut off or blurry) | 0.40–0.60 |
| PDF text extraction, well-structured | 0.80 |
| PDF text, poorly structured | 0.50 |
| Vision extraction with multiple ingredients missing | 0.30–0.50 |

---

## Unit Normalization

Normalize all units at ingest time:

```python
UNIT_MAP = {
    "mcg": "mcg",
    "μg": "mcg",
    "µg": "mcg",
    "ug": "mcg",
    "mg": "mg",
    "g": "g",
    "kg": "g",          # convert: multiply by 1000
    "iu": "IU",
    "IU": "IU",
    "%": "%DV",
    "% dv": "%DV",
    "% daily value": "%DV",
    "billion": "billion CFU",
    "billion cfu": "billion CFU",
    "cfu": "CFU",
    "oz": "oz",
    "fl oz": "fl oz",
    "ml": "ml",
    "l": "ml",          # convert: multiply by 1000
}

def normalize_unit(raw_unit: str) -> str:
    return UNIT_MAP.get(raw_unit.strip().lower(), raw_unit.strip())
```

---

## Common Failure Modes

| Failure | Cause | Fix |
|---|---|---|
| Vision returns wrong ingredient amounts | Low image resolution | Download the highest-res image variant (`src` vs `srcset 2x`) |
| Ingredient list is cut off | Image is too tall for single screenshot | Use scrolling screenshot or element-targeted screenshot |
| `confidence: 0.3` and garbled text | Label is in a language other than English | Add language detection; try `translate_to_english: true` instruction |
| Proprietary blend amounts missing | Blend total shown but sub-ingredients amounts hidden | Store blend name + total, flag sub-ingredients as "in blend" |
| Claude invents amounts not in image | Hallucination | Add explicit instruction: "Only extract values you can clearly read. Do not guess." |
| PDF tables misaligned (wrong column pairing) | `pdfplumber` column detection failure | Fall back to raw text + LLM extraction |

---

## Complete Extraction Flow

```python
def extract_product_supplement_facts(sku: str, product_name: str) -> dict:
    """Full extraction flow for one finished good SKU."""
    
    # Tier 1: DSLD API (fastest, most reliable)
    dsld_result = try_dsld_first(product_name)
    if dsld_result and dsld_result["confidence"] >= 0.85:
        return dsld_result
    
    # Tier 2: Direct retailer URL construction + HTML parse
    url = construct_product_url(sku, product_name)
    if url:
        page_data = browser_agent.fetch(url)
        if page_data:
            tables = extract_supplement_facts_html(page_data["html"])
            if tables:
                return parse_html_supplement_table(tables, source=retailer, url=url)
            
            # Tier 3: Look for embedded image
            img_url = find_supplement_facts_image_url(page_data["html"])
            if img_url:
                img_bytes = download_image(img_url, session)
                if img_bytes:
                    result = extract_supplement_facts_from_image(img_bytes)
                    result["source_url"] = img_url
                    return result
            
            # Tier 4: Full page screenshot + vision
            result = extract_supplement_facts_from_image(page_data["screenshot"], "image/png")
            result["source_url"] = url
            return result
    
    # Tier 5: Google ADK discovery
    url = await discover_product_url(sku, product_name)
    if url:
        return screenshot_and_extract(url)
    
    # All tiers failed
    return {"confidence": 0.0, "error": "all_tiers_failed", "flag": "manual_review"}
```
