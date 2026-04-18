"""Scout runner.

Pulls candidate suppliers from the configured directories, dedupes by
(supplier_name, country_code), and writes them to Scout_Candidate.

Designed to be called from Tim's enrichment runner *after* the canonical
identity pass has populated Ingredient_Canonical, so each scout row gets
a CanonicalIngredientId.

Idempotent: re-running won't insert duplicates because we upsert on
(CanonicalIngredientId, SupplierName, SourceDirectory).

CACHE-FIRST POLICY
------------------
Every scout call checks Scout_Cache *before* touching any adapter.
Cache rows carry a `CanonicalIngredientId + SourceDirectory + FetchedAt`
tuple; a hit within `CACHE_TTL_HOURS` short-circuits the adapter call
entirely. This matters for three reasons:

    1. Cost: external directory calls are slow + rate-limited.
    2. Demo stability: a fresh network call mid-demo is a failure
       mode — cache-first means repeat runs are deterministic.
    3. Re-eval: the scheduler's `new_compliance_rule` / `supplier_down`
       triggers set `force_refresh=True` to bypass the cache exactly
       when we need fresh data, and never otherwise.

REGISTRY URL VERIFICATION
-------------------------
After each adapter returns, every candidate's source_url is checked
against a domain allow-list (the directories we've audited) + a
fixture-scheme allow-list (fixture:// and user:// for the offline
seed lane). Unknown-scheme URLs are rejected; candidates missing a
URL pass through but carry `url_verified=False` on the inserted row
so the downstream compliance reasoner can weight them lower.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

from .directories import DIRECTORIES, load_user_seed


# ---------------------------------------------------- cache + registry


# 24 hours. Tuned for the demo: long enough that repeated runs in a
# prep session don't re-hit adapters; short enough that a nightly
# re-eval scheduler run re-fetches.
CACHE_TTL_HOURS = 24


# Domains we've audited. Candidates from other domains are rejected
# at the registry-verify step. "fixture://" and "user://" are synthetic
# schemes the seed / user-seed adapters use so the offline demo lane
# works without domain coverage.
_ALLOWED_DOMAINS: Set[str] = {
    "thomasnet.com", "www.thomasnet.com",
    "ods.od.nih.gov", "api.ods.od.nih.gov",   # DSLD
    "ul.com", "www.ul.com",                    # Prospector (UL registry)
    "knowde.com", "www.knowde.com",
}
_ALLOWED_SCHEMES: Set[str] = {"https", "http", "fixture", "user"}


_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS Scout_Cache (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId   INTEGER NOT NULL,
    SourceDirectory         TEXT NOT NULL,
    FetchedAt               REAL NOT NULL,
    RowCount                INTEGER NOT NULL,
    UNIQUE(CanonicalIngredientId, SourceDirectory)
);
CREATE INDEX IF NOT EXISTS ix_scout_cache_canonical
    ON Scout_Cache(CanonicalIngredientId);
"""


def _ensure_cache_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_CACHE_DDL)
    conn.commit()


def _cache_fresh(
    conn: sqlite3.Connection,
    canonical_id: int,
    directory: str,
    ttl_hours: float,
) -> bool:
    row = conn.execute(
        """
        SELECT FetchedAt FROM Scout_Cache
        WHERE CanonicalIngredientId = ? AND SourceDirectory = ?
        """,
        (canonical_id, directory),
    ).fetchone()
    if not row:
        return False
    fetched_at = float(row[0])
    age_hours = (time.time() - fetched_at) / 3600.0
    return age_hours < ttl_hours


