"""ReactiveAgent: supplier fallout narrative from structured context data."""
import json
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_AGENT = LlmAgent(
    name="reactive_agent",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain analyst. A supplier fallout event has occurred.
You receive structured supply chain data and must produce a concise, actionable response for a procurement manager.

Your response must include:
1. A brief situation summary (1-2 sentences)
2. Ranked alternative suppliers with key metrics (price, MOQ, lead time, purity)
3. A recommended immediate action
4. Any risk flags

Be factual, cite specific numbers. Note: pricing marked retail_proxy is indicative only.
Keep your response under 200 words.""",
)


async def run(ctx: AgnesContext) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"narrative": None, "ingredient_name": ctx.trigger_payload.get("ingredient_name"), "skipped": "GOOGLE_API_KEY not set"}

    payload = json.dumps({
        "trigger": ctx.trigger_payload,
        "alternatives": ctx.get("find-alternatives", {}),
        "compliance_gate": ctx.get("gate-qualify", {}),
        "bom_impact": ctx.get("bom-impact", {}),
        "rfqs": ctx.get("format-rfqs", {}),
    }, indent=2)

    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    compliance = ctx.get("gate-qualify", {})
    bom = ctx.get("bom-impact", {})
    return {
        "narrative": narrative,
        "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
        "qualified_supplier_count": len(compliance.get("qualified", [])),
        "affected_product_count": bom.get("product_count", 0),
    }
