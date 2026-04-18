"""RegulatoryDriftAgent: generates executive narrative for FDA drift alerts, flags affected opportunities."""
import json
import os
import sqlite3

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_SYSTEM = """You are Agnes, an AI supply chain compliance advisor.
You receive a list of FDA Inactive Ingredient Database regulatory changes
affecting ingredients in a supplement company's supply chain.

For each HIGH severity alert produce:
- One-sentence headline: "[Ingredient] FDA limit [DELETED/CORRECTED from X to Y mg]"
- Compliance risk: what this means for products using this ingredient
- Recommended action: re-qualify supplier, reformulate, or request new CoA
- If alternatives are available: "Consider switching to [alternative]"

For MEDIUM/LOW alerts: one line each.
Flag data gaps honestly. Total narrative <= 300 words.
"""

_AGENT = LlmAgent(name="regulatory_drift_agent", model="gemini-2.5-flash", instruction=_SYSTEM)


async def run(ctx: AgnesContext) -> dict:
    scan = ctx.get("scan-drift", {})
    drift_alerts = scan.get("drift_alerts", [])
    high_count = scan.get("high_severity_count", 0)

    if not drift_alerts:
        return {"alerts_narrative": None, "drift_count": 0, "high_severity_count": 0, "opportunities_flagged": 0}

    if not os.environ.get("GOOGLE_API_KEY"):
        return {"skipped": "GOOGLE_API_KEY not set", "drift_count": len(drift_alerts)}

    alternatives = ctx.get("find-alternatives", {})
    payload = json.dumps({"drift_alerts": drift_alerts, "alternatives": alternatives}, indent=2)
    narrative = await run_adk_agent(_AGENT, payload, ctx.run_id)

    # Write drift flags to DB
    flagged = 0
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    for alert in drift_alerts:
        if alert.get("opportunity_id"):
            conn.execute(
                "UPDATE Consolidation_Opportunity SET regulatory_drift_flag=1, regulatory_drift_reason=? WHERE Id=?",
                (f"{alert['status']}: {alert['change_summary']}", alert["opportunity_id"]),
            )
            flagged += 1
    conn.commit()
    conn.close()

    return {
        "alerts_narrative": narrative,
        "drift_count": len(drift_alerts),
        "high_severity_count": high_count,
        "opportunities_flagged": flagged,
    }
