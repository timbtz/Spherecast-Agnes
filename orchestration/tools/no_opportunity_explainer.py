"""
Deterministic tool: explain why proactive_consolidation found no consolidation opportunities.
Fires as a fallback when scan-opportunities returns an empty list.
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext


def run(ctx: AgnesContext) -> dict:
    ingredient_filter: str = ctx.trigger_payload.get("ingredient_name", "")
    conn = sqlite3.connect(str(ctx.enriched_db_path))

    total_count = conn.execute(
        "SELECT COUNT(*) FROM Consolidation_Opportunity"
    ).fetchone()[0]

    above_threshold = conn.execute(
        "SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Composite_Score >= 0.5"
    ).fetchone()[0]
    conn.close()

    if ingredient_filter and total_count > 0:
        reason = "filter_matched_no_opportunities"
        summary = (
            f"Agnes scanned the consolidation catalog but found no opportunities matching "
            f"'{ingredient_filter}'. There are {total_count} total opportunities in the system "
            f"({above_threshold} above the 0.5 score threshold)."
        )
    elif total_count == 0:
        reason = "no_opportunities_in_catalog"
        summary = (
            "Agnes found no consolidation opportunities in the catalog. "
            "Run the consolidation scoring pipeline to populate them."
        )
    else:
        reason = "no_opportunities_above_threshold"
        summary = (
            f"Agnes found no consolidation opportunities meeting the score threshold (0.5). "
            f"There are {total_count} total opportunities; none scored above 0.5. "
            f"Consider reviewing ingredients with fragmented supplier bases."
        )

    return {
        "summary": summary,
        "proposal_text": summary,
        "reason": reason,
        "opportunity_count": total_count,
        "above_threshold_count": above_threshold,
        "ingredient_filter": ingredient_filter,
    }
