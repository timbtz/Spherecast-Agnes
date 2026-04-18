"""Runnable demo harness.

    python -m Orchestration.sims.sim_runners --db ./db_enriched.sqlite

Walks the anchor case through plan_opportunity once, then walks each
stress mutation through plan_opportunity and prints a compact verdict
per scenario. Useful for the on-stage demo: five scenarios, five
different decisions, all with full audit trails.

This harness assumes the Phase 4 migration has already been applied
(run enrichment/db_migrate_v12.py --db <path> first).
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Dict

from ..planner import OpportunityVerdict, plan_opportunity
from .anchor_case import build_anchor_case
from .stress_injector import MUTATIONS


def _summarize(label: str, v: OpportunityVerdict) -> str:
    decisions = [q.decision for q in v.qualifications]
    return (
        f"[{label}] op={v.opportunity_id} "
        f"candidates={len(v.qualifications)} "
        f"decisions={decisions} "
        f"top_score={(v.ranked_suppliers[0]['score'] if v.ranked_suppliers else 0):.2f} "
        f"drafted_rfqs={len(v.drafted_rfq_ids)}"
    )


def run_all(db_path: str) -> Dict[str, OpportunityVerdict]:
    conn = sqlite3.connect(db_path)
    try:
        verdicts: Dict[str, OpportunityVerdict] = {}

        # Happy path.
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

        # Stress mutations.
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

        return verdicts
    finally:
        conn.close()


def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    verdicts = run_all(args.db)

    if args.verbose:
        for label, v in verdicts.items():
            print("\n" + "=" * 70)
            print(v.summary_md)


if __name__ == "__main__":
    _cli()
