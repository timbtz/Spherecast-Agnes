"""ProactiveAgent: consolidation proposals from opportunity scanner output."""
import json
import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_AGENT = LlmAgent(
    name="proactive_agent",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain consolidation advisor for CPG supplement companies.
You receive scored consolidation opportunities and must produce executive-ready proposals.

For each opportunity produce:
- A one-sentence headline: "Consolidate [ingredient] across [N] companies → est. [X]% savings"
- Current fragmentation: N suppliers, M companies, K SKUs
- Recommended supplier and why (price, quality, compliance)
- Estimated savings narrative (be conservative, cite assumptions)
- Next step: "Issue RFQ to [supplier] for [quantity range]"

One proposal ≤ 150 words. Flag data gaps honestly.
Pricing marked as retail_proxy is indicative only — note this.""",
)


async def run(ctx: AgnesContext) -> dict:
    opportunities = ctx.get("scan-opportunities", {}).get("opportunities", [])
    if not opportunities:
        return {"proposals": [], "count": 0}
    if not os.environ.get("GOOGLE_API_KEY"):
        return {
            "proposals_narrative": None,
            "opportunity_count": len(opportunities),
            "top_ingredient": opportunities[0].get("ingredient_name") if opportunities else None,
            "skipped": "GOOGLE_API_KEY not set",
        }

    payload = json.dumps({"opportunities": opportunities}, indent=2)
    proposals_narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    return {
        "proposals_narrative": proposals_narrative,
        "opportunity_count": len(opportunities),
        "top_ingredient": opportunities[0]["ingredient_name"] if opportunities else None,
    }
