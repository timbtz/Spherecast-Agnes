"""
Deterministic tool: emit a grounded 'no data' explanation when an upstream
data-fetching node (substitute walker, price benchmark, supplier alternatives)
returned nothing for the requested ingredient.

This is the fallback leaf node that fires when a pipeline would otherwise
complete with empty node_outputs. Without it, the user just gets a run_id
and no explanation of why nothing happened.

Output shape mirrors the other writer agents:
    {
      "summary":          str,   # human-readable message
      "proposal_text":    str,   # same content, compatibility with ProposalWriter
      "ingredient_name":  str,
      "pipeline":         str,
      "reason":           str,   # machine-readable reason code
      "missing_data":     list[str],  # what we checked and found empty
    }

Also persists a Refusal_Log row so no-data events contribute to the playbook's
approval/refusal/coverage rates. Without this write, only compliance refusals
were tracked — coverage-gap refusals were invisible to the UI.
"""
import logging
import sqlite3
from typing import Any

from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.no_data_explainer")


def _log_refusal(
    ctx: AgnesContext,
    canonical_id: int | None,
    ingredient_name: str,
    decision: str,
    justification: str,
    blocking_factors: list[str],
    unblock_hint: str,
) -> None:
    """Persist a coverage-gap refusal to Refusal_Log so it shows up alongside
    compliance refusals in the first-class refusal UI."""
    try:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute(
            """INSERT OR IGNORE INTO Refusal_Log
               (CanonicalId, IngredientName, Decision, Justification,
                Confidence, BlockingFactors, UnblockHint, RunId)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                canonical_id,
                ingredient_name or "(unspecified)",
                decision,
                justification,
                1.0,  # we're confident the coverage gap exists — it's a DB fact
                str(blocking_factors),
                unblock_hint,
                getattr(ctx, "run_id", None),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as err:
        logger.warning(f"Refusal_Log write failed in no_data_explainer: {err}")


def _check(ctx: AgnesContext, ingredient_name: str) -> dict[str, Any]:
    """Inspect DB to tell the user *why* we came up empty, not just *that* we did."""
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    canonical_row = conn.execute(
        "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
        (ingredient_name,),
    ).fetchone()

    info: dict[str, Any] = {
        "ingredient_in_canonical": bool(canonical_row),
        "canonical_id": canonical_row["Id"] if canonical_row else None,
    }

    if canonical_row:
        cid = canonical_row["Id"]
        info["supplier_commercial_rows"] = conn.execute(
            "SELECT COUNT(*) FROM Supplier_Commercial WHERE CanonicalIngredientId = ?",
            (cid,),
        ).fetchone()[0]
        info["substitution_rows"] = conn.execute(
            "SELECT COUNT(*) FROM Ingredient_Substitution WHERE IngredientAId = ? OR IngredientBId = ?",
            (cid, cid),
        ).fetchone()[0]
        # BOM is normalized via BOM_Component → SKU_To_Canonical.
        # A row here = one BOM consuming this canonical ingredient.
        info["bom_rows"] = conn.execute(
            """SELECT COUNT(DISTINCT bc.BOMId)
                 FROM BOM_Component bc
                 JOIN SKU_To_Canonical sc ON sc.ProductId = bc.ConsumedProductId
                WHERE sc.CanonicalId = ?""",
            (cid,),
        ).fetchone()[0]
    conn.close()
    return info


def run(ctx: AgnesContext) -> dict:
    pipeline = ctx.pipeline_name
    ingredient_name = (ctx.trigger_payload.get("ingredient_name") or "").strip()
    user_message = ctx.trigger_payload.get("_user_message", "")

    # Identify which upstream was empty so the message is specific.
    subs = ctx.get("find-substitutes", {})
    alts = ctx.get("find-alternatives", {})
    prices = ctx.get("benchmark-prices", {})

    missing: list[str] = []
    if "find-substitutes" in ctx.node_outputs and not subs.get("substitutes"):
        missing.append("no functionally-equivalent substitutes in Ingredient_Substitution")
    if "find-alternatives" in ctx.node_outputs and not alts.get("alternatives"):
        missing.append("no alternative suppliers in Supplier_Commercial")
    if "benchmark-prices" in ctx.node_outputs and not prices.get("annotated_prices"):
        missing.append("no benchmark prices in Supplier_Commercial")

    canonical_id: int | None = None
    blocking_factors: list[str] = []
    unblock_hint: str = ""

    if not ingredient_name:
        reason = "no_ingredient_in_request"
        summary = (
            f"Agnes could not run the {pipeline.replace('_', ' ')} pipeline because "
            "no ingredient was identified in your request. Please specify the ingredient "
            "by name — e.g. 'Find substitutes for magnesium stearate'."
        )
        blocking_factors = ["no_ingredient_identified"]
        unblock_hint = (
            "Specify the ingredient by name — e.g. 'Find substitutes for magnesium stearate'."
        )
        decision = "refuse_no_ingredient"
    else:
        db_info = _check(ctx, ingredient_name)
        canonical_id = db_info.get("canonical_id")
        if not db_info["ingredient_in_canonical"]:
            reason = "ingredient_not_in_canonical"
            summary = (
                f"Agnes does not recognize **{ingredient_name}** in the Ingredient_Canonical table. "
                f"It may be spelled differently, may not be covered by the current dataset, or "
                f"may be a trade-name for a canonical entry. Without a canonical match, "
                f"{pipeline.replace('_', ' ')} cannot proceed. Add the ingredient to "
                f"Ingredient_Canonical (or a synonym mapping) and retry."
            )
            blocking_factors = ["ingredient_not_in_canonical"]
            unblock_hint = (
                f"Add '{ingredient_name}' to Ingredient_Canonical (or register a synonym mapping) and retry."
            )
            decision = "refuse_coverage_gap"
        else:
            reason = "no_coverage_for_ingredient"
            sup = db_info.get("supplier_commercial_rows", 0)
            substr = db_info.get("substitution_rows", 0)
            boms = db_info.get("bom_rows", 0)
            summary = (
                f"Agnes recognizes **{ingredient_name}** (canonical_id={db_info['canonical_id']}) "
                f"but the dataset does not contain the information this pipeline needs. "
                f"Coverage for this ingredient: "
                f"{sup} supplier-commercial rows, "
                f"{substr} substitution rows, "
                f"{boms} BOM rows. "
                f"Gaps detected: {'; '.join(missing) if missing else 'upstream nodes produced empty result'}. "
                f"Either run the enrichment pipeline for this ingredient, or pick an ingredient with coverage."
            )
            blocking_factors = missing or ["empty_upstream_outputs"]
            unblock_hint = (
                f"Run the enrichment pipeline for '{ingredient_name}' to populate Supplier_Commercial / "
                f"Ingredient_Substitution, or pick an ingredient with coverage."
            )
            decision = "refuse_empty_coverage"

    # Persist this no-data event to Refusal_Log so coverage-gap refusals are
    # first-class UI events alongside compliance refusals. Without this, the
    # playbook's approval/refusal/coverage rate dashboards under-count.
    _log_refusal(
        ctx=ctx,
        canonical_id=canonical_id,
        ingredient_name=ingredient_name,
        decision=decision,
        justification=summary,
        blocking_factors=blocking_factors,
        unblock_hint=unblock_hint,
    )

    return {
        "summary": summary,
        "proposal_text": summary,
        "narrative": summary,
        "ingredient_name": ingredient_name,
        "pipeline": pipeline,
        "reason": reason,
        "missing_data": missing,
        "user_message": user_message,
    }
