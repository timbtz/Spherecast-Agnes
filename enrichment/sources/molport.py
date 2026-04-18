"""Molport client with scraper fallback — Clean-4 version.

This file supersedes master's `enrichment/sources/molport.py`. It preserves the
existing API-key contract (`lookup_ingredient(canonical) -> list[dict]`) and
adds a no-key fallback path that drives the public UI via Playwright
(`molport_scraper.MolportScraper`).

Selection logic
---------------
1. If `MOLPORT_FIXTURES_ONLY=1` → return hand-curated demo envelopes only
   (useful 10 minutes before demo when scraper selectors are drifting).
2. Else if `MOLPORT_API_KEY` is set → use REST v3 API (original behavior).
3. Else if `MOLPORT_SCRAPER_ENABLED=1` → use the Playwright scraper,
   with the fixture table as a last-resort fallback for anchor demo CASes.
4. Else → log and return `[]` (no-op, same as master pre-key behavior).

The scraper emits a response envelope shaped exactly like the API's
`/molecule/load` response, so `flatten_suppliers(...)` works unchanged on
both paths. Rows produced by the scraper carry `price_type='retail_proxy'`
and `grade_unverified=1` to match the API-path convention and keep
downstream pricing confidence logic honest.

WARNING: Molport API returns Title Case field names with spaces.
Use: data["Supplier Name"], data["Molport Id"], data["Price"], data["Amount"], data["Measure"]
Do NOT assume snake_case field names.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
MOLPORT_BASE = "https://api.molport.com/api"

logger = logging.getLogger("agnes.molport")

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Agnes/1.0 (supply-chain-enrichment)"


class MolportClient:
    def __init__(self, db_path=None):
        self.api_key = os.getenv("MOLPORT_API_KEY")
        self.scraper_enabled = os.getenv("MOLPORT_SCRAPER_ENABLED") == "1"
        self.fixtures_only = os.getenv("MOLPORT_FIXTURES_ONLY") == "1"
        self.db_path = str(db_path) if db_path else None
        self._scraper = None  # lazy-init
        if self.fixtures_only:
            logger.info("MOLPORT_FIXTURES_ONLY=1 — using pre-baked demo fixtures only")
        elif not self.api_key and not self.scraper_enabled:
            logger.warning(
                "MOLPORT_API_KEY not set and MOLPORT_SCRAPER_ENABLED!=1 — "
                "MolportClient will no-op gracefully"
            )
        elif not self.api_key and self.scraper_enabled:
            logger.info("MOLPORT_API_KEY not set — falling back to Playwright scraper")

    # ---- public API --------------------------------------------------------
    def lookup_ingredient(self, canonical: dict) -> list[dict]:
        """CAS-first → SMILES fallback lookup. Returns list of supplier rows or []."""
        if self.fixtures_only:
            return self._lookup_via_fixtures(canonical)
        if self.api_key:
            return self._lookup_via_api(canonical)
        if self.scraper_enabled:
            rows = self._lookup_via_scraper(canonical)
            if not rows:
                # Last-resort safety net for anchor demo ingredients.
                rows = self._lookup_via_fixtures(canonical)
            return rows
        return []

    def _lookup_via_fixtures(self, canonical: dict) -> list[dict]:
        from enrichment.sources.molport_fixtures import lookup_fixture
        cas = canonical.get("cas_number")
        envelope = lookup_fixture(cas) if cas else None
        if not envelope:
            return []
        logger.info("Using Molport fixture for CAS %s", cas)
        return self.flatten_suppliers(envelope["Molecule"])

    # ---- API path (unchanged from master) ----------------------------------
    def _lookup_via_api(self, canonical: dict) -> list[dict]:
        result = None
        if canonical.get("cas_number"):
            result = self._load_by_cas(canonical["cas_number"])
        if not result and canonical.get("smiles"):
            molport_id = self._search_by_smiles(canonical["smiles"])
            if molport_id:
                result = self._load_by_molport_id(molport_id)
        if not result:
            return []
        return self.flatten_suppliers(result)

    def _load_by_cas(self, cas: str) -> dict | None:
        """Attempt CAS-based load. Not officially documented for REST v3 — test first."""
        url = f"{MOLPORT_BASE}/molecule/load"
        try:
            resp = _SESSION.get(url, params={"molecule": cas, "apikey": self.api_key}, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                molecule = data.get("Molecule") or data.get("Data", {}).get("Molecule")
                if molecule:
                    return molecule
        except Exception as e:
            logger.warning(f"Molport CAS lookup failed for {cas}: {e}")
        return None

    def _search_by_smiles(self, smiles: str) -> str | None:
        """Search by SMILES (exact match, type 3). Returns Molport Id or None."""
        url = f"{MOLPORT_BASE}/chemical-search/search"
        payload = {
            "Structure": smiles,
            "Search Type": 3,
            "Maximum Search Time": 60000,
            "Maximum Result Count": 5,
            "Chemical Similarity Index": 1.0,
            "apikey": self.api_key,
        }
        try:
            time.sleep(0.5)  # Molport concurrent search limit: 3 simultaneous
            resp = _SESSION.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            molecules = data.get("Molecules", data.get("molecules", []))
            return molecules[0].get("Molport Id") if molecules else None
        except Exception as e:
            logger.warning(f"Molport SMILES search failed: {e}")
            return None

    def _load_by_molport_id(self, molport_id: str) -> dict | None:
        """Load full compound record by Molport ID."""
        url = f"{MOLPORT_BASE}/molecule/load"
        try:
            time.sleep(0.5)
            resp = _SESSION.get(url, params={"molecule": molport_id, "apikey": self.api_key}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Molecule") or data.get("Data", {}).get("Molecule")
        except Exception as e:
            logger.warning(f"Molport ID load failed for {molport_id}: {e}")
            return None

    # ---- Scraper path (new) ------------------------------------------------
    def _lookup_via_scraper(self, canonical: dict) -> list[dict]:
        scraper = self._get_scraper()
        if scraper is None:
            return []
        envelope = None
        # Preferred path: SMILES → identity index → direct product URL.
        if canonical.get("smiles"):
            envelope = scraper.scrape_by_smiles(canonical["smiles"])
        # CAS path now forwards SMILES so the scraper can skip search.
        if (not envelope or not envelope.get("Molecule")) and canonical.get("cas_number"):
            envelope = scraper.scrape_by_cas(
                canonical["cas_number"], smiles=canonical.get("smiles")
            )
        if (not envelope or not envelope.get("Molecule")) and canonical.get("name"):
            envelope = scraper.scrape_by_name(canonical["name"])
        if not envelope or not envelope.get("Molecule"):
            return []
        return self.flatten_suppliers(envelope["Molecule"])

    def _get_scraper(self):
        """Lazy-init the scraper; reuse a single browser context for the run."""
        if self._scraper is not None:
            return self._scraper
        try:
            from enrichment.sources.molport_scraper import MolportScraper
            self._scraper = MolportScraper(db_path=self.db_path)
            self._scraper.__enter__()
            return self._scraper
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to start Molport scraper: %s", e)
            return None

    def close(self) -> None:
        """Close the scraper's browser context if one was opened."""
        if self._scraper is not None:
            try:
                self._scraper.__exit__(None, None, None)
            except Exception as e:  # noqa: BLE001
                logger.warning("Scraper teardown error: %s", e)
            self._scraper = None

    # ---- shared flattening (identical shape from API or scraper) -----------
    def flatten_suppliers(self, molecule_data: dict) -> list[dict]:
        """Flatten Suppliers[].Catalogue[].Packings[] into row dicts.

        FIELD NAMES ARE TITLE CASE WITH SPACES — Molport's API convention.
        Validate these against real responses once an API key is obtained or
        the scraper's first live run has verified selectors.

        Output row fields:
            supplier_name, price, currency, price_qty_kg, amount_raw, measure,
            delivery_days, molport_catalog_id, last_update_date, purity,
            country_shipping, country_origin, stock_status, is_minimum_order,
            price_type, grade_unverified

        Post-processing step: for each (supplier_name, molport_catalog_id)
        group, the row with the smallest computable `price_qty_kg` is tagged
        `is_minimum_order=1` — that's the smallest pack size the supplier
        will sell, i.e., the MOQ. Rows where `price_qty_kg` can't be derived
        (unknown measure) stay `is_minimum_order=0`.
        """
        rows = []
        for supplier in molecule_data.get("Suppliers", []):
            for catalogue in supplier.get("Catalogue", []):
                for packing in catalogue.get("Packings", []):
                    amount_raw = packing.get("Amount")
                    measure = packing.get("Measure")
                    price = packing.get("Price")
                    currency = packing.get("Currency") or "USD"
                    # Normalize amount to KG for Price_Qty_KG
                    price_qty_kg = None
                    if amount_raw is not None and measure:
                        measure_lower = str(measure).lower()
                        if measure_lower in ("kg", "kilogram", "kilograms"):
                            price_qty_kg = float(amount_raw)
                        elif measure_lower in ("g", "gram", "grams"):
                            price_qty_kg = float(amount_raw) / 1000
                    # Stock status — normalize free-form strings to a small
                    # vocabulary the decision layer can reason over.
                    raw_stock = packing.get("Stock") or packing.get("Availability")
                    stock_status = _normalize_stock(raw_stock)
                    rows.append({
                        "supplier_name": supplier.get("Supplier Name"),
                        "price": price,
                        "currency": currency,
                        "price_qty_kg": price_qty_kg,
                        "amount_raw": amount_raw,
                        "measure": measure,
                        "delivery_days": packing.get("Delivery Days") or supplier.get("Delivery Days"),
                        "molport_catalog_id": catalogue.get("Catalog Id") or catalogue.get("Molport Catalog Id"),
                        "last_update_date": catalogue.get("Last Update Date"),
                        "purity": catalogue.get("Purity"),
                        "country_shipping": supplier.get("Shipping Country ISO"),
                        "country_origin": supplier.get("Origin Country ISO"),
                        "stock_status": stock_status,
                        "is_minimum_order": 0,  # patched by _tag_minimum_order
                        "price_type": "retail_proxy",
                        "grade_unverified": 1,
                    })

        # Tag the MOQ row per (supplier, catalogue). Smallest computable
        # price_qty_kg wins; ties broken by first-seen. Rows with no
        # price_qty_kg are never tagged (we can't prove they're the min).
        _tag_minimum_order(rows)
        return rows


def _normalize_stock(raw: object) -> str:
    """Map free-form stock strings to {in_stock, backorder, unknown}."""
    if raw is None:
        return "unknown"
    s = str(raw).strip().lower()
    if not s:
        return "unknown"
    if any(t in s for t in ("in stock", "in_stock", "available", "ships")):
        return "in_stock"
    if any(t in s for t in ("backorder", "back order", "out of stock", "unavailable", "weeks", "week")):
        return "backorder"
    return "unknown"


def _tag_minimum_order(rows: list[dict]) -> None:
    """Mutate `rows` in-place: set `is_minimum_order=1` on the smallest
    `price_qty_kg` row per (supplier_name, molport_catalog_id) group.
    """
    groups: dict[tuple, list[int]] = {}
    for i, r in enumerate(rows):
        if r.get("price_qty_kg") is None:
            continue
        key = (r.get("supplier_name"), r.get("molport_catalog_id"))
        groups.setdefault(key, []).append(i)
    for idxs in groups.values():
        if not idxs:
            continue
        min_i = min(idxs, key=lambda i: rows[i]["price_qty_kg"])
        rows[min_i]["is_minimum_order"] = 1
