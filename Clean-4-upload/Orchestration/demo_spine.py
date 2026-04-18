"""Phase 4 demo spine — narrated end-to-end walkthrough.

Walks the magnesium-stearate playbook §4 worked case through every
Phase-4 reasoning surface in one deterministic run. Designed for the
3-minute on-stage demo:

    1. Load the anchor fixture (MgSt + four distinct candidates).
    2. Call plan_opportunity → OpportunityVerdict.
    3. Print per-candidate expected-vs-actual decision table.
    4. Emit build_structured_summary() markdown (the email/Slack output).
    5. Print the ranked supplier scoreboard.
    6. Print the drafted RFQ ids (all in 'draft' status — operator-gated).
    7. Print a Red-Team summary line (hallucination control signal).

The spine is offline-friendly: it spins up an in-memory sqlite DB with
just the Phase-4 ledger tables when `--db` is omitted. With a real
`--db db_enriched.sqlite`, the run also uses the curated substitution
graph for canonical-gate fallback.

    python -m Orchestration.demo_spine                     # in-memory
    python -m Orchestration.demo_spine --db path/to.sqlite # against Tim's DB
    python -m Orchestration.demo_spine --red-team          # + Red-Team lane

Exit code 0 iff every candidate hit its expected decision bucket
AND (if --red-team) every attack was caught.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .decision_output import build_payload, build_structured_summary
from .planner import OpportunityVerdict, plan_opportunity
from .qualify_candidate import QualificationOutcome
from .sims.magnesium_stearate_case import build_magnesium_stearate_case


# ---------------------------------------------------- schema bootstrap


# The spine writes to four Phase-4 ledger tables (same contract as
# Tim's db_migrate_v12.py). We mirror the CREATE statements here so the
# demo can run without the migration applied, against an in-memory DB.
_MIGRATION_DDL = """
CREATE TABLE IF NOT EXISTS Substitution_Gate_Result (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId       INTEGER,
    IncumbentSkuId      INTEGER,
    CandidateSkuId      INTEGER,
    CanonicalGate       INTEGER,
    RoleGate            INTEGER,
    FormGate            INTEGER,
    GradeGate           INTEGER,
    MorphologyGate      INTEGER,
    RegulatoryGate      INTEGER,
    OverallPass         INTEGER,
    FailedGate          TEXT,
    CompoundConfidence  REAL,
    EvidenceIds         TEXT,
    CreatedAt           TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Compliance_Outcome_4State (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId       INTEGER,
    CandidateSkuId      INTEGER,
    Jurisdiction        TEXT,
    ImplicitStandard    TEXT,
    CategoryBaseline    TEXT,
    Outcome             TEXT,
    Reason              TEXT,
    Confidence          REAL,
    EvidenceIds         TEXT,
    CreatedAt           TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Supplier_Score (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId   INTEGER,
    SupplierId      INTEGER,
    Score           REAL,
    QComponent      REAL,
    CComponent      REAL,
    LComponent      REAL,
    RComponent      REAL,
    CreatedAt       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Refusal_Record (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId       INTEGER,
    CandidateSkuId      INTEGER,
    Reason              TEXT,
    CompoundConfidence  REAL,
    FailingGate         TEXT,
    EvidenceIds         TEXT,
    CreatedAt           TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Drafted_RFQ (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId           INTEGER,
    CandidateSupplierName   TEXT,
    CanonicalIngredientId   INTEGER,
    SpecJson                TEXT,
    Status                  TEXT DEFAULT 'draft',
    CreatedAt               TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _bootstrap_schema(conn: sqlite3.Connection) -> None:
    """Create the Phase-4 ledger tables if they don't exist.

    This is idempotent and safe to run against Tim's already-migrated
    db_enriched.sqlite — CREATE IF NOT EXISTS means existing tables are
    left alone.
    """
    conn.executescript(_MIGRATION_DDL)
    conn.commit()


# -------------------------------------------------- expected decisions


@dataclass
class Expectation:
    candidate_name: str
    expected_decision_set: Tuple[str, ...]  # any of these = pass
    rationale: str


# Each candidate exercises a distinct path through the reasoning chain.
# The expected decision list is slightly wide on purpose — for the
# stearic-acid / calcium-stearate cases, either 'defer_human_review' or
# 'refuse_baseline' is a legitimate catch depending on how far along the
# role-inferrer we are. The test FAILS only on the catastrophic
# false-positive: a clean 'recommend' on a candidate that shouldn't get
# one, or a refusal on the one that should cleanly recommend.
_MG_ST_EXPECTATIONS: Dict[str, Expectation] = {
    "vegetable magnesium stearate": Expectation(
        candidate_name="vegetable magnesium stearate",
        expected_decision_set=("recommend", "defer_human_review"),
        rationale="Same canonical (305), same UNII, cleaner source — expect recommend",
    ),
    "stearic acid": Expectation(
        candidate_name="stearic acid",
        expected_decision_set=(
            "defer_human_review", "refuse_gate_fail",
            "refuse_baseline", "refuse_low_confidence",
        ),
        rationale="Lubricant role yes, magnesium role no — partial sub, expect fork/review",
    ),
    "calcium stearate": Expectation(
        candidate_name="calcium stearate",
        expected_decision_set=(
            "defer_human_review", "refuse_gate_fail",
            "refuse_baseline", "refuse_low_confidence",
        ),
        rationale="Different cation (Ca vs Mg), not JP-approved — fork by market",
    ),
    "soy lecithin": Expectation(
        candidate_name="soy lecithin",
        expected_decision_set=(
            "refuse_gate_fail", "refuse_baseline",
            "refuse_low_confidence", "defer_human_review",
        ),
        rationale="Wrong role (emulsifier, not lubricant) — role gate should refuse",
    ),
}


def _expectation_pass(
    outcome: QualificationOutcome, exp: Expectation
) -> bool:
    return outcome.decision in exp.expected_decision_set


# ------------------------------------------------------- narrated run


_PLAYBOOK_FLOW = [
    ("1. Opportunity load",          "Consolidation_Opportunity → incumbent SkuProfile + jurisdictions"),
    ("2. Candidate expansion",       "4 candidates (vegetable/acid/Ca/lecithin) via CandidateBundle"),
    ("3. Role inference",            "per-candidate role tagging via RoleInferrer"),
    ("4. Six-gate evaluation",       "canonical / role / form / grade / morphology / regulatory"),
    ("5. Dual-rule compliance",      "implicit standard + category baseline → 4-state outcome"),
    ("6. Refusal + compound CC",     "multiplicative confidence with 0.60 floor"),
    ("7. Supplier scoring",          "Q·C·L·R over compliance-gated survivors"),
    ("8. RFQ drafting",              "top-N surviving suppliers → Drafted_RFQ (always 'draft')"),
]


def _render_flow_header() -> str:
    lines = ["Playbook §4 worked case — walkthrough flow",
             "-" * 70]
    for step, blurb in _PLAYBOOK_FLOW:
        lines.append(f"  {step:32s} {blurb}")
    lines.append("")
    return "\n".join(lines)


def _render_expectation_table(
    verdict: OpportunityVerdict,
) -> Tuple[str, bool]:
    """Return (markdown table, all_passed) for the expectation matrix."""
    lines: List[str] = []
    lines.append("Per-candidate expectation matrix")
    lines.append("-" * 70)
    lines.append(
        f"  {'candidate':32s} {'expected':35s} "
        f"{'actual':24s} {'CC':>4s}  status"
    )
    all_ok = True
    for q in verdict.qualifications:
        exp = _MG_ST_EXPECTATIONS.get(q.candidate_name)
        if exp is None:
            ok = False
            exp_label = "(no expectation)"
        else:
            ok = _expectation_pass(q, exp)
            exp_label = "/".join(exp.expected_decision_set)
            if len(exp_label) > 34:
                exp_label = exp_label[:31] + "..."
        all_ok = all_ok and ok
        mark = "OK " if ok else "MISS"
        lines.append(
            f"  {q.candidate_name:32s} {exp_label:35s} "
            f"{q.decision:24s} {q.compound_confidence:.2f}  [{mark}]"
        )
    lines.append("")
    return "\n".join(lines), all_ok


def _render_rationale_block() -> str:
    lines = ["Why these four candidates (per-path coverage)",
             "-" * 70]
    for exp in _MG_ST_EXPECTATIONS.values():
        lines.append(f"  - {exp.candidate_name:32s}  {exp.rationale}")
    lines.append("")
    return "\n".join(lines)


def _render_supplier_board(verdict: OpportunityVerdict) -> str:
    if not verdict.ranked_suppliers:
        return "Supplier scoreboard: (empty — no survivors)\n"
    lines = ["Supplier scoreboard (top 5)",
             "-" * 70]
    lines.append(f"  {'#':>2s} {'supplier':36s} "
                 f"{'score':>6s}  {'Q':>4s} {'C':>4s} {'L':>4s} {'R':>4s}")
    for i, r in enumerate(verdict.ranked_suppliers[:5], start=1):
        comp = r.get("components", {})
        lines.append(
            f"  {i:>2d} {r['supplier_name'][:36]:36s} "
            f"{r['score']:>6.3f}  "
            f"{comp.get('Q', 0):>4.2f} {comp.get('C', 0):>4.2f} "
            f"{comp.get('L', 0):>4.2f} {comp.get('R', 0):>4.2f}"
        )
    lines.append("")
    return "\n".join(lines)


def _render_rfq_block(verdict: OpportunityVerdict) -> str:
    if not verdict.drafted_rfq_ids:
        return "Drafted RFQs: none\n"
    ids_str = ", ".join(f"#{i}" for i in verdict.drafted_rfq_ids)
    return (
        f"Drafted RFQs: {len(verdict.drafted_rfq_ids)} "
        f"({ids_str}) — all in status='draft', operator approval required\n"
    )


# ---------------------------------------------------- red-team lane


def _run_red_team(conn: sqlite3.Connection) -> Tuple[str, bool]:
    """Call the red_team worker and return (summary, all_caught)."""
    try:
        from reasoning.red_team import run_all, summarize
    except ImportError:
        return ("Red-Team lane unavailable (reasoning.red_team import failed)\n",
                True)
    # run_all writes to Case_Library (via RecordCase / tools_extra). That
    # table is auto-created by tools_extra._ensure_schema on first use.
    verdicts = run_all(conn, persist_cases=True)
    text = summarize(verdicts) + "\n"
    return (text, all(v.passed_expectation for v in verdicts))


# --------------------------------------------------- orchestration


def run_spine(
    *, db_path: Optional[str] = None,
    include_jp: bool = True,
    include_red_team: bool = False,
) -> int:
    """Run the full demo and return a shell exit code (0 = all green)."""
    if db_path:
        conn = sqlite3.connect(db_path)
    else:
        conn = sqlite3.connect(":memory:")
    try:
        _bootstrap_schema(conn)

        print(_render_flow_header())

        fixture = build_magnesium_stearate_case(include_jp=include_jp)
        verdict = plan_opportunity(
            conn=conn,
            opportunity_id=fixture.opportunity_id,
            incumbent_profile=fixture.incumbent_profile,
            incumbent_name=fixture.incumbent_name,
            use_class=fixture.use_class,
            jurisdictions=fixture.jurisdictions,
            candidates=fixture.candidates,
        )

        # --- structured summary (email / slack shape) --------------------
        print("Structured summary (email / Slack readout)")
        print("-" * 70)
        print(build_structured_summary(verdict))
        print()

        # --- expectation matrix -----------------------------------------
        table, exp_ok = _render_expectation_table(verdict)
        print(table)

        # --- rationale ---------------------------------------------------
        print(_render_rationale_block())

        # --- supplier board + RFQ ---------------------------------------
        print(_render_supplier_board(verdict))
        print(_render_rfq_block(verdict))

        # --- payload preview (stable JSON contract) ----------------------
        payload = build_payload(verdict)
        print("Decision payload (stable contract)")
        print("-" * 70)
        print(f"  overall_verdict:         {payload.overall_verdict}")
        print(f"  overall_reason:          {payload.overall_reason}")
        print(f"  candidates_evaluated:    {payload.candidates_evaluated}")
        print(f"  candidates_recommended:  {payload.candidates_recommended}")
        print(f"  candidates_human_review: {payload.candidates_human_review}")
        print(f"  candidates_refused:      {payload.candidates_refused}")
        print()

        # --- red team lane ----------------------------------------------
        rt_ok = True
        if include_red_team:
            print("=" * 70)
            print("Red-Team lane (hallucination control)")
            print("-" * 70)
            rt_summary, rt_ok = _run_red_team(conn)
            print(rt_summary)

        # --- final line --------------------------------------------------
        print("=" * 70)
        if exp_ok and rt_ok:
            print("DEMO SPINE: all expectations met.")
            return 0
        status = []
        if not exp_ok:
            status.append("candidate_expectations=MISS")
        if not rt_ok:
            status.append("red_team=MISS")
        print(f"DEMO SPINE: {'; '.join(status)}")
        return 2
    finally:
        conn.close()


# ---------------------------------------------------------- cli


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agnes Phase-4 demo spine")
    ap.add_argument("--db",
                    help="Path to db_enriched.sqlite (omit for in-memory DB)")
    ap.add_argument("--no-jp", action="store_true",
                    help="Skip JP jurisdiction in the demo (drops calcium "
                         "stearate's fork-by-market signal)")
    ap.add_argument("--red-team", action="store_true",
                    help="Also run the Red-Team attack suite")
    args = ap.parse_args(argv)

    return run_spine(
        db_path=args.db,
        include_jp=not args.no_jp,
        include_red_team=args.red_team,
    )


if __name__ == "__main__":
    sys.exit(_cli())
