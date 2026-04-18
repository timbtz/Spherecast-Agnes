"""
Deterministic tool: pull top-N consolidation opportunities from Consolidation_Opportunity,
enriched with canonical ingredient name and recommended supplier name.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext

_DEFAULT_TOP_N = 10
_MIN_SCORE = 0.5


def run(ctx: AgnesContext) -> dict:
    top_n = ctx.trigger_payload.get("top_n", _DEFAULT_TOP_N)

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            co.Id,
            co.CanonicalIngredientId    AS canonical_id,
            ic.Name                     AS ingredient_name,
            co.Company_Count,
            co.BOM_Count,
            co.Current_Supplier_Count,
            co.Consolidation_Score,
            co.Unique_SKU_Count,
            co.Compliance_Feasible,
            co.Recommended_SupplierId,
            s.Name                      AS recommended_supplier,
            co.Estimated_Savings_Narrative,
            co.Proposal_Text,
            co.Generated_At,
            co.regulatory_drift_flag,
            co.regulatory_drift_reason
        FROM Consolidation_Opportunity co
        JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
        LEFT JOIN Supplier s ON s.Id = co.Recommended_SupplierId
        WHERE co.Consolidation_Score >= ?
        ORDER BY co.Consolidation_Score DESC
        LIMIT ?
        """,
        (_MIN_SCORE, top_n),
    ).fetchall()

    conn.close()

    opportunities = [
        {**dict(r), "regulatory_drift_flag": bool(r["regulatory_drift_flag"])}
        for r in rows
    ]
    return {
        "opportunities": opportunities,
        "count": len(opportunities),
        "top_n": top_n,
    }
