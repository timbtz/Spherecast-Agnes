"""Render a human-readable justification for one (incumbent, candidate)
decision. Used by the UI under each shortlisted recommendation.

Inputs are the four ToolResult.result dicts produced upstream:
    * gate_result        — from GateEngine
    * compliance_result  — from ComplianceReasoner
    * refusal_result     — from RefusalEngine (decides recommend vs refuse)
    * supplier_top       — top 1-3 entries from SupplierScorer (optional)

Output is a markdown string. We deliberately keep this rule-based (no
LLM) so the demo is reproducible and we can show "no hallucination" with
a straight face. An LLM polish layer can be added later.
"""

from __future__ import annotations

from typing import Dict, List, Optional


GATE_LABELS = {
    "canonical": "Canonical identity",
    "role": "Functional role",
    "form": "Physical form",
    "grade": "Grade tier",
    "morphology": "Morphology / PSD",
    "regulatory": "Regulatory approval",
}


def _fmt_pct(x: float) -> str:
    return f"{round(100 * x)}%"


def render(
    incumbent_name: str,
    candidate_name: str,
    jurisdictions: List[str],
    gate_result: Dict,
    compliance_result: Dict,
    refusal_result: Dict,
    supplier_top: Optional[List[Dict]] = None,
) -> str:
    lines: List[str] = []
    decision = refusal_result.get("decision", "unknown")
    cc = refusal_result.get("compound_confidence", 0.0)

    lines.append(f"### {incumbent_name} → {candidate_name}")
    lines.append(f"**Decision:** `{decision}`  •  **Confidence:** {_fmt_pct(cc)}")
    lines.append(f"**Jurisdictions evaluated:** {', '.join(jurisdictions)}")
    lines.append("")

    # Gate trace
    lines.append("**Substitution gates**")
    notes = gate_result.get("notes", {})
    confs = gate_result.get("per_gate_confidence", {})
    failed = gate_result.get("failed_gate")
    for gate_key, label in GATE_LABELS.items():
        note = notes.get(gate_key, "—")
        conf = confs.get(gate_key, 0.0)
        # Pass/fail is driven by confidence — passing gates sit at 0.95+
        # and failures at ~0.10-0.45. This avoids keyword-matching quirks
        # like `smiles_exact` (passes but has no "ok"/"match" substring)
        # or `no_canonical_match` (fails but contains "match").
        passed = (gate_key != failed) and (conf >= 0.60)
        marker = "✓" if passed else "✗"
        lines.append(f"- {marker} {label}: `{note}` ({_fmt_pct(conf)})")
    if failed:
        lines.append(f"- **First gate failure:** `{failed}`")
    lines.append("")

    # Compliance trace
    lines.append("**Compliance**")
    lines.append(f"- Outcome: `{compliance_result.get('outcome')}`")
    lines.append(f"- Reason: `{compliance_result.get('reason')}`")
    for per in compliance_result.get("per_jurisdiction", []):
        impl = per.get("implicit_ok")
        impl_str = "yes" if impl is True else "no" if impl is False else "unknown"
        lines.append(
            f"  - {per['jurisdiction']}: baseline_ok={per['baseline_ok']}, "
            f"implicit_ok={impl_str}, conf={_fmt_pct(per['confidence'])}"
        )
    lines.append("")

    # Supplier shortlist
    if supplier_top:
        lines.append("**Top suppliers (ranked)**")
        for i, s in enumerate(supplier_top[:3], start=1):
            comps = s.get("components", {})
            lines.append(
                f"{i}. {s['supplier_name']} — score `{s['score']:.3f}` "
                f"(Q={comps.get('Q', 0):.2f}, C={comps.get('C', 0):.2f}, "
                f"L={comps.get('L', 0):.2f}, R={comps.get('R', 0):.2f})"
            )
        lines.append("")

    # Refusal explainer
    if decision.startswith("refuse"):
        lines.append("**Why we refused**")
        lines.append(f"- {refusal_result.get('decision')} at compound confidence {_fmt_pct(cc)}.")
        lines.append("- Every refusal is logged to `Refusal_Record` with full evidence trail.")
    elif decision == "defer_human_review":
        lines.append("**Held for human review**")
        lines.append("- Baseline regulatory check passes, but incumbent precedent is ambiguous.")
        lines.append("- A buyer should sign off before this enters an RFQ.")
    return "\n".join(lines)
