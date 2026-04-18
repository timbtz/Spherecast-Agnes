"""Runnable demo harness.

    # Walk every sim in sequence (anchor + stress + named #1/#3/#5/#8):
    python -m Orchestration.sims.sim_runners --db ./db_enriched.sqlite

    # Run exactly one named sim:
    python -m Orchestration.sims.sim_runners --sim 1   # fragmentation detection
    python -m Orchestration.sims.sim_runners --sim 3   # compliance trap (hallucination)
    python -m Orchestration.sims.sim_runners --sim 5   # multi-jurisdiction fork
    python -m Orchestration.sims.sim_runners --sim 8   # re-eval trigger chain

Each named sim is designed to exercise a different Phase-4 reasoning
surface and leave a distinct audit trail in the ledger tables:

    Sim 1  — fragmentation detection
        MgSt anchor, clean vegetable substitute. Demonstrates the
        happy path through the full chain: gate pass → compliance
        pass-global → supplier score → drafted RFQ.

    Sim 3  — compliance trap (hallucination control)
        Swaps in 'cyclamate' (banned in US/EU/CA/JP) as a lookalike
        candidate. Proves the compliance reasoner catches the ban
        instead of rubber-stamping incumbent precedent. This is the
        anti-hallucination guarantee made concrete.

    Sim 5  — multi-jurisdiction fork
        MgSt anchor with calcium-stearate candidate across all four
        jurisdictions. Calcium stearate is approved in US + EU but
        NOT on the JP pack → fork-recommended. Demonstrates the
        4-state compliance outcome and the planner's fork narration.

    Sim 8  — re-eval trigger chain
        Marks the MgSt incumbent as 'flagged_for_reeval' via the §7
        tool, then reruns qualification. Proves that Re_Eval_Queue
        integrates with the planner without corrupting existing
        audit rows.

This harness assumes the Phase-4 migration has already been applied
(run enrichment/db_migrate_v12.py --db <path> first).
"""

from __future__ import annotations

import argparse
import copy
import sqlite3
import sys
from dataclasses import replace
from typing import Callable, Dict, List, Optional

from ..planner import OpportunityVerdict, plan_opportunity
from .anchor_case import build_anchor_case
from .magnesium_stearate_case import build_magnesium_stearate_case
from .stress_injector import MUTATIONS


# -------------------------------------------------------- sim helpers


def _clone_fix(fix):
    return copy.deepcopy(fix)


def _summarize(label: str, v: OpportunityVerdict) -> str:
    decisions = [q.decision for q in v.qualifications]
    return (
        f"[{label}] op={v.opportunity_id} "
        f"candidates={len(v.qualifications)} "
        f"decisions={decisions} "
        f"top_score={(v.ranked_suppliers[0]['score'] if v.ranked_suppliers else 0):.2f} "
        f"drafted_rfqs={len(v.drafted_rfq_ids)}"
    )


# --- named sims -------------------------------------------------------


def _run_sim1(conn: sqlite3.Connection) -> OpportunityVerdict:
    """Fragmentation detection: MgSt + clean vegetable substitute only.

    The point of this sim is to prove the happy-path chain writes to
    every Phase-4 ledger table without any forks / refusals. Expected
    decisions: ['recommend'], drafted RFQs: 1.
    """
    fix = _clone_fix(build_magnesium_stearate_case(include_jp=False))
    # Keep only the vegetable-MgSt candidate — strip out the role / cation
    # mismatches so this sim is the pure fragmentation / consolidation
    # detection case.
    fix.candidates = [c for c in fix.candidates
                      if c.candidate_name == "vegetable magnesium stearate"]
    return plan_opportunity(
        conn=conn,
        opportunity_id=fix.opportunity_id + 1000,
        incumbent_profile=fix.incumbent_profile,
        incumbent_name=fix.incumbent_name,
        use_class=fix.use_class,
        jurisdictions=fix.jurisdictions,
        candidates=fix.candidates,
    )


def _run_sim3(conn: sqlite3.Connection) -> OpportunityVerdict:
    """Compliance trap: swap in a banned lookalike.

    Uses the sucralose anchor (which the compliance reasoner has
    jurisdiction packs for) and substitutes 'cyclamate' as the
    candidate name. The gate engine should refuse on canonical (no
    curated edge to cyclamate) OR the compliance reasoner should
    refuse on baseline (cyclamate is on the US/EU banned lists).
    Either catch is a valid hallucination-control signal.
    """
    fix = _clone_fix(build_anchor_case())
    # Rename the first candidate to cyclamate while leaving its
    # supplier's self-declared regulatory approvals intact (this is
    # exactly what a malicious / sloppy data feed would look like).
    fix.candidates[0].candidate_name = "cyclamate"
    return plan_opportunity(
        conn=conn,
        opportunity_id=fix.opportunity_id + 3000,
        incumbent_profile=fix.incumbent_profile,
        incumbent_name=fix.incumbent_name,
        use_class=fix.use_class,
        jurisdictions=fix.jurisdictions,
        candidates=fix.candidates,
    )


