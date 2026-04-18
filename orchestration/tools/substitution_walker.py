"""
Deterministic tool: walk Ingredient_Substitution graph for a given canonical ingredient.
Returns scored substitution candidates (identical > equivalent > partial).
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext

_MIN_SCORE = 0.5


def run(ctx: AgnesContext) -> dict:
    payload = ctx.trigger_payload
    ingredient_name: str = payload.get("ingredient_name", "")

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
        (ingredient_name,),
    ).fetchone()

    if not row:
        conn.close()
        return {"substitutes": [], "ingredient_name": ingredient_name}

    canonical_id = row["Id"]

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
        "count": len(rows),
    }
