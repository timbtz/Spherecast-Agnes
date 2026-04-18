"""Mutate an AnchorFixture to force specific failure modes.

Each mutation returns a NEW fixture (the original is left untouched) so
the demo runner can present multiple scenarios without rebuilding from
scratch.

Failure modes covered:
    * gate_grade_downshift   — candidate is technical-grade, should fail grade gate
    * gate_form_mismatch     — candidate is liquid, should fail form gate
    * compliance_baseline    — candidate is on the EU banned list
    * compliance_ambiguous   — incumbent precedent split across jurisdictions
    * low_confidence         — degrades multiple confidences below 0.60
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Callable, Dict

from .anchor_case import AnchorFixture


def _clone(fix: AnchorFixture) -> AnchorFixture:
    return copy.deepcopy(fix)


def gate_grade_downshift(fix: AnchorFixture) -> AnchorFixture:
    f = _clone(fix)
    f.candidates[0].candidate_profile.grade = "technical"
    return f


def gate_form_mismatch(fix: AnchorFixture) -> AnchorFixture:
    f = _clone(fix)
    f.candidates[0].candidate_profile.form = "liquid"
    return f


def compliance_baseline(fix: AnchorFixture) -> AnchorFixture:
    """Swap the candidate to a banned ingredient (cyclamate/BVO style).

    Keeps the supplier's claimed regulatory approvals in place so the
    regulatory gate passes — that lets the compliance reasoner be the
    component that catches the ban (which is the point of this test).
    """
    f = _clone(fix)
    # Rename to a banned key in JURISDICTION_PACKS while leaving the
    # supplier's self-declared jurisdictions intact.
    f.candidates[0].candidate_name = "cyclamate"
    return f


def compliance_ambiguous(fix: AnchorFixture) -> AnchorFixture:
    f = _clone(fix)
    f.candidates[0].incumbent_precedents = {"US-FDA": True, "EU": False}
    return f


def low_confidence(fix: AnchorFixture) -> AnchorFixture:
    """Wipe morphology + role + grade so the chain compounds to <0.60."""
    f = _clone(fix)
    cp = f.candidates[0].candidate_profile
    cp.role = None
    cp.psd_bucket = None
    cp.surface_area_m2g = None
    cp.grade = "unknown"
    f.candidates[0].incumbent_precedents = {"US-FDA": None, "EU": None}
    return f


MUTATIONS: Dict[str, Callable[[AnchorFixture], AnchorFixture]] = {
    "gate_grade_downshift": gate_grade_downshift,
    "gate_form_mismatch": gate_form_mismatch,
    "compliance_baseline": compliance_baseline,
    "compliance_ambiguous": compliance_ambiguous,
    "low_confidence": low_confidence,
}
