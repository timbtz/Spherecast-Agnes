"""
ProposalWriter (Claude): drafts a final, evidence-backed consolidation or substitution proposal.
Uses Claude for richer narrative quality on the final user-facing output.
"""
import json
import os
import sqlite3

import anthropic
from dotenv import load_dotenv

from orchestration.api.agnes_context import AgnesContext

load_dotenv()

_CLIENT = None
_MODEL = "claude-sonnet-4-6"

_SYSTEM = """You are Agnes, a trusted supply chain advisor. Write a final proposal memo for
a procurement manager. The memo must be concise (≤220 words), evidence-backed, and actionable.

Structure:
## Decision Layer
Render the provided `decision_layer` object verbatim on one line as:
action=<action> · tier=<confidence_tier> · EV=<ev_band> · priority=<priority> · confidence=<compound_confidence>
Use the exact values supplied — do NOT derive, re-rank, or second-guess them.
This layer is mechanically computed upstream; your job is to render it, not recompute it.

## Recommendation
One sentence headline consistent with the decision-layer `action`.

## Evidence
2-3 bullet points citing specific data (prices, counts, scores).

## Action
Concrete next step. If pricing is from retail_proxy sources, note:
"Pricing indicative — confirm at production volumes before committing."

## Risks & Caveats
1-2 items. Be honest about data gaps.

Refusal handling. If the payload contains a non-null `refusal` object (decision in
{refuse, defer_human_review, refuse_low_confidence, refuse_no_opportunities_*,
refuse_coverage_gap, refuse_empty_coverage, refuse_no_ingredient}), the memo is a
refusal memo: replace Recommendation with the refusal decision, replace Action
with the UnblockHint verbatim, and list BlockingFactors under Risks & Caveats. Do
not recommend substitutes or alternative suppliers that the compliance gate has
already rejected — the alternatives/substitutes in the payload are informational
only in that case. The Decision Layer still renders (action will be `refuse` or `defer`).
"""


def _tier_from_confidence(c: float) -> str:
    """Map a 0-1 confidence scalar to a human-readable tier."""
    if c >= 0.85:
        return "high"
    if c >= 0.70:
        return "medium-high"
    if c >= 0.55:
        return "medium"
    if c >= 0.40:
        return "medium-low"
    return "low"


def _ev_band(savings_pct: float, product_count: int) -> str:
    """EV band = savings_pct × breadth (product_count). Three coarse bands."""
    leverage = (savings_pct or 0.0) * max(product_count, 1)
    if leverage >= 50:
        return "high-leverage"
    if leverage >= 10:
        return "moderate"
    return "low-leverage"


def _compute_decision_layer(ctx: AgnesContext, refusal: dict | None) -> dict:
    """Mechanically derive a decision-layer quadruple (action, confidence tier,
    EV band, priority) + compound_confidence from existing node outputs.

    This is not new reasoning — just the shape the playbook asks for so UIs and
    downstream consumers can render a structured summary without re-parsing the
    LLM prose. No new LLM call, no new gate; strictly a projection of signals
    already computed upstream.
    """
    # Refusal path: decision layer mirrors the refusal outcome.
    if refusal:
        decision = (refusal.get("decision") or "").lower()
        try:
            refusal_conf = float(refusal.get("confidence") or 0.0)
        except (TypeError, ValueError):
            refusal_conf = 0.0
        action = "defer" if "defer" in decision else "refuse"
        return {
            "action": action,
            "confidence_tier": _tier_from_confidence(refusal_conf),
            "ev_band": "n/a",
            "priority": "do-first",  # refusals need operator acknowledgement
            "compound_confidence": round(refusal_conf, 2),
        }

    outs = ctx.node_outputs or {}

    # Qualified candidate list — either the reasoner's output or the legacy gate's.
    qualified: list = []
    for key in ("gate-compliance", "gate-qualify"):
        q = (outs.get(key) or {}).get("qualified") or []
        if q:
            qualified = q
            break

    # Top candidate confidence (any case-variant of the key).
    top_conf = 0.0
    for cand in qualified:
        if not isinstance(cand, dict):
            continue
        raw = cand.get("Confidence", cand.get("confidence", 0.0))
        try:
            c = float(raw or 0.0)
        except (TypeError, ValueError):
            c = 0.0
        if c > top_conf:
            top_conf = c

    # Product impact breadth.
    product_count = 0
    for key in ("gate-compliance", "gate-qualify", "bom-impact", "scan-opportunities"):
        out = outs.get(key) or {}
        for fld in ("product_count", "affected_count", "count"):
            raw = out.get(fld)
            try:
                pc = int(raw or 0)
            except (TypeError, ValueError):
                pc = 0
            if pc > product_count:
                product_count = pc

    # Savings signal (percent).
    savings_pct = 0.0
    for key in ("benchmark-prices", "rank-opportunities", "price-monitor"):
        out = outs.get(key) or {}
        for fld in ("savings_pct", "avg_savings_pct", "savings_percent"):
            raw = out.get(fld)
            try:
                s = float(raw or 0.0)
            except (TypeError, ValueError):
                s = 0.0
            if s > savings_pct:
                savings_pct = s

    # Action is pipeline-shaped, gated by presence of qualified candidates.
    pipeline = ctx.pipeline_name or ""
    if qualified:
        if "consolidation" in pipeline:
            action = "consolidate"
        elif "substitution" in pipeline or "fallout" in pipeline:
            action = "substitute"
        elif "new_ingredient" in pipeline:
            action = "approve"
        else:
            action = "advance"
    else:
        action = "investigate"

    confidence_tier = _tier_from_confidence(top_conf)
    ev_band = _ev_band(savings_pct, product_count)

    # Priority: broader impact + higher confidence → do-first; degrade from there.
    if product_count >= 5 and top_conf >= 0.70:
        priority = "do-first"
    elif product_count >= 2 and top_conf >= 0.55:
        priority = "follow-up"
    else:
        priority = "backlog"

    # Compound confidence = top × breadth-factor (0.6 at 1 product → 1.0 at 5+).
    if qualified:
        breadth_factor = min(1.0, 0.5 + 0.1 * max(product_count, 1))
        compound = round(top_conf * breadth_factor, 2)
    else:
        compound = 0.3  # no qualified candidates → floor, rendered as "low"

    return {
        "action": action,
        "confidence_tier": confidence_tier,
        "ev_band": ev_band,
        "priority": priority,
        "compound_confidence": compound,
    }


def _client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _CLIENT


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
    import asyncio

    refusal = _read_refusal(ctx)
    decision_layer = _compute_decision_layer(ctx, refusal)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "proposal_text": None,
            "pipeline": ctx.pipeline_name,
            "ingredient_name": ctx.trigger_payload.get("ingredient_name"),
            "refusal": refusal,
            "decision_layer": decision_layer,
            "skipped": "ANTHROPIC_API_KEY not set",
        }

    # Gather all prior node outputs as context
    context_data = {
        "trigger": ctx.trigger_payload,
        "refusal": refusal,
        "decision_layer": decision_layer,
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
        "refusal": refusal,
        "decision_layer": decision_layer,
    }
