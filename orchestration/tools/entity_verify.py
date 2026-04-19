"""
Deterministic tool: verify supplier legal entities via GLEIF LEI API.
Caches results in Supplier_Master (TTL=30 days). Free API, no key required.
"""
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

from orchestration.api.agnes_context import AgnesContext

_GLEIF_URL = "https://api.gleif.org/api/v1/fuzzycompletions"
_CACHE_TTL_DAYS = 30
_STRIP_SUFFIXES = re.compile(
    r"\b(llc|ltd|limited|inc|incorporated|co|corp|corporation|gmbh|ag|sa|bv|nv|plc|pte|pty)\b\.?$",
    re.IGNORECASE,
)


def run(ctx: AgnesContext) -> dict:
    # Collect suppliers from upstream nodes
    suppliers = _collect_suppliers(ctx)
    if not suppliers:
        return {"verified_suppliers": [], "vetted_count": 0, "gleif_hits": 0, "gleif_misses": 0, "cache_hits": 0, "errors": []}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # Ensure Supplier_Master exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Supplier_Master (
            SupplierId INTEGER PRIMARY KEY, DUNS TEXT, LEI TEXT,
            OpenCorporatesId TEXT, Country_Verified TEXT, Legal_Name TEXT,
            GLEIF_Status TEXT, Vetted INTEGER DEFAULT 0, Vetted_Source TEXT,
            Vetted_At TEXT, Notes TEXT
        )
    """)
    conn.commit()

    verified = []
    gleif_hits = 0
    gleif_misses = 0
    cache_hits = 0
    errors = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS)).isoformat()

    for sup in suppliers:
        sid = sup.get("SupplierId") or sup.get("supplier_id")
        name = sup.get("supplier_name") or sup.get("Name") or ""
        country_hint = sup.get("Country_Origin") or sup.get("country_origin")
        if not sid or not name:
            continue

        # Check cache
        cached = conn.execute(
            "SELECT * FROM Supplier_Master WHERE SupplierId = ? AND Vetted_At > ?",
            (sid, cutoff),
        ).fetchone()

        if cached:
            cache_hits += 1
            verified.append({
                "supplier_id": sid,
                "lei": cached["LEI"],
                "legal_name": cached["Legal_Name"],
                "country_verified": cached["Country_Verified"],
                "gleif_status": cached["GLEIF_Status"],
                "vetted": bool(cached["Vetted"]),
                "cached": True,
            })
            continue

        # Live GLEIF lookup
        result = _gleif_lookup(name, country_hint, errors)
        if result:
            gleif_hits += 1
            vetted_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO Supplier_Master
                    (SupplierId, LEI, Legal_Name, Country_Verified, GLEIF_Status, Vetted, Vetted_Source, Vetted_At)
                VALUES (?, ?, ?, ?, ?, 1, 'gleif', ?)
                """,
                (sid, result["lei"], result["legal_name"], result["country"], result["status"], vetted_at),
            )
            conn.commit()
            verified.append({
                "supplier_id": sid,
                "lei": result["lei"],
                "legal_name": result["legal_name"],
                "country_verified": result["country"],
                "gleif_status": result["status"],
                "vetted": True,
                "cached": False,
            })
        else:
            gleif_misses += 1
            vetted_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO Supplier_Master
                    (SupplierId, LEI, Legal_Name, Country_Verified, GLEIF_Status, Vetted, Vetted_Source, Vetted_At, Notes)
                VALUES (?, NULL, NULL, NULL, 'NOT_FOUND', 0, 'gleif', ?, 'No GLEIF match found')
                """,
                (sid, vetted_at),
            )
            conn.commit()
            verified.append({
                "supplier_id": sid,
                "lei": None,
                "legal_name": None,
                "country_verified": None,
                "gleif_status": "NOT_FOUND",
                "vetted": False,
                "cached": False,
            })

    conn.close()
    return {
        "verified_suppliers": verified,
        "vetted_count": sum(1 for v in verified if v["vetted"]),
        "gleif_hits": gleif_hits,
        "gleif_misses": gleif_misses,
        "cache_hits": cache_hits,
        "errors": errors,
    }


def _collect_suppliers(ctx: AgnesContext) -> list[dict]:
    """Pull supplier records from find-alternatives, web-research, or trigger payload."""
    sources = [
        ctx.get("find-alternatives", {}).get("alternatives", []),
        ctx.get("web-research", {}).get("discovered_suppliers", []),
    ]
    seen = set()
    result = []
    for src in sources:
        for sup in src:
            sid = sup.get("SupplierId") or sup.get("supplier_id")
            if sid and sid not in seen:
                seen.add(sid)
                result.append(sup)
    return result


def _gleif_lookup(name: str, country_hint: str | None, errors: list) -> dict | None:
    """Query GLEIF fuzzy completions API. Returns None on miss or error."""
    clean_name = _STRIP_SUFFIXES.sub("", name).strip()
    try:
        resp = httpx.get(
            _GLEIF_URL,
            params={"field": "fullname", "q": clean_name},
            timeout=8.0,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        errors.append(f"GLEIF error for {name!r}: {exc}")
        return None

    if not data:
        return None

    # Prefer country match if hint provided
    if country_hint:
        for item in data:
            attrs = item.get("attributes", {})
            if attrs.get("country", "").upper() == country_hint.upper():
                return _parse_gleif(attrs)

    # Fall back to first result
    attrs = data[0].get("attributes", {})
    return _parse_gleif(attrs)


def _parse_gleif(attrs: dict) -> dict:
    return {
        "lei": attrs.get("lei", ""),
        "legal_name": attrs.get("value", ""),
        "country": attrs.get("country", ""),
        "status": attrs.get("entity", {}).get("status", "UNKNOWN") if isinstance(attrs.get("entity"), dict) else "UNKNOWN",
    }
