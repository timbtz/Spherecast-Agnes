"""Dual-rule compliance reasoner.

Two rules run side-by-side for every (candidate, jurisdiction):

    IMPLICIT_STANDARD = heuristic inferred from trusted suppliers already
        approved in that category (what incumbents *actually* do).
    CATEGORY_BASELINE = the regulatory floor for that jurisdiction/use class
        (what the law requires at minimum).

The outcome is one of four states:
    pass-global        — passes both in every jurisdiction under consideration
    fork-recommended   — passes in some jurisdictions, fails in others
                         (recommend a regional fork rather than one global sub)
    refuse             — fails baseline in any jurisdiction → not a candidate
    human-review       — baseline OK but implicit standard ambiguous

Jurisdiction packs live in JURISDICTION_PACKS. Packs are intentionally
small lookup dicts — real regulatory data will come from tools Tim's
enrichment spine can wire in later (FDA FCS, EU EFSA, USP).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .base import Tool, ToolResult, compound_confidence


# Minimal seed pack — real rules will be loaded from Tim's enriched DB.
# Each rule is (allowed_use_classes, max_ppm, requires_gras, banned).
JURISDICTION_PACKS: Dict[str, Dict[str, Dict]] = {
    "US-FDA": {
        # 21 CFR 172-182 style — deliberately sparse seed.
        "sucralose":     {"allowed_use_classes": {"food", "beverage", "supplement"}, "banned": False, "requires_gras": False},
        "stevia":        {"allowed_use_classes": {"food", "beverage", "supplement"}, "banned": False, "requires_gras": True},
        "aspartame":     {"allowed_use_classes": {"food", "beverage"},               "banned": False, "requires_gras": False},
        "cyclamate":     {"allowed_use_classes": set(),                              "banned": True,  "requires_gras": False},
        "brominated vegetable oil": {"allowed_use_classes": set(),                   "banned": True,  "requires_gras": False},
    },
    "EU": {
        "sucralose":     {"allowed_use_classes": {"food", "beverage"},               "banned": False, "requires_gras": False, "e_number": "E955"},
        "stevia":        {"allowed_use_classes": {"food", "beverage"},               "banned": False, "requires_gras": False, "e_number": "E960"},
        "aspartame":     {"allowed_use_classes": {"food", "beverage"},               "banned": False, "requires_gras": False, "e_number": "E951"},
        "titanium dioxide": {"allowed_use_classes": set(),                           "banned": True,  "requires_gras": False, "e_number": "E171"},
        "brominated vegetable oil": {"allowed_use_classes": set(),                   "banned": True,  "requires_gras": False},
    },
    "US-USP": {
        # Pharma grade — subset of FDA but with tighter ID/purity requirements.
        "sucralose":     {"allowed_use_classes": {"supplement"}, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "stevia":        {"allowed_use_classes": {"supplement"}, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
    },
}


@dataclass
class ComplianceInput:
    candidate_name: str
    use_class: str          # 'food' | 'beverage' | 'supplement'
    jurisdictions: List[str]
    incumbent_precedents: Dict[str, bool]
    # {"US-FDA": True, "EU": True, ...} — whether *trusted* incumbents use it
    # in that jurisdiction. Derived from Tim's enriched supplier data.


@dataclass
class _JurisdictionVerdict:
    jurisdiction: str
    implicit_ok: Optional[bool]   # None = unknown / ambiguous
    baseline_ok: bool
    reason: str
    confidence: float


class ComplianceReasoner(Tool):
    name = "compliance_reasoner"

    # ----------------------------------------------------------- single J

    def _evaluate_one(
        self, cand_key: str, inp: ComplianceInput, jurisdiction: str
    ) -> _JurisdictionVerdict:
        pack = JURISDICTION_PACKS.get(jurisdiction, {})
        rule = pack.get(cand_key)

        # Baseline check (category floor). Confidences are tuned for the
        # multiplicative compound chain — positive checks stay very close
        # to 1.0 so the final compound (gates × compliance) doesn't decay
        # below the 0.60 floor just from stacking.
        if rule is None:
            # No rule loaded → can't assert safe; pessimistic default.
            baseline_ok = False
            reason_base = "baseline_missing_rule"
            conf_base = 0.4
        elif rule.get("banned"):
            baseline_ok = False
            reason_base = "banned_in_jurisdiction"
            conf_base = 0.97
        elif inp.use_class not in rule["allowed_use_classes"]:
            baseline_ok = False
            reason_base = f"use_class_not_allowed:{inp.use_class}"
            conf_base = 0.95
        else:
            baseline_ok = True
            reason_base = "baseline_ok"
            conf_base = 0.97

        # Implicit standard check (do trusted incumbents use this in this J?).
        precedent = inp.incumbent_precedents.get(jurisdiction)
        if precedent is True:
            implicit_ok: Optional[bool] = True
            reason_impl = "incumbent_precedent"
            conf_impl = 0.95
        elif precedent is False:
            implicit_ok = False
            reason_impl = "no_incumbent_precedent"
            conf_impl = 0.85
        else:
            implicit_ok = None
            reason_impl = "implicit_unknown"
            conf_impl = 0.6

        reason = f"{reason_base};{reason_impl}"
        conf = compound_confidence([conf_base, conf_impl])
        return _JurisdictionVerdict(jurisdiction, implicit_ok, baseline_ok, reason, conf)

    # ---------------------------------------------------------- aggregate

    def _aggregate(
        self, verdicts: List[_JurisdictionVerdict]
    ) -> Tuple[str, str, float]:
        # Across-jurisdiction aggregation uses min (weakest jurisdiction
        # wins) rather than another round of multiplication — we already
        # compounded within each jurisdiction, and "all passed" shouldn't
        # decay further just because the caller asked about more markets.
        def weakest(vs: List[_JurisdictionVerdict]) -> float:
            return min(v.confidence for v in vs) if vs else 0.0

        # Refuse if ANY baseline fails.
        if any(not v.baseline_ok for v in verdicts):
            bad = [v.jurisdiction for v in verdicts if not v.baseline_ok]
            return ("refuse", f"baseline_fail:{','.join(bad)}", weakest(verdicts))

        # If every jurisdiction has implicit precedent -> pass-global.
        if all(v.implicit_ok is True for v in verdicts):
            return ("pass-global", "baseline_ok;implicit_ok_all", weakest(verdicts))

        # Mix of yes/no precedent -> fork-recommended.
        implicit_states = Counter(v.implicit_ok for v in verdicts)
        if implicit_states[True] and implicit_states[False]:
            return ("fork-recommended", "baseline_ok;implicit_mixed_across_jurisdictions", weakest(verdicts) * 0.9)

        # Everything else -> human-review (baseline OK but precedent unclear).
        return ("human-review", "baseline_ok;implicit_ambiguous", weakest(verdicts) * 0.8)

    # ---------------------------------------------------------------- run

    def _run(self, inp: ComplianceInput, evidence_ids: Optional[List[int]] = None) -> ToolResult:
        cand_key = (inp.candidate_name or "").strip().lower()
        if not cand_key:
            return ToolResult(result=None, confidence=0.0, refusal="empty_candidate")
        if not inp.jurisdictions:
            return ToolResult(result=None, confidence=0.0, refusal="no_jurisdictions")

        verdicts = [self._evaluate_one(cand_key, inp, j) for j in inp.jurisdictions]
        outcome, reason, conf = self._aggregate(verdicts)

        per_j = [
            {
                "jurisdiction": v.jurisdiction,
                "baseline_ok": v.baseline_ok,
                "implicit_ok": v.implicit_ok,
                "reason": v.reason,
                "confidence": v.confidence,
            }
            for v in verdicts
        ]

        return ToolResult(
            result={"outcome": outcome, "reason": reason, "per_jurisdiction": per_j},
            confidence=conf,
            evidence_ids=list(evidence_ids or []),
            refusal=None if outcome != "refuse" else reason,
        )
