"""Playbook §7 tools — light-weight typed wrappers around the persistence
layer that the planner / critic / re-evaluator lean on.

Five tools:
    update_research_map       — append/merge facts into an LLM-maintained
                                wiki page per (ingredient, topic).
    record_case               — close the loop on every decision by writing
                                a case entry (lesson + confidence) the
                                re-evaluator and critic can learn from.
    flag_for_reeval           — enqueue a (substitution, trigger_class)
                                pair for the re-evaluator daemon.
    aggregate_demand          — roll up BOM_Component_Quantity into a
                                (canonical_id -> total_kg / company_count)
                                view; also persists a snapshot so the
                                planner can decide RFQ urgency tiers.
    derive_implicit_standard  — infer the "what do trusted incumbents
                                actually use in this J?" answer from
                                Product_Compliance + Supplier_Commercial,
                                with an evidence trail.

Every tool obeys the ToolResult contract (`result`, `confidence`,
`evidence_ids`, `refusal`). Every tool self-heals its backing table on
first call so the demo can run without a separate migration step.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import Tool, ToolResult, compound_confidence


# --------------------------------------------------------------- schema


_SCHEMA_RESEARCH_MAP = """
CREATE TABLE IF NOT EXISTS Research_Map (
    Id            INTEGER PRIMARY KEY AUTOINCREMENT,
    IngredientId  INTEGER NOT NULL,
    Topic         TEXT    NOT NULL,
    FactsJson     TEXT    NOT NULL,      -- append-only JSON array of facts
    Source        TEXT,
    Confidence    REAL,
    UpdatedAt     TEXT    DEFAULT (datetime('now')),
    UNIQUE (IngredientId, Topic)
);
"""

_SCHEMA_CASE_LIBRARY = """
CREATE TABLE IF NOT EXISTS Case_Library (
    CaseId         INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId  INTEGER,
    CandidateSkuId INTEGER,
    Decision       TEXT    NOT NULL,
    Reason         TEXT,
    Lesson         TEXT,
    Confidence     REAL,
    EvidenceIds    TEXT,
    CreatedAt      TEXT    DEFAULT (datetime('now'))
);
"""

_SCHEMA_REEVAL_QUEUE = """
CREATE TABLE IF NOT EXISTS Re_Eval_Queue (
    QueueId        INTEGER PRIMARY KEY AUTOINCREMENT,
    SubstitutionId INTEGER,
    OpportunityId  INTEGER,
    CandidateSkuId INTEGER,
    TriggerClass   TEXT    NOT NULL,    -- one of TRIGGER_CLASSES below
    Reason         TEXT,
    Urgency        TEXT    NOT NULL DEFAULT 'normal',
    Status         TEXT    NOT NULL DEFAULT 'pending',
    CreatedAt      TEXT    DEFAULT (datetime('now')),
    ResolvedAt     TEXT
);
"""

_SCHEMA_DEMAND = """
CREATE TABLE IF NOT EXISTS Demand_Aggregate (
    CanonicalId  INTEGER PRIMARY KEY,
    TotalKg      REAL,
    CompanyCount INTEGER,
    BomCount     INTEGER,
    SnapshotAt   TEXT DEFAULT (datetime('now'))
);
"""


TRIGGER_CLASSES = {
    "cert_expiring",
    "flagged_for_reeval",
    "supplier_down",
    "new_compliance_rule",
    "price_shift",
    "lead_time_shift",
    "demand_shift",
    "new_case_learned",
}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Idempotently create the §7 tables. Caller is free to run this
    multiple times. We don't touch existing tables or alter columns."""
    for stmt in (_SCHEMA_RESEARCH_MAP, _SCHEMA_CASE_LIBRARY,
                 _SCHEMA_REEVAL_QUEUE, _SCHEMA_DEMAND):
        conn.execute(stmt)
    conn.commit()


# ---------------------------------------------------------- tool classes


@dataclass
class ResearchFact:
    claim: str
    source: Optional[str] = None
    confidence: Optional[float] = None


