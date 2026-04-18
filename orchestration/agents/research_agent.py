"""ResearchAgent: discovers new suppliers via web search (google_search via ADK)."""
import json
import os
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_SYSTEM = """You are Agnes, a supply chain research agent.
You receive raw web search results about bulk ingredient suppliers.
Extract and return a JSON array of supplier records:
[{"supplier_name": "...", "country": "...", "website": "...", "certifications": ["NSF", ...],
  "price_range_usd_per_kg": "...", "moq_range_kg": "...", "notes": "..."}]
Include only suppliers clearly offering this ingredient in bulk B2B quantities.
Mark uncertain fields as null. Include 3-8 suppliers.
"""

_AGENT = LlmAgent(name="research_agent", model="gemini-2.5-flash", instruction=_SYSTEM)


async def run(ctx: AgnesContext) -> dict:
    ingredient_name: str = ctx.trigger_payload.get("ingredient_name", "")
    if not ingredient_name:
        return {"discovered_suppliers": [], "error": "no ingredient_name in payload"}

    if not os.environ.get("GOOGLE_API_KEY"):
        return {"discovered_suppliers": [], "ingredient_name": ingredient_name, "count": 0, "skipped": "GOOGLE_API_KEY not set"}

    try:
        from orchestration.agents.search_sub_agent import search
        raw_search = await search(ingredient_name, query_hint="bulk supplier B2B certificate")
    except Exception as e:
        raw_search = f"Search unavailable: {e}"

    payload = f"Ingredient: {ingredient_name}\n\nSearch results:\n{raw_search}"
    raw = await run_adk_agent(_AGENT, payload, ctx.run_id)
    discovered = _parse_suppliers(raw, ingredient_name)

    if discovered:
        _stage_suppliers(discovered, ingredient_name, ctx.enriched_db_path)

    return {
        "discovered_suppliers": discovered,
        "ingredient_name": ingredient_name,
        "count": len(discovered),
        "raw_output": raw[:500],
    }


def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    import re
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    if raw.strip():
        return [{"supplier_name": "research_result", "notes": raw[:400]}]
    return []


def _stage_suppliers(suppliers: list[dict], ingredient_name: str, db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
        (ingredient_name,),
    ).fetchone()
    canonical_id = row[0] if row else None
    for s in suppliers:
        try:
            conn.execute(
                """INSERT INTO Agent_Log (Run_Id, Agent, Node, Status, Input_JSON, Output_JSON, Related_IngredientId, Logged_At)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("research_run", "research_agent", "stage_discovered_supplier", "success",
                 json.dumps({"ingredient_name": ingredient_name}), json.dumps(s), canonical_id, datetime.utcnow().isoformat()),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()
