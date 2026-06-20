"""Molport cache helpers — thin wrapper around the existing API_Response_Cache table.

The master schema already ships a generic `API_Response_Cache` table whose `Source`
column is explicitly documented to accept `'molport'`. Rather than introducing a
new per-source cache table (which would require a schema migration), this module
provides Molport-shaped convenience functions on top of that existing table.

Cache key conventions (stable, URL-safe):
    cas:<cas_number>              — CAS-based lookup
    smiles:<smiles>               — SMILES-based lookup (rarely used on scrape path)
    molport_id:<Molport_Id>       — direct ID load
    search:<query>                — free-text search page results

Every cached value is JSON-serialised. Responses from the scrape path should be
shaped to match the same `{"Molecule": {"Suppliers": [...]}}` envelope the API
client expects, so downstream flattening logic in `molport.py` stays unchanged.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("agnes.molport.cache")

SOURCE = "molport"
DEFAULT_TTL_DAYS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_key(query_type: str, query_value: str) -> str:
    """Build a canonical cache key. Lowercases the value, strips whitespace."""
    return f"{query_type}:{(query_value or '').strip().lower()}"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """No-op for Molport — table is defined in schema/enriched_schema.sql.

    Kept for symmetry with other scout-style modules that create their own tables.
    If an older enriched DB is missing the table, we create it on the fly so the
    scraper can run in isolation against a fresh sandbox.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS API_Response_Cache (
            Id          INTEGER PRIMARY KEY AUTOINCREMENT,
            Source      TEXT    NOT NULL,
            Cache_Key   TEXT    NOT NULL,
            Response    TEXT,
            Fetched_At  TEXT    NOT NULL DEFAULT (datetime('now')),
            TTL_Days    INTEGER NOT NULL DEFAULT 30,
            UNIQUE (Source, Cache_Key)
        )
        """
    )
    conn.commit()


def cache_get(
    conn: sqlite3.Connection,
    query_type: str,
    query_value: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> dict[str, Any] | None:
    """Return cached JSON response, or None if missing/expired."""
    key = build_key(query_type, query_value)
    row = conn.execute(
        """
        SELECT Response, Fetched_At, TTL_Days
        FROM API_Response_Cache
        WHERE Source = ? AND Cache_Key = ?
        """,
        (SOURCE, key),
    ).fetchone()
    if not row:
        return None

    response_json, fetched_at, stored_ttl = row
    ttl = stored_ttl if stored_ttl is not None else ttl_days
    try:
        fetched_dt = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        logger.warning("Unparseable Fetched_At %r for key %s", fetched_at, key)
        return None

    if datetime.now(timezone.utc) - fetched_dt > timedelta(days=ttl):
        logger.debug("Cache expired for %s (age > %dd)", key, ttl)
        return None

    try:
        return json.loads(response_json) if response_json else None
    except json.JSONDecodeError:
        logger.warning("Corrupt cached JSON for key %s", key)
        return None


def cache_put(
    conn: sqlite3.Connection,
    query_type: str,
    query_value: str,
    response: dict[str, Any],
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Upsert a Molport response into the shared cache table."""
    key = build_key(query_type, query_value)
    payload = json.dumps(response, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO API_Response_Cache (Source, Cache_Key, Response, Fetched_At, TTL_Days)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (Source, Cache_Key) DO UPDATE SET
            Response   = excluded.Response,
            Fetched_At = excluded.Fetched_At,
            TTL_Days   = excluded.TTL_Days
        """,
        (SOURCE, key, payload, _now_iso(), ttl_days),
    )
    conn.commit()


def cache_invalidate(conn: sqlite3.Connection, query_type: str, query_value: str) -> None:
    """Remove a specific cache entry (useful when a fetch produced a known-bad body)."""
    key = build_key(query_type, query_value)
    conn.execute(
        "DELETE FROM API_Response_Cache WHERE Source = ? AND Cache_Key = ?",
        (SOURCE, key),
    )
    conn.commit()


def cache_stats(conn: sqlite3.Connection) -> dict[str, int]:
    """Quick health check — counts used by pipeline log lines."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE
                WHEN (julianday('now') - julianday(Fetched_At)) <= TTL_Days THEN 1
                ELSE 0
            END) AS fresh
        FROM API_Response_Cache
        WHERE Source = ?
        """,
        (SOURCE,),
    ).fetchone()
    total, fresh = row or (0, 0)
    return {"total": total or 0, "fresh": fresh or 0, "expired": (total or 0) - (fresh or 0)}