class UpdateResearchMap(Tool):
    """Append facts to the per-(ingredient, topic) research map.

    The map is an append-only JSON list — we never overwrite a prior claim
    because auditability matters more than size. Callers dedupe on `claim`
    before handing us the list.
    """
    name = "update_research_map"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        _ensure_schema(conn)

    def _run(
        self,
        ingredient_id: int,
        topic: str,
        facts: List[ResearchFact],
        evidence_ids: Optional[List[int]] = None,
    ) -> ToolResult:
        if not topic:
            return ToolResult(result=None, confidence=0.0, refusal="empty_topic")
        if not facts:
            return ToolResult(result=None, confidence=0.0, refusal="empty_facts")

        evidence_ids = list(evidence_ids or [])
        confs = [f.confidence for f in facts if f.confidence is not None]
        # Compound is *too* harsh when rolling up dozens of facts; use mean
        # so adding more evidence doesn't paradoxically lower our trust.
        rollup_conf = sum(confs) / len(confs) if confs else None

        row = self.conn.execute(
            "SELECT Id, FactsJson FROM Research_Map WHERE IngredientId=? AND Topic=?",
            (ingredient_id, topic),
        ).fetchone()

        new_facts = [
            {"claim": f.claim, "source": f.source, "confidence": f.confidence}
            for f in facts
        ]

        if row is None:
            cur = self.conn.execute(
                """INSERT INTO Research_Map
                   (IngredientId, Topic, FactsJson, Source, Confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (ingredient_id, topic, json.dumps(new_facts),
                 facts[0].source, rollup_conf),
            )
            map_id = int(cur.lastrowid)
            merged = new_facts
        else:
            map_id = int(row[0])
            existing = json.loads(row[1] or "[]")
            # Dedupe by (claim, source).
            seen = {(f["claim"], f.get("source")) for f in existing}
            to_add = [f for f in new_facts if (f["claim"], f["source"]) not in seen]
            merged = existing + to_add
            self.conn.execute(
                """UPDATE Research_Map
                   SET FactsJson=?, Confidence=?, UpdatedAt=datetime('now')
                   WHERE Id=?""",
                (json.dumps(merged), rollup_conf, map_id),
            )
        self.conn.commit()

        return ToolResult(
            result={
                "map_id": map_id,
                "ingredient_id": ingredient_id,
                "topic": topic,
                "fact_count": len(merged),
                "added": len([f for f in new_facts if f]),
            },
            confidence=rollup_conf if rollup_conf is not None else 0.6,
            evidence_ids=evidence_ids,
        )


class RecordCase(Tool):
    """Write a closed-decision entry the critic / re-evaluator can learn from."""
    name = "record_case"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        _ensure_schema(conn)

    def _run(
        self,
        decision: str,
        reason: str,
        lesson: Optional[str] = None,
        opportunity_id: Optional[int] = None,
        candidate_sku_id: Optional[int] = None,
        confidence: Optional[float] = None,
        evidence_ids: Optional[List[int]] = None,
    ) -> ToolResult:
        if not decision:
            return ToolResult(result=None, confidence=0.0, refusal="empty_decision")

        evidence_ids = list(evidence_ids or [])
        cur = self.conn.execute(
            """INSERT INTO Case_Library
               (OpportunityId, CandidateSkuId, Decision, Reason, Lesson,
                Confidence, EvidenceIds)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                opportunity_id,
                candidate_sku_id,
                decision,
                reason,
                lesson,
                confidence,
                ",".join(str(e) for e in evidence_ids) if evidence_ids else None,
            ),
        )
        self.conn.commit()
        return ToolResult(
            result={"case_id": int(cur.lastrowid), "decision": decision},
            confidence=confidence if confidence is not None else 0.9,
            evidence_ids=evidence_ids,
        )


