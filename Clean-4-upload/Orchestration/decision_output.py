"""Decision-layer output adapter.

Turns a raw OpportunityVerdict (produced by plan_opportunity) into the
two shapes we actually ship:

  1. A structured dict / JSON payload the UI and API layer can render
     without understanding the internals. Stable schema — field names
     and types are considered part of the external contract.
  2. A short text summary (markdown) suitable for email, Slack, or the
     top-of-screen demo readout. Does NOT duplicate the per-candidate
     justifications the verdict already carries.

We deliberately keep this adapter stateless and dependency-free: it
reads an OpportunityVerdict, renders output, done. No DB writes, no
LLM calls.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .planner import OpportunityVerdict
from .qualify_candidate import QualificationOutcome


# ------------------------------------------------------------ structured


@dataclass
class DecisionPayload:
    """Stable contract. Every field populated (possibly with a default)."""
    opportunity_id: int
    incumbent_name: str
    use_class: str
    jurisdictions: List[str]

    # Aggregated decision across all candidates.
    overall_verdict: str          # 'actionable' | 'fork' | 'review' | 'refuse'
    overall_reason: str
    candidates_evaluated: int
    candidates_recommended: int
    candidates_refused: int
    candidates_human_review: int

    # Top-N ranked supplier picks (see SupplierScorer.run() for schema).
    top_suppliers: List[Dict[str, Any]]

    # Drafted RFQ ids (always 'draft' status — the UI surfaces them for
    # operator approval before anything actually sends).
    drafted_rfq_ids: List[int]

    # Each candidate's normalized row for the UI refusal panel.
    candidates: List[Dict[str, Any]]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)


# ------------------------------------------------ candidate row render


def _candidate_row(q: QualificationOutcome) -> Dict[str, Any]:
    gate = q.gate_result or {}
    comp = q.compliance_result or {}
    ref = q.refusal_result or {}

    per_gate = gate.get("per_gate_passed") or {}
    failed_gate = gate.get("failed_gate")

    return {
        "candidate_name": q.candidate_name,
        "candidate_sku_id": q.candidate_sku_id,
        "candidate_supplier_name": q.candidate_supplier_name,
        "decision": q.decision,
        "compound_confidence": q.compound_confidence,
        "gate": {
            "passed": bool(gate.get("passed")),
            "failed_gate": failed_gate,
            "per_gate": per_gate,
            "notes": gate.get("notes") or {},
        },
        "compliance": {
            "outcome": comp.get("outcome"),
            "reason": comp.get("reason"),
            "per_jurisdiction": comp.get("per_jurisdiction") or [],
        },
        "refusal": {
            "decision": ref.get("decision"),
            "reason": ref.get("reason"),
            "compound_confidence": ref.get("compound_confidence"),
        },
        # Short natural-language paragraph (already rendered by
        # reasoning.justification.render). Kept inline so the UI
        # doesn't need a second fetch.
        "justification_md": q.justification_md,
    }


# --------------------------------------------------- aggregate verdict


_OUTCOME_GROUPS = {
    "recommend":           "recommend",
    "defer_human_review":  "human_review",
    # Every refusal variant (refuse_gate_fail, refuse_compliance,
    # refuse_low_confidence, refuse_baseline) collapses to 'refuse'.
}


def _bucket(decision: str) -> str:
    return _OUTCOME_GROUPS.get(decision,
                               "refuse" if decision.startswith("refuse") else "other")


def _aggregate_verdict(qs: List[QualificationOutcome]) -> Dict[str, Any]:
    buckets = {"recommend": 0, "human_review": 0, "refuse": 0, "other": 0}
    for q in qs:
        buckets[_bucket(q.decision)] += 1

    if buckets["recommend"] > 0:
        # Any clean recommend = at least one actionable path forward.
        # Fork only if we ALSO have human_review or refuse candidates
        # (i.e. there's regional or risk-split behavior).
        if buckets["human_review"] > 0 or buckets["refuse"] > 0:
            verdict = "fork"
            reason = (
                f"{buckets['recommend']} actionable; "
                f"{buckets['human_review']} need review; "
                f"{buckets['refuse']} refused"
            )
        else:
            verdict = "actionable"
            reason = f"{buckets['recommend']} / {len(qs)} candidates recommend cleanly"
    elif buckets["human_review"] > 0:
        verdict = "review"
        reason = f"{buckets['human_review']} candidates need human review"
    else:
        verdict = "refuse"
        reason = f"all {len(qs)} candidates refused"

    return {
        "verdict": verdict,
        "reason": reason,
        "recommend": buckets["recommend"],
        "human_review": buckets["human_review"],
        "refuse": buckets["refuse"],
    }


# --------------------------------------------------------- public API


def build_payload(verdict: OpportunityVerdict) -> DecisionPayload:
    agg = _aggregate_verdict(verdict.qualifications)

    return DecisionPayload(
        opportunity_id=verdict.opportunity_id,
        incumbent_name=verdict.incumbent_name,
        use_class=verdict.use_class,
        jurisdictions=list(verdict.jurisdictions),
        overall_verdict=agg["verdict"],
        overall_reason=agg["reason"],
        candidates_evaluated=len(verdict.qualifications),
        candidates_recommended=agg["recommend"],
        candidates_refused=agg["refuse"],
        candidates_human_review=agg["human_review"],
        top_suppliers=list(verdict.ranked_suppliers[:5]),
        drafted_rfq_ids=list(verdict.drafted_rfq_ids),
        candidates=[_candidate_row(q) for q in verdict.qualifications],
    )


def build_structured_summary(verdict: OpportunityVerdict, *, max_candidates: int = 3) -> str:
    """Short markdown suitable for email / slack / demo readout.

    One-line headline + a 3-column table of the top candidates + the
    top supplier (if any). No per-candidate justifications (those go
    in the DecisionPayload.candidates[*].justification_md field for
    anyone who wants the deep dive).
    """
    payload = build_payload(verdict)

    lines: List[str] = []
    verdict_label = {
        "actionable":   "ACTIONABLE",
        "fork":         "FORK RECOMMENDED",
        "review":       "HUMAN REVIEW",
        "refuse":       "REFUSED",
    }.get(payload.overall_verdict, payload.overall_verdict.upper())

    lines.append(
        f"**Opp #{payload.opportunity_id} — {payload.incumbent_name}**: "
        f"`{verdict_label}` — {payload.overall_reason}"
    )
    lines.append(
        f"- use_class: `{payload.use_class}`  ·  "
        f"jurisdictions: {', '.join(payload.jurisdictions)}  ·  "
        f"candidates: {payload.candidates_evaluated} "
        f"(✓{payload.candidates_recommended} / "
        f"⚠{payload.candidates_human_review} / "
        f"✗{payload.candidates_refused})"
    )

    # Top-N candidate table.
    lines.append("")
    lines.append("| Candidate | Decision | Compliance | Compound CC |")
    lines.append("|:----------|:---------|:-----------|------------:|")
    for row in payload.candidates[:max_candidates]:
        cname = row.get("candidate_name") or "(candidate)"
        if row.get("candidate_supplier_name"):
            cname = f"{cname} · {row['candidate_supplier_name']}"
        dec = row["decision"]
        comp = row["compliance"]["outcome"] or "—"
        cc = row["compound_confidence"]
        lines.append(f"| {cname} | `{dec}` | {comp} | {cc:.2f} |")

    # Top supplier line — the scoreboard's #1.
    if payload.top_suppliers:
        top = payload.top_suppliers[0]
        lines.append("")
        lines.append(
            f"**Top supplier:** {top['supplier_name']} "
            f"(id {top['supplier_id']})  ·  "
            f"score `{top['score']:.3f}` "
            f"(Q={top['components']['Q']:.2f} "
            f"C={top['components']['C']:.2f} "
            f"L={top['components']['L']:.2f} "
            f"R={top['components']['R']:.2f})"
        )

    if payload.drafted_rfq_ids:
        lines.append(
            f"**Drafted RFQs:** {len(payload.drafted_rfq_ids)} "
            f"({', '.join(f'#{i}' for i in payload.drafted_rfq_ids[:5])})"
        )

    return "\n".join(lines)


# ---------------------------------------------------- module self-test


def _self_test() -> None:
    """Smoke test you can run without a DB — builds a fake verdict.

    Useful for the CI-ish lane: `python -m Orchestration.decision_output`
    exits 0 and prints a demo summary.
    """
    from reasoning.gate_engine import SkuProfile
    from .planner import OpportunityVerdict
    from .qualify_candidate import QualificationOutcome

    v = OpportunityVerdict(
        opportunity_id=1,
        incumbent_name="sucralose",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU"],
    )
    v.qualifications = [
        QualificationOutcome(
            decision="recommend",
            compound_confidence=0.82,
            gate_result={
                "passed": True, "failed_gate": None,
                "notes": {}, "per_gate_passed": {"canonical": True},
            },
            compliance_result={"outcome": "pass-global", "reason": "baseline_ok",
                               "per_jurisdiction": []},
            refusal_result={"decision": "recommend", "reason": "ok",
                            "compound_confidence": 0.82},
            justification_md="- passes all gates",
        ),
        QualificationOutcome(
            decision="refuse_gate_fail",
            compound_confidence=0.15,
            gate_result={"passed": False, "failed_gate": "grade",
                         "notes": {"grade": "grade_downshift"},
                         "per_gate_passed": {"grade": False}},
            compliance_result={"outcome": "pass-global",
                               "reason": "baseline_ok", "per_jurisdiction": []},
            refusal_result={"decision": "refuse_gate_fail",
                            "reason": "gate_failed:grade",
                            "compound_confidence": 0.15},
            justification_md="- grade gate failed",
        ),
    ]
    v.ranked_suppliers = [
        {"supplier_id": 1, "supplier_name": "Demo Co",
         "score": 0.73, "components": {"Q": 0.8, "C": 0.7, "L": 0.9, "R": 0.2}},
    ]
    v.drafted_rfq_ids = [42]

    p = build_payload(v)
    print("Structured payload:")
    print(p.to_json())
    print()
    print("Structured summary:")
    print(build_structured_summary(v))


if __name__ == "__main__":
    _self_test()
