"""
Deterministic tool: find ranked alternative suppliers for a given canonical ingredient.
Uses _ingredient_resolver for 3-stage name resolution.
Joins Supplier_Master for GLEIF vetting state when available.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext
from orchestration.tools._ingredient_resolver import resolve


def run(ctx: AgnesContext) -> dict:
    payload = ctx.trigger_payload
    ingredient_name: str = payload.get("ingredient_name", "")
    exclude_supplier_id: int | None = payload.get("exclude_supplier_id")

    resolution = resolve(ingredient_name, db_path=ctx.enriched_db_path)

    if resolution["resolution_failed"]:
        return {
            "alternatives": [],
            "ingredient_name": ingredient_name,
            "error": f"ingredient not found ({resolution.get('reason', 'no_match')})",
            "resolution": resolution,
        }

    canonical_id = resolution["canonical_id"]

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    exclude_clause = "AND sc.SupplierId != ?" if exclude_supplier_id else ""
    params: list = [canonical_id]
    if exclude_supplier_id:
        params.append(exclude_supplier_id)

    rows = conn.execute(
        f"""
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
            sc.Last_Updated,
            COALESCE(sm.Vetted, 0)       AS vetted,
            sm.LEI,
            sm.Legal_Name,
            sm.Country_Verified,
            sm.GLEIF_Status
        FROM Supplier_Commercial sc
        JOIN Supplier s ON s.Id = sc.SupplierId
        LEFT JOIN Supplier_Master sm ON sm.SupplierId = sc.SupplierId
        WHERE sc.CanonicalIngredientId = ?
        AND sc.Confidence >= 0.5
        {exclude_clause}
        ORDER BY sc.Price_USD_Per_KG ASC NULLS LAST,
                 COALESCE(sm.Vetted, 0) DESC,
                 sc.Confidence DESC
        """,
        params,
    ).fetchall()
    conn.close()

    alternatives = [dict(r) for r in rows]
    return {
        "alternatives": alternatives,
        "canonical_id": canonical_id,
        "canonical_name": resolution["canonical_name"],
        "ingredient_name": ingredient_name,
        "count": len(alternatives),
        "resolution": resolution,
    }
