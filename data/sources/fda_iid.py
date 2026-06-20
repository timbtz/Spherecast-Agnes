"""Load FDA Inactive Ingredient Database CSVs into FDA_Inactive_Ingredient table."""
import csv
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
CSV_DIR = ROOT / "Orchestration" / "Data" / "api"
IIR_CSV = CSV_DIR / "IIR_OCOMM.csv"

logger = logging.getLogger("agnes.fda_iid")


def _float_or_none(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_iir(db_path=ENRICHED_DB) -> int:
    """Load IIR_OCOMM.csv into FDA_Inactive_Ingredient. Returns row count inserted."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Build UNII → CanonicalIngredientId lookup from existing canonicals
    unii_map: dict[str, int] = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT UNII_Code, Id FROM Ingredient_Canonical WHERE UNII_Code IS NOT NULL"
        ).fetchall()
    }
    logger.info(f"UNII map: {len(unii_map)} known canonicals")

    inserted = 0
    with open(IIR_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            unii = row.get("UNII", "").strip() or None
            canonical_id = unii_map.get(unii) if unii else None
            conn.execute(
                """INSERT OR IGNORE INTO FDA_Inactive_Ingredient
                   (IngredientName, UNII, CAS_Number, Route, DosageForm,
                    MaxPotencyAmount, MaxPotencyUnit, MaxDailyExposure,
                    MaxDailyExposureUnit, RecordUpdated, CanonicalIngredientId)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["INGREDIENT_NAME"].strip(),
                    unii,
                    row.get("CAS_NUMBER", "").strip() or None,
                    row["ROUTE"].strip(),
                    row["DOSAGE_FORM"].strip(),
                    _float_or_none(row.get("POTENCY_AMOUNT", "")),
                    row.get("POTENCY_UNIT", "").strip() or None,
                    _float_or_none(row.get("MAXIMUM_DAILY_EXPOSURE", "")),
                    row.get("MAXIMUM_DAILY_EXPOSURE_UNIT", "").strip() or None,
                    row.get("RECORD_UPDATED", "").strip() or None,
                    canonical_id,
                ),
            )
            inserted += 1
    conn.commit()

    matched = conn.execute(
        "SELECT COUNT(*) FROM FDA_Inactive_Ingredient WHERE CanonicalIngredientId IS NOT NULL"
    ).fetchone()[0]
    logger.info(f"Inserted {inserted} IIR rows; {matched} matched to canonical ingredients")
    conn.execute(
        """INSERT INTO Enrichment_Run_Log
           (ProductId, Phase, Step, Status, Confidence, Method)
           VALUES (NULL, 1, 'fda_iid_load', 'success', 1.0, 'csv_import')"""
    )
    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = load_iir()
    print(f"Loaded {n} IIR rows.")
