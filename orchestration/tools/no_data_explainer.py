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
"""
import sqlite3
from typing import Any

from orchestration.api.agnes_context import AgnesContext


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

    if not ingredient_name:
        reason = "no_ingredient_in_request"
        summary = (
            f"Agnes could not run the {pipeline.replace('_', ' ')} pipeline because "
            "no ingredient was identified in your request. Please specify the ingredient "
            "by name — e.g. 'Find substitutes for magnesium stearate'."
        )
    else:
        db_info = _check(ctx, ingredient_name)
        if not db_info["ingredient_in_canonical"]:
            reason = "ingredient_not_in_canonical"
            summary = (
                f"Agnes does not recognize **{ingredient_name}** in the Ingredient_Canonical table. "
                f"It may be spelled differently, may not be covered by the current dataset, or "
                f"may be a trade-name for a canonical entry. Without a canonical match, "
                f"{pipeline.replace('_', ' ')} cannot proceed. Add the ingredient to "
                f"Ingredient_Canonical (or a synonym mapping) and retry."
            )
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
