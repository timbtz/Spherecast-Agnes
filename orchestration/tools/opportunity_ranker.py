"""
Deterministic tool: pull top-N consolidation opportunities from Consolidation_Opportunity,
enriched with canonical ingredient name and recommended supplier name.

Accepts an optional `ingredient_filter` (case-insensitive substring) to scope the
scan to a single ingredient family (e.g. "stearate", "vitamin"). Without the filter,
returns the global top-N.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext

_DEFAULT_TOP_N = 10
_MIN_SCORE_GLOBAL = 0.5   # score floor for catalog-wide scans
_MIN_SCORE_FILTERED = 0.1  # lower floor when the user explicitly filters to one ingredient
                           # family — they've already told us what they care about.


def run(ctx: AgnesContext) -> dict:
    top_n = ctx.trigger_payload.get("top_n", _DEFAULT_TOP_N)
    ingredient_filter = (ctx.trigger_payload.get("ingredient_filter") or "").strip()

    # Explicit override wins; otherwise use a lower floor when filtered.
    min_score = ctx.trigger_payload.get(
        "min_score",
        _MIN_SCORE_FILTERED if ingredient_filter else _MIN_SCORE_GLOBAL,
    )

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    params: list = [min_score]
    where_filter = ""
    if ingredient_filter:
        # Try raw term; if it's plural, also match the singular stem. Keeps
        # "stearates" → "stearate", "vitamins" → "vitamin", etc.
        low = ingredient_filter.lower()
        alternates = {low}
        if len(low) > 3 and low.endswith("s"):
            alternates.add(low[:-1])
        where_filter = " AND (" + " OR ".join(["LOWER(ic.Name) LIKE ?"] * len(alternates)) + ")"
        for alt in alternates:
            params.append(f"%{alt}%")
    params.append(top_n)

    rows = conn.execute(
        f"""
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
        WHERE co.Consolidation_Score >= ?{where_filter}
        ORDER BY co.Consolidation_Score DESC
        LIMIT ?
        """,
        params,
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
        "min_score": min_score,
        "ingredient_filter": ingredient_filter or None,
    }
