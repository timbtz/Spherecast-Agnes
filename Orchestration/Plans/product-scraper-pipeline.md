# Feature: Product Scraper Pipeline (Phase 2 — Retailer BOM Enrichment)

The following plan should be complete, but validate codebase patterns and task sanity before implementing.
Pay special attention to naming of existing utils, types, and models. Import from the right files.

---

## Feature Description

Build a general-purpose, reusable product scraping pipeline (`enrichment/sources/retailer_scraper.py`)
that, given a finished-good SKU or product name, discovers the retailer product page, scrapes
supplement facts, size variants, and pricing, and stores everything in `db_enriched.sqlite`.

The pipeline fills the explicit `# TODO: implement in Phase 2 sprint` stub in
`enrichment/enrichers/quantity_enricher.py:64`. It must scale to 800–1,000 finished goods,
handle all 12 retailer profiles in the project, and be reused verbatim by the Stage 3C
research agent (supplier discovery).

**Key constraint from user**: primarily use `GOOGLE_API_KEY` (already loaded in `.env`).
Claude Haiku is used only for vision extraction (image-rendered supplement facts labels).

---

## User Story

As Agnes (the enrichment pipeline),
I want to automatically scrape any finished-good product page from any supported retailer
So that BOM component quantities, size variants, and retail prices are populated in
`db_enriched.sqlite` without manual intervention.

---

## Problem Statement

`QuantityEnricher._enrich_product` has a working DSLD tier but a stubbed-out browser tier.
149 finished goods currently in `db.sqlite` need supplement facts extracted; the system
must be built to scale to 800–1,000 products. Without retailer scraping, any BOM component
that DSLD misses (complex products, store-brand items like Equate/up&up) remains at
`confidence=0.0` and blocks downstream Phase 3 reasoning.

---

## Solution Statement

A 5-tier cascading `ProductScraper` class:

```
Tier 1 — URL construction from SKU pattern (zero network cost)
Tier 2 — Playwright fetch + extraction cascade:
  2A: __NEXT_DATA__ JSON parse (Walmart, CVS, Target — Next.js sites; zero LLM cost)
  2B: BeautifulSoup4 supplement facts HTML table (Vitacost, Walgreens, Vitamin Shoppe)
  2C: Embedded supplement facts image → Claude Haiku vision (iHerb, Amazon)
  2D: Full-page screenshot → Claude Haiku vision (universal fallback)
Tier 3 — Google ADK search → discover URL → repeat Tier 2
Tier 4 — browser-use + Gemini Flash agent (JS-heavy variant selectors; last resort)
Tier 5 — Flag for manual review (all tiers failed)
```

Google ADK search is isolated in `enrichment/sources/google_search.py` (ADK constraint:
`google_search` tool cannot mix with other tools in the same agent — requires its own
`Agent` + `InMemoryRunner`).

All size variants are extracted and stored in a new `Product_Retail_Variant` table.
All extractions are cached in `API_Response_Cache` with 7-day TTL.

---

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**:
  - `enrichment/sources/` (2 new files)
  - `enrichment/enrichers/quantity_enricher.py` (fill TODO stub)
  - `schema/enriched_schema.sql` + `enrichment/db_bootstrap.py` (new table)
  - `requirements.txt` (new deps)
**Dependencies**:
  - `google-adk>=0.5.0` ← already installed
  - `playwright>=1.44.0` ← already installed
  - `beautifulsoup4>=4.12.0` ← already installed
  - `anthropic>=0.40.0` ← already installed
  - `instructor[anthropic]>=1.7.0` ← NEW: structured + validated LLM output
  - `browser-use>=0.35.0` ← NEW: AI-driven browser fallback
  - `langchain-google-genai>=2.0.0` ← NEW: LLM adapter for browser-use + Gemini Flash

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `enrichment/sources/dsld.py` (lines 1–166)
  Why: **Primary pattern to mirror**. Cache key format, `_get_cache`/`_set_cache` methods,
  `INSERT OR REPLACE INTO API_Response_Cache`, logger naming (`agnes.{module}`),
  `ROOT = Path(__file__).parent.parent.parent` pattern, `requests.Session` with User-Agent header.

- `enrichment/enrichers/quantity_enricher.py` (lines 38–66)
  Why: **The TODO stub to fill**. `_enrich_product` calls DSLD (Tier 1) then falls
  through; your `ProductScraper().scrape(sku, product_name)` becomes Tier 2 here.
  Also shows how `_store_amounts` writes to `BOM_Component_Quantity` — don't duplicate this.

- `enrichment/parsers/sku_parser.py` (lines 1–30)
  Why: SKU format reference. `FG-{retailer}-{product_id}` is parsed by
  `QuantityEnricher._sku_to_product_name` (line 68). Your URL construction uses
  the same retailer token extracted from the FG SKU.

- `enrichment/pipeline.py` (lines 1–50)
  Why: `run_phase_2()` calls `QuantityEnricher().run()`. No changes needed here —
  the integration happens only in `quantity_enricher.py`.

- `Orchestration/References/retailer-scraping.md`
  Why: **Canonical source** for all 12 retailer URL patterns, anti-bot risk levels,
  extraction strategy per retailer, rate limits, and delay requirements.
  Must be read before writing any URL construction or Playwright config code.

- `Orchestration/References/browser-automation.md`
  Why: Complete Playwright patterns including stealth context, `is_blocked()` detection,
  Pattern 1 (BeautifulSoup), Pattern 2 (screenshot → Claude vision), Pattern 3 (browser-use).

- `Orchestration/References/google-adk-search.md`
  Why: Critical ADK constraint (google_search cannot mix with other tools), exact
  `Agent` + `InMemoryRunner` + `run_debug` pattern, `extract_grounding_urls()`,
  Agnes-specific query templates, retry decorator.

- `Orchestration/References/ingredient-image-extraction.md`
  Why: `SUPPLEMENT_FACTS_PROMPT` exact text, confidence calibration table,
  `find_supplement_facts_image_url()` with 3 strategies (alt text, src path, lazy-load attrs),
  complete `extract_product_supplement_facts()` flow.

- `schema/enriched_schema.sql` (lines 50–63 for BOM_Component_Quantity)
  Why: The table your `_store_results` writes to. Column names exactly: `BOMId`,
  `ConsumedProductId`, `Amount`, `Unit`, `PerServing`, `ServingUnit`, `Source`,
  `Source_URL`, `Confidence`.

- `enrichment/db_bootstrap.py`
  Why: `schema/enriched_schema.sql` is executed here. The new `Product_Retail_Variant`
  table DDL must be added to `enriched_schema.sql`, and `db_bootstrap.py` automatically
  applies it on next bootstrap run.

### New Files to Create

- `enrichment/sources/google_search.py`
  Google ADK search wrapper: isolated `Agent` + `InMemoryRunner`, cache in `API_Response_Cache`,
  retry on RESOURCE_EXHAUSTED, async-to-sync bridge.

- `enrichment/sources/retailer_scraper.py`
  `ProductScraper` class with 5-tier cascade, `ProductData` + `SupplementFacts` + `SizeVariant`
  dataclasses, per-retailer URL construction, Playwright stealth config, BeautifulSoup parsing,
  `__NEXT_DATA__` extraction, Claude Haiku vision via `instructor`, browser-use fallback.

