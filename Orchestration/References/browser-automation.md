# Browser Automation Reference

Reference guide for implementing `enrichment/sources/browser_agent.py`.

The PRD mentions "Vercel AI SDK browser tool" — this is a **TypeScript/Node.js library and is not available for Python**. The correct Python-native stack is: **Playwright** (navigation) + **BeautifulSoup4** (HTML parsing) + **pdfplumber** (PDF extraction) + optionally **browser-use** (AI-driven agent).

---

## Installation

```bash
pip install playwright beautifulsoup4 pdfplumber
playwright install chromium   # download browser binary (required once)

# Optional AI browser agent
pip install browser-use       # 79k+ GitHub stars, Python-native
```

---

## Anti-Bot Risk by Target Site

| Site | Risk | Strategy |
|---|---|---|
| iHerb | HIGH (Cloudflare + fingerprinting) | Stealth context + screenshot → vision |
| Amazon | MEDIUM-HIGH | Stealth context; try DSLD first |
| Walmart | MEDIUM (Akamai) | Stealth context + delays |
| Target | MEDIUM (Akamai) | Stealth context + delays |
| Thrive Market | MEDIUM | Standard Playwright often works |
| Vitamin Shoppe | LOW-MEDIUM | Standard Playwright |
| Walgreens | MEDIUM | Standard Playwright + delays |
| Vitacost | LOW | Standard Playwright |
| CVS | LOW-MEDIUM | Standard Playwright |
| Costco | LOW | Standard Playwright |
| PureBulk | LOW (Shopify) | Standard Playwright |
| DSLD API | NONE | Direct requests |
| PubChem | NONE | Direct requests |

---

## Stealth Configuration (Required for HIGH-risk Sites)

Use this context instead of default `new_context()` when targeting iHerb or Amazon:

```python
def stealth_context(playwright):
    """Browser context that reduces bot detection signals."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-size=1440,900",
        ]
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }
    )
    
    # Remove the webdriver property that flags automation
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        window.chrome = {runtime: {}};
    """)
    
    return browser, context

# Usage:
with sync_playwright() as p:
    browser, context = stealth_context(p)
    page = context.new_page()
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2.5)  # extra wait for JS
    screenshot = page.screenshot(full_page=True)
    browser.close()
```

**Note:** `playwright-stealth` npm plugin (often referenced) is Node.js only. The init_script approach above achieves ~80% of its effect for Python.

---

## Delay Strategy by Risk Level

```python
import time
import random

def polite_delay(risk_level: str = "medium"):
    """Add a delay appropriate to site risk level."""
    delays = {
        "none": 0,
        "low": (0.5, 1.5),
        "medium": (2.0, 3.5),
        "high": (3.0, 5.0),
    }
    if risk_level == "none":
        return
    lo, hi = delays.get(risk_level, (2.0, 3.5))
    time.sleep(random.uniform(lo, hi))

SITE_RISK = {
    "iherb.com": "high",
    "amazon.com": "high",
    "walmart.com": "medium",
    "target.com": "medium",
    "thrivemarket.com": "medium",
    "vitaminshoppe.com": "low",
    "vitacost.com": "low",
    "costco.com": "low",
    "purebulk.com": "low",
}
```

---

## Cloudflare Handling

If Playwright hits a Cloudflare challenge page (HTTP 403 or `cf-ray` header present):

1. **Retry with longer delay** (sometimes Cloudflare challenges expire)
2. **Switch to DSLD API** — if the product is in DSLD, skip scraping entirely
3. **Use Google ADK** to find a cached/mirror page with the same data
4. **Flag for manual review** — store `confidence=0.0`, `flag="bot_blocked"`

```python
def is_blocked(page) -> bool:
    """Detect Cloudflare or generic bot-block page."""
    title = page.title().lower()
    url = page.url.lower()
    return (
        "access denied" in title
        or "403 forbidden" in title
        or "cloudflare" in title
        or "cf-ray" in page.evaluate("() => document.cookie")
        or "challenge" in url
    )

def fetch_with_block_detection(page, url: str) -> dict:
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=10000)
    time.sleep(2.0)
    
    if is_blocked(page):
        return {"blocked": True, "url": url}
    
    return {
        "blocked": False,
        "html": page.content(),
        "screenshot": page.screenshot(full_page=True),
        "url": page.url
    }
```

---

## Pattern Selection

| Scenario | Recommended pattern |
|---|---|
| Static HTML pages (iHerb, PureBulk) | Playwright + BeautifulSoup4 |
| Dynamic JS-heavy pages (Walmart, Target) | browser-use OR Playwright + wait_for_load_state |
| Supplement Facts table from screenshot | Playwright screenshot → Claude vision |
| PDF label extraction (NDI spreadsheets) | pdfplumber |
| Complex multi-step navigation | browser-use |

---

## Pattern 1: Playwright + BeautifulSoup4

Best for static pages — fast and free.

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