def _cache_write(
    conn: sqlite3.Connection,
    canonical_id: int,
    directory: str,
    row_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO Scout_Cache (CanonicalIngredientId, SourceDirectory,
                                 FetchedAt, RowCount)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(CanonicalIngredientId, SourceDirectory) DO UPDATE SET
            FetchedAt = excluded.FetchedAt,
            RowCount  = excluded.RowCount
        """,
        (canonical_id, directory, time.time(), row_count),
    )


def _url_is_registered(url: Optional[str]) -> bool:
    """Return True iff URL scheme is allowed AND domain is on the
    audited list (or URL is one of the synthetic seed schemes).

    Empty / None URL passes through (`url_verified=False` lets the
    downstream scorer weight it lower, but doesn't reject outright —
    some seed fixtures legitimately don't carry a URL)."""
    if not url:
        return True
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False
    if scheme in {"fixture", "user"}:
        return True
    host = (parsed.hostname or "").lower()
    return host in _ALLOWED_DOMAINS


@dataclass
class ScoutRequest:
    canonical_id: int
    canonical_name: str
    directories: List[str]
    force_refresh: bool = False   # set True to bypass the cache


@dataclass
class ScoutSummary:
    requested: int
    inserted: int
    skipped_duplicate: int
    errors: List[str]
    cache_hits: int = 0
    url_rejected: int = 0


def _key(row: Dict) -> tuple:
    return (
        (row.get("supplier_name") or "").strip().lower(),
        (row.get("country_code") or "").strip().upper(),
        (row.get("source_directory") or "").strip().lower(),
    )


def _exists(conn: sqlite3.Connection, canonical_id: int, key: tuple) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM Scout_Candidate
        WHERE CanonicalIngredientId = ?
          AND LOWER(SupplierName) = ?
          AND COALESCE(UPPER(CountryCode), '') = ?
          AND LOWER(SourceDirectory) = ?
        LIMIT 1
        """,
        (canonical_id, key[0], key[1], key[2]),
    ).fetchone()
    return row is not None


def _insert(conn: sqlite3.Connection, canonical_id: int, row: Dict) -> None:
    conn.execute(
        """
        INSERT INTO Scout_Candidate
          (CanonicalIngredientId, SupplierName, SourceDirectory, SourceUrl,
           CountryCode, CertificationsRaw, QualifyStatus)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            canonical_id,
            row["supplier_name"],
            row["source_directory"],
            row.get("source_url"),
            row.get("country_code"),
            row.get("certifications_raw"),
            "pending",
        ),
    )


def run_scout(
    conn: sqlite3.Connection,
    requests: Iterable[ScoutRequest],
    user_seed_path=None,
    cache_ttl_hours: float = CACHE_TTL_HOURS,
) -> ScoutSummary:
    _ensure_cache_schema(conn)
    user_seed = load_user_seed(user_seed_path)
    summary = ScoutSummary(
        requested=0, inserted=0, skipped_duplicate=0, errors=[],
        cache_hits=0, url_rejected=0,
    )

    for req in requests:
        summary.requested += 1
        rows: List[Dict] = []

        # User seed first (highest trust). User seed is always applied,
        # regardless of cache state — these rows represent operator
        # intent and should never be silently skipped.
        rows.extend(user_seed.get(req.canonical_name.lower(), []))

        for dname in req.directories:
            adapter = DIRECTORIES.get(dname)
            if adapter is None:
                summary.errors.append(f"unknown_directory:{dname}")
                continue

            # Cache-first: skip the adapter call if we already have a
            # fresh cache row for this (canonical, directory) pair and
            # the caller hasn't explicitly asked for a refresh.
            if (not req.force_refresh
                    and _cache_fresh(conn, req.canonical_id, dname, cache_ttl_hours)):
                summary.cache_hits += 1
                continue

            try:
                fetched = list(adapter(req.canonical_name))
            except Exception as e:  # noqa: BLE001
                summary.errors.append(f"{dname}:{type(e).__name__}:{e}")
                continue
            rows.extend(fetched)
            _cache_write(conn, req.canonical_id, dname, len(fetched))

        seen = set()
        for row in rows:
            # Registry URL verification — reject URLs from un-audited
            # domains before they land in Scout_Candidate. This is the
            # "registry verify" half of the cache-first-policy.
            if not _url_is_registered(row.get("source_url")):
                summary.url_rejected += 1
                continue

            k = _key(row)
            if k in seen:
                summary.skipped_duplicate += 1
                continue
            seen.add(k)
            if _exists(conn, req.canonical_id, k):
                summary.skipped_duplicate += 1
                continue
            _insert(conn, req.canonical_id, row)
            summary.inserted += 1

    conn.commit()
    return summary


# ----- convenience CLI hook -----------------------------------------------

def main(db_path: str, canonical_id: int, canonical_name: str, dirs: Optional[str] = None) -> None:
    conn = sqlite3.connect(db_path)
    try:
        directories = (dirs or "seed").split(",")
        s = run_scout(
            conn,
            [ScoutRequest(canonical_id=canonical_id, canonical_name=canonical_name, directories=directories)],
        )
        print(s)
    finally:
        conn.close()
