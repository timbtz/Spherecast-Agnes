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
small lookup dicts — real regulatory data will come from tools the
enrichment spine can wire in later (FDA FCS, EU EFSA, USP). For the
hackathon demo, the packs below cover the dietary-supplement ingredients
that show up in the enriched DB (vitamins, minerals, excipients), so
the top-10 consolidation opportunities actually hit a rule instead of
tripping the pessimistic default.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from reasoning.base import Tool, ToolResult, compound_confidence


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
# inferrer produces.
JURISDICTION_PACKS: Dict[str, Dict[str, Dict]] = {
    "US-FDA": {
        # --- Seed sweeteners / bans ------------
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

        # --- Protein (opp #287) ------------------------------------------
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
        # --- Seed sweeteners / bans ------------
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

    "CA": {
        # Canada — Health Canada NNHPD (Natural and Non-prescription Health
        # Products Directorate). Rule keys mirror the NHPID (Natural Health
        # Products Ingredients Database).
        "sucralose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "stevia":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "aspartame":                {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False, "npn_required": False},
        "cyclamate":                {"allowed_use_classes": set(), "banned": True,  "requires_gras": False, "npn_required": False},
        "brominated vegetable oil": {"allowed_use_classes": set(), "banned": True,  "requires_gras": False, "npn_required": False},

        # --- Vitamin C family --------------------------------------------
        "vitamin c":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "ascorbic acid":            {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "l-ascorbic acid":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "sodium ascorbate":         {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "calcium ascorbate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "magnesium ascorbate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Cellulose / excipients (approved per Food and Drug Regulations B.16)
        "cellulose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "microcrystalline cellulose": {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "croscarmellose sodium":    {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "npn_required": False},
        "silicon dioxide":          {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "npn_required": False},
        "magnesium stearate":       {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "npn_required": False},
        "vegetable magnesium stearate": {"allowed_use_classes": _FS, "banned": False, "requires_gras": False, "npn_required": False},

        # --- Calcium salts ----------------------------------------------
        "calcium citrate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "calcium carbonate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "calcium phosphate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Gelatin -----------------------------------------------------
        "gelatin":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},

        # --- Vitamin D family (approved per NHPID)
        "vitamin d":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "cholecalciferol":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "ergocalciferol":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Protein families -------------------------------------------
        "protein":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "whey protein":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "pea protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},
        "soy protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},

        # --- Citric acid ------------------------------------------------
        "citric acid":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": False},

        # --- Magnesium salts --------------------------------------------
        "magnesium oxide":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "magnesium citrate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "magnesium glycinate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},
        "magnesium malate":         {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Zinc salts -------------------------------------------------
        "zinc oxide":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},
        "zinc citrate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "zinc gluconate":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "zinc picolinate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Iron salts -------------------------------------------------
        "ferrous sulfate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "ferrous gluconate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Folate forms -----------------------------------------------
        "folic acid":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "methylfolate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "5-mthf":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},

        # --- B12 forms --------------------------------------------------
        "cyanocobalamin":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "methylcobalamin":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "adenosylcobalamin":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "npn_required": True},

        # --- Tocopherols (vitamin E) ------------------------------------
        "d-alpha tocopherol":       {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "dl-alpha tocopherol":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
        "mixed tocopherols":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "npn_required": True},
    },

    "JP": {
        # Japan — MHLW (Ministry of Health, Labour and Welfare) + CAA
        # (Consumer Affairs Agency). Japan uses a *positive-list* system for
        # food additives; anything not on the list is effectively unapproved.
        "sucralose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "stevia":                   {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "aspartame":                {"allowed_use_classes": {"food", "beverage"}, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "cyclamate":                {"allowed_use_classes": set(), "banned": True,  "requires_gras": False, "foshu_eligible": False},
        "brominated vegetable oil": {"allowed_use_classes": set(), "banned": True,  "requires_gras": False, "foshu_eligible": False},

        # --- Vitamin C family (permitted as food additive + supplement)
        "vitamin c":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "ascorbic acid":            {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "l-ascorbic acid":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "sodium ascorbate":         {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "calcium ascorbate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "magnesium ascorbate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Cellulose / excipients (all on JP positive list) ------------
        "cellulose":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "microcrystalline cellulose": {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "croscarmellose sodium":    {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "foshu_eligible": False},
        "silicon dioxide":          {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "foshu_eligible": False},
        "magnesium stearate":       {"allowed_use_classes": _FS,  "banned": False, "requires_gras": False, "foshu_eligible": False},
        "vegetable magnesium stearate": {"allowed_use_classes": _FS, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Calcium salts (positive list: carbonate/citrate/phosphate) --
        "calcium citrate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "calcium carbonate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "calcium phosphate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},

        # --- Gelatin (natural food, not additive) ------------------------
        "gelatin":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Vitamin D (both forms on positive list) ---------------------
        "vitamin d":                {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "cholecalciferol":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "ergocalciferol":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Protein families --------------------------------------------
        "protein":                  {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "whey protein":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "pea protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "soy protein":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},

        # --- Citric acid -------------------------------------------------
        "citric acid":              {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Magnesium salts --------------------------------------------
        "magnesium oxide":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "magnesium citrate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "magnesium glycinate":      {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "magnesium malate":         {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Zinc salts -------------------------------------------------
        "zinc oxide":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "zinc citrate":             {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "zinc gluconate":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "zinc picolinate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Iron salts -------------------------------------------------
        "ferrous sulfate":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "ferrous gluconate":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},

        # --- Folate forms -----------------------------------------------
        "folic acid":               {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": True},
        "methylfolate":             {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "5-mthf":                   {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- B12 forms --------------------------------------------------
        "cyanocobalamin":           {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "methylcobalamin":          {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "adenosylcobalamin":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "foshu_eligible": False},

        # --- Tocopherols (vitamin E) ------------------------------------
        "d-alpha tocopherol":       {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "dl-alpha tocopherol":      {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
        "mixed tocopherols":        {"allowed_use_classes": _FBS, "banned": False, "requires_gras": False, "foshu_eligible": False},
    },

    "US-USP": {
        # Pharma grade — USP-NF monograph requirement.
        "sucralose":                {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "stevia":                   {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ascorbic acid":            {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "l-ascorbic acid":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "sodium ascorbate":         {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium ascorbate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "microcrystalline cellulose": {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "croscarmellose sodium":    {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "silicon dioxide":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "magnesium stearate":       {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium citrate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium carbonate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "calcium phosphate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "gelatin":                  {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "cholecalciferol":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ergocalciferol":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "citric acid":              {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "magnesium oxide":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "magnesium citrate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "zinc oxide":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "zinc gluconate":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ferrous sulfate":          {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "ferrous gluconate":        {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "folic acid":               {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
        "cyanocobalamin":           {"allowed_use_classes": _SUP, "banned": False, "requires_gras": False, "requires_usp_monograph": True},
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
    # in that jurisdiction. Derived from enriched supplier data.


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

        if rule is None:
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
            conf_impl = 0.75

        reason = f"{reason_base};{reason_impl}"
        conf = compound_confidence([conf_base, conf_impl])
        return _JurisdictionVerdict(jurisdiction, implicit_ok, baseline_ok, reason, conf)

    # ---------------------------------------------------------- aggregate

    def _aggregate(
        self, verdicts: List[_JurisdictionVerdict]
    ) -> Tuple[str, str, float]:
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
