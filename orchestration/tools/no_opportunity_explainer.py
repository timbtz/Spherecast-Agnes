"""
Deterministic tool: emit a grounded 'no opportunities' explanation when
proactive_consolidation's scan-opportunities returned no rows (either because
the user's ingredient filter matched nothing, or because no opportunities meet
the score threshold catalog-wide).

Also persists a Refusal_Log row so opportunity-gap events contribute to the
playbook's approval/refusal/coverage rates. Without this write, only compliance
refusals were tracked — consolidation coverage gaps were invisible to the UI.
"""
import logging
import sqlite3

from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.no_opportunity_explainer")


def _log_refusal(
    ctx: AgnesContext,
    ingredient_name: str,
    decision: str,
    justification: str,
    blocking_factors: list[str],
    unblock_hint: str,
) -> None:
    """Persist a no-opportunity refusal to Refusal_Log so it shows up alongside
    compliance refusals in the first-class refusal UI."""
    try:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute(
            """INSERT OR IGNORE INTO Refusal_Log
               (CanonicalId, IngredientName, Decision, Justification,
                Confidence, BlockingFactors, UnblockHint, RunId)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                None,
                ingredient_name or "(catalog-wide)",
                decision,
                justification,
                1.0,
                str(blocking_factors),
                unblock_hint,
                getattr(ctx, "run_id", None),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as err:
        logger.warning(f"Refusal_Log write failed in no_opportunity_explainer: {err}")


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
        decision = "refuse_no_opportunities_for_filter"
        blocking_factors = [
            f"filter='{ingredient_filter}'",
            f"min_score={min_score}",
            f"catalog_total={total_opps}",
        ]
        unblock_hint = (
            f"Widen the ingredient filter, lower the score floor below {min_score}, "
            f"or run opportunity ranking for this ingredient family."
        )
    else:
        reason = "no_opportunities_above_threshold"
        summary = (
            f"Agnes found no consolidation opportunities meeting the score threshold "
            f"({min_score}). There are {total_opps} opportunity rows total; none qualified. "
            f"Re-run the opportunity ranker or lower the score floor."
        )
        decision = "refuse_no_opportunities_global"
        blocking_factors = [
            f"min_score={min_score}",
            f"catalog_total={total_opps}",
        ]
        unblock_hint = (
            f"Re-run the opportunity ranker to refresh scores, or lower the score floor below {min_score}."
        )

    _log_refusal(
        ctx=ctx,
        ingredient_name=ingredient_filter or "",
        decision=decision,
        justification=summary,
        blocking_factors=blocking_factors,
        unblock_hint=unblock_hint,
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
