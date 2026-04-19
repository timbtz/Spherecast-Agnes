"""
Deterministic tool: emit a grounded 'no opportunities' explanation when
proactive_consolidation's scan-opportunities returned no rows (either because
the user's ingredient filter matched nothing, or because no opportunities meet
the score threshold catalog-wide).
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext


def run(ctx: AgnesContext) -> dict:
    scan = ctx.get("scan-opportunities", {})
    ingredient_filter = scan.get("ingredient_filter")
    min_score = scan.get("min_score", 0.5)
    user_message = ctx.trigger_payload.get("_user_message", "")
    count_above = scan.get("count", 0)

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    total_opps = conn.execute("SELECT COUNT(*) FROM Consolidation_Opportunity").fetchone()[0]
    conn.close()

    if ingredient_filter:
        reason = "filter_matched_no_opportunities"
        summary = (
            f"Agnes scanned Consolidation_Opportunity for ingredients matching "
            f"'**{ingredient_filter}**' but found no rows at or above the "
            f"Consolidation_Score threshold ({min_score}). "
            f"There are {total_opps} opportunities in the catalog in total. "
            f"Either widen the filter, lower the score floor, or run opportunity ranking "
            f"for this ingredient family."
        )
    else:
        reason = "no_opportunities_above_threshold"
        summary = (
            f"Agnes found no consolidation opportunities meeting the score threshold "
            f"({min_score}). There are {total_opps} opportunity rows total; none qualified. "
            f"Re-run the opportunity ranker or lower the score floor."
        )

    return {
        "summary": summary,
        "proposals_narrative": summary,
        "proposal_text": summary,
        "opportunity_count": count_above,
        "ingredient_filter": ingredient_filter,
        "reason": reason,
        "user_message": user_message,
    }
