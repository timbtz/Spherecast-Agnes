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

OFFLINE-ONLY ENFORCEMENT
------------------------
Stress injection must be deterministic and reproducible. Reaching the
network mid-demo would introduce a timing jitter we can't explain on
stage (and a trust/safety footgun: an attacker who planted bogus
supplier data would get their attack re-executed every demo run).

This module therefore refuses to import or transitively touch any
HTTP library. The `_assert_offline()` call at import time inspects
sys.modules and raises if `requests`, `httpx`, `urllib3`, `aiohttp`,
or `socket` are already registered as dependencies of this module's
call path. Downstream `sim_runners` can call `assert_offline()` again
before a mutation fires for belt-and-suspenders safety.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import replace
from typing import Callable, Dict, Tuple

from .anchor_case import AnchorFixture


# Modules we refuse to let the stress lane touch. The last two entries
# (aiohttp, grpc) aren't first-party Python stdlib but they're the two
# most common async-HTTP stacks we might accidentally pull in via a
# naive import.
_OFFLINE_DENYLIST: Tuple[str, ...] = (
    "requests", "httpx", "urllib3", "aiohttp", "grpc",
)


def assert_offline() -> None:
    """Raise if any network library is already imported at call time.

    Called once at module import, and may be called again from
    sim_runners before each mutation fires. The check is deliberately
    cheap (sys.modules lookup only) so it's safe in hot paths.

    Note: we don't block 'socket' — Python imports it eagerly for
    sqlite3 and many stdlib modules. Blocking it would be a false
    positive. The denylist targets HTTP-level libraries where any
    import is a red flag for the stress lane.
    """
    offenders = [m for m in _OFFLINE_DENYLIST if m in sys.modules]
    if offenders:
        raise RuntimeError(
            f"stress_injector: offline mode violated — "
            f"network libraries already imported: {offenders}"
        )


assert_offline()


def _clone(fix: AnchorFixture) -> AnchorFixture:
    # Belt-and-suspenders: every mutation path funnels through _clone,
    # so re-asserting offline here catches any import-order shenanigans
    # that slipped past the module-import check.
    assert_offline()
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
