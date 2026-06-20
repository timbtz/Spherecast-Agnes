"""Run FDA IID change log migration and CSV ingestion."""
import logging
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import enrichment.db_migrate_iid_changelog as migration
import enrichment.sources.fda_iid_changelog as changelog_loader

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migration.migrate(conn)
    conn.close()

    n = changelog_loader.load_iid_changelog(ENRICHED_DB)

    import sqlite3 as _sq
    c = _sq.connect(str(ENRICHED_DB))
    total, matched = c.execute(
        "SELECT COUNT(*), SUM(CASE WHEN CanonicalIngredientId IS NOT NULL THEN 1 END) FROM FDA_IID_Change_Log"
    ).fetchone()
    statuses = dict(c.execute("SELECT Status, COUNT(*) FROM FDA_IID_Change_Log GROUP BY Status").fetchall())
    c.close()

    print(f"Processed {n} rows. DB total: {total}, matched to canonical: {matched}")
    print(f"Status breakdown: {statuses}")
