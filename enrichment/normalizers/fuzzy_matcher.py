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
