"""Run UNII dedup and seed Ingredient_Substitution edges. Safe to re-run (idempotent)."""
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)

from enrichment.normalizers.fuzzy_matcher import dedup_by_unii
from reasoning.substitution_graph import seed_substitutions_from_unii_history

conn = sqlite3.connect(ROOT / "db_enriched.sqlite")
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")

merge_log = dedup_by_unii(conn)
seed_substitutions_from_unii_history(conn, merge_log)

conn.close()
print(f"Done. Merged {len(merge_log)} canonical pairs.")
