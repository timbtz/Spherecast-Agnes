"""
Deterministic tool: format a structured RFQ record from a qualified supplier candidate.
Does NOT send anything — outputs JSON that the ProposalWriter agent turns into narrative.
"""
from datetime import datetime
from pathlib import Path

from orchestration.api.agnes_context import AgnesContext


def run(ctx: AgnesContext) -> dict:
    qualified = ctx.get("gate-qualify", {}).get("qualified", [])
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "unknown")
    bom_impact = ctx.get("bom-impact", {})

    rfqs = []
    for supplier in qualified[:3]:  # top 3 qualified suppliers
        rfq = {
            "rfq_type": "consolidation_inquiry",
            "ingredient_name": ingredient_name,
            "supplier_id": supplier.get("SupplierId"),
            "supplier_name": supplier.get("supplier_name"),
            "current_price_usd_per_kg": supplier.get("Price_USD_Per_KG"),
            "moq_kg": supplier.get("MOQ_KG"),
            "lead_time_days": supplier.get("Lead_Time_Days"),
            "purity": supplier.get("Purity_Qualifier"),
            "affected_product_count": bom_impact.get("product_count", 0),
            "affected_company_count": bom_impact.get("company_count", 0),
            "pricing_note": "Pricing indicative at research quantities — production volume requires direct negotiation.",
            "generated_at": datetime.utcnow().isoformat(),
            "status": "draft_pending_review",
        }
        rfqs.append(rfq)

    return {
        "rfqs": rfqs,
        "count": len(rfqs),
        "ingredient_name": ingredient_name,
    }
