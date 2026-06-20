"""RegulatoryResearchAgent: searches for latest FDA IID quarterly change log and ingests new rows."""
import json
import os
import re
import urllib.request
import tempfile

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from orchestration.agents._adk_runner import run_adk_agent
from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_SYSTEM = """You are Agnes, a regulatory research agent.
You receive raw web search results about the FDA Inactive Ingredient Database quarterly change log.

Extract and return JSON with this exact shape:
{
  "download_url": "<direct CSV download URL or null>",
  "snapshot_date": "<quarter and year e.g. Q2 2026 or null>",
  "ingredient_names": ["<name>", ...],
  "summary": "<one sentence summary of what was found>"
}

The FDA IID change log is published at:
https://www.fda.gov/drugs/drug-approvals-and-databases/quarterly-inactive-ingredient-database-iid-change-log

Look for a direct link to a downloadable CSV file containing regulatory changes.
If no direct CSV URL is found, set download_url to null.
"""

_AGENT = LlmAgent(name="regulatory_research_agent", model="gemini-2.5-flash", instruction=_SYSTEM)


async def run(ctx: AgnesContext) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"skipped": "GOOGLE_API_KEY not set", "new_rows_ingested": 0, "search_completed": False}

    try:
        from orchestration.agents.search_sub_agent import search
        raw_search = await search(
            "FDA Inactive Ingredient Database quarterly change log 2026 site:fda.gov",
            query_hint="CSV download quarterly IID changes",
        )
    except Exception as e:
        raw_search = f"Search unavailable: {e}"

    payload = f"Search results:\n{raw_search}"
    raw = await run_adk_agent(_AGENT, payload, ctx.run_id)

    parsed = _parse_json(raw)
    download_url = parsed.get("download_url")
    snapshot_date = parsed.get("snapshot_date")
    summary = parsed.get("summary", raw[:200])

    new_rows = 0
    if download_url:
        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp_path = tmp.name
            urllib.request.urlretrieve(download_url, tmp_path)
            from enrichment.sources.fda_iid_changelog import load_iid_changelog
            new_rows = load_iid_changelog(db_path=ctx.enriched_db_path, csv_path=tmp_path)
        except Exception as e:
            summary = f"Download failed: {e}. {summary}"

    return {
        "search_completed": True,
        "download_url_found": bool(download_url),
        "new_rows_ingested": new_rows,
        "snapshot_date": snapshot_date,
        "raw_summary": summary,
    }


def _parse_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}