### Files to Modify

- `enrichment/enrichers/quantity_enricher.py`
  Replace the `# TODO` stub (line 64) with `ProductScraper` Tier 2 call.

- `schema/enriched_schema.sql`
  Add `Product_Retail_Variant` table DDL.

- `requirements.txt`
  Add `instructor[anthropic]`, `browser-use`, `langchain-google-genai`.

### Relevant Documentation — READ BEFORE IMPLEMENTING

- [Google ADK Python Quickstart](https://google.github.io/adk-docs/get-started/python/)
  Section: "Tool use" and "Multi-agent" — shows `InMemoryRunner.run_debug()` and `output_key`.

- [instructor + Anthropic integration](https://python.useinstructor.com/integrations/anthropic/)
  Section: "Basic Usage" — `instructor.from_anthropic(Anthropic())` + `response_model=`.
  Why: Gives Pydantic-validated output from Claude vision; auto-retries on parse failure.

- [browser-use Quickstart](https://docs.browser-use.com/quickstart)
  Section: "Custom LLM" — shows `langchain_google_genai.ChatGoogleGenerativeAI` as LLM.
  Why: We use Gemini Flash for browser-use (not Claude) to stay on GOOGLE_API_KEY.

- [Walmart __NEXT_DATA__ scraping](https://scrapfly.io/blog/posts/how-to-scrape-walmartcom)
  Section: "Parsing Product Data" — exact JSON path through `props.pageProps.initialData.data.product`.

### Patterns to Follow

**Module logger naming:**
```python
logger = logging.getLogger("agnes.retailer_scraper")  # matches dsld.py pattern
```

**ROOT path pattern (from dsld.py:16):**
```python
ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
```

**Cache key format (mirror dsld.py):**
```python
# Source field: "retailer_scraper" or "google_search"
# Cache_Key: "{retailer}:{url}" for page HTML, "search:{query}" for ADK results
```

**`_get_cache` / `_set_cache` (exact copy from dsld.py:136–165):**
```python
def _get_cache(self, source: str, key: str) -> tuple[bool, dict | None]:
    conn = sqlite3.connect(self.db_path)
    row = conn.execute(
        """SELECT Response FROM API_Response_Cache
           WHERE Source = ? AND Cache_Key = ?
           AND (TTL_Days = 0 OR julianday('now') - julianday(Fetched_At) < TTL_Days)""",
        (source, key),
    ).fetchone()
    conn.close()
    if row is not None:
        return True, json.loads(row[0]) if row[0] != "null" else None
    return False, None
```

**Enrichment log pattern (from quantity_enricher.py:121–134):**
```python
conn.execute(
    """INSERT INTO Enrichment_Run_Log
       (ProductId, Phase, Step, Status, Confidence, Method, Error_Msg)
       VALUES (?, 2, ?, ?, ?, ?, ?)""",
    (product_id, step_name, status, confidence, method, error_msg),
)
```

**Dataclass pattern for structured results:**
```python
from dataclasses import dataclass, field

@dataclass
class SizeVariant:
    label: str           # "120 ct", "500 g", "1 kg"
    price_usd: float | None
    price_per_unit: float | None
    unit_type: str | None  # "tablet", "capsule", "gram"

@dataclass
class SupplementFacts:
    serving_size: str | None
    servings_per_container: int | None
    ingredients: list[dict]   # [{name, amount, unit, daily_value_pct}]
    other_ingredients: list[str]
    confidence: float

@dataclass
class ProductData:
    product_name: str | None
    brand: str | None
    retailer: str
    source_url: str
    size_variants: list[SizeVariant] = field(default_factory=list)
    supplement_facts: SupplementFacts | None = None
    certifications: list[str] = field(default_factory=list)
    extraction_method: str = "unknown"
    confidence: float = 0.0
```

**Pydantic models for `instructor` (vision extraction):**
```python
from pydantic import BaseModel, Field

class IngredientRow(BaseModel):
    name: str
    amount: float | None = None
    unit: str | None = Field(None, description="mg, mcg, g, IU, %DV, CFU")
    daily_value_pct: float | None = None

class SupplementFactsVision(BaseModel):
    serving_size: str | None = None
    servings_per_container: int | None = None
    ingredients: list[IngredientRow]
    other_ingredients: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
```

**RETAILER_DOMAINS + SITE_RISK dicts (from browser-automation.md + retailer-scraping.md):**
```python
SITE_RISK = {
    "iherb": "high",
    "amazon": "high",
    "walmart": "medium",
    "target": "medium",
    "thrive-market": "medium",
    "the-vitamin-shoppe": "low",
    "walgreens": "medium",
    "vitacost": "low",
    "cvs": "low",
    "costco": "low",
    "sams-club": "medium",
    "gnc": "low",
}

RETAILER_DELAY = {  # minimum seconds between requests
    "iherb": 3.0, "amazon": 3.0, "walmart": 2.0, "target": 2.0,
    "thrive-market": 2.0, "the-vitamin-shoppe": 1.5, "walgreens": 2.0,
    "vitacost": 1.5, "cvs": 1.5, "costco": 1.0, "sams-club": 2.0, "gnc": 1.5,
}
```

**URL construction (from retailer-scraping.md — all patterns):**
```python
def _construct_url(self, sku: str) -> str | None:
    """Map FG-{retailer}-{id} → canonical product URL."""
    parts = sku.split("-", 2)
    if len(parts) < 3 or parts[0] != "FG":
        return None
    retailer = parts[1] if parts[1] != "the" else "the-vitamin-shoppe"
    # Handle multi-word retailers (thrive-market, sams-club, the-vitamin-shoppe)
    raw = sku[len("FG-"):]
    for prefix, domain_token in RETAILER_URL_PREFIXES.items():
        if raw.startswith(prefix):
            item_id = raw[len(prefix):]
            return URL_BUILDERS[domain_token](item_id)
    return None
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Add dependencies, extend DB schema with `Product_Retail_Variant`, create dataclasses.

### Phase 2: Google ADK Search Wrapper

`enrichment/sources/google_search.py` — isolated ADK search agent with SQLite caching.
Exposes a synchronous `search_product_url(product_name, retailer) -> str | None` that
bridges `asyncio.run()` internally.

### Phase 3: Core ProductScraper

`enrichment/sources/retailer_scraper.py` — 5-tier cascade.
Starts with Tier 1 (URL construction) and Tier 2A (`__NEXT_DATA__` JSON) since those
are zero-LLM-cost and cover Walmart + CVS (28 products combined).
Then adds Tiers 2B–2D (BeautifulSoup → image vision → screenshot vision).
Then adds Tier 3 (Google ADK search fallback) and Tier 4 (browser-use last resort).

### Phase 4: Integration + Storage

Wire `ProductScraper.scrape()` into `QuantityEnricher._enrich_product` as Tier 2.
Implement `_store_size_variants()` to write `Product_Retail_Variant` rows.
`_store_amounts()` already exists in `QuantityEnricher` — call it with scraped data.

### Phase 5: Scale Validation

Test against Vitacost (6 products, clean HTML), then Walmart (18 products, `__NEXT_DATA__`),
then iHerb (12 products, vision-only). Verify caching prevents re-fetch on second run.

---

## STEP-BY-STEP TASKS

### Task 1 — UPDATE `requirements.txt`

- **ADD** three new dependencies:
  ```
  instructor[anthropic]>=1.7.0
  browser-use>=0.35.0
  langchain-google-genai>=2.0.0
  ```
- **GOTCHA**: `browser-use` requires Python 3.11+; project is on 3.12 — no issue.
- **VALIDATE**: `pip install -r requirements.txt --dry-run 2>&1 | tail -5`

---

### Task 2 — UPDATE `schema/enriched_schema.sql`

- **ADD** `Product_Retail_Variant` table DDL at the end of the Phase 2 section (after `BOM_Component_Quantity`, before the Phase 3 comment):

```sql
-- Retail size variants per finished product (all container sizes with pricing)
CREATE TABLE IF NOT EXISTS Product_Retail_Variant (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ProductId       INTEGER NOT NULL,
    RetailSizeLabel TEXT    NOT NULL,     -- "60 ct", "120 ct", "500 g", "1 kg"
    Price_USD       REAL,
    Price_Per_Unit  REAL,                 -- USD per tablet/gram/etc.
    Unit_Type       TEXT,                 -- "tablet", "capsule", "gram", "oz"
    Is_Default      INTEGER DEFAULT 0,    -- 1 if this is the page-load default variant
    Source          TEXT,                 -- "walmart", "cvs", "vitacost", etc.
    Source_URL      TEXT,
    Scraped_At      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (ProductId) REFERENCES Product(Id)
);
```

- **VALIDATE**: `sqlite3 db_enriched.sqlite ".schema Product_Retail_Variant"` (after bootstrap runs)

---

### Task 3 — UPDATE `enrichment/db_bootstrap.py`

- **READ** `enrichment/db_bootstrap.py` fully before editing.
- **VERIFY** it already runs `enriched_schema.sql` via `executescript`. If yes, no code change
  needed — the new table DDL in Task 2 applies automatically on next `--bootstrap` run.
- **IF** `db_bootstrap.py` uses explicit `CREATE TABLE` statements instead of reading the SQL file,
  mirror the DDL pattern there too.
- **VALIDATE**: `python enrichment/pipeline.py --bootstrap 2>&1 | head -20`

---

### Task 4 — CREATE `enrichment/sources/google_search.py`

Implement the Google ADK search wrapper. Mirror `dsld.py` class structure exactly.

```python
"""Google ADK web search wrapper for Agnes.

google_search MUST be in its own Agent instance — it cannot be combined with
other tools in the same agent (ADK constraint from google-adk-search.md).
"""
import asyncio
import json
import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.google_search")


class GoogleSearchClient:
    SOURCE = "google_search"
    TTL_DAYS = 7

    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self._runner = None  # lazy-init; ADK runner is expensive to create

    def search_product_url(self, product_name: str, retailer: str) -> str | None:
        """Find the canonical product URL on a specific retailer site.

        Returns the first URL matching the retailer domain, or None.
        Caches results for TTL_DAYS days.
        """
        from enrichment.sources.retailer_scraper import RETAILER_DOMAINS  # avoid circular
        domain = RETAILER_DOMAINS.get(retailer, "")
        query = f"site:{domain} {product_name}"
        key = f"product_url:{retailer}:{product_name.lower()}"

        in_cache, cached = self._get_cache(key)
        if in_cache:
            return cached.get("url") if cached else None

        result = asyncio.run(self._search(query))
        urls = self._extract_urls(result, domain)
        url = urls[0] if urls else None
        self._set_cache(key, {"url": url, "all_urls": urls})
        return url

    def search_raw(self, query: str) -> str | None:
        """Run a raw search query; return the model's text response."""
        key = f"raw:{query.lower()[:120]}"
        in_cache, cached = self._get_cache(key)
        if in_cache:
            return cached.get("text") if cached else None

        text = asyncio.run(self._search(query))
        self._set_cache(key, {"text": text})
        return text

    async def _search(self, query: str, retries: int = 3) -> str:
        from google.adk.agents import Agent
        from google.adk.models.lite_llm import LiteLlm
        from google.adk.runners import InMemoryRunner
        from google.adk.tools import google_search as google_search_tool

        # Lazy-build runner (one per instance)
        agent = Agent(
            name="agnes_searcher",
            model=LiteLlm(model="gemini/gemini-2.5-flash"),
            instruction=(
                "You are a supply chain research assistant. "
                "Search the web and return factual results with source URLs. "
                "Format: return the product URLs you find, one per line."
            ),
            tools=[google_search_tool],
        )
        runner = InMemoryRunner(agent=agent)

        for attempt in range(retries):
            try:
                events = runner.run(
                    user_id="agnes",
                    session_id="search",
                    new_message=query,
                )
                for event in events:
                    if event.is_final_response():
                        return event.content.parts[0].text
                return ""
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e) and attempt < retries - 1:
                    await asyncio.sleep(2 ** (attempt + 1))
                else:
                    logger.error(f"ADK search failed for '{query}': {e}")
                    return ""
        return ""

    def _extract_urls(self, text: str, domain: str) -> list[str]:
        """Pull URLs from ADK response text that match the target domain."""
        import re
        pattern = rf"https?://(?:www\.)?{re.escape(domain)}/\S+"
        return re.findall(pattern, text)

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                """SELECT Response FROM API_Response_Cache
                   WHERE Source = ? AND Cache_Key = ?
                   AND (TTL_Days = 0 OR julianday('now') - julianday(Fetched_At) < TTL_Days)""",
                (self.SOURCE, key),
            ).fetchone()
            conn.close()
            if row is not None:
                return True, json.loads(row[0]) if row[0] != "null" else None
        except Exception:
            pass
        return False, None

    def _set_cache(self, key: str, result: dict | None) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES (?, ?, ?, ?)""",
                (self.SOURCE, key, json.dumps(result), self.TTL_DAYS),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
```

- **GOTCHA**: `google_search` tool requires `GOOGLE_API_KEY` in env — already set per user confirmation.
- **GOTCHA**: ADK `InMemoryRunner.run()` is sync in newer ADK versions but `run_debug()` is async.
  Check which exists: `python -c "from google.adk.runners import InMemoryRunner; print(dir(InMemoryRunner))"`.
  Use whichever is available; wrap in `asyncio.run()` if async.
- **GOTCHA**: ADK model string format may differ. Try `"gemini-2.5-flash"` first; if that fails
  try `LiteLlm(model="gemini/gemini-2.5-flash")` or check ADK docs for current Gemini model naming.
- **VALIDATE**: `python -c "from enrichment.sources.google_search import GoogleSearchClient; print(GoogleSearchClient().search_raw('Nature Made Vitamin C 500mg walmart'))"`

---

### Task 5 — CREATE `enrichment/sources/retailer_scraper.py`

Implement `ProductScraper` in full. Structure:

```python
"""Retailer product page scraper for Agnes Phase 2 BOM enrichment.

5-tier cascade per product:
  Tier 1 — URL construction from SKU pattern
  Tier 2A — __NEXT_DATA__ JSON (Walmart, CVS, Target)
  Tier 2B — BeautifulSoup supplement facts HTML table
  Tier 2C — Embedded image → Claude Haiku vision
  Tier 2D — Full-page screenshot → Claude Haiku vision
  Tier 3 — Google ADK search → URL discovery → repeat Tier 2
  Tier 4 — browser-use + Gemini Flash agent
  Tier 5 — Flag manual review
"""
import base64
import json
import logging
import random
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import instructor
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.retailer_scraper")
```

**Section A — Constants (copy from retailer-scraping.md)**

```python
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

SITE_RISK = {
    "iherb": "high", "amazon": "high",
    "walmart": "medium", "target": "medium", "thrive-market": "medium",
    "sams-club": "medium", "walgreens": "medium",
    "the-vitamin-shoppe": "low", "vitacost": "low",
    "cvs": "low", "costco": "low", "gnc": "low",
}

RETAILER_DELAY = {
    "iherb": 3.0, "amazon": 3.0, "walmart": 2.0, "target": 2.0,
    "thrive-market": 2.0, "the-vitamin-shoppe": 1.5, "walgreens": 2.0,
    "vitacost": 1.5, "cvs": 1.5, "costco": 1.0, "sams-club": 2.0, "gnc": 1.5,
}

# Exact URL builder map per retailer (from retailer-scraping.md)
def _build_url(retailer: str, item_id: str) -> str | None:
    builders = {
        "walmart":          lambda x: f"https://www.walmart.com/ip/{x}",
        "cvs":              lambda x: f"https://www.cvs.com/shop/product-detail/{x}",
        "target":           lambda x: f"https://www.target.com/p/-/{x}",
        "iherb":            lambda x: f"https://www.iherb.com/pr/product/{x}",
        "the-vitamin-shoppe": lambda x: f"https://www.vitaminshoppe.com/p/{x}",
        "walgreens":        lambda x: f"https://www.walgreens.com/store/c/productDetail.jsp?ID={x}",
        "vitacost":         lambda x: f"https://www.vitacost.com/vitacost-{x}",
        "costco":           lambda x: f"https://www.costco.com/.product.{x}.html",
        "sams-club":        lambda x: f"https://www.samsclub.com/p/{x}",
        "thrive-market":    lambda x: f"https://thrivemarket.com/p/{x}",
    }
    fn = builders.get(retailer)
    return fn(item_id) if fn else None
```

**Section B — Dataclasses + Pydantic models**

```python
@dataclass
class SizeVariant:
    label: str
    price_usd: float | None = None
    price_per_unit: float | None = None
    unit_type: str | None = None
    is_default: bool = False

@dataclass
class ProductData:
    product_name: str | None
    brand: str | None
    retailer: str
    source_url: str
    size_variants: list[SizeVariant] = field(default_factory=list)
    supplement_facts: dict | None = None   # keys: serving_size, servings_per_container, ingredients
    certifications: list[str] = field(default_factory=list)
    extraction_method: str = "unknown"
    confidence: float = 0.0

class IngredientRow(BaseModel):
    name: str
    amount: float | None = None
    unit: str | None = Field(None, description="mg, mcg, g, IU, %DV, CFU, billion CFU")
    daily_value_pct: float | None = None

class SupplementFactsVision(BaseModel):
    serving_size: str | None = None
    servings_per_container: int | None = None
    ingredients: list[IngredientRow]
    other_ingredients: list[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

**Section C — `ProductScraper` class**

```python
class ProductScraper:
    SOURCE = "retailer_scraper"
    CACHE_TTL = 7

    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self._anthropic = instructor.from_anthropic(Anthropic())

    # ── Public API ──────────────────────────────────────────────────────────────

    def scrape(self, sku: str, product_name: str) -> ProductData | None:
        """Full 5-tier cascade for one finished-good SKU."""
        retailer = self._parse_retailer(sku)
        if not retailer:
            return None

        # Tier 1 — URL from SKU
        url = self._construct_url(sku, retailer)

        # Tier 2 — Playwright fetch + extraction
        if url:
            data = self._scrape_url(url, retailer, product_name)
            if data and data.confidence >= 0.5:
                return data

        # Tier 3 — ADK search → URL discovery
        from enrichment.sources.google_search import GoogleSearchClient
        search_url = GoogleSearchClient(self.db_path).search_product_url(product_name, retailer)
        if search_url and search_url != url:
            data = self._scrape_url(search_url, retailer, product_name)
            if data and data.confidence >= 0.4:
                return data

        # Tier 4 — browser-use agent
        target_url = search_url or url
        if target_url:
            return self._scrape_browser_use(target_url, retailer, product_name)

        return None  # Tier 5: caller flags for manual review

    # ── Tier 2: Playwright scrape ───────────────────────────────────────────────

    def _scrape_url(self, url: str, retailer: str, product_name: str) -> ProductData | None:
        """Fetch page + run extraction cascade."""
        cache_key = f"page:{url}"
        in_cache, cached = self._get_cache(cache_key)

        if in_cache and cached:
            html = cached.get("html", "")
            screenshot = base64.b64decode(cached["screenshot"]) if cached.get("screenshot") else None
        else:
            page_data = self._playwright_fetch(url, retailer)
            if not page_data:
                return None
            html = page_data["html"]
            screenshot = page_data.get("screenshot")
            self._set_cache(cache_key, {
                "html": html,
                "screenshot": base64.b64encode(screenshot).decode() if screenshot else None,
                "url": page_data.get("final_url", url),
            })

        soup = BeautifulSoup(html, "lxml")

        # 2A — __NEXT_DATA__ JSON (Walmart, CVS, Target)
        if retailer in ("walmart", "cvs", "target"):
            result = self._try_next_data(html, retailer)
            if result and result.supplement_facts:
                result.source_url = url
                return result

        # 2B — HTML supplement facts table
        result = self._try_html_table(soup, retailer, url)
        if result and result.supplement_facts and result.confidence >= 0.7:
            return result

        # 2C — Embedded image URL in page
        img_url = self._find_supplement_image_url(html)
        if img_url:
            img_bytes = self._download_image(img_url)
            if img_bytes:
                facts = self._extract_vision(img_bytes, "image/jpeg")
                if facts and facts.confidence >= 0.5:
                    return ProductData(
                        product_name=self._extract_product_name(soup),
                        brand=self._extract_brand(soup),
                        retailer=retailer,
                        source_url=url,
                        supplement_facts=facts.model_dump(),
                        size_variants=self._extract_size_variants(soup),
                        certifications=self._extract_certifications(soup),
                        extraction_method="image_vision",
                        confidence=facts.confidence,
                    )

        # 2D — Full-page screenshot
        if screenshot:
            facts = self._extract_vision(screenshot, "image/png")
            if facts:
                return ProductData(
                    product_name=self._extract_product_name(soup),
                    brand=self._extract_brand(soup),
                    retailer=retailer,
                    source_url=url,
                    supplement_facts=facts.model_dump(),
                    size_variants=self._extract_size_variants(soup),
                    certifications=self._extract_certifications(soup),
                    extraction_method="screenshot_vision",
                    confidence=facts.confidence * 0.85,  # penalty for full-page
                )

        return None

    # ── Tier 2A: __NEXT_DATA__ JSON extraction ──────────────────────────────────

    def _try_next_data(self, html: str, retailer: str) -> ProductData | None:
        """Extract product data from Next.js __NEXT_DATA__ JSON blob."""
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if not tag or not tag.string:
            return None
        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            return None

        if retailer == "walmart":
            return self._parse_walmart_next_data(data)
        elif retailer == "cvs":
            return self._parse_cvs_next_data(data)
        elif retailer == "target":
            return self._parse_target_next_data(data)
        return None

    def _parse_walmart_next_data(self, data: dict) -> ProductData | None:
        """Parse Walmart's __NEXT_DATA__ structure.

        JSON path: props.pageProps.initialData.data.product
        Variants: product.variantList[].variants[]
        Supplement facts: product.idmlContent.modules (look for "ingredients" key)
        """
        try:
            product = (
                data["props"]["pageProps"]["initialData"]["data"]["product"]
            )
        except (KeyError, TypeError):
            return None

        name = product.get("name")
        brand = product.get("brand", {}).get("name") if isinstance(product.get("brand"), dict) else product.get("brand")

        # Size variants
        variants: list[SizeVariant] = []
        for v in product.get("variantList", []):
            label = v.get("name", "")
            price = v.get("priceInfo", {}).get("currentPrice", {}).get("price")
            if label:
                variants.append(SizeVariant(label=label, price_usd=price))
        # Default price if no variants
        if not variants:
            price_info = product.get("priceInfo", {})
            price = price_info.get("currentPrice", {}).get("price")
            if price:
                variants.append(SizeVariant(label="default", price_usd=price, is_default=True))

        # Supplement facts from idmlContent (structure varies by product)
        facts = self._parse_walmart_supplement_facts(product)

        return ProductData(
            product_name=name,
            brand=brand,
            retailer="walmart",
            source_url="",
            size_variants=variants,
            supplement_facts=facts,
            extraction_method="next_data_json",
            confidence=0.92 if facts else 0.5,
        )

    def _parse_walmart_supplement_facts(self, product: dict) -> dict | None:
        """Try to find supplement facts in Walmart's IDML content modules."""
        # Walmart stores spec content in idmlContent.modules — look for ingredient tables
        idml = product.get("idmlContent") or {}
        modules = idml.get("modules", {})
        ingredients_raw = ""
        for key, module in modules.items():
            if "ingredient" in key.lower() or "supplement" in key.lower():
                ingredients_raw = str(module)
                break
        if not ingredients_raw:
            return None
        # Return as raw text for now — vision extraction handles structured parsing
        return {"raw_text": ingredients_raw[:2000], "source": "next_data_walmart"}

    def _parse_cvs_next_data(self, data: dict) -> ProductData | None:
        """Parse CVS's __NEXT_DATA__ structure. Path varies — inspect at runtime."""
        # CVS path: props.pageProps.productDetails or props.pageProps.product
        try:
            page_props = data["props"]["pageProps"]
            product = page_props.get("productDetails") or page_props.get("product") or {}
        except (KeyError, TypeError):
            return None
        if not product:
            return None

        name = product.get("name") or product.get("displayName")
        brand = product.get("brandName") or product.get("brand")
        facts_text = (
            product.get("supplementFacts")
            or product.get("ingredients")
            or product.get("nutritionFacts")
        )

        return ProductData(
            product_name=name,
            brand=brand,
            retailer="cvs",
            source_url="",
            supplement_facts={"raw_text": str(facts_text)[:2000]} if facts_text else None,
            extraction_method="next_data_json",
            confidence=0.88 if facts_text else 0.4,
        )

    def _parse_target_next_data(self, data: dict) -> ProductData | None:
        """Parse Target's __NEXT_DATA__ — try common paths."""
        try:
            # Target path varies; inspect __NEXT_DATA__ for a sample product first
            product = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("__REDUX_STATE__", {})
                    .get("productDetail", {})
                    .get("item", {})
            )
        except Exception:
            return None
        if not product:
            return None
        return ProductData(
            product_name=product.get("general_description") or product.get("title"),
            brand=None,
            retailer="target",
            source_url="",
            extraction_method="next_data_json",
            confidence=0.5,
        )

    # ── Tier 2B: HTML Table parsing ─────────────────────────────────────────────

    def _try_html_table(self, soup: BeautifulSoup, retailer: str, url: str) -> ProductData | None:
        """Find and parse supplement facts table from HTML DOM."""
        # Strategy 1: find any <table> containing "supplement facts" text
        for table in soup.find_all("table"):
            text = table.get_text().lower()
            if "supplement facts" in text or "serving size" in text:
                rows = []
                for tr in table.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)
                if rows:
                    facts = self._parse_supplement_table_rows(rows)
                    if facts:
                        return ProductData(
                            product_name=self._extract_product_name(soup),
                            brand=self._extract_brand(soup),
                            retailer=retailer,
                            source_url=url,
                            supplement_facts=facts,
                            size_variants=self._extract_size_variants(soup),
                            certifications=self._extract_certifications(soup),
                            extraction_method="html_table",
                            confidence=0.90,
                        )

        # Strategy 2: retailer-specific selectors (from retailer-scraping.md)
        selectors = {
            "vitacost": "div.supplement-facts",
            "walgreens": 'div[data-id="supplement-facts"]',
            "target": 'div[data-test="item-details-spec"]',
            "walmart": 'div[data-automation-id="product-overview"]',
        }
        sel = selectors.get(retailer)
        if sel:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text and len(text) > 50:
                    return ProductData(
                        product_name=self._extract_product_name(soup),
                        brand=self._extract_brand(soup),
                        retailer=retailer,
                        source_url=url,
                        supplement_facts={"raw_text": text[:3000]},
                        size_variants=self._extract_size_variants(soup),
                        extraction_method="html_selector",
                        confidence=0.70,
                    )
        return None

    def _parse_supplement_table_rows(self, rows: list[list[str]]) -> dict | None:
        """Convert raw table rows into structured supplement facts dict."""
        ingredients = []
        serving_size = None
        servings = None

        for row in rows:
            if len(row) < 2:
                continue
            name = row[0].strip()
            amount_raw = row[1].strip() if len(row) > 1 else ""
            if "serving size" in name.lower():
                serving_size = amount_raw
            elif "servings per" in name.lower():
                try:
                    servings = int("".join(filter(str.isdigit, amount_raw)))
                except ValueError:
                    pass
            elif name and amount_raw:
                amount, unit = self._split_amount_unit(amount_raw)
                ingredients.append({"name": name, "amount": amount, "unit": unit,
                                     "daily_value_pct": row[2] if len(row) > 2 else None})

        if not ingredients:
            return None
        return {"serving_size": serving_size, "servings_per_container": servings,
                "ingredients": ingredients}

    def _split_amount_unit(self, raw: str) -> tuple[float | None, str | None]:
        import re
        m = re.match(r"([\d,.]+)\s*([a-zA-Z%]+)?", raw.strip())
        if not m:
            return None, None
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            amount = None
        unit = m.group(2) or None
        return amount, unit

    # ── Tier 2C/2D: Claude Haiku vision via instructor ──────────────────────────

    VISION_PROMPT = """Extract all data from this Supplement Facts / Nutrition Facts label.
Return structured data only.
Rules:
- amount: numeric value only (no units in this field)
- unit: mg | mcg | g | IU | %DV | CFU | billion CFU (normalize to these)
- daily_value_pct: numeric only, null if not shown
- confidence: 0.9 if clearly readable, 0.6 if partially obscured, 0.3 if very unclear
- Include ALL ingredients, including sub-ingredients in proprietary blends
- Do NOT guess amounts not visible in the image"""

    def _extract_vision(self, image_bytes: bytes, media_type: str) -> SupplementFactsVision | None:
        """Send image to Claude Haiku via instructor for validated structured extraction."""
        try:
            result = self._anthropic.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                response_model=SupplementFactsVision,
                max_retries=2,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(image_bytes).decode(),
                            },
                        },
                        {"type": "text", "text": self.VISION_PROMPT},
                    ],
                }],
            )
            return result
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            return None

    # ── Tier 4: browser-use fallback ────────────────────────────────────────────

    def _scrape_browser_use(self, url: str, retailer: str, product_name: str) -> ProductData | None:
        """AI-driven browser agent — last resort for JS-heavy variant selectors.

        Uses Gemini Flash (langchain-google-genai) so GOOGLE_API_KEY is sufficient.
        """
        import asyncio
        try:
            return asyncio.run(self._async_browser_use(url, retailer, product_name))
        except Exception as e:
            logger.error(f"browser-use failed for {url}: {e}")
            return None

    async def _async_browser_use(self, url: str, retailer: str, product_name: str) -> ProductData | None:
        try:
            from browser_use import Agent
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            logger.warning("browser-use or langchain-google-genai not installed — Tier 4 skipped")
            return None

        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0)
        agent = Agent(
            task=f"""Navigate to {url}.
1. Wait for page to load fully.
2. Extract: product name, brand, ALL size/count variants with prices.
3. Find the Supplement Facts table. Extract: serving size, servings per container,
   and all ingredients with their amounts and units.
4. Return as JSON: {{
     "product_name": "...",
     "brand": "...",
     "size_variants": [{{"label": "...", "price_usd": 0.0}}],
     "supplement_facts": {{
       "serving_size": "...",
       "servings_per_container": 0,
       "ingredients": [{{"name": "...", "amount": 0.0, "unit": "..."}}]
     }}
   }}""",
            llm=llm,
            max_actions=25,
        )
        try:
            import asyncio
            result = await asyncio.wait_for(agent.run(), timeout=90)
            text = result.final_result() if hasattr(result, "final_result") else str(result)
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            parsed = json.loads(text)
            return ProductData(
                product_name=parsed.get("product_name"),
                brand=parsed.get("brand"),
                retailer=retailer,
                source_url=url,
                size_variants=[
                    SizeVariant(label=v.get("label", ""), price_usd=v.get("price_usd"))
                    for v in parsed.get("size_variants", [])
                ],
                supplement_facts=parsed.get("supplement_facts"),
                extraction_method="browser_use",
                confidence=0.75,
            )
        except Exception as e:
            logger.error(f"browser-use agent error: {e}")
            return None

    # ── Playwright page fetch ────────────────────────────────────────────────────

    def _playwright_fetch(self, url: str, retailer: str) -> dict | None:
        """Navigate to URL; return {html, screenshot, final_url} or None."""
        risk = SITE_RISK.get(retailer, "medium")
        delay = RETAILER_DELAY.get(retailer, 2.0)

        try:
            with sync_playwright() as p:
                launch_args = [
                    "--no-sandbox", "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage", "--window-size=1440,900",
                ]
                browser = p.chromium.launch(headless=True, args=launch_args)

                ctx_kwargs = dict(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 900},
                    locale="en-US",
                    timezone_id="America/Chicago",
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br",
                    },
                )
                context = browser.new_context(**ctx_kwargs)
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});"
                    "window.chrome = {runtime: {}};"
                )

                page = context.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass  # continue even if networkidle times out

                time.sleep(delay + random.uniform(0, 1.0))

                # Bot detection
                title = page.title().lower()
                if any(x in title for x in ["access denied", "403", "cloudflare", "challenge"]):
                    logger.warning(f"Bot-blocked at {url}")
                    browser.close()
                    return None

                html = page.content()
                screenshot = page.screenshot(full_page=True)
                final_url = page.url
                browser.close()

            return {"html": html, "screenshot": screenshot, "final_url": final_url}
        except Exception as e:
            logger.error(f"Playwright fetch failed for {url}: {e}")
            return None

    # ── Helper extraction methods ────────────────────────────────────────────────

    def _find_supplement_image_url(self, html: str) -> str | None:
        """Find supplement facts image URL in page HTML (from ingredient-image-extraction.md)."""
        soup = BeautifulSoup(html, "lxml")
        # Strategy A: alt text
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            if any(kw in alt for kw in ["supplement facts", "nutrition facts", "drug facts"]):
                return img.get("src") or img.get("data-src")
        # Strategy B: src path
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if any(kw in src.lower() for kw in ["supplement", "label", "nutrition", "facts"]):
                return src
        return None

    def _download_image(self, url: str) -> bytes | None:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.content
        except Exception:
            return None

    def _extract_product_name(self, soup: BeautifulSoup) -> str | None:
        for sel in ["h1", 'meta[property="og:title"]', 'title']:
            el = soup.select_one(sel)
            if el:
                return (el.get("content") or el.get_text()).strip()[:200]
        return None

    def _extract_brand(self, soup: BeautifulSoup) -> str | None:
        for sel in ['[itemprop="brand"]', 'meta[property="product:brand"]', ".brand-name"]:
            el = soup.select_one(sel)
            if el:
                return (el.get("content") or el.get_text()).strip()[:100]
        return None

    def _extract_size_variants(self, soup: BeautifulSoup) -> list[SizeVariant]:
        """Extract all size/count options from select dropdowns or radio buttons."""
        import re
        variants = []
        for option in soup.find_all("option"):
            text = option.get_text(strip=True)
            if any(unit in text.lower() for unit in ["ct", "mg", "g", "kg", "lb", "oz", "ml", "count"]):
                price = None
                # Try to find price in adjacent element
                parent = option.parent
                if parent:
                    price_text = parent.get_text()
                    m = re.search(r"\$(\d+\.?\d*)", price_text)
                    if m:
                        price = float(m.group(1))
                variants.append(SizeVariant(label=text, price_usd=price))
        return variants

    def _extract_certifications(self, soup: BeautifulSoup) -> list[str]:
        certs = []
        text = soup.get_text().lower()
        for cert in ["nsf certified", "usp verified", "informed sport", "bscg", "kosher",
                     "gluten free", "non-gmo", "vegan", "organic"]:
            if cert in text:
                certs.append(cert.title())
        return certs

    # ── SKU parsing ──────────────────────────────────────────────────────────────

    def _parse_retailer(self, sku: str) -> str | None:
        """Extract retailer token from FG-{retailer}-{id} SKU."""
        if not sku.startswith("FG-"):
            return None
        # Handle multi-word retailers: thrive-market, sams-club, the-vitamin-shoppe
        for retailer in RETAILER_DOMAINS:
            prefix = f"FG-{retailer}-"
            if sku.startswith(prefix):
                return retailer
        # Fallback: second token
        parts = sku.split("-", 2)
        return parts[1] if len(parts) >= 2 else None

    def _construct_url(self, sku: str, retailer: str) -> str | None:
        """Build product URL from SKU using retailer-scraping.md patterns."""
        prefix = f"FG-{retailer}-"
        if not sku.startswith(prefix):
            return None
        item_id = sku[len(prefix):]
        return _build_url(retailer, item_id)

    # ── Cache (mirrors dsld.py exactly) ─────────────────────────────────────────

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                """SELECT Response FROM API_Response_Cache
                   WHERE Source = ? AND Cache_Key = ?
                   AND (TTL_Days = 0 OR julianday('now') - julianday(Fetched_At) < TTL_Days)""",
                (self.SOURCE, key),
            ).fetchone()
            conn.close()
            if row is not None:
                return True, json.loads(row[0]) if row[0] != "null" else None
        except Exception:
            pass
        return False, None

    def _set_cache(self, key: str, result: dict | None) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES (?, ?, ?, ?)""",
                (self.SOURCE, key, json.dumps(result), self.CACHE_TTL),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
```

- **GOTCHA**: `instructor.from_anthropic()` wraps the sync Anthropic client. Do NOT use `async` here.
- **GOTCHA**: `browser-use` `agent.run()` is async — always call via `asyncio.run()` from sync context.
- **GOTCHA**: Playwright `sync_playwright` is **not** thread-safe. Each `scrape()` call opens a new browser. This is intentional for simplicity; don't share browser instances across calls.
- **GOTCHA**: `__NEXT_DATA__` JSON structure varies by product type on the same retailer. Log the raw structure for the first failed parse: `logger.debug(f"NEXT_DATA keys: {list(data.get('props',{}).get('pageProps',{}).keys())}")` to discover the actual path.
- **VALIDATE**: `python -c "from enrichment.sources.retailer_scraper import ProductScraper; print('import ok')"`

---

### Task 6 — UPDATE `enrichment/enrichers/quantity_enricher.py`

Replace the `# TODO` stub at line 64 with the Tier 2 call. Keep everything else identical.

Find this block (lines 62–66):
```python
        # Tier 2: Retailer browser scraping — TODO: implement in Phase 2 sprint
        logger.debug(f"DSLD miss for product_id={product_id} '{product_name}' — browser agent needed")
        self._log_skip(product_id, "DSLD miss — browser scraping not yet implemented")
```

Replace with:
```python
        # Tier 2: Retailer browser scraping
        from enrichment.sources.retailer_scraper import ProductScraper
        scraper = ProductScraper(self.db_path)
        product_data = scraper.scrape(sku, product_name)

        if product_data and product_data.supplement_facts:
            facts = product_data.supplement_facts
            ingredients = facts.get("ingredients", [])
            if ingredients:
                amounts = [
                    {
                        "ingredient_name": ing.get("name", ""),
                        "amount": ing.get("amount"),
                        "unit": ing.get("unit"),
                        "per_serving": facts.get("servings_per_container"),
                        "serving_unit": facts.get("serving_size"),
                        "source": product_data.retailer,
                        "confidence": product_data.confidence,
                    }
                    for ing in ingredients if ing.get("name")
                ]
                self._store_amounts(product_id, amounts)
                self._store_size_variants(product_id, product_data)
                self._log_skip(
                    product_id,
                    f"browser_scrape:{product_data.extraction_method}:conf={product_data.confidence:.2f}",
                )
                return

        self._log_skip(product_id, "all_tiers_failed — flagged for manual review")
```

Also **ADD** `_store_size_variants` method to `QuantityEnricher` (after `_store_amounts`):
```python
def _store_size_variants(self, product_id: int, product_data) -> None:
    """Store all scraped size variants in Product_Retail_Variant."""
    if not product_data.size_variants:
        return
    conn = sqlite3.connect(self.db_path)
    for v in product_data.size_variants:
        conn.execute(
            """INSERT OR REPLACE INTO Product_Retail_Variant
               (ProductId, RetailSizeLabel, Price_USD, Source, Source_URL, Is_Default)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                product_id, v.label, v.price_usd,
                product_data.retailer, product_data.source_url,
                1 if v.is_default else 0,
            ),
        )
    conn.commit()
    conn.close()