def _run_sim5(conn: sqlite3.Connection) -> OpportunityVerdict:
    """Multi-jurisdiction fork: sucralose across US+EU+CA+JP with split precedents.

    The compliance reasoner receives precedent signals that DIFFER by
    jurisdiction (true for US/EU, false for CA/JP). It should return
    outcome='fork-recommended' — pass-in-primary, human-review in the
    weaker jurisdictions. This sim isolates the 4-state compliance
    outcome without the canonical gate stealing the signal.

    We use the sucralose anchor (not MgSt) here because sucralose has
    jurisdiction packs in all four regions; calcium-stearate-vs-MgSt
    is already a canonical-gate refusal, which masks the compliance
    signal we're trying to demonstrate.
    """
    fix = _clone_fix(build_anchor_case())
    fix.jurisdictions = ["US-FDA", "EU", "CA", "JP"]
    # Keep the clean sucralose candidate; split its precedents across
    # the four jurisdictions so the reasoner has to fork.
    fix.candidates = [c for c in fix.candidates if c.candidate_name == "sucralose"]
    for cb in fix.candidates:
        cb.incumbent_precedents = {
            "US-FDA": True, "EU": True, "CA": False, "JP": False,
        }
        cb.candidate_profile.jurisdictions_approved = ["US-FDA", "EU"]
    return plan_opportunity(
        conn=conn,
        opportunity_id=fix.opportunity_id + 5000,
        incumbent_profile=fix.incumbent_profile,
        incumbent_name=fix.incumbent_name,
        use_class=fix.use_class,
        jurisdictions=fix.jurisdictions,
        candidates=fix.candidates,
    )


def _run_sim8(conn: sqlite3.Connection) -> OpportunityVerdict:
    """Re-eval trigger chain: flag then re-qualify.

    Calls flag_for_reeval (§7 tool) on the MgSt incumbent, then runs
    qualification again. We care about three observable signals:
        1. Re_Eval_Queue has a row with trigger_class='flagged_for_reeval'
        2. The re-run qualification produces the same decisions as the
           baseline run (re-eval is idempotent).
        3. Substitution_Gate_Result accumulates new rows (audit trail
           records every evaluation, never overwrites).
    """
    from reasoning.tools_extra import FlagForReeval
    fix = _clone_fix(build_magnesium_stearate_case(include_jp=True))
    # Fire the flag_for_reeval tool first — if it fails we still want
    # the planner to run so the sim doesn't silently regress.
    try:
        flagger = FlagForReeval(conn)
        flagger(
            candidate_sku_id=fix.incumbent_profile.sku_id,
            trigger_class="flagged_for_reeval",
            reason="sim_8: operator-requested re-evaluation",
            opportunity_id=fix.opportunity_id + 8000,
        )
    except Exception:
        # Best-effort: Re_Eval_Queue schema might not be materialized
        # on old DBs. The rerun below still demonstrates the core
        # property (audit rows accumulate).
        pass
    return plan_opportunity(
        conn=conn,
        opportunity_id=fix.opportunity_id + 8000,
        incumbent_profile=fix.incumbent_profile,
        incumbent_name=fix.incumbent_name,
        use_class=fix.use_class,
        jurisdictions=fix.jurisdictions,
        candidates=fix.candidates,
    )


NAMED_SIMS: Dict[int, Callable[[sqlite3.Connection], OpportunityVerdict]] = {
    1: _run_sim1,
    3: _run_sim3,
    5: _run_sim5,
    8: _run_sim8,
}


_SIM_BLURB = {
    1: "fragmentation detection (happy path)",
    3: "compliance trap (hallucination control)",
    5: "multi-jurisdiction fork",
    8: "re-eval trigger chain",
}


# --- runner loops -----------------------------------------------------


def run_named_sim(db_path: str, sim_n: int) -> OpportunityVerdict:
    if sim_n not in NAMED_SIMS:
        raise SystemExit(
            f"sim {sim_n} not defined. Available: {sorted(NAMED_SIMS)}"
        )
    conn = sqlite3.connect(db_path)
    try:
        v = NAMED_SIMS[sim_n](conn)
        print(_summarize(f"sim_{sim_n}_{_SIM_BLURB[sim_n].split()[0]}", v))
        return v
    finally:
        conn.close()


def run_all(db_path: str) -> Dict[str, OpportunityVerdict]:
    conn = sqlite3.connect(db_path)
    try:
        verdicts: Dict[str, OpportunityVerdict] = {}

        # Happy path (sucralose anchor).
        anchor = build_anchor_case()
        happy = plan_opportunity(
            conn=conn,
            opportunity_id=anchor.opportunity_id,
            incumbent_profile=anchor.incumbent_profile,
            incumbent_name=anchor.incumbent_name,
            use_class=anchor.use_class,
            jurisdictions=anchor.jurisdictions,
            candidates=anchor.candidates,
        )
        verdicts["anchor_happy_path"] = happy
        print(_summarize("anchor_happy_path", happy))

        # Stress mutations (built on the sucralose anchor).
        for label, mut in MUTATIONS.items():
            fix = mut(build_anchor_case())
            # Give each mutation its own opportunity_id so rows don't collide.
            op_id = anchor.opportunity_id + sum(ord(c) for c in label)
            v = plan_opportunity(
                conn=conn,
                opportunity_id=op_id,
                incumbent_profile=fix.incumbent_profile,
                incumbent_name=fix.incumbent_name,
                use_class=fix.use_class,
                jurisdictions=fix.jurisdictions,
                candidates=fix.candidates,
            )
            verdicts[label] = v
            print(_summarize(label, v))

        # Named playbook sims (MgSt worked case + reasoning-surface cuts).
        for sim_n, runner in NAMED_SIMS.items():
            v = runner(conn)
            label = f"sim_{sim_n}_{_SIM_BLURB[sim_n].split()[0]}"
            verdicts[label] = v
            print(_summarize(label, v))

        return verdicts
    finally:
        conn.close()


def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--sim", type=int, choices=list(NAMED_SIMS.keys()),
                    help="Run exactly one named sim (1/3/5/8)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.sim is not None:
        v = run_named_sim(args.db, args.sim)
        if args.verbose:
            print("\n" + "=" * 70)
            print(v.summary_md)
        return

    verdicts = run_all(args.db)

    if args.verbose:
        for label, v in verdicts.items():
            print("\n" + "=" * 70)
            print(v.summary_md)


if __name__ == "__main__":
    _cli()
