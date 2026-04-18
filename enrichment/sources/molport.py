"""Molport v3 API client — CAS-first → SMILES fallback → supplier price rows.

WARNING: Molport API returns Title Case field names with spaces.
Use: data["Supplier Name"], data["Molport Id"], data["Price"], data["Amount"], data["Measure"]
Do NOT assume snake_case field names.

All prices are research/lab scale. Always set Price_Type='retail_proxy', Grade_Unverified=1.

NOTE: Response schemas are inferred from Molport docs — not live-validated.
The first implementor with a real API key must verify field names against actual responses
and update this file accordingly.
"""
import json
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
        self.db_path = str(db_path) if db_path else None
        if not self.api_key:
            logger.warning("MOLPORT_API_KEY not set — MolportClient will no-op gracefully")

    def lookup_ingredient(self, canonical: dict) -> list[dict]:
        """CAS-first → SMILES fallback lookup. Returns list of supplier rows or []."""
        if not self.api_key:
            return []

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

    def flatten_suppliers(self, molecule_data: dict) -> list[dict]:
        """Flatten Suppliers[].Catalogue[].Packings[] into row dicts.

        FIELD NAMES ARE TITLE CASE WITH SPACES — Molport's API convention.
        Validate these against real responses once an API key is obtained.
        """
        rows = []
        for supplier in molecule_data.get("Suppliers", []):
            for catalogue in supplier.get("Catalogue", []):
                for packing in catalogue.get("Packings", []):
                    amount_raw = packing.get("Amount")
                    measure = packing.get("Measure")
                    price_usd = packing.get("Price")
                    # Normalize amount to KG for Price_Qty_KG
                    price_qty_kg = None
                    if amount_raw is not None and measure:
                        measure_lower = str(measure).lower()
                        if measure_lower in ("kg", "kilogram", "kilograms"):
                            price_qty_kg = float(amount_raw)
                        elif measure_lower in ("g", "gram", "grams"):
                            price_qty_kg = float(amount_raw) / 1000
                    rows.append({
                        "supplier_name": supplier.get("Supplier Name"),
                        "price_usd": price_usd,
                        "price_qty_kg": price_qty_kg,
                        "amount_raw": amount_raw,
                        "measure": measure,
                        "delivery_days": packing.get("Delivery Days") or supplier.get("Delivery Days"),
                        "molport_catalog_id": catalogue.get("Catalog Id") or catalogue.get("Molport Catalog Id"),
                        "last_update_date": catalogue.get("Last Update Date"),
                        "purity": catalogue.get("Purity"),
                        "country_shipping": supplier.get("Shipping Country ISO"),
                        "country_origin": supplier.get("Origin Country ISO"),
                        "price_type": "retail_proxy",
                        "grade_unverified": 1,
                    })
        return rows
