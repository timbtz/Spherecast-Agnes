"""
Deterministic tool: given a canonical ingredient, return all affected finished-good
products and their companies. Used for change-impact analysis before a supplier swap.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext


def run(ctx: AgnesContext) -> dict:
    # Accept canonical_id from a prior node OR from trigger_payload
    canonical_id = (
        ctx.get("find-alternatives", {}).get("canonical_id")
        or ctx.get("scan-opportunities", {}).get("canonical_id")
        or ctx.trigger_payload.get("canonical_id")
    )
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "")

    if not canonical_id and ingredient_name:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
            (ingredient_name,),
        ).fetchone()
        conn.close()
        if row:
            canonical_id = row["Id"]

    if not canonical_id:
        return {"affected_products": [], "affected_companies": [], "error": "no canonical_id resolved"}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            p.Id            AS product_id,
            p.SKU           AS sku,
            p.SKU           AS product_name,
            p.Type          AS product_type,
            c.Id            AS company_id,
            c.Name          AS company_name,
            stc.Confidence  AS match_confidence
        FROM SKU_To_Canonical stc
        JOIN Product p  ON p.Id  = stc.ProductId
        JOIN Company c  ON c.Id  = p.CompanyId
        WHERE stc.CanonicalId = ?
        ORDER BY c.Name, p.SKU
        """,
        (canonical_id,),
    ).fetchall()

    conn.close()

    affected_products = [dict(r) for r in rows]
    affected_companies = list({r["company_name"] for r in affected_products})

    return {
        "affected_products": affected_products,
        "affected_companies": sorted(affected_companies),
        "product_count": len(affected_products),
        "company_count": len(affected_companies),
        "canonical_id": canonical_id,
    }
