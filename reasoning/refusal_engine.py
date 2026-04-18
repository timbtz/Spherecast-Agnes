"""Refusal engine.

Single chokepoint for "do we recommend this candidate at all". Wraps gate
+ compliance results and decides:
    * recommend
    * refuse_low_confidence  (compound < 0.60)
    * refuse_gate_fail
    * refuse_compliance
    * defer_human_review

Every refusal is persisted to Refusal_Record so the demo can show *why*
something didn't make the shortlist (this is the proposal's "auditable"
promise made concrete).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from .base import Tool, ToolResult


CONFIDENCE_FLOOR = 0.60


@dataclass
class RefusalContext:
    opportunity_id: int
    candidate_sku_id: Optional[int]
    gate_result: dict          # ToolResult.result from GateEngine
    gate_confidence: float
    compliance_result: dict    # ToolResult.result from ComplianceReasoner
    compliance_confidence: float
    evidence_ids: List[int]


class RefusalEngine(Tool):
    name = "refusal_engine"

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self.conn = conn

    def _persist(
        self,
        opportunity_id: int,
        candidate_sku_id: Optional[int],
        reason: str,
        compound_confidence: float,
        failing_gate: Optional[str],
        evidence_ids: List[int],
    ) -> Optional[int]:
        if self.conn is None:
            return None
        cur = self.conn.execute(
            """
            INSERT INTO Refusal_Record
              (OpportunityId, CandidateSkuId, Reason, CompoundConfidence,
               FailingGate, EvidenceIds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                candidate_sku_id,
                reason,
                compound_confidence,
                failing_gate,
                ",".join(str(e) for e in evidence_ids) if evidence_ids else None,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _run(self, ctx: RefusalContext) -> ToolResult:
        # Compound confidence across gate + compliance.
        compound = ctx.gate_confidence * ctx.compliance_confidence

        gate_passed = bool(ctx.gate_result.get("passed"))
        outcome = ctx.compliance_result.get("outcome")

        if not gate_passed:
            failing = ctx.gate_result.get("failed_gate")
            self._persist(
                ctx.opportunity_id,
                ctx.candidate_sku_id,
                f"gate_fail:{failing}",
                compound,
                failing,
                ctx.evidence_ids,
            )
            return ToolResult(
                result={"decision": "refuse_gate_fail", "compound_confidence": compound},
                confidence=compound,
                refusal=f"gate_fail:{failing}",
            )

        if outcome == "refuse":
            self._persist(
                ctx.opportunity_id,
                ctx.candidate_sku_id,
                "compliance_refuse",
                compound,
                None,
                ctx.evidence_ids,
            )
            return ToolResult(
                result={"decision": "refuse_compliance", "compound_confidence": compound},
                confidence=compound,
                refusal="compliance_refuse",
            )

        if compound < CONFIDENCE_FLOOR:
            self._persist(
                ctx.opportunity_id,
                ctx.candidate_sku_id,
                "below_threshold",
                compound,
                None,
                ctx.evidence_ids,
            )
            return ToolResult(
                result={"decision": "refuse_low_confidence", "compound_confidence": compound},
                confidence=compound,
                refusal=f"low_confidence:{compound:.2f}",
            )

        if outcome == "human-review":
            return ToolResult(
                result={"decision": "defer_human_review", "compound_confidence": compound},
                confidence=compound,
            )

        return ToolResult(
            result={"decision": "recommend", "compound_confidence": compound, "outcome": outcome},
            confidence=compound,
        )
