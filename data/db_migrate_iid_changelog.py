"""Idempotent migration: FDA_IID_Change_Log table, regulatory drift columns on Consolidation_Opportunity."""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_iid_changelog")


def _add_col(conn, table: str, col: str, typedef: str) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        logger.info(f"  + {table}.{col}")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS FDA_IID_Change_Log (
        Id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        ChangeId              INTEGER NOT NULL,
        SnapshotDate          TEXT NOT NULL,
        IngredientName        TEXT NOT NULL,
        Route                 TEXT,
        DosageForm            TEXT,
        MaxPotencyPerUnit     TEXT,
        MaxDailyExposure      TEXT,
        MaxDailyExposureUOM   TEXT,
        Status                TEXT NOT NULL CHECK(Status IN ('C','D','R')),
        CanonicalIngredientId INTEGER,
        MatchMethod           TEXT,
        MatchScore            REAL,
        IngestedAt            TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
        UNIQUE(ChangeId, SnapshotDate, Route, DosageForm)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_iid_cl_canonical ON FDA_IID_Change_Log(CanonicalIngredientId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_iid_cl_status    ON FDA_IID_Change_Log(Status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_iid_cl_changeid  ON FDA_IID_Change_Log(ChangeId)")

    _add_col(conn, "Consolidation_Opportunity", "regulatory_drift_flag", "INTEGER DEFAULT 0")
    _add_col(conn, "Consolidation_Opportunity", "regulatory_drift_reason", "TEXT")

    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_iid_changelog', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()
