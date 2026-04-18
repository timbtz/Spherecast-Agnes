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
enrichment spine can wire in later (FDA FCS, EU EFSA, USP). For the
hackathon demo, the packs below cover the dietary-supplement ingredients
that show up in Tim's enriched DB (vitamins, minerals, excipients), so
the top-10 consolidation opportunities actually hit a rule instead of
tripping the pessimistic default.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .base import Tool, ToolResult, compound_confidence


# Common use-class sets reused across ingredients below.
_FBS = {"food", "beverage", "supplement"}   # food + beverage + supplement
_FS = {"food", "supplement"}                # food + supplement only (not beverage)
_SUP = {"supplement"}                       # supplement only


# Pack rule schema per ingredient key:
#     allowed_use_classes: set of use_class strings the rule permits
#     banned:              hard ban (overrides allowed_use_classes)
#     requires_gras:       must carry a GRAS notice (US)
#     e_number:            EU additive number, if any
#     requires_usp_monograph: must conform to USP monograph (pharma grade)
#
# Keys are matched against `(candidate_name or "").strip().lower()` in
# _run, so entries must be lowercase and match the name the canonical
# inferrer produces. The demo adapter resolves each SKU to its
# Ingredient_Canonical.Name before calling us — that name flows straight
# through as the candidate_name, so these keys mirror the rows in
# Ingredient_Canonical (plus a couple of aliases).
JURISDICTION_PACKS: Dict[str, Dict[str, Dict]] = {
    "US-FDA": {
        # --- Seed sweeteners / bans (kept from original pack) ------------
        "sucralose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "stevia":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": True},
        "aspartame":                {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False},
        "cyclamate":                {"allowed_use_classes": set(), "banned": True,  "requires_gras": False},
        "brominated vegetable oil": {"allowed_use_classes": set(), "banned": True,  "requires_gras": False},

        # --- Vitamin C family (opp #268 + #269) --------------------------
        "vitamin c":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "ascorbic acid":            {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "l-ascorbic acid":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "sodium ascorbate":         {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "calcium ascorbate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "magnesium ascorbate":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Cellulose & excipients (opp #260, #261, #305) ----------------
        "cellulose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "microcrystalline cellulose": {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "croscarmellose sodium":    {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False},
        "silicon dioxide":          {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False},
        "magnesium stearate":       {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False},
        "vegetable magnesium stearate": {"allowed_use_classes": _FS, "banned": False, "requires_gras": False},

        # --- Calcium salts (opp #259) ------------------------------------
        "calcium citrate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "calcium carbonate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "calcium phosphate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Gelatin (opp #302) ------------------------------------------
        "gelatin":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Vitamin D family (opp #298) ---------------------------------
        "vitamin d":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "cholecalciferol":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "ergocalciferol":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Protein (opp #287) — catch-all; real work will split by source
        "protein":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "whey protein":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "pea protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "soy protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Citric acid (opp #279) --------------------------------------
        "citric acid":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Magnesium salts (substitution-rule neighbors) ---------------
        "magnesium oxide":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "magnesium citrate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "magnesium glycinate":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "magnesium malate":         {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Zinc salts --------------------------------------------------
        "zinc oxide":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "zinc citrate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "zinc gluconate":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "zinc picolinate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Iron salts --------------------------------------------------
        "ferrous sulfate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "ferrous gluconate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Folate forms ------------------------------------------------
        "folic acid":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "methylfolate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "5-mthf":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- B12 forms ---------------------------------------------------
        "cyanocobalamin":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "methylcobalamin":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "adenosylcobalamin":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Tocopherols (vitamin E) ------------------------------------
        "d-alpha tocopherol":       {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "dl-alpha tocopherol":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "mixed tocopherols":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
    },

    "EU": {
        # --- Seed sweeteners / bans (kept from original pack) ------------
        "sucralose":                {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False, "e_number": "E955"},
        "stevia":                   {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False, "e_number": "E960"},
        "aspartame":                {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False, "e_number": "E951"},
        "titanium dioxide":         {"allowed_use_classes": set(), "banned": True, "requires_gras": False, "e_number": "E171"},
        "brominated vegetable oil": {"allowed_use_classes": set(), "banned": True, "requires_gras": False},

        # --- Vitamin C family (E300 / E301 / E302 / E303) ---------------
        "vitamin c":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E300"},
        "ascorbic acid":            {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E300"},
        "l-ascorbic acid":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E300"},
        "sodium ascorbate":         {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E301"},
        "calcium ascorbate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E302"},
        # Magnesium ascorbate is permitted as a vitamin-C source in supplements
        # but is not on the EU food-additive list, so no E-number.
        "magnesium ascorbate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},

        # --- Cellulose / excipients (E460 / E468 / E551 / E470b) --------
        "cellulose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E460"},
        "microcrystalline cellulose": {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E460i"},
        "croscarmellose sodium":    {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "e_number": "E468"},
        "silicon dioxide":          {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "e_number": "E551"},
        "magnesium stearate":       {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "e_number": "E470b"},
        "vegetable magnesium stearate": {"allowed_use_classes": _FS, "banned": False, "requires_gras": False, "e_number": "E470b"},

        # --- Calcium salts (E333 / E170 / E341) -------------------------
        "calcium citrate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E333"},
        "calcium carbonate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E170"},
        "calcium phosphate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E341"},

        # --- Gelatin (no E-number; regulated as food ingredient, not additive)
        "gelatin":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Vitamin D family (permitted as vitamin-D source per Annex II)
        "vitamin d":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "cholecalciferol":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "ergocalciferol":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Protein families --------------------------------------------
        "protein":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "whey protein":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "pea protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "soy protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Citric acid (E330) -----------------------------------------
        "citric acid":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E330"},

        # --- Magnesium salts --------------------------------------------
        "magnesium oxide":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E530"},
        "magnesium citrate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "magnesium glycinate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},
        "magnesium malate":         {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},

        # --- Zinc salts -------------------------------------------------
        # Zinc oxide lost its EU food-additive status in 2016 but remains a
        # permitted mineral source in food supplements per Directive 2002/46/EC.
        "zinc oxide":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},
        "zinc citrate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "zinc gluconate":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "zinc picolinate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},

        # --- Iron salts -------------------------------------------------
        "ferrous sulfate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "ferrous gluconate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- Folate forms -----------------------------------------------
        "folic acid":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "methylfolate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "5-mthf":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},

        # --- B12 forms --------------------------------------------------
        "cyanocobalamin":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "methylcobalamin":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False},
        "adenosylcobalamin":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False},

        # --- Tocopherols (E306 / E307 / E308) --------------------------
        "d-alpha tocopherol":       {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E307"},
        "dl-alpha tocopherol":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E307"},
        "mixed tocopherols":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "e_number": "E306"},
    },

    "US-USP": {
        # Pharma grade — USP-NF monograph requirement tightens what's
        # "compliant". Only ingredients with a real USP monograph go here.
        "sucralose":                {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "stevia":                   {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Vitamin C: USP monograph exists for ascorbic acid and sodium ascorbate
        "ascorbic acid":            {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "l-ascorbic acid":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "sodium ascorbate":         {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium ascorbate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Excipients with USP-NF monographs
        "microcrystalline cellulose": {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "croscarmellose sodium":    {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "silicon dioxide":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "magnesium stearate":       {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Calcium salts (USP monographs: Calcium Carbonate, Calcium Citrate, Calcium Phosphate)
        "calcium citrate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium carbonate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium phosphate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Gelatin (USP monograph)
        "gelatin":                  {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Vitamin D (USP monographs: Cholecalciferol, Ergocalciferol)
        "cholecalciferol":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ergocalciferol":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Citric acid (USP monograph: Anhydrous + Monohydrate)
        "citric acid":              {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Magnesium salts (USP monographs exist for oxide / citrate; glycinate / malate are supplement-only)
        "magnesium oxide":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "magnesium citrate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Zinc salts (USP monographs: oxide, gluconate)
        "zinc oxide":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "zinc gluconate":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Iron salts (USP monograph: Ferrous Sulfate, Ferrous Gluconate)
        "ferrous sulfate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ferrous gluconate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Folate / B12 (USP monographs exist for folic acid, cyanocobalamin)
        "folic acid":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "cyanocobalamin":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},

        # Tocopherols (USP monographs: Vitamin E)
        "d-alpha tocopherol":       {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "dl-alpha tocopherol":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
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
            # 0.75, not 0.6 — "we don't know" shouldn't punch as hard as
            # "we have negative evidence" (0.85). When incumbent_precedents
            # is sparse (common during enrichment rollout) this prevents the
            # multiplicative chain from collapsing on every candidate just
            # because precedent data isn't populated yet.
            conf_impl = 0.75

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
        # 0.9 multiplier (not 0.8) — human-review is NOT a refusal; baseline
        # has already passed and we're flagging implicit-ambiguity for a
        # reviewer. A 20% confidence haircut was enough to push the whole
        # chain under the refusal floor on every sparse-precedent candidate.
        return ("human-review", "baseline_ok;implicit_ambiguous", weakest(verdicts) * 0.9)

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