```

- **VALIDATE**: `python enrichment/pipeline.py --phase 2 2>&1 | head -50`

---

### Task 7 — Smoke Test: Vitacost (easiest retailer, clean HTML)

Run a one-off scrape against a known Vitacost SKU to validate the full pipeline before bulk run.

```python
# test_scrape_vitacost.py (run manually, do not commit)
from enrichment.sources.retailer_scraper import ProductScraper
scraper = ProductScraper()

# FG-vitacost-vitacost-vitamin-d3-as-cholecalciferol-25-mcg-1000-iu-300-capsules
result = scraper.scrape(
    sku="FG-vitacost-vitacost-vitamin-d3-as-cholecalciferol-25-mcg-1000-iu-300-capsules",
    product_name="vitacost vitamin d3 cholecalciferol 25 mcg 1000 iu 300 capsules",
)
print(result)
assert result is not None, "Tier 2 failed — check Playwright + BeautifulSoup"
assert result.supplement_facts is not None, "No supplement facts found"
assert len(result.supplement_facts.get("ingredients", [])) > 0
print("✓ Vitacost smoke test passed")
```

- **VALIDATE**: `python test_scrape_vitacost.py`

---

### Task 8 — Smoke Test: Walmart __NEXT_DATA__

```python
# test_scrape_walmart.py (manual, do not commit)
from enrichment.sources.retailer_scraper import ProductScraper
scraper = ProductScraper()

