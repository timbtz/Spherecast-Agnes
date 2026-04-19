"""
Migration: create Supplier_Master table for GLEIF entity verification cache.
Idempotent — safe to re-run.
"""
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "db_enriched.sqlite"


def migrate(db_path: Path = _DB_PATH) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Supplier_Master (
            SupplierId        INTEGER PRIMARY KEY,
            DUNS              TEXT,
            LEI               TEXT,
            OpenCorporatesId  TEXT,
            Country_Verified  TEXT,
            Legal_Name        TEXT,
            GLEIF_Status      TEXT,
            Vetted            INTEGER DEFAULT 0,
            Vetted_Source     TEXT,
            Vetted_At         TEXT,
            Notes             TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("Supplier_Master table ensured.")


if __name__ == "__main__":
    migrate()
