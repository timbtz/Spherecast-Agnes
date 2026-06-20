"""
Deterministic tool: explain why upstream data-fetching returned empty results.
Fires as a fallback node when find-substitutes or find-alternatives returned [].
"""
import sqlite3

from orchestration.api.agnes_context import AgnesContext
from orchestration.tools._ingredient_resolver import resolve

_REASON_MESSAGES = {
    "ingredient_not_in_canonical": "Agnes searched the ingredient catalog but could not find '{name}' as a known canonical ingredient.",
    "no_substitutes": "Agnes scanned the substitution graph for '{name}' but found no functionally-equivalent substitutes.",
    "no_suppliers": "Agnes found '{name}' in the catalog but no supplier records exist for it.",
    "no_bom": "Agnes found '{name}' in the catalog but no Bill-of-Materials references exist.",
    "no_price_data": "Agnes found '{name}' in the catalog but no pricing data is available for benchmarking.",
}


def run(ctx: AgnesContext) -> dict:
    ingredient_name: str = ctx.trigger_payload.get("ingredient_name", "")
    resolution = resolve(ingredient_name, db_path=ctx.enriched_db_path)

    missing_data: list[str] = []
    reason = "unknown"

    if resolution["resolution_failed"]:
        reason = "ingredient_not_in_canonical"
        missing_data.append(f"'{ingredient_name}' not found in Ingredient_Canonical")
    else:
        canonical_id = resolution["canonical_id"]
        conn = sqlite3.connect(str(ctx.enriched_db_path))

        # Check substitution graph
        sub_count = conn.execute(
            "SELECT COUNT(*) FROM Ingredient_Substitution WHERE IngredientAId = ? OR IngredientBId = ?",
            (canonical_id, canonical_id),
        ).fetchone()[0]
        if sub_count == 0:
            missing_data.append("no functionally-equivalent substitutes in Ingredient_Substitution")
            reason = "no_substitutes"

        # Check supplier records
        sup_count = conn.execute(
            "SELECT COUNT(*) FROM Supplier_Commercial WHERE CanonicalIngredientId = ?",
            (canonical_id,),
        ).fetchone()[0]
        if sup_count == 0:
            missing_data.append("no supplier records in Supplier_Commercial")
            if reason == "unknown":
                reason = "no_suppliers"

        # Check BOM
        bom_count = conn.execute(
            "SELECT COUNT(*) FROM BOM_Component_Quantity WHERE CanonicalIngredientId = ?",
            (canonical_id,),
        ).fetchone()[0]
        if bom_count == 0:
            missing_data.append("no BOM entries in BOM_Component_Quantity")
            if reason == "unknown":
                reason = "no_bom"

        conn.close()

        if not missing_data:
            reason = "no_price_data"
            missing_data.append("no pricing data available")

    display_name = resolution.get("canonical_name") or ingredient_name
    template = _REASON_MESSAGES.get(reason, "Agnes found no results for '{name}'.")
    summary = template.format(name=display_name)

    return {
        "summary": summary,
        "proposal_text": summary,
        "reason": reason,
        "missing_data": missing_data,
        "ingredient_name": ingredient_name,
        "resolution": resolution,
    }
