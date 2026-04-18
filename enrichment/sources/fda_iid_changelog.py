"""Load FDA IID Change_Log_Data.csv into FDA_IID_Change_Log table."""
import csv
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from rapidfuzz import fuzz, process

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
CSV_DIR = ROOT / "Orchestration" / "Data" / "api"
CHANGELOG_CSV = CSV_DIR / "Change_Log_Data.csv"

logger = logging.getLogger("agnes.fda_iid_changelog")


def load_iid_changelog(db_path=ENRICHED_DB, csv_path=None) -> int:
    """Load Change_Log_Data.csv into FDA_IID_Change_Log. Returns rows processed."""
    csv_path = Path(csv_path) if csv_path else CHANGELOG_CSV
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Build lowercase name → canonical_id lookup
    name_map: dict[str, int] = {
        row[0].lower(): row[1]
        for row in conn.execute("SELECT Name, Id FROM Ingredient_Canonical").fetchall()
    }
    name_keys = list(name_map.keys())
    logger.info(f"Canonical name map: {len(name_map)} entries")

    processed = 0
    matched = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_name = row["Inactive Ingredient"].strip()
            name_lower = raw_name.lower()

            canonical_id = None
            match_method = None
            match_score = None

            exact = name_map.get(name_lower)
            if exact is not None:
                canonical_id = exact
                match_method = "exact"
                match_score = 1.0
            else:
                result = process.extractOne(name_lower, name_keys, scorer=fuzz.token_sort_ratio, score_cutoff=80)
                if result is not None:
                    matched_key, score, _ = result
                    canonical_id = name_map[matched_key]
                    match_method = "fuzzy"
                    match_score = score / 100.0

            if canonical_id is not None:
                matched += 1

            conn.execute(
                """INSERT OR IGNORE INTO FDA_IID_Change_Log
                   (ChangeId, SnapshotDate, IngredientName, Route, DosageForm,
                    MaxPotencyPerUnit, MaxDailyExposure, MaxDailyExposureUOM,
                    Status, CanonicalIngredientId, MatchMethod, MatchScore)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(row["Change ID"]),
                    row["Snapshot Date"].strip(),
                    raw_name,
                    row["Route of Administration"].strip() or None,
                    row["Dosage Form"].strip() or None,
                    row["Maximum Potency per Unit Dose"].strip() or None,
                    row["Maximum Daily Exposure"].strip() or None,
                    row["Maximum Daily Exposure UOM"].strip() or None,
                    row["Status"].strip(),
                    canonical_id,
                    match_method,
                    match_score,
                ),
            )
            processed += 1

    conn.commit()
    logger.info(f"Processed {processed} rows; {matched} matched to canonical ingredients")

    conn.execute(
        """INSERT INTO Enrichment_Run_Log
           (ProductId, Phase, Step, Status, Confidence, Method)
           VALUES (NULL, 1, 'fda_iid_changelog_load', 'success', 1.0, 'csv_import')"""
    )
    conn.commit()
    conn.close()
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = load_iid_changelog()
    print(f"Processed {n} changelog rows.")