# FG-walmart-8053802024
result = scraper.scrape(
    sku="FG-walmart-8053802024",
    product_name="equate vitamin c",
)
print(result)
assert result is not None
assert result.extraction_method in ("next_data_json", "html_table", "screenshot_vision")
print(f"✓ Walmart smoke test passed via {result.extraction_method}")
print(f"  Size variants: {result.size_variants}")
```

If `extraction_method` is NOT `next_data_json`, log the raw `__NEXT_DATA__` key structure
and update `_parse_walmart_next_data` accordingly:
```python
# Debug path (add temporarily):
import json
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
# ... fetch page, then:
tag = soup.find("script", {"id": "__NEXT_DATA__"})
data = json.loads(tag.string)
print(list(data.get("props", {}).get("pageProps", {}).keys()))
```

- **VALIDATE**: `python test_scrape_walmart.py`

---

### Task 9 — Smoke Test: Google ADK Search

```python
# test_google_search.py (manual)
from enrichment.sources.google_search import GoogleSearchClient
client = GoogleSearchClient()
url = client.search_product_url("Nature Made Vitamin C 500mg 100 count", "walmart")
print(f"Found URL: {url}")
assert url is not None and "walmart.com" in url
print("✓ ADK search smoke test passed")
```

- **GOTCHA**: If `RESOURCE_EXHAUSTED`, the free tier limit (100 searches/day) may be hit.
  The retry decorator handles transient exhaustion. Cache ensures each query is only executed once.
- **VALIDATE**: `python test_google_search.py`

---

### Task 10 — Run Full Phase 2

```bash
python enrichment/pipeline.py --phase 2 2>&1 | tee /tmp/phase2_run.log
```

Check enrichment log for success rates:
```bash
sqlite3 db_enriched.sqlite "
SELECT Method, Status, COUNT(*) as n
FROM Enrichment_Run_Log
WHERE Phase = 2
GROUP BY Method, Status
ORDER BY n DESC;"
```

Check BOM quantity coverage:
```bash
sqlite3 db_enriched.sqlite "
SELECT COUNT(*) as enriched FROM BOM_Component_Quantity WHERE Confidence > 0.5;"
```

Check size variants:
```bash
sqlite3 db_enriched.sqlite "
SELECT Source, COUNT(*) FROM Product_Retail_Variant GROUP BY Source;"
```

- **VALIDATE**: Enriched count > 80% of total BOM components attempted.

---

## TESTING STRATEGY

### Unit Tests

No formal test suite currently exists in the project. Write quick smoke scripts (Tasks 7–9) and validate manually. If pytest is added later:

- Test `_construct_url` for all 12 retailers with sample SKUs
- Test `_parse_supplement_table_rows` with known table fixtures
- Test `_split_amount_unit` edge cases: "500mg", "1,000 IU", "25 mcg", "50%"
- Test `_try_next_data` with a saved `__NEXT_DATA__` JSON fixture for Walmart

### Integration Tests

- Run `scrape()` against one product from each retailer tier (Vitacost, Walmart, iHerb)
- Verify `BOM_Component_Quantity` rows are created with `Confidence > 0.5`
- Verify `Product_Retail_Variant` rows are created for multi-size products
- Verify second run uses cache (no Playwright calls, instant return)

### Edge Cases

| Scenario | Expected behavior |
|---|---|
| SKU with no matching retailer | `_parse_retailer` returns None → log skip |
| `__NEXT_DATA__` path changed by retailer | Log key structure, fall through to Tier 2B |
| Cloudflare block page returned | `is_blocked()` → log warning → Tier 3 |
| Vision extraction returns 0 ingredients | `confidence=0.3` → fall through to next tier |
| All tiers fail | `_log_skip(..., "all_tiers_failed")`, return None |
| Second run on same SKU | Cache hit → instant return, no Playwright |
| `GOOGLE_API_KEY` missing | `GoogleSearchClient.search_product_url` returns None → skip Tier 3, log warning |
| `browser-use` not installed | `ImportError` caught → log warning → return None from Tier 4 |

---

## VALIDATION COMMANDS

### Level 1: Import Check
```bash
python -c "from enrichment.sources.retailer_scraper import ProductScraper; print('ok')"
python -c "from enrichment.sources.google_search import GoogleSearchClient; print('ok')"
python -c "import instructor; print('instructor ok')"
```

### Level 2: Single-product smoke test
```bash
python test_scrape_vitacost.py
python test_scrape_walmart.py
python test_google_search.py
```

### Level 3: Phase 2 full run
```bash
python enrichment/pipeline.py --phase 2 2>&1 | tail -30
```

### Level 4: DB validation queries
```bash
sqlite3 db_enriched.sqlite "SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Confidence > 0.5;"
sqlite3 db_enriched.sqlite "SELECT COUNT(*) FROM Product_Retail_Variant;"
sqlite3 db_enriched.sqlite "SELECT Status, COUNT(*) FROM Enrichment_Run_Log WHERE Phase=2 GROUP BY Status;"
```

### Level 5: Cache validation (idempotency)
```bash
# Run Phase 2 twice — second run should be near-instant
time python enrichment/pipeline.py --phase 2 2>&1 | grep "complete"
time python enrichment/pipeline.py --phase 2 2>&1 | grep "complete"
# Second run should be 5–10× faster due to cache hits
```

---

## ACCEPTANCE CRITERIA

- [ ] `ProductScraper.scrape()` returns a populated `ProductData` for ≥1 Vitacost product
- [ ] `ProductScraper.scrape()` returns Walmart data via `__NEXT_DATA__` for ≥1 Walmart SKU
- [ ] All size variants found on page are stored in `Product_Retail_Variant`
- [ ] `BOM_Component_Quantity` rows are created with `Confidence > 0.5` for scraped products
- [ ] Cache prevents re-scraping on a second Phase 2 run (verify via timing or log)
- [ ] `GoogleSearchClient` returns a valid URL for a product name + retailer query
- [ ] browser-use Tier 4 degrades gracefully if library not installed (ImportError caught)
- [ ] All `Enrichment_Run_Log` rows have non-null `Method` for successful scrapes
- [ ] Phase 2 full run completes without uncaught exceptions
- [ ] BOM quantity enrichment rate ≥ 60% of all finished goods (up from ~0% before browser scraping)

---

## COMPLETION CHECKLIST

- [ ] `requirements.txt` updated with instructor, browser-use, langchain-google-genai
- [ ] `schema/enriched_schema.sql` contains `Product_Retail_Variant` DDL
- [ ] `db_bootstrap.py` verified to apply the new table automatically
- [ ] `enrichment/sources/google_search.py` created and import-tested
- [ ] `enrichment/sources/retailer_scraper.py` created and import-tested
- [ ] `quantity_enricher.py` TODO stub replaced with ProductScraper call
- [ ] `_store_size_variants` added to QuantityEnricher
- [ ] Vitacost smoke test passes
- [ ] Walmart smoke test passes (verify __NEXT_DATA__ path at runtime)
- [ ] Google ADK search smoke test passes
- [ ] Phase 2 full run completes, DB has enriched data
- [ ] Second Phase 2 run is cache-hit fast (idempotency verified)

---

## NOTES

### ADK `run()` vs `run_debug()` — Check at Runtime

The ADK API evolved between 0.4 and 0.6. The method name for running a query may be
`runner.run()` (sync, returns iterable of events) or `runner.run_debug()` (async, returns
response object directly). Check which exists:
```python
python -c "from google.adk.runners import InMemoryRunner; print([m for m in dir(InMemoryRunner) if 'run' in m])"
```
Adjust `google_search.py` accordingly. The reference in `google-adk-search.md` uses `run_debug`.

### Walmart __NEXT_DATA__ Path Stability

The JSON path `props.pageProps.initialData.data.product` is based on Walmart's Next.js version
as of early 2026. It may change. If it fails: log `list(data["props"]["pageProps"].keys())`
to find the new path. The fallback to Tier 2B (HTML) will cover this automatically.

### Scale Design (800–1,000 products)

The current `QuantityEnricher.run()` is synchronous and sequential. For 800 products at ~3–5
seconds per page, full enrichment takes ~40–70 minutes. This is acceptable for a nightly
batch job. If faster turnaround is needed, wrap `_enrich_product` in `asyncio.gather` with
a `Semaphore(concurrency=3)` and switch to `async_playwright`. This is a future optimization —
do NOT implement in this sprint unless the sequential run proves too slow.

### Reuse for Stage 3C (Supplier Discovery)

`ProductScraper.scrape()` accepts any URL, not just retail products. For supplier discovery
in Stage 3C, the `GoogleSearchClient.search_raw()` method provides free-form web search.
The browser-use Tier 4 already supports arbitrary URLs. Stage 3C can call:
```python
url = google_client.search_raw(f"{supplier_name} {ingredient_name} bulk supplier price MOQ")
# Extract URL from text, then:
data = scraper._scrape_url(url, retailer="supplier", product_name=ingredient_name)
```

### No Paid Services

Per `meta-workflow.md`: no Apify, ChemAnalyst, or paid proxy. The stealth Playwright
approach (init_script + realistic headers) handles Walmart (MEDIUM) and CVS (LOW-MEDIUM)
at MVP scale. iHerb (HIGH risk) will have higher failure rates — that's expected; DSLD
covers most iHerb supplements anyway.
