"""Backfill openfda_adverse_event_count on all UNII-bearing canonical ingredients."""
import logging
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_openfda")


def backfill_adverse_events(db_path=ENRICHED_DB) -> None:
    from enrichment.sources.openfda import OpenFDAClient
    client = OpenFDAClient(db_path)

    with sqlite3.connect(str(db_path), timeout=30) as _r:
        rows = _r.execute(
            """SELECT Id, Name, UNII_Code FROM Ingredient_Canonical
               WHERE UNII_Code IS NOT NULL AND openfda_adverse_event_count IS NULL"""
        ).fetchall()

    logger.info(f"Adverse event backfill: {len(rows)} canonicals to process")
    for canonical_id, name, unii in rows:
        count = client.adverse_event_count(unii)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE Ingredient_Canonical SET openfda_adverse_event_count = ? WHERE Id = ?",
            (count, canonical_id),
        )
        conn.execute(
            """INSERT INTO Enrichment_Run_Log
               (ProductId, Phase, Step, Status, Confidence, Method)
               VALUES (NULL, 2, 'openfda_ae_backfill', 'success', 0.95, 'openfda')"""
        )
        conn.commit()
        conn.close()
        logger.info(f"  {name} ({unii}): {count} adverse events")

    logger.info("Adverse event backfill complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill_adverse_events()
