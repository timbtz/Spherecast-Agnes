"""NIH DSLD v9 API client with caching.

Critical: use v9 + X-Api-Key header. v9 without key returns 0 hits.
Search param is 'q=', NOT 'query='.
"""
import json
import logging
import os
import sqlite3
from pathlib import Path

import requests
from rapidfuzz import process as fuzz_process

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
DSLD_BASE = "https://api.ods.od.nih.gov/dsld/v9"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Agnes/1.0"

logger = logging.getLogger("agnes.dsld")


class DSLDClient:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        api_key = os.getenv("DSLD_API_KEY", "")
        if api_key:
            SESSION.headers["X-Api-Key"] = api_key
        else:
            logger.warning("DSLD_API_KEY not set — v9 will return 0 hits")

    # ── Phase 1: Ingredient identity ─────────────────────────────────────────

    def search_ingredient(self, name: str) -> dict | None:
        """Search DSLD for a raw ingredient name; return canonical name + confidence."""
        data = self._search({"q": name, "size": 10})
        if not data or not data.get("hits"):
            return None

        candidate_names: list[str] = []
        for hit in data["hits"]:
            src = hit.get("_source", hit)
            for row in src.get("allIngredients", []):
                n = row.get("name", "").strip()
                if n:
                    candidate_names.append(n)
            # legacy field names kept as fallback
            for row in src.get("ingredientRows", []):
                n = row.get("ingredientName", "").strip()
                if n:
                    candidate_names.append(n)

        if not candidate_names:
            return None

        best = fuzz_process.extractOne(name, candidate_names)
        if not best:
            return None

        return {
            "name": best[0],
            "confidence": 0.88,
            "method": "dsld",
            "sources": ["dsld"],
        }

    # ── Phase 2: BOM quantity enrichment ─────────────────────────────────────

    def search_product(self, product_name: str, size: int = 5) -> dict | None:
        """Search DSLD for a finished product by name; return hits list."""
        key = f"product_search:{product_name.lower()}"
        in_cache, cached = self._get_cache(key)
        if in_cache:
            return cached

        data = self._search({"q": product_name, "size": size})
        self._set_cache(key, data, ttl_days=30)
        return data

    def get_label(self, label_id: int) -> dict | None:
        """Fetch full label details — ingredient amounts, serving size, certifications."""
        key = f"label:{label_id}"
        in_cache, cached = self._get_cache(key)
        if in_cache:
            return cached

        try:
            resp = SESSION.get(f"{DSLD_BASE}/label/{label_id}", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._set_cache(key, data, ttl_days=90)
            return data
        except Exception as e:
            logger.error(f"DSLD label fetch failed id={label_id}: {e}")
            return None

    def find_label(self, brand: str, product_name: str,
                   min_confidence: float = 0.65) -> dict | None:
        """Search DSLD for a finished product; return best match metadata or None."""
        from rapidfuzz import fuzz
        query = f"{brand} {product_name}".strip()
        data = self._search({"q": query, "size": 5})
        if not data or not data.get("hits"):
            return None

        best, best_score = None, 0.0
        for hit in data["hits"]:
            src = hit.get("_source", {})
            b = fuzz.partial_ratio(brand.lower(), src.get("brandName", "").lower()) / 100
            n = fuzz.token_set_ratio(product_name.lower(), src.get("fullName", "").lower()) / 100
            if b < 0.60 or n < 0.60:
                continue
            score = round((b * 0.4) + (n * 0.6), 3)
            if score > best_score:
                best_score = score
                best = {
                    "dsld_id": hit["_id"],
                    "confidence": score,
                    "off_market": src.get("offMarket", "1"),
                    "brand_name": src.get("brandName"),
                    "full_name": src.get("fullName"),
                }
        return best if best and best_score >= min_confidence else None

    def extract_label_ingredients(self, label_id: str | int) -> list[dict]:
        """Fetch label and return structured ingredient list with amounts.

        Reads ingredientRows[].name and ingredientRows[].quantity[] (array).
        Recurses into nestedRows for proprietary blends.
        """
        label = self.get_label(label_id)
        if not label:
            return []

        results = []

        def _parse_rows(rows: list[dict]) -> None:
            for row in rows:
                name = row.get("name", "").strip()
                if not name or name in ("Calories", "Calories from Fat"):
                    continue
                for qty in row.get("quantity", []):
                    if qty.get("servingSizeOrder", 1) != 1:
                        continue
                    results.append({
                        "ingredient_name": name,
                        "unii_code": row.get("uniiCode"),
                        "category": row.get("category"),
                        "ingredient_group": row.get("ingredientGroup"),
                        "forms": [f["name"] for f in row.get("forms", [])],
                        "amount": qty.get("quantity"),
                        "unit": qty.get("unit"),
                        "per_serving": qty.get("servingSizeQuantity"),
                        "serving_unit": qty.get("servingSizeUnit"),
                        "source": "dsld",
                        "confidence": 0.90,
                        "dsld_label_id": label_id,
                    })
                for nested in row.get("nestedRows", []):
                    _parse_rows([nested])

        _parse_rows(label.get("ingredientRows", []))
        return results

    def extract_ingredient_amounts(self, label_data: dict) -> list[dict]:
        """Deprecated: use extract_label_ingredients(label_id) instead."""
        label_id = label_data.get("id") or label_data.get("_id")
        if label_id:
            return self.extract_label_ingredients(label_id)
        return []

    # ── Private: HTTP + Cache ─────────────────────────────────────────────────

    def _search(self, params: dict) -> dict | None:
        key = f"search:{json.dumps(params, sort_keys=True)}"
        in_cache, cached = self._get_cache(key)
        if in_cache:
            return cached

        try:
            resp = SESSION.get(f"{DSLD_BASE}/search-filter", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._set_cache(key, data, ttl_days=30)
            return data
        except Exception as e:
            logger.error(f"DSLD search failed params={params}: {e}")
            return None

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                """SELECT Response FROM API_Response_Cache
                   WHERE Source = 'dsld' AND Cache_Key = ?
                   AND (TTL_Days = 0 OR
                        julianday('now') - julianday(Fetched_At) < TTL_Days)""",
                (key,),
            ).fetchone()
            conn.close()
            if row is not None:
                return True, json.loads(row[0]) if row[0] != "null" else None
        except Exception:
            pass
        return False, None

    def _set_cache(self, key: str, result, ttl_days: int = 30) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES ('dsld', ?, ?, ?)""",
                (key, json.dumps(result), ttl_days),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
