"""Supplier scoring (proposal's S = w_Q·Q + w_C·C + w_L·L − w_R·R).

This is distinct from Tim's consolidation score (which ranks opportunities).
Supplier score ranks SUPPLIERS within an already-chosen opportunity. It
does not override compliance — a supplier that fails compliance is not
scored, period (CompliancePass = 0 in the row we persist).

Q  quality     — certifications + past spec deviation + lab confidence
C  cost        — unit cost + logistics landed cost (normalized 0..1)
L  logistics   — lead time + lane reliability
R  risk        — single-source, geopolitical, audit failures

Weights default to 0.35 / 0.30 / 0.20 / 0.15 but are configurable per
ingredient class (e.g. pharma weights Q higher).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .base import Tool, ToolResult


DEFAULT_WEIGHTS = {"Q": 0.35, "C": 0.30, "L": 0.20, "R": 0.15}


@dataclass
class SupplierFeatures:
    supplier_id: int
    supplier_name: str
    quality: float        # 0..1 (higher is better)
    cost: float           # 0..1 (higher is better = cheaper landed)
    logistics: float      # 0..1 (higher is better = faster/steadier)
    risk: float           # 0..1 (higher is worse)
    compliance_pass: bool
    evidence_ids: List[int] = field(default_factory=list)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class SupplierScorer(Tool):
    name = "supplier_scorer"

    def __init__(self, conn: Optional[sqlite3.Connection] = None, weights: Optional[Dict[str, float]] = None):
        self.conn = conn
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def _score(self, f: SupplierFeatures) -> float:
        w = self.weights
        return (
            w["Q"] * _clip01(f.quality)
            + w["C"] * _clip01(f.cost)
            + w["L"] * _clip01(f.logistics)
            - w["R"] * _clip01(f.risk)
        )

    def _persist(self, opportunity_id: int, f: SupplierFeatures, s_total: float) -> Optional[int]:
        if self.conn is None:
            return None
        cur = self.conn.execute(
            """
            INSERT INTO Supplier_Score
              (OpportunityId, SupplierId,
               Q_Quality, C_Cost, L_Logistics, R_Risk,
               W_Q, W_C, W_L, W_R, S_Total, CompliancePass, EvidenceIds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                f.supplier_id,
                f.quality, f.cost, f.logistics, f.risk,
                self.weights["Q"], self.weights["C"], self.weights["L"], self.weights["R"],
                s_total,
                1 if f.compliance_pass else 0,
                ",".join(str(e) for e in f.evidence_ids) if f.evidence_ids else None,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _run(self, opportunity_id: int, suppliers: List[SupplierFeatures]) -> ToolResult:
        if not suppliers:
            return ToolResult(result=[], confidence=0.0, refusal="no_suppliers")

        ranked: List[dict] = []
        kept_evidence: List[int] = []

        for f in suppliers:
            if not f.compliance_pass:
                # Still persist the row (so the UI can explain the drop) but
                # do not include in the ranked list.
                self._persist(opportunity_id, f, 0.0)
                continue
            s_total = self._score(f)
            self._persist(opportunity_id, f, s_total)
            ranked.append(
                {
                    "supplier_id": f.supplier_id,
                    "supplier_name": f.supplier_name,
                    "score": s_total,
                    "components": {"Q": f.quality, "C": f.cost, "L": f.logistics, "R": f.risk},
                    "weights": self.weights,
                    "evidence_ids": f.evidence_ids,
                }
            )
            kept_evidence.extend(f.evidence_ids)

        ranked.sort(key=lambda r: r["score"], reverse=True)

        if not ranked:
            return ToolResult(
                result=[],
                confidence=0.0,
                refusal="all_suppliers_failed_compliance",
            )

        # Confidence = top-supplier score, clipped. Reflects how strong the
        # best option actually is — weak winners shouldn't look confident.
        return ToolResult(
            result=ranked,
            confidence=_clip01(ranked[0]["score"]),
            evidence_ids=kept_evidence,
        )
