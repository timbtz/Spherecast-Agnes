"""PubChem PUG REST API client with caching and rate limiting.

Rate limit: 5 req/sec, 400 req/min.
Cache: permanent (TTL_Days=0) — CAS/IUPAC mappings do not expire.
"""
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
MIN_REQUEST_INTERVAL = 0.22   # ~4.5 req/sec, safely under 5/sec limit
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Agnes/1.0 (supply-chain-enrichment; contact: research)"

logger = logging.getLogger("agnes.pubchem")
_last_request_time: float = 0.0
_throttle_lock = __import__("threading").Lock()


class PubChemClient:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def lookup(self, name: str) -> dict | None:
        """Look up compound by name. Returns enrichment dict or None if not found."""
        in_cache, cached = self._get_cache(name.lower())
        if in_cache:
            return cached

        _throttle()
        try:
            cid = self._get_cid(name)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self._set_cache(name.lower(), None)
                return None
            logger.warning(f"PubChem CID lookup HTTP error for '{name}': {e}")
            return None
        except Exception as e:
            logger.error(f"PubChem CID lookup failed for '{name}': {e}")
            return None

        if not cid:
            self._set_cache(name.lower(), None)
            return None

        try:
            synonyms = self._get_synonyms(cid)
            props = self._get_properties(cid)
        except Exception as e:
            logger.error(f"PubChem property fetch failed for CID={cid}: {e}")
            return None

        cas = _extract_cas(synonyms)
        preferred = _pick_preferred_name(synonyms, fallback=name)
        result = {
            "name": preferred,
            "cas_number": cas,
            "pubchem_cid": cid,
            "iupac_name": props.get("IUPACName"),
            "molecular_formula": props.get("MolecularFormula"),
            "synonyms": synonyms[:20],
            "confidence": 0.97 if cas else 0.80,
            "method": "pubchem",
            "sources": ["pubchem"],
        }
        self._set_cache(name.lower(), result)
        return result

    # ── Private: API calls ───────────────────────────────────────────────────

    def _get_cid(self, name: str) -> int | None:
        url = f"{PUBCHEM_BASE}/name/{requests.utils.quote(name)}/cids/JSON"
        resp = _get(url)
        if resp is None:
            return None
        cids = resp.json().get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None

    def _get_synonyms(self, cid: int) -> list[str]:
        _throttle()
        url = f"{PUBCHEM_BASE}/cid/{cid}/synonyms/JSON"
        resp = _get(url)
        if resp is None:
            return []
        info = resp.json().get("InformationList", {}).get("Information", [{}])
        return info[0].get("Synonym", []) if info else []

    def _get_properties(self, cid: int) -> dict:
        _throttle()
        url = f"{PUBCHEM_BASE}/cid/{cid}/property/IUPACName,MolecularFormula/JSON"
        resp = _get(url)
        if resp is None:
            return {}
        props = resp.json().get("PropertyTable", {}).get("Properties", [{}])
        return props[0] if props else {}

    # ── Private: Cache ───────────────────────────────────────────────────────

    def _get_cache(self, key: str) -> tuple[bool, dict | None]:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                """SELECT Response FROM API_Response_Cache
                   WHERE Source = 'pubchem' AND Cache_Key = ?
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

    def _set_cache(self, key: str, result: dict | None) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO API_Response_Cache
                   (Source, Cache_Key, Response, TTL_Days)
                   VALUES ('pubchem', ?, ?, 0)""",
                (key, json.dumps(result)),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ── Module-level helpers ─────────────────────────────────────────────────────

def _throttle() -> None:
    global _last_request_time
    with _throttle_lock:
        elapsed = time.monotonic() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        _last_request_time = time.monotonic()


def _get(url: str) -> requests.Response | None:
    """GET with error handling; returns None on 404, raises on other errors."""
    try:
        resp = SESSION.get(url, timeout=12)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp
    except requests.HTTPError:
        raise
    except requests.RequestException as e:
        logger.warning(f"PubChem request error: {e}")
        return None


def _extract_cas(synonyms: list[str]) -> str | None:
    """Extract the first CAS-format string from a PubChem synonym list."""
    for syn in synonyms:
        if CAS_RE.match(syn.strip()):
            return syn.strip()
    return None


def _pick_preferred_name(synonyms: list[str], fallback: str) -> str:
    """Return the first synonym that looks like a human-readable name."""
    for syn in synonyms:
        if re.match(r'^[A-Z0-9\-]+$', syn):  # all-caps / registry ID
            continue
        if len(syn) > 80:  # IUPAC names tend to be long
            continue
        if syn.count('(') > 2:  # IUPAC nesting
            continue
        return syn.strip()
    return fallback
