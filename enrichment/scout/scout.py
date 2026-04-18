"""Scout runner.

Pulls candidate suppliers from the configured directories, dedupes by
(supplier_name, country_code), and writes them to Scout_Candidate.

Designed to be called from Tim's enrichment runner *after* the canonical
identity pass has populated Ingredient_Canonical, so each scout row gets
a CanonicalIngredientId.

Idempotent: re-running won't insert duplicates because we upsert on
(CanonicalIngredientId, SupplierName, SourceDirectory).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .directories import DIRECTORIES, load_user_seed


@dataclass
class ScoutRequest:
    canonical_id: int
    canonical_name: str
    directories: List[str]


@dataclass
class ScoutSummary:
    requested: int
    inserted: int
    skipped_duplicate: int
    errors: List[str]


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
) -> ScoutSummary:
    user_seed = load_user_seed(user_seed_path)
    summary = ScoutSummary(requested=0, inserted=0, skipped_duplicate=0, errors=[])

    for req in requests:
        summary.requested += 1
        rows: List[Dict] = []

        # User seed first (highest trust).
        rows.extend(user_seed.get(req.canonical_name.lower(), []))

        for dname in req.directories:
            adapter = DIRECTORIES.get(dname)
            if adapter is None:
                summary.errors.append(f"unknown_directory:{dname}")
                continue
            try:
                rows.extend(adapter(req.canonical_name))
            except Exception as e:  # noqa: BLE001
                summary.errors.append(f"{dname}:{type(e).__name__}:{e}")

        seen = set()
        for row in rows:
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
