"""Runtime helpers for querying `db_molport_index.sqlite`.

Purpose
-------
Anti-hallucination layer sitting between the upstream CAS→SMILES resolution
step and the scraper. Answers three questions:

1.  "Does Molport even sell a compound with this SMILES?"
    → `lookup_by_smiles(smiles) -> molport_id | None`
2.  "Build a direct URL so the scraper skips search-page parsing."
    → `product_url(molport_id) -> str`
3.  "Did the scraper actually land on the compound we asked for?"
    → `validate(molport_id, scraped_smiles) -> bool`

If the index file is missing the helper degrades gracefully — every method
returns `None` / `False` / a default URL and logs a warning. The scraper
then falls back to its original search-driven path (still functional, just
without the identity guarantee).

Build the index once per machine:

    python -m enrichment.sources.molport_index_build \
        --src "/Users/.../All Stock Compounds/SMILES" \
        --out db_molport_index.sqlite
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("agnes.molport.index")

MOLPORT_COMPOUND_URL = "https://www.molport.com/shop/compound/{molport_id}"

# Default locations tried in order until one exists.
_DEFAULT_CANDIDATES: tuple[str, ...] = (
    "db_molport_index.sqlite",
    "../db_molport_index.sqlite",
    "../../db_molport_index.sqlite",
)


class MolportIndex:
    """Thin read-only wrapper over db_molport_index.sqlite."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self._autodetect()
        self._conn: sqlite3.Connection | None = None
        if self.db_path is None or not self.db_path.exists():
            logger.warning(
                "Molport index DB not found (tried %s). "
                "Run `python -m enrichment.sources.molport_index_build --src <SMILES dir>` to build it.",
                self.db_path or _DEFAULT_CANDIDATES,
            )

    @staticmethod
    def _autodetect() -> Path | None:
        for rel in _DEFAULT_CANDIDATES:
            p = Path(rel).resolve()
            if p.exists():
                return p
        return None

    def available(self) -> bool:
        return self.db_path is not None and self.db_path.exists()

    def _connection(self) -> sqlite3.Connection | None:
        if not self.available():
            return None
        if self._conn is None:
            # uri=True + mode=ro so accidental writes raise loudly
            uri = f"file:{self.db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- lookup API --------------------------------------------------------
    def lookup_by_smiles(self, smiles: str) -> str | None:
        """Return the first Molport ID matching either raw or canonical SMILES column."""
        if not smiles:
            return None
        conn = self._connection()
        if conn is None:
            return None
        q = smiles.strip()
        row = conn.execute(
            """
            SELECT molport_id FROM compounds
             WHERE smiles = ? OR smiles_canonical = ?
             LIMIT 1
            """,
            (q, q),
        ).fetchone()
        return row[0] if row else None

    def lookup_many(self, smiles_list: Iterable[str]) -> dict[str, str | None]:
        """Batch lookup → {smiles: molport_id|None}. Useful for pre-flight."""
        out: dict[str, str | None] = {}
        for s in smiles_list:
            out[s] = self.lookup_by_smiles(s)
        return out

    def get_smiles(self, molport_id: str) -> tuple[str | None, str | None]:
        """Return (smiles, smiles_canonical) for a Molport ID."""
        if not molport_id:
            return (None, None)
        conn = self._connection()
        if conn is None:
            return (None, None)
        row = conn.execute(
            "SELECT smiles, smiles_canonical FROM compounds WHERE molport_id = ?",
            (molport_id.strip(),),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def exists(self, molport_id: str) -> bool:
        return self.get_smiles(molport_id) != (None, None)

    def validate(self, molport_id: str, scraped_smiles: str | None) -> bool:
        """True iff `molport_id` is in the index AND the scraped SMILES (if any)
        matches either the raw or canonical column for that ID.

        If `scraped_smiles` is None the check only verifies ID existence.
        """
        raw, canon = self.get_smiles(molport_id)
        if raw is None and canon is None:
            return False  # unknown Molport ID → reject
        if not scraped_smiles:
            return True
        s = scraped_smiles.strip()
        return s == (raw or "") or s == (canon or "")

    # ---- stats -------------------------------------------------------------
    def stats(self) -> dict:
        conn = self._connection()
        if conn is None:
            return {"available": False}
        total = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
        return {
            "available": True,
            "path": str(self.db_path),
            "rows": total,
        }


def product_url(molport_id: str) -> str:
    """Direct compound page URL — no search required."""
    return MOLPORT_COMPOUND_URL.format(molport_id=molport_id)
