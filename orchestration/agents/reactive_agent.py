"""ReactiveAgent: supplier fallout narrative from structured context data."""
import json
import os
import sqlite3

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

Refusal handling. If the payload contains a non-null `refusal` object (decision in
{refuse, defer_human_review, refuse_low_confidence}), DO NOT recommend alternative
suppliers — the compliance gate has blocked this path. Instead produce a refusal
memo that:
  - Names the decision in the situation summary (e.g. "Refused: baseline_fail on
    US-FDA, EU, CA, JP")
  - Quotes the BlockingFactors verbatim under "Blocking factors"
  - States the UnblockHint verbatim under "To unblock"
  - Does not invent alternatives; the alternatives list is informational only
    (shown to help a human decide whether to override).

Be factual, cite specific numbers. Note: pricing marked retail_proxy is indicative only.
Keep your response under 200 words.""",
)


def _read_refusal(ctx: AgnesContext) -> dict | None:
    """Read the Refusal_Log row written in this run, if any. Tools like
    compliance_reasoner_tool persist refuse/defer decisions there; surface
    them in the narrative so refusals become first-class UI output instead
    of silent DB events."""
    try:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT Decision, Justification, Confidence, BlockingFactors,
                      UnblockHint, IngredientName, CanonicalId
               FROM Refusal_Log WHERE RunId = ?
               ORDER BY Id DESC LIMIT 1""",
            (ctx.run_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "decision": row["Decision"],
            "justification": row["Justification"],
            "confidence": row["Confidence"],
            "blocking_factors": row["BlockingFactors"],
            "unblock_hint": row["UnblockHint"],
            "ingredient_name": row["IngredientName"],
            "canonical_id": row["CanonicalId"],
        }
    except Exception:
        return None


async def run(ctx: AgnesContext) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"narrative": None, "ingredient_name": ctx.trigger_payload.get("ingredient_name"), "skipped": "GOOGLE_API_KEY not set"}

    refusal = _read_refusal(ctx)
    compliance = ctx.get("gate-compliance", {})

    payload = json.dumps({
        "trigger": ctx.trigger_payload,
        "alternatives": ctx.get("find-alternatives", {}),
        "compliance_gate": compliance,
        "refusal": refusal,
        "bom_impact": ctx.get("bom-impact", {}),
        "rfqs": ctx.get("format-rfqs", {}),
    }, indent=2)

    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    bom = ctx.get("bom-impact", {})
    alternatives = ctx.get("find-alternatives", {}).get("alternatives", [])
    return {
        "summary": narrative,
        "narrative": narrative,
        "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
        "qualified_supplier_count": len(alternatives) if not refusal else 0,
        "affected_product_count": bom.get("product_count", 0),
        "refusal": refusal,
    }