class FlagForReeval(Tool):
    """Enqueue a substitution for re-evaluation by the daemon.

    trigger_class must be one of TRIGGER_CLASSES; unknown triggers refuse
    rather than silently corrupt the queue schema.
    """
    name = "flag_for_reeval"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        _ensure_schema(conn)

    def _run(
        self,
        trigger_class: str,
        reason: str,
        substitution_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        candidate_sku_id: Optional[int] = None,
        urgency: str = "normal",
        evidence_ids: Optional[List[int]] = None,
    ) -> ToolResult:
        if trigger_class not in TRIGGER_CLASSES:
            return ToolResult(
                result=None,
                confidence=0.0,
                refusal=f"unknown_trigger_class:{trigger_class}",
            )
        if urgency not in {"low", "normal", "high", "critical"}:
            urgency = "normal"

        evidence_ids = list(evidence_ids or [])
        cur = self.conn.execute(
            """INSERT INTO Re_Eval_Queue
               (SubstitutionId, OpportunityId, CandidateSkuId,
                TriggerClass, Reason, Urgency)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (substitution_id, opportunity_id, candidate_sku_id,
             trigger_class, reason, urgency),
        )
        self.conn.commit()
        return ToolResult(
            result={
                "queue_id": int(cur.lastrowid),
                "trigger_class": trigger_class,
                "urgency": urgency,
            },
            # High-quality "known trigger" flag; confidence reflects that the
            # daemon is guaranteed to pick this up, not that the trigger is
            # itself accurate.
            confidence=0.9,
            evidence_ids=evidence_ids,
        )


class AggregateDemand(Tool):
    """Roll up BOM_Component_Quantity into (canonical_id -> total_kg)."""
    name = "aggregate_demand"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        _ensure_schema(conn)

    # Mass-like units only (anything dimensionless like IU or "mcg DFE" is
    # skipped — we only aggregate what we can honestly add together).
    _UNIT_TO_KG = {
        "kg": 1.0,
        "g": 1e-3, "gram(s)": 1e-3, "grams": 1e-3,
        "mg": 1e-6, "milligram(s)": 1e-6,
        "mcg": 1e-9, "microgram(s)": 1e-9, "ug": 1e-9, "µg": 1e-9,
    }

    def _to_kg(self, amount: Optional[float], unit: Optional[str]) -> Optional[float]:
        if amount is None or unit is None:
            return None
        mult = self._UNIT_TO_KG.get(unit.strip().lower())
        if mult is None:
            return None
        return float(amount) * mult

    def _run(
        self,
        canonical_id: Optional[int] = None,
        persist_snapshot: bool = True,
    ) -> ToolResult:
        # The enriched schema uses (BOMId, ConsumedProductId) as the component
        # key — there is no separate BOM_Component.Id surrogate. Company
        # linkage runs through the *consumed* product (the ingredient SKU)
        # rather than through BOM itself, since the enrichment pipeline
        # doesn't populate a CompanyId on BOM.
        where = "WHERE stc.CanonicalId = ?" if canonical_id is not None else ""
        params = (canonical_id,) if canonical_id is not None else ()

        rows = self.conn.execute(
            f"""
            SELECT stc.CanonicalId             AS cid,
                   bcq.Amount                  AS amount,
                   bcq.Unit                    AS unit,
                   bc.BOMId                    AS bom_id,
                   p.CompanyId                 AS company_id
            FROM BOM_Component bc
            LEFT JOIN BOM_Component_Quantity bcq
                   ON bcq.BOMId = bc.BOMId
                  AND bcq.ConsumedProductId = bc.ConsumedProductId
            JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
            LEFT JOIN Product p         ON p.Id = bc.ConsumedProductId
            {where}
            """,
            params,
        ).fetchall()

        by_cid: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            cid = int(r[0])
            entry = by_cid.setdefault(cid, {
                "canonical_id": cid,
                "total_kg": 0.0,
                "_kg_seen": False,
                "_companies": set(),
                "_boms": set(),
            })
            kg = self._to_kg(r[1], r[2])
            if kg is not None:
                entry["total_kg"] += kg
                entry["_kg_seen"] = True
            if r[3] is not None:
                entry["_boms"].add(int(r[3]))
            if r[4] is not None:
                entry["_companies"].add(int(r[4]))

        out: List[Dict[str, Any]] = []
        for e in by_cid.values():
            out.append({
                "canonical_id": e["canonical_id"],
                "total_kg": e["total_kg"] if e["_kg_seen"] else None,
                "company_count": len(e["_companies"]),
                "bom_count": len(e["_boms"]),
            })

        if persist_snapshot and out:
            for r in out:
                self.conn.execute(
                    """INSERT OR REPLACE INTO Demand_Aggregate
                       (CanonicalId, TotalKg, CompanyCount, BomCount, SnapshotAt)
                       VALUES (?, ?, ?, ?, datetime('now'))""",
                    (r["canonical_id"], r["total_kg"],
                     r["company_count"], r["bom_count"]),
                )
            self.conn.commit()

        if not out:
            return ToolResult(
                result={"rows": [], "canonical_id": canonical_id},
                confidence=0.5,
                refusal="no_demand_rows",
            )

        return ToolResult(
            result={"rows": out, "canonical_id": canonical_id},
            # Confidence reflects data density — more companies = more trust.
            confidence=min(0.95, 0.5 + 0.05 * sum(r["company_count"] for r in out)),
        )


class DeriveImplicitStandard(Tool):
    """Infer 'do trusted incumbents use this canonical in this J?' from the
    enriched data: any product mapped to this canonical carrying a
    confirmed cert counts as an incumbent precedent. We report the
    evidence count + the jurisdictional outcome (True/False/None)."""
    name = "derive_implicit_standard"

    # Cert -> jurisdiction weight. These mirror the logic in
    # Orchestration.demo_real.fetch_incumbent_precedents so the two code
    # paths stay consistent.
    CERT_TO_J: Dict[str, List[str]] = {
        "NSF":           ["US-FDA", "CA"],
        "USP":           ["US-FDA", "US-USP", "CA"],
        "InformedSport": ["US-FDA", "EU"],
        "BSCG":          ["US-FDA", "EU"],
        "NonGMO":        ["US-FDA", "CA"],
        "Kosher":        ["US-FDA", "EU", "CA", "JP"],
        "GlutenFree":    ["US-FDA", "EU", "CA", "JP"],
        "Vegan":         ["US-FDA", "EU", "CA"],
        "Organic":       ["US-FDA", "EU"],
        "Halal":         ["US-FDA", "EU", "JP"],
        "JHFA":          ["JP"],            # Japan Health Food Authorization
        "FOSHU":         ["JP"],            # Food for Specified Health Uses
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # Status weight: 'confirmed' carries full weight; 'implied' (the
    # default state of an enrichment-inferred cert) is counted at half
    # weight — real enough to matter, not strong enough to greenlight
    # global use alone.
    _STATUS_WEIGHT = {"confirmed": 1.0, "implied": 0.5}

    def _run(
        self,
        canonical_id: int,
        jurisdiction: str,
    ) -> ToolResult:
        # Product_Compliance tags the *finished* product (BOM producer),
        # while SKU_To_Canonical maps the *consumed* ingredient SKU. To
        # infer implicit standard for an ingredient canonical, walk:
        #   Ingredient canonical → consumed SKU → BOM → produced SKU →
        #   finished product certs.
        #
        # We DISTINCT on (ProductId, Certification) so a single finished
        # product with a cert contributes at most once, regardless of how
        # many times it appears in BOM_Component.
        rows = self.conn.execute(
            """SELECT DISTINCT pc.Certification, pc.Status
               FROM Product_Compliance pc
               JOIN BOM b              ON b.ProducedProductId = pc.ProductId
               JOIN BOM_Component bc   ON bc.BOMId = b.Id
               JOIN SKU_To_Canonical m ON m.ProductId = bc.ConsumedProductId
               WHERE m.CanonicalId = ?""",
            (canonical_id,),
        ).fetchall()

        if not rows:
            return ToolResult(
                result={
                    "canonical_id": canonical_id,
                    "jurisdiction": jurisdiction,
                    "implicit_ok": False,
                    "match_weight": 0.0,
                    "match_count": 0,
                    "total_certs": 0,
                    "reason": "no_incumbent_precedent",
                },
                confidence=0.75,
            )

        match_weight = 0.0
        match_count = 0
        for cert, status in rows:
            w = self._STATUS_WEIGHT.get((status or "").lower(), 0.0)
            if w == 0.0:
                continue
            if jurisdiction in self.CERT_TO_J.get((cert or "").strip(), []):
                match_weight += w
                match_count += 1

        if match_weight >= 2.0:
            implicit_ok: Optional[bool] = True
            reason = f"implicit_ok:weight={match_weight:.1f}"
            confidence = 0.92
        elif match_weight >= 1.0:
            implicit_ok = True
            reason = f"implicit_ok_soft:weight={match_weight:.1f}"
            confidence = 0.80
        elif match_weight > 0.0:
            # Sub-unity weight is weak evidence — flag as ambiguous.
            implicit_ok = None
            reason = f"implicit_ambiguous:weight={match_weight:.1f}"
            confidence = 0.70
        else:
            implicit_ok = False
            reason = "no_cert_matched_jurisdiction"
            confidence = 0.72

        return ToolResult(
            result={
                "canonical_id": canonical_id,
                "jurisdiction": jurisdiction,
                "implicit_ok": implicit_ok,
                "match_weight": round(match_weight, 2),
                "match_count": match_count,
                "total_certs": len(rows),
                "reason": reason,
            },
            confidence=confidence,
        )
