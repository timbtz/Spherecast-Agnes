"""Phase 4: Build Ingredient_Substitution edges from curated rules + canonical data."""
import json
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.substitution_graph")


class SubstitutionGraphBuilder:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        self._apply_curated_rules(conn)
        self._apply_identical_cas_edges(conn)
        conn.commit()
        conn.close()

        count = sqlite3.connect(self.db_path).execute(
            "SELECT COUNT(*) FROM Ingredient_Substitution"
        ).fetchone()[0]
        logger.info(f"Substitution graph built: {count} edges")

    def _apply_curated_rules(self, conn: sqlite3.Connection) -> None:
        """Translate Ingredient_Substitution_Rule rows into Ingredient_Substitution edges."""
        rules = conn.execute(
            "SELECT Name_A, Name_B, Rule_Type, Confidence, Justification, Source "
            "FROM Ingredient_Substitution_Rule"
        ).fetchall()

        inserted = 0
        for name_a, name_b, rule_type, confidence, justification, source in rules:
            id_a = self._canonical_id(conn, name_a)
            id_b = self._canonical_id(conn, name_b)
            if id_a is None or id_b is None:
                logger.debug(f"Skipping rule '{name_a}' ↔ '{name_b}': one or both not in canonical table")
                continue

            sources_json = json.dumps([source])
            conn.execute(
                """INSERT OR REPLACE INTO Ingredient_Substitution
                   (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (id_a, id_b, rule_type, confidence, justification, sources_json),
            )
            # Insert reverse edge too
            conn.execute(
                """INSERT OR REPLACE INTO Ingredient_Substitution
                   (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (id_b, id_a, rule_type, confidence, justification, sources_json),
            )
            inserted += 2
        logger.info(f"Applied {inserted} curated substitution edges ({inserted // 2} rules)")

    def _apply_identical_cas_edges(self, conn: sqlite3.Connection) -> None:
        """Add identical edges for canonical ingredients sharing the same CAS number."""
        rows = conn.execute(
            """SELECT a.Id, b.Id
               FROM Ingredient_Canonical a
               JOIN Ingredient_Canonical b ON b.CAS_Number = a.CAS_Number AND b.Id != a.Id
               WHERE a.CAS_Number IS NOT NULL"""
        ).fetchall()

        inserted = 0
        for id_a, id_b in rows:
            conn.execute(
                """INSERT OR IGNORE INTO Ingredient_Substitution
                   (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
                   VALUES (?, ?, 'identical', 1.0, 'Same CAS number', '["cas_match"]')""",
                (id_a, id_b),
            )
            inserted += 1
        if inserted:
            logger.info(f"Added {inserted} identical-CAS substitution edges")

    def _canonical_id(self, conn: sqlite3.Connection, name: str) -> int | None:
        row = conn.execute(
            "SELECT Id FROM Ingredient_Canonical WHERE Name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return row[0] if row else None


def seed_substitutions_from_unii_history(
    conn: sqlite3.Connection,
    merge_log: list[tuple[int, int, str]],
) -> None:
    """Seed Ingredient_Substitution rows for pairs merged during UNII dedup.

    merge_log: list of (keep_id, drop_id, unii_code) from dedup_by_unii().
    drop_id is deleted from Ingredient_Canonical during dedup, so we can't
    reference it as an FK. We log the merge instead and skip edge insertion.
    Inserts self-referential notes on the kept canonical only.
    """
    existing_ids = {
        r[0] for r in conn.execute("SELECT Id FROM Ingredient_Canonical")
    }
    skipped = 0
    inserted = 0
    for keep_id, drop_id, unii in merge_log:
        if keep_id not in existing_ids or drop_id not in existing_ids:
            # drop_id was deleted — can't FK-reference it; record in log only
            skipped += 1
            continue
        conn.execute(
            """INSERT OR REPLACE INTO Ingredient_Substitution
               (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
               VALUES (?, ?, 'identical', 1.0, ?, '["unii_dedup"]')""",
            (keep_id, drop_id, f"Same UNII: {unii}"),
        )
        conn.execute(
            """INSERT OR REPLACE INTO Ingredient_Substitution
               (IngredientAId, IngredientBId, SubstitutionType, Score, Notes, Sources)
               VALUES (?, ?, 'identical', 1.0, ?, '["unii_dedup"]')""",
            (drop_id, keep_id, f"Same UNII: {unii}"),
        )
        inserted += 2
    conn.commit()
    if skipped:
        logger.info(f"Skipped {skipped} dedup pairs (drop_id deleted — expected)")
    logger.info(f"Seeded {inserted} substitution edges from UNII dedup merge log")
