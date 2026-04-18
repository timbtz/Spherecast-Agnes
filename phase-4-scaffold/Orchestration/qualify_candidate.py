"""Run the full qualification chain for one (incumbent, candidate) pair.

Sequence:
    1. Role inference (incumbent + candidate, by recipe slot)
    2. Six-gate substitution check
    3. Compliance reasoner (per requested jurisdictions)
    4. Refusal engine (compound decision)
    5. Persist to Substitution_Gate_Result + Compliance_Outcome_4State
    6. Return a packaged result + a markdown justification

This is the primary entry point planner.py uses per opportunity. It is
deliberately *blocking* (no async) so the demo is easy to step through.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from reasoning.compliance_reasoner import ComplianceInput, ComplianceReasoner
from reasoning.gate_engine import GateEngine, SkuProfile
from reasoning.justification import render
from reasoning.refusal_engine import RefusalContext, RefusalEngine
from reasoning.role_inferrer import RoleInferrer


@dataclass
class QualificationOutcome:
    decision: str
    compound_confidence: float
    gate_result: dict
    compliance_result: dict
    refusal_result: dict
    justification_md: str


def _persist_gate(
    conn: sqlite3.Connection,
    opportunity_id: int,
    incumbent: SkuProfile,
    candidate: SkuProfile,
    gate_res: dict,
    cc: float,
    evidence_ids: List[int],
) -> int:
    notes = gate_res.get("notes", {})
    cur = conn.execute(
        """
        INSERT INTO Substitution_Gate_Result
          (OpportunityId, IncumbentSkuId, CandidateSkuId,
           CanonicalGate, RoleGate, FormGate, GradeGate, MorphologyGate, RegulatoryGate,
           OverallPass, FailedGate, CompoundConfidence, EvidenceIds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            opportunity_id,
            incumbent.sku_id,
            candidate.sku_id,
            int("ok" in notes.get("canonical", "") or "match" in notes.get("canonical", "")),
            int("match" in notes.get("role", "") or "ok" in notes.get("role", "")),
            int("ok" in notes.get("form", "") or "match" in notes.get("form", "")),
            int("ok" in notes.get("grade", "")),
            int("match" in notes.get("morphology", "") or "within" in notes.get("morphology", "")),
            int("approved" in notes.get("regulatory", "")),
            int(bool(gate_res.get("passed"))),
            gate_res.get("failed_gate"),
            cc,
            ",".join(str(e) for e in evidence_ids) if evidence_ids else None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _persist_compliance(
    conn: sqlite3.Connection,
    opportunity_id: int,
    candidate: SkuProfile,
    candidate_name: str,
    inp: ComplianceInput,
    comp_res: dict,
    confidence: float,
    evidence_ids: List[int],
) -> List[int]:
    ids: List[int] = []
    for per in comp_res.get("per_jurisdiction", []):
        cur = conn.execute(
            """
            INSERT INTO Compliance_Outcome_4State
              (OpportunityId, CandidateSkuId, Jurisdiction,
               ImplicitStandard, CategoryBaseline, Outcome, Reason, Confidence, EvidenceIds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                candidate.sku_id,
                per["jurisdiction"],
                "yes" if per.get("implicit_ok") is True else "no" if per.get("implicit_ok") is False else "unknown",
                "ok" if per.get("baseline_ok") else "fail",
                comp_res.get("outcome"),
                per.get("reason"),
                per.get("confidence"),
                ",".join(str(e) for e in evidence_ids) if evidence_ids else None,
            ),
        )
        ids.append(int(cur.lastrowid))
    conn.commit()
    return ids


def qualify_candidate(
    conn: sqlite3.Connection,
    opportunity_id: int,
    incumbent: SkuProfile,
    candidate: SkuProfile,
    incumbent_name: str,
    candidate_name: str,
    use_class: str,
    jurisdictions: List[str],
    incumbent_precedents: Dict[str, bool],
    evidence_ids: Optional[List[int]] = None,
    supplier_top: Optional[List[dict]] = None,
) -> QualificationOutcome:
    evidence_ids = list(evidence_ids or [])

    # 1. Role inference (annotate the SkuProfiles in-place if missing).
    role_tool = RoleInferrer()
    if not incumbent.role:
        r_inc = role_tool(incumbent_name)
        incumbent.role = r_inc.result if r_inc.passed else None
    if not candidate.role:
        r_cand = role_tool(candidate_name)
        candidate.role = r_cand.result if r_cand.passed else None

    # 2. Six-gate check (we run once per primary jurisdiction; the planner
    #    can call this repeatedly for fork analyses).
    primary_j = jurisdictions[0]
    gate = GateEngine()
    gate_tr = gate(incumbent=incumbent, candidate=candidate, jurisdiction=primary_j, evidence_ids=evidence_ids)

    # 3. Compliance — runs across ALL jurisdictions.
    comp_tool = ComplianceReasoner()
    comp_inp = ComplianceInput(
        candidate_name=candidate_name,
        use_class=use_class,
        jurisdictions=jurisdictions,
        incumbent_precedents=incumbent_precedents,
    )
    comp_tr = comp_tool(comp_inp, evidence_ids=evidence_ids)

    # 4. Refusal engine.
    refusal_tool = RefusalEngine(conn=conn)
    ref_ctx = RefusalContext(
        opportunity_id=opportunity_id,
        candidate_sku_id=candidate.sku_id,
        gate_result=gate_tr.result or {},
        gate_confidence=gate_tr.confidence or 0.0,
        compliance_result=comp_tr.result or {},
        compliance_confidence=comp_tr.confidence or 0.0,
        evidence_ids=evidence_ids,
    )
    ref_tr = refusal_tool(ref_ctx)

    # 5. Persist.
    _persist_gate(conn, opportunity_id, incumbent, candidate, gate_tr.result or {}, gate_tr.confidence or 0.0, evidence_ids)
    if comp_tr.result:
        _persist_compliance(
            conn,
            opportunity_id,
            candidate,
            candidate_name,
            comp_inp,
            comp_tr.result,
            comp_tr.confidence or 0.0,
            evidence_ids,
        )

    # 6. Justification.
    md = render(
        incumbent_name=incumbent_name,
        candidate_name=candidate_name,
        jurisdictions=jurisdictions,
        gate_result=gate_tr.result or {},
        compliance_result=comp_tr.result or {},
        refusal_result=ref_tr.result or {},
        supplier_top=supplier_top,
    )

    return QualificationOutcome(
        decision=(ref_tr.result or {}).get("decision", "unknown"),
        compound_confidence=(ref_tr.result or {}).get("compound_confidence", 0.0),
        gate_result=gate_tr.result or {},
        compliance_result=comp_tr.result or {},
        refusal_result=ref_tr.result or {},
        justification_md=md,
    )
