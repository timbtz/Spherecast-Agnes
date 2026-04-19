"""RouterAgent: intent classifier. Classifies natural-language chat → pipeline + params JSON."""
import json
import os
import re

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent

load_dotenv()

_SYSTEM = """You are Agnes's intent router. Classify the user's message into exactly one of these pipelines:

- supplier_fallout: A supplier is unavailable, lost, or needs urgent replacement. Params: {"ingredient_name": "..."}
- proactive_consolidation: Scan the portfolio for consolidation or cost-reduction opportunities. Params: {}
- new_ingredient_research: Research new supplier candidates for an ingredient. Params: {"ingredient_name": "..."}
- substitution_discovery: Find substitute ingredients or alternative raw materials. Params: {"ingredient_name": "..."}
- price_audit: Audit or check current pricing for an ingredient. Params: {"ingredient_name": "..."}
- price_monitor: Check for stale prices or recent price changes across all ingredients. Params: {}
- regulatory_drift_alert: Check for FDA regulatory changes, IID drift, or compliance shifts. Params: {}

Rules:
- Extract ingredient_name from the message when relevant; leave empty string if not mentioned.
- Default to proactive_consolidation when the intent is general/unclear.
- Prefer regulatory_drift_alert for any mention of FDA, regulations, compliance changes, or quarterly updates.
- Prefer price_monitor for broad price check requests; prefer price_audit when a specific ingredient is named.

Respond with ONLY valid JSON:
{"pipeline": "<name>", "params": {<extracted params>}, "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}
"""

_AGENT = LlmAgent(name="router_agent", model="gemini-2.5-flash", instruction=_SYSTEM)


async def classify(message: str) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": "GOOGLE_API_KEY not set"}

    raw = await run_adk_agent(_AGENT, message, run_id="router")
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": raw[:100]}
    except Exception:
        return {"pipeline": "supplier_fallout", "params": {}, "confidence": 0.0, "reasoning": "parse error"}
