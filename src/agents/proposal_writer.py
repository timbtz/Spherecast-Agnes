"""
ProposalWriter (Claude): drafts a final, evidence-backed consolidation or substitution proposal.
Uses Claude for richer narrative quality on the final user-facing output.
"""
import json
import os

import anthropic
from dotenv import load_dotenv

from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_CLIENT = None
_MODEL = "claude-sonnet-4-6"

_SYSTEM = """You are Agnes, a trusted supply chain advisor. Write a final proposal memo for
a procurement manager. The memo must be concise (≤200 words), evidence-backed, and actionable.

Structure:
## Recommendation
One sentence headline.

## Evidence
2-3 bullet points citing specific data (prices, counts, scores).

## Action
Concrete next step. If pricing is from retail_proxy sources, note:
"Pricing indicative — confirm at production volumes before committing."

## Risks & Caveats
1-2 items. Be honest about data gaps.
"""


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


async def run(ctx: AgnesContext) -> dict:
    import asyncio

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "proposal_text": None,
            "pipeline": ctx.pipeline_name,
            "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
            "skipped": "ANTHROPIC_API_KEY not set",
        }

    # Gather all prior node outputs as context
    context_data = {
        "trigger": ctx.trigger_payload,
        "node_outputs": {k: v for k, v in ctx.node_outputs.items() if k != "write-proposal"},
    }
    payload = json.dumps(context_data, indent=2)

    # Run synchronously in executor to avoid blocking the event loop
    def _call():
        resp = _client().messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
        return resp.content[0].text.strip()

    proposal_text = await asyncio.get_event_loop().run_in_executor(None, _call)

    return {
        "proposal_text": proposal_text,
        "pipeline": ctx.pipeline_name,
        "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
    }
