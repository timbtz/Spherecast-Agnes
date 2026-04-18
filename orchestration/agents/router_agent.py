"""RouterAgent: intent classifier. Classifies natural-language chat → pipeline + params JSON."""
import json
import os
import re

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent

load_dotenv()

_SYSTEM = """You are Agnes's intent router. Classify the user's message into exactly one of these pipelines:

- supplier_fallout: A supplier is unavailable or needs replacement. Params: {"ingredient_name": "..."}
- proactive_consolidation: Scan for consolidation opportunities. Params: {}
- new_ingredient_research: Research new supplier candidates. Params: {"ingredient_name": "..."}
- substitution_discovery: Find substitution options for an ingredient. Params: {"ingredient_name": "..."}
- price_audit: Audit pricing for an ingredient. Params: {"ingredient_name": "..."}

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
