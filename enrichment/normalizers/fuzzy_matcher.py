"""RapidFuzz-based ingredient name matcher against existing Ingredient_Canonical rows."""
import logging
import sqlite3
from pathlib import Path

from rapidfuzz import fuzz, process as fuzz_process

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

SCORE_THRESHOLD = 85   # rapidfuzz 0–100 score; below this is low-confidence
MAX_CONFIDENCE = 0.85  # cap — fuzzy match can never exceed this

logger = logging.getLogger("agnes.fuzzy")


class FuzzyMatcher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self._cache: list[tuple[int, str]] | None = None

    def match(self, name: str) -> dict | None:
        """Match name against existing Ingredient_Canonical names.

        Returns result dict with confidence, or None if no candidates exist.
        Confidence is capped at MAX_CONFIDENCE regardless of score.
        """
        canonicals = self._load_canonicals()
        if not canonicals:
            return None

        names = [c[1] for c in canonicals]
        best = fuzz_process.extractOne(
            name, names,
            scorer=fuzz.token_set_ratio,
        )
        if best is None:
            return None

        matched_name, raw_score, _ = best
        scaled_confidence = min(raw_score / 100.0 * MAX_CONFIDENCE, MAX_CONFIDENCE)
        canonical_id = next((c[0] for c in canonicals if c[1] == matched_name), None)

        return {
            "name": matched_name,
            "canonical_id": canonical_id,
            "confidence": round(scaled_confidence, 4),
            "method": "fuzzy",
            "sources": ["fuzzy_cache"],
            "fuzzy_score": raw_score,
            "flag": "manual_review" if raw_score < SCORE_THRESHOLD else None,
        }

    def _load_canonicals(self) -> list[tuple[int, str]]:
        if self._cache is not None:
            return self._cache
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("""
                SELECT DISTINCT ic.Id, ic.Name
                FROM Ingredient_Canonical ic
                UNION
                SELECT ic.Id, stc.ExtractedName
                FROM Ingredient_Canonical ic
                JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
                WHERE stc.ExtractedName IS NOT NULL
            """).fetchall()
            conn.close()
            self._cache = rows
            return rows
        except Exception as e:
            logger.error(f"Failed to load canonicals for fuzzy matching: {e}")
            return []

    def invalidate_cache(self) -> None:
        """Force reload of canonical names on next match call."""
        self._cache = None


def dedup_by_unii(conn: sqlite3.Connection) -> list[tuple[int, int, str]]:
    """Merge Ingredient_Canonical rows sharing a UNII_Code.

    Keeps the row with the lowest Id (earliest resolved). Re-points all FK references.
    Returns list of (keep_id, drop_id, unii_code) for substitution seeding.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT UNII_Code, MIN(Id) AS keep_id, GROUP_CONCAT(Id) AS all_ids,
               GROUP_CONCAT(Name, '|||') AS all_names
        FROM Ingredient_Canonical
        WHERE UNII_Code IS NOT NULL
        GROUP BY UNII_Code
        HAVING COUNT(*) > 1
    """)
    groups = cur.fetchall()
    merge_log: list[tuple[int, int, str]] = []

    for unii, keep_id, all_ids_str, all_names_str in groups:
        all_ids = [int(x) for x in all_ids_str.split(",")]
        drop_ids = [i for i in all_ids if i != keep_id]
        all_names = all_names_str.split("|||")
        drop_names = [n for i, n in zip(all_ids, all_names) if i != keep_id]

        for drop_id, drop_name in zip(drop_ids, drop_names):
            # Safety: if both rows have CAS numbers and they differ, they're provably different
            # compounds (e.g. elemental Zn vs Zinc glycinate sharing elemental UNII). Skip.
            keep_cas = cur.execute(
                "SELECT CAS_Number FROM Ingredient_Canonical WHERE Id = ?", (keep_id,)
            ).fetchone()[0]
            drop_cas = cur.execute(
                "SELECT CAS_Number FROM Ingredient_Canonical WHERE Id = ?", (drop_id,)
            ).fetchone()[0]
            if keep_cas and drop_cas and keep_cas != drop_cas:
                logger.warning(
                    f"UNII {unii}: skipping merge — CAS mismatch "
                    f"({keep_cas} vs {drop_cas}) for {drop_name!r}"
                )
                continue

            # Re-point SKU_To_Canonical; use OR IGNORE to skip conflicts (same product mapped to both)
            cur.execute(
                "UPDATE OR IGNORE SKU_To_Canonical SET CanonicalId = ? WHERE CanonicalId = ?",
                (keep_id, drop_id)
            )
            # Drop any remaining rows for drop_id (couldn't be re-pointed due to PK conflict)
            cur.execute("DELETE FROM SKU_To_Canonical WHERE CanonicalId = ?", (drop_id,))

            # Re-point Ingredient_Substitution FKs
            cur.execute(
                "UPDATE OR IGNORE Ingredient_Substitution SET IngredientAId = ? WHERE IngredientAId = ?",
                (keep_id, drop_id)
            )
            cur.execute(
                "UPDATE OR IGNORE Ingredient_Substitution SET IngredientBId = ? WHERE IngredientBId = ?",
                (keep_id, drop_id)
            )
            # Remove self-referencing rows created by the merge
            cur.execute(
                "DELETE FROM Ingredient_Substitution WHERE IngredientAId = IngredientBId"
            )

            # Remove CO row for dropped canonical (scorer re-run will regenerate with merged data)
            cur.execute(
                "DELETE FROM Consolidation_Opportunity WHERE CanonicalIngredientId = ?",
                (drop_id,)
            )

            cur.execute("DELETE FROM Ingredient_Canonical WHERE Id = ?", (drop_id,))
            merge_log.append((keep_id, drop_id, unii))
            logger.info(f"UNII {unii}: merged {drop_name!r} (Id={drop_id}) → keep Id={keep_id}")

    conn.commit()
    logger.info(f"UNII dedup complete: {len(merge_log)} canonical rows merged")
    return merge_log
