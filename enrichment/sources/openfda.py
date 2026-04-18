"""openFDA client: drug label search and adverse event counts.

API key at OPENFDA_API_KEY env var (240 req/min without, 12k req/hr with).
"""
import json
import logging
import os
import sqlite3
import threading
import time

import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
_BASE_URL = "https://api.fda.gov"
_MIN_INTERVAL = 0.26  # ~230 req/min — stay under 240/min limit
_last_req: float = 0.0
_lock = threading.Lock()
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Agnes/1.0 (supply-chain-agent)"

logger = logging.getLogger("agnes.openfda")


def _throttle() -> None:
    global _last_req
    with _lock:
        elapsed = time.monotonic() - _last_req
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_req = time.monotonic()


class OpenFDAClient:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self.api_key = os.getenv("OPENFDA_API_KEY", "")

    def _build_url(self, path: str, params: dict) -> str:
        if self.api_key:
            params["api_key"] = self.api_key
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{_BASE_URL}{path}?{qs}"

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT Response FROM API_Response_Cache WHERE Source = 'openfda' AND Cache_Key = ?",
                (key,),
            ).fetchone()
            conn.close()
            if row:
                return True, json.loads(row[0])
        except Exception:
            pass
        return False, None

    def _set_cache(self, key: str, result: dict | None) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES ('openfda', ?, ?, 7)""",
                (key, json.dumps(result)),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def adverse_event_count(self, unii: str) -> int:
        """Return total adverse event reports mentioning this UNII code."""
        cache_key = f"ae_count:{unii}"
        hit, cached = self._get_cache(cache_key)
        if hit:
            return cached.get("count", 0) if cached else 0

        url = self._build_url(
            "/drug/event.json",
            {
                "search": f'patient.drug.openfda.unii:"{unii}"',
                "limit": "1",
            },
        )
        _throttle()
        try:
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code == 404:
                self._set_cache(cache_key, {"count": 0})
                return 0
            resp.raise_for_status()
            data = resp.json()
            total = data.get("meta", {}).get("results", {}).get("total", 0)
            self._set_cache(cache_key, {"count": total})
            return total
        except Exception as e:
            logger.warning(f"openFDA adverse_event_count({unii}) failed: {e}")
            return 0

    def search_labels(self, ingredient_name: str, limit: int = 5) -> list[dict]:
        """Search drug labels for ingredient in inactive_ingredient field."""
        cache_key = f"label:{ingredient_name.lower()}:{limit}"
        hit, cached = self._get_cache(cache_key)
        if hit:
            return cached or []

        url = self._build_url(
            "/drug/label.json",
            {
                "search": f'inactive_ingredient:"{ingredient_name}"',
                "limit": str(limit),
            },
        )
        _throttle()
        try:
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code == 404:
                self._set_cache(cache_key, [])
                return []
            resp.raise_for_status()
            results = resp.json().get("results", [])
            simplified = [
                {
                    "brand_name": r.get("openfda", {}).get("brand_name", [None])[0],
                    "manufacturer": r.get("openfda", {}).get("manufacturer_name", [None])[0],
                    "route": r.get("openfda", {}).get("route", [None])[0],
                    "inactive_ingredient": r.get("inactive_ingredient", [""]),
                }
                for r in results
            ]
            self._set_cache(cache_key, simplified)
            return simplified
        except Exception as e:
            logger.warning(f"openFDA search_labels({ingredient_name!r}) failed: {e}")
            return []
