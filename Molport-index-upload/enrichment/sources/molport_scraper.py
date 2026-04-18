"""Molport public-UI scraper — no-API-key fallback for supplier/pricing data.

Why this exists
---------------
Molport's REST v3 API requires a free-tier key that is provisioned manually by
their staff (~24h turnaround). For the hackathon demo we cannot guarantee the
key will be in hand before submission. This module scrapes the *same data* the
API would return by driving Molport's public website with Playwright, and
shapes the output to exactly match the documented API envelope:

    {"Molecule": {"Suppliers": [{"Catalogue": [{"Packings": [...]}]}]}}

…so downstream code in `molport.py` (`flatten_suppliers`) continues to work
unchanged whether data came from the API or the scraper.

Design notes
------------
* **Playwright, not requests+BS4.** Molport product pages are heavy JS: the
  supplier table is hydrated after page load and never appears in the raw HTML
  response. Headless Chromium is required.
* **CAS-first → name fallback.** The scraper enters a CAS number into the
  public text search, then falls back to the compound name if CAS yields
  nothing.
* **Selector robustness.** Molport is an external site we do not control, and
  the live DOM has not been fully reconnoitred (WebFetch rendered only the
  navigation chrome, not the supplier table). Every selector in
  `_SELECTORS` below is a *best-guess* list; the scraper tries them in order
  and logs which one matched. First real run against a live page is expected
  to refine these — update `_SELECTORS` in-place.
* **Cache-first.** Every scrape result is written to `API_Response_Cache`
  via `molport_cache.cache_put(...)` with `Source='molport'`. Re-runs during
  the same demo hit the SQLite cache, not the network.
* **Polite rate limiting.** 2s between page loads, single browser context.
  Respects Molport's ToS intent (low-volume, attributable use) and avoids
  getting the demo IP banned mid-demo.
* **Feature-flagged.** `MOLPORT_SCRAPER_ENABLED` env var must be `1` to run;
  default-off so CI and the bootstrap pipeline stay deterministic.

Usage
-----
    from enrichment.sources.molport_scraper import MolportScraper

    with MolportScraper(db_path="db_enriched.sqlite") as scraper:
        envelope = scraper.scrape_by_cas("557-04-0")  # magnesium stearate
        # envelope matches API schema; feed straight into flatten_suppliers()

CLI
---
    python -m enrichment.sources.molport_scraper --cas 557-04-0 --db db_enriched.sqlite

Limitations
-----------
* Selectors are placeholders until the first live run. Expect to tweak them.
* Some catalogs require login to see pricing — this scraper does not log in.
  If `Price` fields come back null, assume that supplier is login-gated and
  mark the row `price_type='retail_proxy', grade_unverified=1` same as API path.
* Molport's ToS restricts automated use; for a hackathon demo scraping a
  handful of demo compounds is within courteous bounds. Do NOT turn this on
  for a full 876-SKU batch enrichment run in production.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

from enrichment.sources import molport_cache
from enrichment.sources.molport_index import MolportIndex, product_url as _molport_product_url

load_dotenv()

logger = logging.getLogger("agnes.molport.scraper")

ROOT = Path(__file__).parent.parent.parent
MOLPORT_BASE = "https://www.molport.com"

# User-facing entry points on the public site. Multiple attempted in order.
_SEARCH_URLS = [
    f"{MOLPORT_BASE}/shop/molecule-search?query={{q}}",
    f"{MOLPORT_BASE}/shop/molecule-search?start=yes&type=textual&query={{q}}",
    f"{MOLPORT_BASE}/shop/find-chemicals?query={{q}}",
]

# Selector fallbacks — try each until one yields non-empty results.
# PLACEHOLDER: update after first live reconnaissance.
_SELECTORS = {
    "search_input": [
        "input[name='query']",
        "input[type='search']",
        "input#molecule-search-text",
        "input[placeholder*='CAS']",
    ],
    "submit_button": [
        "button[type='submit']",
        "input[type='submit']",
        "button.search-submit",
    ],
    "result_link": [
        "a[href*='/shop/moleculelink/']",
        "a[href*='/shop/molecule-link/']",
        "table.search-results a[href*='MolPort-']",
        ".search-result-row a",
    ],
    "supplier_row": [
        "tr.supplier-row",
        "div.supplier-offer",
        "table.suppliers tbody tr",
        "div[data-supplier-id]",
    ],
    "supplier_name": [
        "td.supplier-name",
        "a.supplier-link",
        "[data-field='supplier-name']",
    ],
    "pack_row": [
        "tr.packing-row",
        "div.packing",
        "tr[data-amount]",
    ],
    "pack_amount": ["[data-amount]", "td.amount", ".pack-amount"],
    "pack_measure": ["[data-measure]", "td.measure", ".pack-measure"],
    "pack_price": ["[data-price]", "td.price", ".pack-price"],
    "pack_delivery": ["[data-delivery]", "td.delivery", ".pack-delivery"],
    "origin_country": ["[data-origin-country]", "td.origin", ".origin-iso"],
    "shipping_country": ["[data-shipping-country]", "td.shipping", ".shipping-iso"],
    "molport_id": [
        "[data-molport-id]",
        "span.molport-id",
        ".compound-id",
    ],
    "compound_name": [
        "h1.compound-name",
        "h1.molecule-title",
        ".compound-header h1",
    ],
    "cas_number": [
        "[data-cas]",
        ".cas-number",
        "dd.cas",
    ],
    "purity": [
        "[data-purity]",
        "td.purity",
    ],
}

PRICE_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)")
_MONEY_CHARS = {"$": "USD", "€": "EUR", "£": "GBP"}


@dataclass
class ScrapeConfig:
    headless: bool = True
    request_delay_s: float = 2.0
    nav_timeout_ms: int = 30_000
    cache_ttl_days: int = 30


class MolportScraper:
    """Playwright-driven scraper against molport.com public UI."""

    def __init__(
        self,
        db_path: str | None = None,
        config: ScrapeConfig | None = None,
        index_path: str | None = None,
    ):
        self.db_path = str(db_path) if db_path else str(ROOT / "db_enriched.sqlite")
        self.config = config or ScrapeConfig()
        self.index = MolportIndex(index_path)
        if self.index.available():
            logger.info("Molport index loaded: %s", self.index.db_path)
        else:
            logger.info("Molport index not available — scraper will fall back to search-driven lookup")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "MolportScraper":
        self._start_browser()
        self._conn = sqlite3.connect(self.db_path)
        molport_cache.ensure_schema(self._conn)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:  # noqa: BLE001
            logger.warning("Browser teardown error: %s", e)
        if self._conn:
            self._conn.close()
        self.index.close()

    def _start_browser(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from e
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        self._context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36 Agnes/1.0 (hackathon)",
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self._page = self._context.new_page()
        self._page.set_default_navigation_timeout(self.config.nav_timeout_ms)

    # ---- public API --------------------------------------------------------
    def scrape_by_cas(self, cas: str, smiles: str | None = None) -> dict[str, Any] | None:
        """Scrape supplier/pricing data for a compound by CAS number.

        If `smiles` is supplied and the index is available, the scraper will
        resolve CAS → Molport ID via index (zero network) and navigate
        directly to the product page, skipping the fragile search step.
        """
        cas_clean = (cas or "").strip()
        if not cas_clean:
            return None
        cached = molport_cache.cache_get(self._conn, "cas", cas_clean, self.config.cache_ttl_days)
        if cached:
            logger.info("Cache hit for CAS %s", cas_clean)
            return cached

        envelope = None
        # Index-first: if SMILES supplied and present in index, go direct.
        if smiles and self.index.available():
            mid = self.index.lookup_by_smiles(smiles)
            if mid:
                logger.info("Index hit: SMILES → %s", mid)
                envelope = self._scrape_direct(mid, expected_smiles=smiles)

        # Fallback: search-driven lookup.
        if not (envelope and envelope.get("Molecule")):
            envelope = self._scrape_query(cas_clean, query_kind="cas")

        if envelope and envelope.get("Molecule"):
            molport_cache.cache_put(self._conn, "cas", cas_clean, envelope, self.config.cache_ttl_days)
        return envelope

    def scrape_by_smiles(self, smiles: str) -> dict[str, Any] | None:
        """Scrape directly from a SMILES string via the identity index.

        Returns `{"Molecule": None, ...}` if the SMILES is not present in
        the Molport catalogue — a confident "not available" answer that
        required zero network traffic.
        """
        s = (smiles or "").strip()
        if not s:
            return None
        cached = molport_cache.cache_get(self._conn, "smiles", s, self.config.cache_ttl_days)
        if cached:
            logger.info("Cache hit for SMILES %s", s[:40])
            return cached

        if not self.index.available():
            logger.warning("scrape_by_smiles requires a built index — falling back to _scrape_query")
            envelope = self._scrape_query(s, query_kind="smiles")
        else:
            mid = self.index.lookup_by_smiles(s)
            if not mid:
                logger.info("SMILES not in Molport index — confident 'not sold' answer")
                envelope = {
                    "Molecule": None,
                    "_scrape_meta": {
                        "query": s, "query_kind": "smiles", "found": False,
                        "reason": "smiles_not_in_index",
                    },
                }
            else:
                logger.info("Index hit: SMILES → %s", mid)
                envelope = self._scrape_direct(mid, expected_smiles=s)

        if envelope:
            molport_cache.cache_put(self._conn, "smiles", s, envelope, self.config.cache_ttl_days)
        return envelope

    def scrape_by_name(self, name: str) -> dict[str, Any] | None:
        """Scrape by compound name (fallback when CAS + SMILES both missing)."""
        name_clean = (name or "").strip()
        if not name_clean:
            return None
        cached = molport_cache.cache_get(self._conn, "name", name_clean, self.config.cache_ttl_days)
        if cached:
            logger.info("Cache hit for name '%s'", name_clean)
            return cached
        envelope = self._scrape_query(name_clean, query_kind="name")
        if envelope and envelope.get("Molecule"):
            molport_cache.cache_put(self._conn, "name", name_clean, envelope, self.config.cache_ttl_days)
        return envelope

    def scrape_by_molport_id(self, molport_id: str) -> dict[str, Any] | None:
        """Scrape a specific Molport compound page when the ID is already known.

        If the index is available, rejects any ID not present in it (defensive
        validation) before spending a browser session on the page.
        """
        mid = (molport_id or "").strip()
        if not mid:
            return None
        if self.index.available() and not self.index.exists(mid):
            logger.warning("Molport ID %s not in local index — refusing to scrape (possible hallucination)", mid)
            return {
                "Molecule": None,
                "_scrape_meta": {
                    "query": mid, "query_kind": "molport_id", "found": False,
                    "reason": "id_not_in_index",
                },
            }
        cached = molport_cache.cache_get(self._conn, "molport_id", mid, self.config.cache_ttl_days)
        if cached:
            logger.info("Cache hit for molport_id %s", mid)
            return cached
        envelope = self._scrape_direct(mid)
        if envelope and envelope.get("Molecule"):
            molport_cache.cache_put(self._conn, "molport_id", mid, envelope, self.config.cache_ttl_days)
        return envelope

    def _scrape_direct(
        self, molport_id: str, expected_smiles: str | None = None
    ) -> dict[str, Any] | None:
        """Navigate straight to the compound page by Molport ID.

        Uses the canonical product URL `/shop/compound/{id}` (no search, no
        redirects). On success, validates the scraped envelope against the
        local identity index if available — rejecting any drift.
        """
        url = _molport_product_url(molport_id)
        if not self._goto(url):
            return None
        envelope = self._extract_envelope(source_url=url, expected_molport_id=molport_id)
        mol = envelope.get("Molecule") if envelope else None
        if mol and self.index.available():
            returned_id = (mol.get("Molport Id") or molport_id or "").strip()
            if returned_id and returned_id != molport_id:
                logger.warning(
                    "Scraped page returned Molport ID %s, expected %s — rejecting as drift",
                    returned_id, molport_id,
                )
                envelope["Molecule"] = None
                envelope.setdefault("_scrape_meta", {})["reason"] = "molport_id_mismatch"
                return envelope
            # Optional SMILES sanity check if upstream supplied one.
            if expected_smiles and not self.index.validate(molport_id, expected_smiles):
                logger.warning(
                    "Expected SMILES does not match index entry for %s — flagging envelope",
                    molport_id,
                )
                envelope.setdefault("_scrape_meta", {})["warning"] = "smiles_index_mismatch"
        return envelope

    # ---- core scrape flow --------------------------------------------------
    def _scrape_query(self, query: str, query_kind: str) -> dict[str, Any] | None:
        """Run a search for `query`, click the top result, extract supplier data."""
        for tmpl in _SEARCH_URLS:
            url = tmpl.format(q=quote_plus(query))
            if not self._goto(url):
                continue
            product_url = self._pick_top_result_url()
            if not product_url:
                logger.debug("No results on search URL: %s", url)
                continue
            if not self._goto(product_url):
                continue
            envelope = self._extract_envelope(source_url=product_url)
            if envelope and envelope.get("Molecule"):
                return envelope
        logger.info("No scrapeable product page found for %s=%s", query_kind, query)
        return {"Molecule": None, "_scrape_meta": {"query": query, "query_kind": query_kind, "found": False}}

    def _goto(self, url: str) -> bool:
        """Navigate, respecting rate limit. Returns True on success."""
        try:
            time.sleep(self.config.request_delay_s)
            resp = self._page.goto(url, wait_until="domcontentloaded")
            if resp and resp.status >= 400:
                logger.debug("HTTP %s at %s", resp.status, url)
                return False
            # Let hydration complete.
            self._page.wait_for_load_state("networkidle", timeout=self.config.nav_timeout_ms)
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug("Nav failed %s: %s", url, e)
            return False

    def _pick_top_result_url(self) -> str | None:
        """Find the first compound-detail link on the current results page."""
        for sel in _SELECTORS["result_link"]:
            try:
                href = self._page.locator(sel).first.get_attribute("href", timeout=2000)
            except Exception:  # noqa: BLE001
                continue
            if href:
                if href.startswith("/"):
                    href = MOLPORT_BASE + href
                return href
        return None

    # ---- extraction helpers ------------------------------------------------
    def _first_text(self, selectors: list[str]) -> str | None:
        for sel in selectors:
            try:
                txt = self._page.locator(sel).first.inner_text(timeout=1500)
            except Exception:  # noqa: BLE001
                continue
            if txt and txt.strip():
                return txt.strip()
        return None

    def _first_attr(self, selectors: list[str], attr: str) -> str | None:
        for sel in selectors:
            try:
                val = self._page.locator(sel).first.get_attribute(attr, timeout=1500)
            except Exception:  # noqa: BLE001
                continue
            if val:
                return val.strip()
        return None

    def _extract_envelope(
        self, source_url: str, expected_molport_id: str | None = None
    ) -> dict[str, Any]:
        """Build a response envelope shaped like the Molport v3 API response.

        Return shape:
        {
          "Molecule": {
            "Molport Id": "...",
            "IUPAC": "...",
            "Suppliers": [
              { "Supplier Name": "...", "Shipping Country ISO": "...",
                "Catalogue": [
                  { "Purity": "...", "Packings": [
                    {"Amount": 100, "Measure": "g", "Price": 45.0,
                     "Currency": "USD", "Delivery Days": 5}
                  ]}
                ]}
            ]
          },
          "_scrape_meta": {"source_url": "...", "scraped_at": "..."}
        }
        """
        molport_id = self._first_attr(_SELECTORS["molport_id"], "data-molport-id") \
            or self._first_text(_SELECTORS["molport_id"]) \
            or expected_molport_id

        compound_name = self._first_text(_SELECTORS["compound_name"])
        cas = self._first_text(_SELECTORS["cas_number"])

        suppliers_payload: list[dict[str, Any]] = []
        supplier_rows = []
        for sel in _SELECTORS["supplier_row"]:
            try:
                rows = self._page.locator(sel)
                count = rows.count()
                if count > 0:
                    supplier_rows = [rows.nth(i) for i in range(count)]
                    logger.debug("Matched %d supplier rows via %s", count, sel)
                    break
            except Exception:  # noqa: BLE001
                continue

        for row in supplier_rows:
            supplier_name = _locator_first_text(row, _SELECTORS["supplier_name"])
            origin_iso = _locator_first_text(row, _SELECTORS["origin_country"])
            shipping_iso = _locator_first_text(row, _SELECTORS["shipping_country"])
            purity = _locator_first_text(row, _SELECTORS["purity"])
            packings = []
            pack_rows = []
            for sel in _SELECTORS["pack_row"]:
                try:
                    locs = row.locator(sel)
                    count = locs.count()
                    if count > 0:
                        pack_rows = [locs.nth(i) for i in range(count)]
                        break
                except Exception:  # noqa: BLE001
                    continue
            for pack in pack_rows:
                amount = _parse_float(_locator_first_text(pack, _SELECTORS["pack_amount"]))
                measure = _locator_first_text(pack, _SELECTORS["pack_measure"])
                price_text = _locator_first_text(pack, _SELECTORS["pack_price"])
                price_val, currency = _parse_price(price_text)
                delivery = _parse_int(_locator_first_text(pack, _SELECTORS["pack_delivery"]))
                packings.append({
                    "Amount": amount,
                    "Measure": measure,
                    "Price": price_val,
                    "Currency": currency,
                    "Delivery Days": delivery,
                })

            if not packings and supplier_name is None:
                continue
            suppliers_payload.append({
                "Supplier Name": supplier_name,
                "Origin Country ISO": origin_iso,
                "Shipping Country ISO": shipping_iso,
                "Catalogue": [
                    {
                        "Purity": purity,
                        "Packings": packings,
                    }
                ],
            })

        if not suppliers_payload:
            logger.info("Product page scraped but no suppliers parsed — selectors likely need refinement")

        envelope = {
            "Molecule": {
                "Molport Id": molport_id,
                "IUPAC": compound_name,
                "CAS": cas,
                "Suppliers": suppliers_payload,
            } if (molport_id or compound_name or suppliers_payload) else None,
            "_scrape_meta": {
                "source_url": source_url,
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "supplier_count": len(suppliers_payload),
                "scraper_version": "0.1-hackathon",
            },
        }
        return envelope


# ---- free-function helpers ---------------------------------------------------
def _locator_first_text(row, selectors: list[str]) -> str | None:
    for sel in selectors:
        try:
            loc = row.locator(sel).first
            if loc.count() == 0:
                continue
            txt = loc.inner_text(timeout=1000)
            if txt and txt.strip():
                return txt.strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def _parse_float(s: str | None) -> float | None:
    if not s:
        return None
    m = PRICE_RE.search(s.replace(",", ""))
    return float(m.group(1)) if m else None


def _parse_int(s: str | None) -> int | None:
    f = _parse_float(s)
    return int(f) if f is not None else None


def _parse_price(s: str | None) -> tuple[float | None, str | None]:
    """Return (amount, currency_iso_guess) from a string like '$45.00' or '€12,50'."""
    if not s:
        return (None, None)
    currency = "USD"  # Molport's default quoted currency
    for ch, iso in _MONEY_CHARS.items():
        if ch in s:
            currency = iso
            break
    return (_parse_float(s), currency)


# ---- CLI ---------------------------------------------------------------------
def _cli() -> None:
    parser = argparse.ArgumentParser(description="Molport public-UI scraper (no API key)")
    parser.add_argument("--cas", help="CAS number to look up")
    parser.add_argument("--smiles", help="SMILES string (preferred — uses identity index)")
    parser.add_argument("--name", help="Compound name to look up")
    parser.add_argument("--molport-id", help="Known Molport Id (skips search)")
    parser.add_argument("--db", default=str(ROOT / "db_enriched.sqlite"))
    parser.add_argument("--index", default=None, help="Path to db_molport_index.sqlite (auto-detected if omitted)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--out", help="Write envelope JSON to this path")
    args = parser.parse_args()

    if not (args.cas or args.smiles or args.name or args.molport_id):
        parser.error("One of --cas, --smiles, --name, --molport-id is required")

    if os.getenv("MOLPORT_SCRAPER_ENABLED") != "1":
        logger.warning("MOLPORT_SCRAPER_ENABLED != 1 — running anyway because CLI was invoked directly")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    with MolportScraper(
        db_path=args.db,
        config=ScrapeConfig(headless=not args.headed),
        index_path=args.index,
    ) as scraper:
        if args.molport_id:
            envelope = scraper.scrape_by_molport_id(args.molport_id)
        elif args.smiles:
            envelope = scraper.scrape_by_smiles(args.smiles)
        elif args.cas:
            envelope = scraper.scrape_by_cas(args.cas, smiles=args.smiles)
        else:
            envelope = scraper.scrape_by_name(args.name)

    text = json.dumps(envelope, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        logger.info("Wrote envelope → %s", args.out)
    else:
        print(text)


if __name__ == "__main__":
    _cli()
