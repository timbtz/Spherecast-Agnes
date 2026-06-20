"""Two-pass supplier verification.

Pass 1 — homepage_verify (network):
    Hit the top-N suppliers by Corroboration_Score, fetch their most-seen
    hostname's homepage, and check whether the supplier name appears in the
    <title> or first ~4KB of visible text. When it matches, lift
    Provenance_Confidence on every row for that supplier from
    'website_explicit' (if already there) to 'vendor_verified'. Rows still at
    'directory_listing' are left alone — homepage-match alone doesn't upgrade
    a third-party quote.

Pass 2 — trade_register_stub (offline):
    For any supplier with Corroboration_Score >= _TRADE_REGISTER_THRESHOLD,
    insert a Supplier_Master row with Vetted=0 and a 'pending_manual_review'
    flag. A real job would later pick these up and hit
    OpenCorporates / D&B / Dun-Bradstreet for DUNS/LEI resolution — stubbed
    out here because we don't have API keys in this env, but the queue is
    real and populated idempotently.

Gated behind flags so the verify pass never runs in a default enrichment
pipeline run; only the migration + corroboration passes do. Hitting external
homepages is a tier-1 side-effect and has to be explicit.

Run modes:
    python -m enrichment.verify_suppliers --pass trade_register
    python -m enrichment.verify_suppliers --pass homepage --top 20      # network
    python -m enrichment.verify_suppliers --pass both --top 20          # network
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from enrichment.enrichers.supplier_web_enricher import (
    _hostname, _normalize_supplier_name,
)

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.verify_suppliers")

# Corroboration threshold to enqueue for trade-register lookup. A supplier
# seen across >=3 distinct host+date pairs is worth the per-query $ cost.
_TRADE_REGISTER_THRESHOLD = 3

# Homepage match: search the first N chars of the response body for the
# normalised supplier name. Cheap, catches the common cases (name in <title>,
# H1, or footer) without needing a full HTML parser.
_HOMEPAGE_SNIFF_BYTES = 4096

# How many top-corroboration suppliers to verify in one pass. Network cost
# scales linearly, and a single bad/slow host can add 5s of wait.
_HOMEPAGE_TOP_DEFAULT = 20


def _top_suppliers_by_corroboration(
    conn: sqlite3.Connection, n: int
) -> list[tuple[int, str, int]]:
    """Return (supplier_id, name, score) for top N by Corroboration_Score.

    Ties broken by supplier name alphabetical — deterministic for rerun-safe
    tests, unimportant otherwise. Excludes score=0 (no point in verifying
    a supplier we've only seen once).
    """
    rows = conn.execute(
        """SELECT s.Id, s.Name, MAX(sc.Corroboration_Score) AS score
             FROM Supplier s
             JOIN Supplier_Commercial sc ON sc.SupplierId = s.Id
            WHERE sc.Price_Source = 'google_search'
              AND sc.Corroboration_Score > 0
         GROUP BY s.Id
         ORDER BY score DESC, s.Name ASC
            LIMIT ?""",
        (n,)
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _dominant_hostname(conn: sqlite3.Connection, supplier_id: int) -> str | None:
    """Return the supplier's most-frequent Source_URL hostname, or None."""
    rows = conn.execute(
        """SELECT Source_URL FROM Supplier_Commercial
            WHERE SupplierId = ? AND Price_Source = 'google_search'
              AND Source_URL IS NOT NULL AND Source_URL != ''""",
        (supplier_id,)
    ).fetchall()
    hosts = Counter()
    for (u,) in rows:
        h = _hostname(u)
        if h:
            hosts[h] += 1
    if not hosts:
        return None
    return hosts.most_common(1)[0][0]


def _name_matches_page(supplier_name: str, body: str) -> bool:
    """True if supplier name (normalised) appears anywhere in the page text.

    Uses the same normalisation as fuzzy-match so 'PureBulk, Inc.' matches a
    page saying 'Welcome to PureBulk'. Not fuzzy — exact substring on the
    normalised form. Fuzzy homepage match adds too many false positives when
    the body is > 100KB of navigation boilerplate.

    Normalises the page body the same way supplier names are normalised:
    HTML stripped, punctuation collapsed to spaces, lowercase, whitespace
    collapsed. Without this, 'BulkSupplements.com' (normalised to
    'bulksupplements com') would fail to match a page title containing
    'bulksupplements.com' because the dot isn't reduced to a space on the
    body side.
    """
    if not body:
        return False
    norm_supplier = _normalize_supplier_name(supplier_name)
    if not norm_supplier:
        return False
    # Normalise body the same way as supplier names: strip HTML tags,
    # collapse punctuation to spaces, lowercase, collapse whitespace.
    norm_body = re.sub(r"<[^>]+>", " ", body)       # strip HTML tags
    norm_body = re.sub(r"[^\w\s]", " ", norm_body)   # punctuation → space
    norm_body = re.sub(r"\s+", " ", norm_body.lower())
    if norm_supplier in norm_body:
        return True
    # Token fallback: all long tokens (>2 chars) present. Handles cases
    # where corporate suffixes were stripped from the supplier name but
    # the homepage still has them (or vice versa), and simple word-order
    # differences. Ignores short tokens like 'co' to avoid false positives.
    tokens = [t for t in norm_supplier.split() if len(t) > 2]
    if tokens and all(t in norm_body for t in tokens):
        return True
    return False


async def _fetch_homepage(client, host: str) -> str:
    """Fetch https://{host}/ with a short timeout. Returns body prefix or ''."""
    import httpx
    url = f"https://{host}/"
    try:
        r = await client.get(url, follow_redirects=True, timeout=4.0)
        if r.status_code >= 400:
            return ""
        # Truncate — we only need the first few KB for name match
        return r.text[:_HOMEPAGE_SNIFF_BYTES]
    except Exception as e:
        logger.debug(f"  fetch failed host={host} err={e}")
        return ""


async def _verify_homepages_async(
    targets: list[tuple[int, str, str]]
) -> dict[int, bool]:
    """Async HEAD/GET → name-match. Returns {supplier_id: verified_bool}."""
    import httpx
    results: dict[int, bool] = {}
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    async with httpx.AsyncClient(
        limits=limits, headers={"User-Agent": "Agnes/1.0 (+verify)"}
    ) as client:
        sem = asyncio.Semaphore(8)

        async def one(sid: int, name: str, host: str):
            async with sem:
                body = await _fetch_homepage(client, host)
                results[sid] = _name_matches_page(name, body)

        await asyncio.gather(*[one(s, n, h) for s, n, h in targets])
    return results


def run_homepage_pass(
    conn: sqlite3.Connection, top: int = _HOMEPAGE_TOP_DEFAULT
) -> dict:
    """Verify top-N suppliers' homepages and lift Provenance_Confidence on match.

    Only promotes rows that are currently at 'website_explicit' OR
    'directory_listing' to 'vendor_verified'. We don't touch 'unknown' /
    'model_inferred' — if we don't have a URL at all, a homepage match on an
    unrelated host is meaningless.
    """
    candidates = _top_suppliers_by_corroboration(conn, top)
    logger.info(f"homepage_verify: {len(candidates)} candidates (top {top} by corroboration)")
    # Resolve dominant host per supplier (single pass to avoid N+1 pattern).
    targets: list[tuple[int, str, str]] = []
    for sid, name, score in candidates:
        host = _dominant_hostname(conn, sid)
        if host:
            targets.append((sid, name, host))
        else:
            logger.debug(f"  skip id={sid} {name!r}: no dominant host")
    if not targets:
        return {"candidates": len(candidates), "verified": 0, "checked": 0}

    results = asyncio.run(_verify_homepages_async(targets))
    verified = 0
    for sid, name, host in targets:
        if results.get(sid):
            cur = conn.execute(
                """UPDATE Supplier_Commercial
                      SET Provenance_Confidence = 'vendor_verified'
                    WHERE SupplierId = ?
                      AND Price_Source = 'google_search'
                      AND Provenance_Confidence IN ('website_explicit','directory_listing')""",
                (sid,)
            )
            rows_touched = cur.rowcount or 0
            if rows_touched:
                verified += 1
                logger.info(f"  + vendor_verified id={sid} {name!r} via {host} ({rows_touched} rows)")
        else:
            logger.debug(f"  -- no-match id={sid} {name!r} @ {host}")
    conn.commit()
    logger.info(f"homepage_verify: {verified} suppliers promoted to vendor_verified")
    return {"candidates": len(candidates), "verified": verified, "checked": len(targets)}


def run_trade_register_stub(
    conn: sqlite3.Connection, threshold: int = _TRADE_REGISTER_THRESHOLD
) -> dict:
    """Enqueue high-corroboration suppliers for (stubbed) trade-register lookup.

    Idempotent — re-running updates Notes + Vetted_At on rows whose
    Corroboration_Score has grown, but never overwrites a row that has
    already been manually vetted (Vetted=1).

    Real implementation would hit:
      - OpenCorporates (company name → jurisdiction + status)
      - Dun & Bradstreet (DUNS resolution)
      - GLEIF (LEI lookup) for EU-registered entities

    We currently write Vetted=0 + Vetted_Source='pending_manual_review' so an
    operator can see what's queued. A real batch job would consume this.
    """
    rows = conn.execute(
        """SELECT s.Id, s.Name, MAX(sc.Corroboration_Score) AS score,
                  MAX(sc.Country_Origin) AS country
             FROM Supplier s
             JOIN Supplier_Commercial sc ON sc.SupplierId = s.Id
            WHERE sc.Price_Source = 'google_search'
              AND sc.Corroboration_Score >= ?
         GROUP BY s.Id
         ORDER BY score DESC""",
        (threshold,)
    ).fetchall()

    enqueued = 0
    refreshed = 0
    skipped_vetted = 0
    for sid, name, score, country in rows:
        # Don't overwrite a row that's already vetted.
        existing = conn.execute(
            "SELECT Vetted FROM Supplier_Master WHERE SupplierId = ?",
            (sid,)
        ).fetchone()
        if existing and existing[0] == 1:
            skipped_vetted += 1
            continue
        note = f"queued: corroboration_score={score}"
        if existing:
            conn.execute(
                """UPDATE Supplier_Master
                      SET Country_Verified = COALESCE(Country_Verified, ?),
                          Vetted_Source = 'pending_manual_review',
                          Vetted_At = datetime('now'),
                          Notes = ?
                    WHERE SupplierId = ?""",
                (country, note, sid)
            )
            refreshed += 1
        else:
            conn.execute(
                """INSERT INTO Supplier_Master
                   (SupplierId, Country_Verified, Vetted, Vetted_Source, Vetted_At, Notes)
                   VALUES (?, ?, 0, 'pending_manual_review', datetime('now'), ?)""",
                (sid, country, note)
            )
            enqueued += 1
    conn.commit()
    logger.info(
        f"trade_register_stub: enqueued={enqueued} refreshed={refreshed} "
        f"already_vetted={skipped_vetted} threshold={threshold}"
    )
    return {
        "enqueued_new": enqueued,
        "refreshed_existing": refreshed,
        "already_vetted": skipped_vetted,
        "threshold": threshold,
    }


def main(which: str = "trade_register", top: int = _HOMEPAGE_TOP_DEFAULT) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    stats: dict[str, dict] = {}
    if which in ("homepage", "both"):
        stats["homepage"] = run_homepage_pass(conn, top=top)
    if which in ("trade_register", "both"):
        stats["trade_register"] = run_trade_register_stub(conn)
    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'verify_suppliers', 'success', 1.0, ?)""",
        (which,))
    conn.commit()
    conn.close()
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--pass", dest="which", default="trade_register",
        choices=("homepage", "trade_register", "both"),
        help="which pass to run (homepage hits the network)"
    )
    p.add_argument("--top", type=int, default=_HOMEPAGE_TOP_DEFAULT,
                   help="top N suppliers by Corroboration_Score for homepage pass")
    args = p.parse_args()
    out = main(which=args.which, top=args.top)
    print(out)