def fetch_page(url: str, wait_for: str = "networkidle") -> dict:
    """Navigate to URL and return HTML + text."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state(wait_for)

        time.sleep(1.5)  # politeness delay
        html = page.content()
        screenshot = page.screenshot()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    return {"html": html, "screenshot": screenshot, "soup": soup}

def extract_supplement_facts_html(soup: BeautifulSoup) -> list[dict]:
    """Find and parse supplement facts table from parsed HTML."""
    for table in soup.find_all("table"):
        text = table.get_text().lower()
        if "supplement facts" in text or "serving size" in text:
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            return rows
    return []
```

---

## Pattern 2: Playwright Screenshot → Claude Vision

Best accuracy for complex or image-rendered Supplement Facts panels.

```python
import base64
import json
from playwright.sync_api import sync_playwright
from anthropic import Anthropic

def extract_via_vision(url: str) -> dict:
    """Take screenshot → send to Claude → return structured JSON."""
    # Step 1: Capture screenshot
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        screenshot_bytes = page.screenshot(full_page=True)
        browser.close()

    # Step 2: Send to Claude vision
    client = Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5",   # cheap + fast for extraction
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(screenshot_bytes).decode()
                    }
                },
                {
                    "type": "text",
                    "text": """Extract supplement facts from this image.
Return JSON:
{
  "product_name": "...",
  "serving_size": "...",
  "servings_per_container": "...",
  "ingredients": [{"name": "...", "amount": "...", "unit": "...", "daily_value_pct": "..."}],
  "other_ingredients": [...],
  "confidence": 0.0
}"""
                }
            ]
        }]
    )

    try:
        text = response.content[0].text
        # Claude sometimes wraps JSON in markdown — strip it
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return {"confidence": 0.0, "error": "parse_failed", "raw": response.content[0].text}
```

---

## Pattern 3: browser-use (AI-Driven Agent)

Best for complex workflows where navigation logic is hard to write explicitly.

```python
import asyncio
from browser_use import Agent
from anthropic import Anthropic

async def extract_supplement_facts_agent(url: str, timeout: int = 60) -> dict:
    """Use browser-use AI agent for complex page navigation."""
    agent = Agent(
        task=f"""
        1. Navigate to {url}
        2. Wait for page to load
        3. Find the Supplement Facts label/table
        4. Extract as JSON: {{product_name, serving_size, ingredients: [{{name, amount, unit}}]}}
        5. Return the JSON
        """,
        llm=Anthropic(),
        use_vision=True,
        max_actions=20
    )
    try:
        result = await asyncio.wait_for(agent.run(), timeout=timeout)
        return {"success": True, "data": result}
    except asyncio.TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

---

## Pattern 4: PDF Extraction with pdfplumber

For NDI spreadsheets and manufacturer-provided spec sheets.

```python
import pdfplumber
import pandas as pd

def extract_pdf_tables(pdf_path: str) -> list[pd.DataFrame]:
    """Extract all tables from a PDF as DataFrames."""
    frames = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in (tables or []):
                if table and table[0]:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    frames.append(df)
    return frames

def extract_supplement_facts_pdf(pdf_path: str) -> dict:
    """Extract supplement facts from a PDF label."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = page.extract_tables(
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
        )
        result = {"raw_text": text, "facts": []}
        if tables:
            for row in tables[0][1:]:   # skip header
                if len(row) >= 2:
                    result["facts"].append({"name": row[0], "amount": row[1]})
    return result
```

---

## Complete `browser_agent.py` Starter

```python
"""Browser agent for Agnes enrichment pipeline."""

import time
import base64
import json
from typing import Optional
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from anthropic import Anthropic
import pdfplumber

POLITENESS_DELAY = 1.5   # seconds between requests

class BrowserAgent:
    def __init__(self):
        self.client = Anthropic()

    def fetch(self, url: str) -> Optional[dict]:
        """Navigate to URL, return HTML + screenshot. Returns None on failure."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle")
                time.sleep(POLITENESS_DELAY)
                html = page.content()
                screenshot = page.screenshot(full_page=True)
                browser.close()
            return {"html": html, "screenshot": screenshot, "url": url}
        except Exception as e:
            return None

    def extract_tables_from_html(self, html: str) -> list[list]:
        """Parse all tables from HTML, return as list of row-lists."""
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                results.append(rows)
        return results

    def extract_structured_from_screenshot(self, screenshot_bytes: bytes, prompt: str) -> dict:
        """Pass screenshot to Claude vision for structured extraction."""
        response = self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.standard_b64encode(screenshot_bytes).decode()
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        try:
            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            return json.loads(text)
        except Exception:
            return {"confidence": 0.0, "raw": response.content[0].text}

    def extract_pdf(self, pdf_path: str) -> dict:
        """Extract tables and text from a PDF file."""
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            return {
                "text": page.extract_text() or "",
                "tables": page.extract_tables() or []
            }
```

---

## Agnes Integration Pattern

For each product page in the enrichment pipeline:

```python
agent = BrowserAgent()

# 1. Try DSLD first (no scraping needed)
dsld_result = dsld_client.search_by_product(product_name)
if dsld_result["confidence"] >= 0.85:
    store_quantity(dsld_result)
    continue

# 2. Fall back to browser + vision
page_data = agent.fetch(iherb_url)
if page_data:
    tables = agent.extract_tables_from_html(page_data["html"])
    if tables:
        # Try HTML parsing first (faster, cheaper)
        structured = parse_supplement_facts_table(tables)
    else:
        # Fall back to vision
        structured = agent.extract_structured_from_screenshot(
            page_data["screenshot"],
            "Extract supplement facts as JSON: {ingredients: [{name, amount, unit}]}"
        )
    store_quantity(structured, source="iherb", confidence=structured.get("confidence", 0.5))
else:
    store_quantity(None, source=None, confidence=0.0, flag="manual_review")
```
