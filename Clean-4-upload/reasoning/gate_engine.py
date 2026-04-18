"""Substitution gate engine.

Six-gate chain in strict order:
    1. Canonical  -- same SMILES or same UNII (identity check) OR a curated
                     Ingredient_Substitution edge (equivalent/partial) when
                     identity checks don't match
    2. Role       -- same functional role in the recipe slot
    3. Form       -- compatible physical form (powder / liquid / etc.)
    4. Grade      -- pharma >= food >= feed; never downshift silently
    5. Morphology -- PSD / surface area / density (process-fit)
    6. Regulatory -- approved for target jurisdiction + use class

Each gate returns a ToolResult. If any gate fails, the chain short-circuits
and the Substitution_Gate_Result row is written with FailedGate set.

Compound confidence = product of gate confidences. Below 0.60 triggers
auto-refusal (see refusal_engine).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

from .base import Tool, ToolResult, compound_confidence


GRADE_RANK: Dict[str, int] = {
    "pharma": 3,
    "pharmaceutical": 3,
    "usp": 3,
    "ep": 3,
    "food": 2,
    "food-grade": 2,
    "technical": 1,
    "feed": 1,
    "industrial": 0,
    "unknown": -1,
}


@dataclass
class SkuProfile:
    """Normalized view of one SKU for gating. Populated by the slot inferrer
    (Tim's 4b) + canonical enrichment (Tim's 4a)."""

    sku_id: int
    canonical_id: Optional[int]
    smiles: Optional[str]
    unii: Optional[str]
    role: Optional[str]
    form: Optional[str]          # 'powder'|'liquid'|...
    processing: Optional[str]    # 'spray-dried'|...
    grade: Optional[str]         # 'pharma'|'food'|...
    psd_bucket: Optional[str]
    surface_area_m2g: Optional[float]
    bulk_density_gml: Optional[float]
    jurisdictions_approved: List[str]  # ['US-FDA', 'EU', ...]
    use_class: Optional[str]     # 'direct-food-additive', 'dietary-supplement', ...


@dataclass
class GateOutcome:
    passed: bool
    confidence: float
    note: str


class GateEngine(Tool):
    name = "gate_engine"

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        """Optional sqlite connection unlocks the curated-substitution
        fallback in the canonical gate. Without it, the gate is strictly
        identity-based (smiles / unii / canonical_id)."""
        self.conn = conn

    # ------------------------------------------------------------------ gates

    # Passing-gate confidences are intentionally close to 1.0 -- the compound
    # is multiplicative across 6 gates, so per-gate confidence below ~0.95
    # collapses any chain to <0.60. Failure confidences are lower because
    # the chain short-circuits and we want the floor to bite hard.

    def _canonical(self, inc: SkuProfile, cand: SkuProfile) -> GateOutcome:
        if inc.smiles and cand.smiles and inc.smiles == cand.smiles:
            return GateOutcome(True, 0.99, "smiles_exact")
        if inc.unii and cand.unii and inc.unii == cand.unii:
            return GateOutcome(True, 0.98, "unii_exact")
        if inc.canonical_id and cand.canonical_id and inc.canonical_id == cand.canonical_id:
            return GateOutcome(True, 0.95, "canonical_id_match")

        # Curated-graph fallback: if a curated substitution edge exists for
        # this pair, treat it as a soft-canonical pass. The edge type and
        # score drive the confidence — an 'identical' edge is near-par with
        # an SMILES match; 'equivalent' salts/forms sit in the 0.85-0.95
        # range; 'partial' subs sit lower and must be strong enough (>=0.75
        # curated score) to pass the chain at all.
        if self.conn is not None and inc.canonical_id and cand.canonical_id:
            row = self.conn.execute(
                """SELECT SubstitutionType, Score
                   FROM Ingredient_Substitution
                   WHERE IngredientAId = ? AND IngredientBId = ?""",
                (inc.canonical_id, cand.canonical_id),
            ).fetchone()
            if row:
                sub_type, score = row
                score = float(score or 0.0)
                if sub_type == "identical":
                    return GateOutcome(True, 0.96, f"curated_identical:{score:.2f}")
                if sub_type == "equivalent" and score >= 0.80:
                    # Equivalent salts of the same active -- interchangeable
                    # at the recipe level but with a small confidence hit
                    # vs strict chemical identity.
                    return GateOutcome(True, 0.92, f"curated_equivalent:{score:.2f}")
                if sub_type == "partial" and score >= 0.75:
                    # Partial subs always leave something on the table
                    # (bioavailability, solubility, etc). Pass with a
                    # visible confidence dent so downstream sees the risk.
                    return GateOutcome(True, 0.84, f"curated_partial:{score:.2f}")
                # Below-threshold curated edge -- still treat as soft-fail.
                return GateOutcome(False, 0.3, f"curated_below_threshold:{sub_type}:{score:.2f}")

        return GateOutcome(False, 0.1, "no_canonical_match")

    def _role(self, inc: SkuProfile, cand: SkuProfile) -> GateOutcome:
        # Empty role on BOTH sides (or "unknown" on both) means we have no
        # signal either way — we can't catch a real mismatch, but we also
        # can't fabricate one. Soft-pass with a visible confidence dent so
        # downstream sees the uncertainty. If only one side is annotated
        # we still can't compare, but we know at least one side expects
        # something specific — keep that as a soft fail.
        inc_role = (inc.role or "").lower() or None
        cand_role = (cand.role or "").lower() or None
        inc_missing = inc_role in (None, "unknown")
        cand_missing = cand_role in (None, "unknown")
        if inc_missing and cand_missing:
            # 0.88 (not 0.75) — this note compounds with up to four other
            # "unknown but accepted" passes (form/grade/morphology/regulatory).
            # Keep it close enough to 1.0 that the chain doesn't collapse
            # below the 0.60 floor purely from stacking missing-data passes,
            # but low enough to flag the missing signal in the audit trail.
            return GateOutcome(True, 0.88, "role_unknown_both_sides_accepted")
        if inc_missing or cand_missing:
            return GateOutcome(False, 0.35, "role_missing_one_side")
        if inc_role == cand_role:
            return GateOutcome(True, 0.97, f"role_match:{inc_role}")
        return GateOutcome(False, 0.2, f"role_mismatch:{inc_role}!={cand_role}")

    def _form(self, inc: SkuProfile, cand: SkuProfile) -> GateOutcome:
        # Liquid vs powder is a hard line for most processes.
        if not inc.form or not cand.form:
            return GateOutcome(False, 0.4, "form_missing")
        compatible = {
            ("powder", "powder"), ("powder", "granular"), ("granular", "powder"),
            ("granular", "granular"), ("liquid", "liquid"), ("flake", "flake"),
            ("crystal", "crystal"), ("crystal", "powder"), ("powder", "crystal"),
        }
        if (inc.form, cand.form) in compatible:
            return GateOutcome(True, 0.96, f"form_ok:{inc.form}/{cand.form}")
        return GateOutcome(False, 0.2, f"form_incompatible:{inc.form}/{cand.form}")

    def _grade(self, inc: SkuProfile, cand: SkuProfile) -> GateOutcome:
        inc_rank = GRADE_RANK.get((inc.grade or "unknown").lower(), -1)
        cand_rank = GRADE_RANK.get((cand.grade or "unknown").lower(), -1)
        if inc_rank < 0 or cand_rank < 0:
            return GateOutcome(False, 0.35, "grade_unknown")
        if cand_rank >= inc_rank:
            return GateOutcome(True, 0.97, f"grade_ok:{cand.grade}>={inc.grade}")
        return GateOutcome(False, 0.2, f"grade_downshift:{cand.grade}<{inc.grade}")

    def _morphology(self, inc: SkuProfile, cand: SkuProfile) -> GateOutcome:
        # PSD bucket match is the strongest signal; otherwise surface area within 2x.
        if inc.psd_bucket and cand.psd_bucket:
            if inc.psd_bucket == cand.psd_bucket:
                return GateOutcome(True, 0.95, f"psd_match:{inc.psd_bucket}")
            return GateOutcome(False, 0.4, f"psd_mismatch:{inc.psd_bucket}/{cand.psd_bucket}")
        if inc.surface_area_m2g and cand.surface_area_m2g:
            ratio = cand.surface_area_m2g / inc.surface_area_m2g
            if 0.5 <= ratio <= 2.0:
                return GateOutcome(True, 0.85, f"surface_area_within_2x:{ratio:.2f}")
            return GateOutcome(False, 0.3, f"surface_area_outside_2x:{ratio:.2f}")
        # If nothing is known, be honest -- don't fake confidence. But
        # don't nuke the chain either: 0.90 keeps a curated-equivalent
        # pair with unknown role+morphology above the 0.60 floor when
        # everything else lines up. Tim's morphology enrichment (PSD,
        # surface area, bulk density) will light up the stronger paths
        # automatically once populated.
        return GateOutcome(True, 0.90, "morphology_unknown_accepted")

    def _regulatory(
        self, inc: SkuProfile, cand: SkuProfile, jurisdiction: str
    ) -> GateOutcome:
        if jurisdiction in cand.jurisdictions_approved:
            return GateOutcome(True, 0.97, f"reg_approved:{jurisdiction}")
        return GateOutcome(False, 0.2, f"reg_not_approved:{jurisdiction}")

    # ---------------------------------------------------------------- entry

    def _run(
        self,
        incumbent: SkuProfile,
        candidate: SkuProfile,
        jurisdiction: str,
        evidence_ids: Optional[List[int]] = None,
    ) -> ToolResult:
        chain = [
            ("canonical", self._canonical(incumbent, candidate)),
            ("role", self._role(incumbent, candidate)),
            ("form", self._form(incumbent, candidate)),
            ("grade", self._grade(incumbent, candidate)),
            ("morphology", self._morphology(incumbent, candidate)),
            ("regulatory", self._regulatory(incumbent, candidate, jurisdiction)),
        ]

        first_failure: Optional[str] = None
        confidences: List[float] = []
        for gate_name, outcome in chain:
            confidences.append(outcome.confidence)
            if not outcome.passed and first_failure is None:
                first_failure = gate_name
                # Keep walking so we capture the full trace in the result, but
                # downstream persister only needs the first failure.

        overall = first_failure is None
        cc = compound_confidence(confidences)
        notes = {name: out.note for name, out in chain}

        return ToolResult(
            result={
                "passed": overall,
                "failed_gate": first_failure,
                "notes": notes,
                "per_gate_confidence": {n: c for (n, _), c in zip(chain, confidences)},
                "per_gate_passed": {name: bool(out.passed) for name, out in chain},
            },
            confidence=cc,
            evidence_ids=list(evidence_ids or []),
            refusal=None if overall else f"gate_failed:{first_failure}",
        )
