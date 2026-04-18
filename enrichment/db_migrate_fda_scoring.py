"""Idempotent migration: FDA_Inactive_Ingredient table, Scoring_Config table,
openfda_adverse_event_count column on Ingredient_Canonical."""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_fda_scoring")


def _add_col(conn, table: str, col: str, typedef: str) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        logger.info(f"  + {table}.{col}")


def migrate(conn: sqlite3.Connection) -> None:
    # 1. FDA_Inactive_Ingredient table
    conn.execute("""CREATE TABLE IF NOT EXISTS FDA_Inactive_Ingredient (
        Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        IngredientName          TEXT NOT NULL,
        UNII                    TEXT,
        CAS_Number              TEXT,
        Route                   TEXT NOT NULL,
        DosageForm              TEXT NOT NULL,
        MaxPotencyAmount        REAL,
        MaxPotencyUnit          TEXT,
        MaxDailyExposure        REAL,
        MaxDailyExposureUnit    TEXT,
        RecordUpdated           TEXT,
        CanonicalIngredientId   INTEGER,
        Source                  TEXT DEFAULT 'fda_iid_csv',
        FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fda_iid_unii ON FDA_Inactive_Ingredient(UNII)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fda_iid_canonical ON FDA_Inactive_Ingredient(CanonicalIngredientId)")

    # 2. Scoring_Config table with defaults
    conn.execute("""CREATE TABLE IF NOT EXISTS Scoring_Config (
        Key   TEXT PRIMARY KEY,
        Value REAL NOT NULL
    )""")
    for key, default in [("weight_price", 3.0), ("weight_lead_time", 3.0), ("weight_quality", 3.0)]:
        conn.execute("INSERT OR IGNORE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, default))

    # 3. New column on Ingredient_Canonical
    _add_col(conn, "Ingredient_Canonical", "openfda_adverse_event_count", "INTEGER")

    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_fda_scoring', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()
