"""Idempotent migration: Price_Change_Alert table for price monitor pipeline."""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_price_monitor")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS Price_Change_Alert (
        Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        CanonicalIngredientId   INTEGER NOT NULL,
        SupplierId              INTEGER,
        Ingredient_Name         TEXT NOT NULL,
        Supplier_Name           TEXT,
        Previous_Price_USD      REAL,
        New_Price_USD           REAL,
        Change_Pct              REAL,
        Direction               TEXT NOT NULL,
        Severity                TEXT NOT NULL DEFAULT 'info',
        Alert_Narrative         TEXT,
        Dismissed               INTEGER NOT NULL DEFAULT 0,
        Detected_At             TEXT NOT NULL DEFAULT (datetime('now')),
        Run_Id                  TEXT,
        FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
        FOREIGN KEY (SupplierId) REFERENCES Supplier(Id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_alert_canonical ON Price_Change_Alert(CanonicalIngredientId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_alert_dismissed ON Price_Change_Alert(Dismissed, Detected_At)")
    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_price_monitor', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Price monitor migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()
