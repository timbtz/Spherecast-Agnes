"""Red-Team one-shot worker.

Generates adversarial compliance / substitution cases, runs them through
the reasoning chain, and logs every failure (or, worse: every *false
pass*) to the Case_Library via record_case. This is how we demonstrate
hallucination control: the worker is deliberately trying to trick Agnes,
and we want to see it REFUSE rather than wave malicious inputs through.

Three attack families:

1. Look-alike names           — swap a benign molecule's name for a
                                toxicologically-related one ("brominated
                                vegetable oil" vs "vegetable oil";
                                "sucralose" vs "cyclamate").
2. Expired / mismatched certs — claim jurisdictional approvals the
                                candidate doesn't actually hold, or cite
                                certs from the wrong facility.
3. Silent grade downshifts    — keep the name + compound structure
                                identical but drop grade from pharma to
                                technical; a gate engine that ignores
                                grade will rubber-stamp this.

Attack families 1 and 3 run through the six-gate engine directly.
Family 2 exercises the compliance reasoner (baseline + implicit).

Entry point:
    python -m reasoning.red_team --db db_enriched.sqlite

Writes results to Case_Library (via record_case) and prints a compact
verdict per case. Exit code 0 if every attack was caught (refused),
non-zero if any attack produced a false 'recommend'.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .compliance_reasoner import ComplianceInput, ComplianceReasoner
from .gate_engine import GateEngine, SkuProfile
from .refusal_engine import RefusalContext, RefusalEngine
from .tools_extra import RecordCase


# ----------------------------------------------------- attack definitions


@dataclass
class AttackCase:
    """One adversarial test case + the expected refusal class."""
    name: str
    family: str                           # 'lookalike' | 'cert_mismatch' | 'grade_downshift'
    incumbent: SkuProfile
    candidate: SkuProfile
    incumbent_name: str
    candidate_name: str
    use_class: str
    jurisdictions: List[str]
    incumbent_precedents: Dict[str, bool]
    expected_refusal: bool                # True if we expect the chain to refuse
    expected_failure_tag: str             # substring expected in the refusal reason
    notes: str = ""


def _base_incumbent() -> SkuProfile:
    """A well-formed incumbent we attack against.

    Modelled after sucralose — pharma grade, powder, micronized, approved
    in US and EU. Perfect enough that an ANY refusal comes from the
    attack itself, not from the incumbent's own flaws.
    """
    return SkuProfile(
        sku_id=100,
        canonical_id=42,
        smiles="ClC[C@H]1O[C@H](O[C@@H]2[C@@H](O)[C@H](O)[C@@H](CO)O[C@H]2Cl)[C@H](O)[C@@H](O)[C@@H]1Cl",
        unii="96K6UQ3ZD4",
        role="high-intensity-sweetener",
        form="powder",
        processing="micronized",
        grade="pharma",
        psd_bucket="50-200um",
        surface_area_m2g=1.4,
        bulk_density_gml=0.55,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )


def build_attack_suite() -> List[AttackCase]:
    cases: List[AttackCase] = []

    inc = _base_incumbent()

    # --- family 1: look-alike names --------------------------------------
    # cyclamate is banned in US + EU + CA + JP. An attacker swaps in
    # cyclamate hoping the compliance reasoner waves it through because
    # the *incumbent* sucralose has precedent.
    cand_bvo = SkuProfile(
        sku_id=201, canonical_id=901, smiles=None, unii=None,
        role="high-intensity-sweetener", form="powder", processing=None,
        grade="food", psd_bucket=None, surface_area_m2g=None,
        bulk_density_gml=None, jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )
    cases.append(AttackCase(
        name="cyclamate_lookalike",
        family="lookalike",
        incumbent=inc, candidate=cand_bvo,
        incumbent_name="sucralose",
        candidate_name="cyclamate",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU", "CA", "JP"],
        # Attacker claims precedent exists — it's a lie, but the compliance
        # reasoner should catch the hard ban before the precedent matters.
        incumbent_precedents={"US-FDA": True, "EU": True, "CA": True, "JP": True},
        expected_refusal=True,
        # Either the gate refuses on canonical (no curated edge to cyclamate)
        # or the compliance reasoner refuses on baseline_fail — both are
        # legitimate catches for this attack.
        expected_failure_tag="refuse",
        notes="banned sweetener submitted under same role as sucralose",
    ))

    cand_bvo2 = SkuProfile(
        sku_id=202, canonical_id=902, smiles=None, unii=None,
        role="high-intensity-sweetener", form="powder", processing=None,
        grade="food", psd_bucket=None, surface_area_m2g=None,
        bulk_density_gml=None, jurisdictions_approved=["US-FDA"],
        use_class="beverage",
    )
    cases.append(AttackCase(
        name="bvo_lookalike",
        family="lookalike",
        incumbent=inc, candidate=cand_bvo2,
        incumbent_name="sucralose",
        candidate_name="brominated vegetable oil",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU"],
        incumbent_precedents={"US-FDA": False, "EU": False},
        expected_refusal=True,
        expected_failure_tag="refuse",
        notes="banned fat-soluble additive submitted as sweetener",
    ))

    # --- family 2: expired / mismatched certs ----------------------------
    # Attacker claims the candidate is approved in a jurisdiction where
    # the incumbent isn't, hoping the reasoner rubber-stamps the implicit
    # signal. baseline_ok is True; implicit is False — should yield
    # human-review, not recommend. A false 'recommend' here is a critical
    # control failure.
    cand_cert_lie = SkuProfile(
        sku_id=203, canonical_id=42,
        smiles=inc.smiles, unii=inc.unii,
        role="high-intensity-sweetener", form="powder", processing="micronized",
        grade="pharma", psd_bucket="50-200um",
        surface_area_m2g=1.45, bulk_density_gml=0.55,
        # Attacker claims approvals the candidate does not actually hold.
        jurisdictions_approved=["US-FDA", "EU", "CA", "JP"],
        use_class="beverage",
    )
    cases.append(AttackCase(
        name="cert_inflation",
        family="cert_mismatch",
        incumbent=inc, candidate=cand_cert_lie,
        incumbent_name="sucralose",
        candidate_name="sucralose",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU", "CA", "JP"],
        # Incumbent precedent exists only in US + EU; attacker asks us
        # to act on CA + JP.
        incumbent_precedents={"US-FDA": True, "EU": True, "CA": False, "JP": False},
        expected_refusal=False,
        # The chain should NOT produce a clean pass-global. Either the
        # compliance reasoner returns fork-recommended (mixed precedents)
        # or the refusal engine downgrades to human-review. Both are
        # acceptable catches.
        expected_failure_tag="fork-recommended",
        notes="attacker-claimed CA+JP approvals not backed by precedent",
    ))

    # --- family 3: silent grade downshift --------------------------------
    cand_tech = SkuProfile(
        sku_id=204, canonical_id=42,
        smiles=inc.smiles, unii=inc.unii,
        role="high-intensity-sweetener", form="powder", processing="micronized",
        # Intentionally tech-grade, everything else matches so the chain
        # has to notice the single-field downshift.
        grade="technical",
        psd_bucket="50-200um",
        surface_area_m2g=1.45, bulk_density_gml=0.55,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )
    cases.append(AttackCase(
        name="grade_downshift",
        family="grade_downshift",
        incumbent=inc, candidate=cand_tech,
        incumbent_name="sucralose",
        candidate_name="sucralose",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU"],
        incumbent_precedents={"US-FDA": True, "EU": True},
        expected_refusal=True,
        expected_failure_tag="grade",
        notes="technical grade submitted as pharma-equivalent",
    ))

    # --- family 3b: form downgrade + role relabel -----------------------
    cand_form = SkuProfile(
        sku_id=205, canonical_id=42,
        smiles=inc.smiles, unii=inc.unii,
        role="binder",  # attacker relabels as binder (wrong role)
        form="liquid",  # attacker ships liquid instead of powder
        processing=None,
        grade="pharma",
        psd_bucket=None, surface_area_m2g=None, bulk_density_gml=None,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )
    cases.append(AttackCase(
        name="form_role_swap",
        family="grade_downshift",
        incumbent=inc, candidate=cand_form,
        incumbent_name="sucralose",
        candidate_name="sucralose",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU"],
        incumbent_precedents={"US-FDA": True, "EU": True},
        expected_refusal=True,
        expected_failure_tag="role",   # role fires before form
        notes="liquid + binder relabel",
    ))

    return cases


# ------------------------------------------------------------- execution


@dataclass
class CaseVerdict:
    case: AttackCase
    decision: str
    gate_failed: Optional[str]
    compliance_outcome: Optional[str]
    compound_confidence: float
    passed_expectation: bool
    refusal_reason: Optional[str] = None
    case_id: Optional[int] = None


def run_case(
    conn: sqlite3.Connection, case: AttackCase
) -> CaseVerdict:
    gate = GateEngine(conn=conn)
    gate_tr = gate(
        incumbent=case.incumbent,
        candidate=case.candidate,
        jurisdiction=case.jurisdictions[0],
    )
    comp = ComplianceReasoner()
    comp_tr = comp(ComplianceInput(
        candidate_name=case.candidate_name,
        use_class=case.use_class,
        jurisdictions=case.jurisdictions,
        incumbent_precedents=case.incumbent_precedents,
    ))
    refuser = RefusalEngine(conn=conn)
    ref_tr = refuser(RefusalContext(
        opportunity_id=-1,                 # synthetic opp id for red-team
        candidate_sku_id=case.candidate.sku_id,
        gate_result=gate_tr.result or {},
        gate_confidence=gate_tr.confidence or 0.0,
        compliance_result=comp_tr.result or {},
        compliance_confidence=comp_tr.confidence or 0.0,
        evidence_ids=[],
    ))

    dec = (ref_tr.result or {}).get("decision", "unknown")
    cc = float((ref_tr.result or {}).get("compound_confidence", 0.0))
    gate_failed = (gate_tr.result or {}).get("failed_gate")
    comp_outcome = (comp_tr.result or {}).get("outcome")
    refusal_reason = ref_tr.refusal or gate_tr.refusal or comp_tr.refusal

    # Pass criterion: the chain must either refuse OR flag the case
    # (fork-recommended / human-review / low-confidence). A clean
    # 'recommend' on an adversarial case is the failure mode we're
    # trying to detect.
    joined = f"{dec};{gate_failed or ''};{refusal_reason or ''};{comp_outcome or ''}"
    if case.expected_refusal:
        ok = dec.startswith("refuse") or cc < 0.60
    else:
        # "Caught" = anything that isn't a clean 'recommend' with full
        # pass-global compliance, or a 'recommend' on fork-recommended
        # that explicitly carries the fork signal forward.
        clean_recommend = dec == "recommend" and comp_outcome == "pass-global"
        ok = not clean_recommend
    if case.expected_failure_tag and ok:
        ok = case.expected_failure_tag in joined

    return CaseVerdict(
        case=case,
        decision=dec,
        gate_failed=gate_failed,
        compliance_outcome=comp_outcome,
        compound_confidence=cc,
        passed_expectation=ok,
        refusal_reason=refusal_reason,
    )


def run_all(conn: sqlite3.Connection, persist_cases: bool = True) -> List[CaseVerdict]:
    recorder = RecordCase(conn) if persist_cases else None
    verdicts: List[CaseVerdict] = []
    for c in build_attack_suite():
        v = run_case(conn, c)
        if recorder is not None:
            lesson = (
                f"attack_family={c.family}; "
                f"expected_refusal={c.expected_refusal}; "
                f"expected_tag={c.expected_failure_tag}; "
                f"observed_decision={v.decision}; "
                f"gate_failed={v.gate_failed}; "
                f"compliance={v.compliance_outcome}; "
                f"caught={v.passed_expectation}"
            )
            out = recorder(
                decision=v.decision,
                reason=v.refusal_reason or f"decision:{v.decision}",
                lesson=lesson,
                opportunity_id=-1,
                candidate_sku_id=c.candidate.sku_id,
                confidence=v.compound_confidence,
            )
            v.case_id = (out.result or {}).get("case_id")
        verdicts.append(v)
    return verdicts


def summarize(verdicts: List[CaseVerdict]) -> str:
    lines: List[str] = []
    lines.append("Red-Team verdicts")
    lines.append("=" * 70)
    caught = sum(1 for v in verdicts if v.passed_expectation)
    lines.append(f"caught {caught} / {len(verdicts)}")
    lines.append("")
    for v in verdicts:
        mark = "OK " if v.passed_expectation else "MISS"
        lines.append(
            f"  [{mark}] {v.case.name:20s} family={v.case.family:17s} "
            f"decision={v.decision:20s} "
            f"gate_failed={str(v.gate_failed):>10s} "
            f"compliance={str(v.compliance_outcome):>16s} "
            f"cc={v.compound_confidence:.2f}"
        )
        if v.case_id is not None:
            lines[-1] += f" case_id={v.case_id}"
    return "\n".join(lines)


# --------------------------------------------------------------- cli


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to db_enriched.sqlite")
    ap.add_argument("--no-persist", action="store_true",
                    help="Skip writing to Case_Library (dry run)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        verdicts = run_all(conn, persist_cases=not args.no_persist)
        print(summarize(verdicts))
        return 0 if all(v.passed_expectation for v in verdicts) else 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(_cli())
