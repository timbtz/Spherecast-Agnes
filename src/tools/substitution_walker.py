"""
Deterministic tool: walk Ingredient_Substitution graph for a given canonical ingredient.
Uses _ingredient_resolver for 3-stage name resolution.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext
from orchestration.tools._ingredient_resolver import resolve

_MIN_SCORE = 0.5


def run(ctx: AgnesContext) -> dict:
    payload = ctx.trigger_payload
    ingredient_name: str = payload.get("ingredient_name", "")

    resolution = resolve(ingredient_name, db_path=ctx.enriched_db_path)

    if resolution["resolution_failed"]:
        return {
            "substitutes": [],
            "ingredient_name": ingredient_name,
            "error": f"ingredient not found ({resolution.get('reason', 'no_match')})",
            "resolution": resolution,
        }

    canonical_id = resolution["canonical_id"]
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            CASE WHEN is_.IngredientAId = ? THEN is_.IngredientBId ELSE is_.IngredientAId END AS sub_id,
            ic.Name         AS substitute_name,
            ic.Grade_Flag,
            ic.SMILES,
            is_.SubstitutionType,
            is_.Score,
            is_.Notes,
            is_.Caveats
        FROM Ingredient_Substitution is_
        JOIN Ingredient_Canonical ic ON ic.Id = CASE
            WHEN is_.IngredientAId = ? THEN is_.IngredientBId ELSE is_.IngredientAId END
        WHERE (is_.IngredientAId = ? OR is_.IngredientBId = ?)
        AND is_.Score >= ?
        AND is_.SubstitutionType != 'incompatible'
        ORDER BY
            CASE is_.SubstitutionType WHEN 'identical' THEN 0 WHEN 'equivalent' THEN 1 ELSE 2 END,
            is_.Score DESC
        """,
        (canonical_id, canonical_id, canonical_id, canonical_id, _MIN_SCORE),
    ).fetchall()

    conn.close()
    return {
        "substitutes": [dict(r) for r in rows],
        "ingredient_name": ingredient_name,
        "canonical_id": canonical_id,
        "canonical_name": resolution["canonical_name"],
        "count": len(rows),
        "resolution": resolution,
    }
