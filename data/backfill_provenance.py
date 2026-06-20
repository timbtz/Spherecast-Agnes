"""Backfill script for provenance/archetype/corroboration on existing rows.

Three independent passes. Each pass is idempotent — rerunning overwrites
the relevant columns from scratch, but leaves the rest of the row alone.

Passes:
    1. url_archetype    — classify existing Source_URL into URL_Archetype
                          (directory_listing/distributor/lab_reagent/
                          manufacturer_direct/unknown). Read-only on other
                          fields.
    2. provenance       — re-derive Provenance_Confidence given the current
                          URL_Archetype, Country_Origin, and Evidence_Snippet.
                          Useful after the archetype pass lands new values.
    3. corroboration    — Corroboration_Score per supplier, computed as
                          (distinct URL hostnames) + (distinct UTC dates) - 2.
                          Floors at 0. Written back to every row for that
                          supplier.
    4. url_health       — issue async HEAD requests (2s timeout, pooled) and
                          set URL_Health to ok/stale/unreachable. Disabled
                          unless --check-urls is passed; hits the network.

Run modes:
    python -m enrichment.backfill_provenance              # all passes except URL health
    python -m enrichment.backfill_provenance --check-urls # include URL health checks
    python -m enrichment.backfill_provenance --only archetype
    python -m enrichment.backfill_provenance --only corroboration
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from enrichment.enrichers.supplier_web_enricher import (
    _classify_archetype, _classify_provenance, _hostname,
)

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_provenance")


def backfill_archetype(conn: sqlite3.Connection) -> int:
    """Set URL_Archetype for every google_search row based on Source_URL."""
    rows = conn.execute(
        """SELECT rowid, Source_URL FROM Supplier_Commercial
           WHERE Price_Source = 'google_search'"""
    ).fetchall()
    updated = 0
    for rowid, url in rows:
        archetype = _classify_archetype(url)
        conn.execute(
            "UPDATE Supplier_Commercial SET URL_Archetype = ? WHERE rowid = ?",
            (archetype, rowid)
        )
        updated += 1
    conn.commit()
    logger.info(f"archetype pass: {updated} rows updated")
    return updated


def backfill_provenance(conn: sqlite3.Connection) -> int:
    """Re-derive Provenance_Confidence for every google_search row.

    Needs URL_Archetype already set (run backfill_archetype first).

    Skips rows that have already been promoted to 'vendor_verified' by
    verify_suppliers.run_homepage_pass — that signal comes from an
    independent homepage check, and the URL-pattern classifier used here
    can't recover it. Without this guard, running backfill after verify
    would demote vendor_verified back to website_explicit.
    """
    rows = conn.execute(
        """SELECT rowid, Source_URL, Country_Origin, Evidence_Snippet,
                  URL_Archetype, Provenance_Confidence
           FROM Supplier_Commercial
           WHERE Price_Source = 'google_search'"""
    ).fetchall()
    updated = 0
    preserved = 0
    for rowid, url, country, evidence, archetype, current in rows:
        if current == 'vendor_verified':
            preserved += 1
            continue
        provenance = _classify_provenance(
            url, country is not None and country != "", evidence, archetype or "unknown"
        )
        conn.execute(
            "UPDATE Supplier_Commercial SET Provenance_Confidence = ? WHERE rowid = ?",
            (provenance, rowid)
        )
        updated += 1
    conn.commit()
    logger.info(
        f"provenance pass: {updated} rows updated, {preserved} vendor_verified preserved"
    )
    return updated


def backfill_corroboration(conn: sqlite3.Connection) -> int:
    """Corroboration_Score per supplier.

    Formula: (distinct URL hostnames) + (distinct UTC dates) - 2, floored at 0.
    A supplier with 1 URL seen on 1 day scores 0. Diversity of sources OR
    diversity of refresh dates increases the score. Written to every row for
    that supplier so the score is available per-row without a join.
    """
    rows = conn.execute(
        """SELECT SupplierId, Source_URL, Last_Updated FROM Supplier_Commercial
           WHERE Price_Source = 'google_search' AND SupplierId IS NOT NULL"""
    ).fetchall()

    per_supplier_hosts: dict[int, set[str]] = defaultdict(set)
    per_supplier_dates: dict[int, set[str]] = defaultdict(set)
    for sid, url, last_updated in rows:
        host = _hostname(url)
        if host:
            per_supplier_hosts[sid].add(host)
        if last_updated:
            per_supplier_dates[sid].add(last_updated[:10])  # YYYY-MM-DD

    updated = 0
    for sid in set(per_supplier_hosts) | set(per_supplier_dates):
        hosts = len(per_supplier_hosts.get(sid, set()))
        dates = len(per_supplier_dates.get(sid, set()))
        score = max(0, hosts + dates - 2)
        conn.execute(
            """UPDATE Supplier_Commercial
               SET Corroboration_Score = ?
               WHERE SupplierId = ? AND Price_Source = 'google_search'""",
            (score, sid)
        )
        updated += 1
    conn.commit()
    logger.info(f"corroboration pass: {updated} suppliers scored")
    return updated


async def _check_url(client, url: str) -> str:
    """Return 'ok' | 'stale' | 'unreachable' for a single URL."""
    try:
        r = await client.head(url, follow_redirects=True, timeout=2.0)
    except Exception:
        # Some servers reject HEAD — retry with GET but bail fast
        try:
            r = await client.get(url, follow_redirects=True, timeout=2.0)
        except Exception:
            return "unreachable"
    if r.status_code >= 500 or r.status_code in (404, 410, 451):
        return "stale"
    if r.status_code >= 400:
        return "stale"
    return "ok"


async def _check_urls_async(urls: list[tuple[int, str]]) -> dict[int, str]:
    """Return {rowid: health} for a batch of (rowid, url) pairs."""
    import httpx
    results: dict[int, str] = {}
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    async with httpx.AsyncClient(limits=limits, headers={"User-Agent": "Agnes/1.0"}) as client:
        sem = asyncio.Semaphore(10)

        async def one(rowid: int, url: str):
            async with sem:
                results[rowid] = await _check_url(client, url)

        await asyncio.gather(*[one(rid, u) for rid, u in urls])
    return results


def backfill_url_health(conn: sqlite3.Connection, limit: int | None = None) -> int:
    """Async HEAD-check every Source_URL and set URL_Health.

    Expensive — makes O(N) outbound requests. Gated by --check-urls flag.
    """
    q = """SELECT rowid, Source_URL FROM Supplier_Commercial
           WHERE Price_Source = 'google_search'
             AND Source_URL IS NOT NULL AND Source_URL != ''"""
    rows = conn.execute(q).fetchall()
    if limit:
        rows = rows[:limit]
    if not rows:
        logger.info("url_health pass: no rows with Source_URL")
        return 0
    logger.info(f"url_health pass: checking {len(rows)} URLs (async, max 10 concurrent)")
    results = asyncio.run(_check_urls_async([(r[0], r[1]) for r in rows]))
    for rowid, health in results.items():
        conn.execute(
            "UPDATE Supplier_Commercial SET URL_Health = ? WHERE rowid = ?",
            (health, rowid)
        )
    conn.commit()
    by_health: dict[str, int] = defaultdict(int)
    for h in results.values():
        by_health[h] += 1
    logger.info(f"url_health pass: {dict(by_health)}")
    return len(results)


def main(only: str | None = None, check_urls: bool = False,
         url_limit: int | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    stats: dict[str, int] = {}

    passes = only.split(",") if only else ["archetype", "provenance", "corroboration"]
    if check_urls or (only and "url_health" in passes):
        if "url_health" not in passes:
            passes.append("url_health")

    if "archetype" in passes:
        stats["archetype_updated"] = backfill_archetype(conn)
    if "provenance" in passes:
        stats["provenance_updated"] = backfill_provenance(conn)
    if "corroboration" in passes:
        stats["corroboration_suppliers"] = backfill_corroboration(conn)
    if "url_health" in passes:
        stats["url_health_checked"] = backfill_url_health(conn, limit=url_limit)

    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'backfill_provenance', 'success', 1.0, 'migration')""")
    conn.commit()
    conn.close()
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated passes: archetype,provenance,corroboration,url_health")
    p.add_argument("--check-urls", action="store_true", help="include URL health checks (network)")
    p.add_argument("--url-limit", type=int, default=None, help="cap URL health check at N rows")
    args = p.parse_args()
    result = main(only=args.only, check_urls=args.check_urls, url_limit=args.url_limit)
    print(result)
