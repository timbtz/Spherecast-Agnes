"""Async DAG agent: Gemini narrative summarizing detected price changes."""
import json
import logging
import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import LlmAgent
from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.price_alert_writer")

_AGENT = LlmAgent(
    name="price_alert_writer",
    model="gemini-2.5-flash",
    instruction="""You are Agnes, an AI supply chain advisor. You receive a list of ingredient price changes
detected from live market data. Write a <=200-word executive briefing:

- Open with the most significant change (largest % drop/increase)
- Group by direction: drops first (opportunity), then increases (risk)
- For each: ingredient, supplier, old price -> new price, % change, recommended action
- Close with a one-sentence priority recommendation

Use bullet points. Be concrete. Flag data-confidence caveats (web-search prices are indicative).
No headers. Plain prose bullets.""",
)


async def run(ctx: AgnesContext) -> dict:
    alerts = ctx.get("fetch-prices", {}).get("alerts_created", [])
    if not alerts:
        return {"alert_narrative": None, "alert_count": 0, "run_id": ctx.run_id}

    if not os.environ.get("GOOGLE_API_KEY"):
        return {"alert_narrative": None, "alert_count": len(alerts), "run_id": ctx.run_id, "skipped": "GOOGLE_API_KEY not set"}

    payload = json.dumps({"price_changes": alerts}, indent=2)
    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    if narrative:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute(
            "UPDATE Price_Change_Alert SET Alert_Narrative = ? WHERE Run_Id = ? AND Alert_Narrative IS NULL",
            (narrative, ctx.run_id)
        )
        conn.commit()
        conn.close()

    return {
        "alert_narrative": narrative,
        "alert_count": len(alerts),
        "run_id": ctx.run_id,
        "top_change": max(alerts, key=lambda a: abs(a["change_pct"]), default=None),
    }
