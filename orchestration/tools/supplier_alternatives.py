"""
Deterministic tool: find ranked alternative suppliers for a given canonical ingredient.
Reads from db_enriched.sqlite Supplier_Commercial and Ingredient_Canonical.
"""
import json
import sqlite3

from orchestration.api.agnes_context import AgnesContext


def run(ctx: AgnesContext) -> dict:
    payload = ctx.trigger_payload
    ingredient_name: str = payload.get("ingredient_name", "")
    exclude_supplier_id: int | None = payload.get("exclude_supplier_id")

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # Resolve canonical ID from name
    row = conn.execute(
        "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
        (ingredient_name,),
    ).fetchone()

    if not row:
        conn.close()
        return {"alternatives": [], "ingredient_name": ingredient_name, "error": "ingredient not found"}

    canonical_id = row["Id"]

    query = """
        SELECT
            sc.SupplierId,
            s.Name               AS supplier_name,
            sc.Price_USD_Per_KG,
            sc.MOQ_KG,
            sc.Lead_Time_Days,
            sc.Country_Origin,
            sc.Purity_Pct,
            sc.Purity_Qualifier,
            sc.Confidence,
            sc.Price_Type,
            sc.Last_Updated
        FROM Supplier_Commercial sc
        JOIN Supplier s ON s.Id = sc.SupplierId
        WHERE sc.CanonicalIngredientId = ?
        AND sc.Confidence >= 0.5
        {exclude_clause}
        ORDER BY sc.Price_USD_Per_KG ASC NULLS LAST, sc.Confidence DESC
    """
    exclude_clause = "AND sc.SupplierId != ?" if exclude_supplier_id else ""
    params = [canonical_id]
    if exclude_supplier_id:
        params.append(exclude_supplier_id)

    rows = conn.execute(query.format(exclude_clause=exclude_clause), params).fetchall()
    conn.close()

    alternatives = [dict(r) for r in rows]
    return {
        "alternatives": alternatives,
        "canonical_id": canonical_id,
        "ingredient_name": ingredient_name,
        "count": len(alternatives),
    }
