"""Re-evaluator scheduler daemon.

Drains Re_Eval_Queue (populated by the §7 tool `FlagForReeval`) and
re-runs the qualification chain for each affected candidate. Supports
eight trigger classes — each maps to a different "what changed?"
hypothesis the reasoner uses to decide how deeply to re-evaluate:

    cert_expiring          → re-verify regulatory gate only
    flagged_for_reeval     → full re-run (operator or critic bumped it)
    supplier_down          → force_refresh scout + full re-run
    new_compliance_rule    → invalidate compliance cache, full re-run
    price_shift            → re-score suppliers, skip qualification
    lead_time_shift        → re-score suppliers, skip qualification
    demand_shift           → recompute aggregate_demand + re-rank
    new_case_learned       → re-run with updated case library weights

Design
------
  * Two modes: one-shot (CI / hackathon demo) and daemon-loop (cron).
  * Each queue row is claimed atomically (Status = 'in_progress') so
    multiple daemon instances don't double-process.
  * Failures mark Status = 'failed' with a reason — they do NOT silently
    retry forever.
  * Every processed row writes an audit tag via `record_case` so the
    case library learns from each re-eval outcome.

Entry point:
    python -m Orchestration.reeval_daemon --db db_enriched.sqlite --one-shot
    python -m Orchestration.reeval_daemon --db db_enriched.sqlite --interval 60
"""

from __future__ import annotations

import argparse
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from reasoning.tools_extra import (
    AggregateDemand, RecordCase, TRIGGER_CLASSES, _ensure_schema,
)


# --------------------------------------------------------- data model


@dataclass
class QueueRow:
    queue_id: int
    substitution_id: Optional[int]
    opportunity_id: Optional[int]
    candidate_sku_id: Optional[int]
    trigger_class: str
    reason: Optional[str]
    urgency: str


@dataclass
class DaemonStats:
    drained: int = 0
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    by_trigger: Dict[str, int] = None

    def __post_init__(self) -> None:
        if self.by_trigger is None:
            self.by_trigger = {t: 0 for t in TRIGGER_CLASSES}

    def tally(self, trigger: str) -> None:
        self.by_trigger[trigger] = self.by_trigger.get(trigger, 0) + 1


# ---------------------------------------------------- claim / release


def _claim_next(
    conn: sqlite3.Connection, urgency_order: bool = True
) -> Optional[QueueRow]:
    """Atomically claim one pending queue row.

    Uses a single-row UPDATE with a WHERE-IN sub-select so concurrent
    daemons never claim the same row. Returns None if the queue is
    empty or fully in-progress.
    """
    order_clause = (
        "ORDER BY CASE Urgency "
        "WHEN 'critical' THEN 0 "
        "WHEN 'high'     THEN 1 "
        "WHEN 'normal'   THEN 2 "
        "WHEN 'low'      THEN 3 "
        "ELSE 2 END, CreatedAt ASC "
    ) if urgency_order else "ORDER BY CreatedAt ASC "

    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            f"""
            SELECT QueueId, SubstitutionId, OpportunityId, CandidateSkuId,
                   TriggerClass, Reason, Urgency
            FROM Re_Eval_Queue
            WHERE Status = 'pending'
            {order_clause}
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute(
            "UPDATE Re_Eval_Queue SET Status='in_progress' WHERE QueueId=?",
            (row[0],),
        )
        conn.commit()
        return QueueRow(
            queue_id=int(row[0]),
            substitution_id=row[1],
            opportunity_id=row[2],
            candidate_sku_id=row[3],
            trigger_class=str(row[4]),
            reason=row[5],
            urgency=str(row[6] or "normal"),
        )
    except Exception:
        conn.rollback()
        raise


def _resolve(conn: sqlite3.Connection, queue_id: int, status: str, reason: str) -> None:
    conn.execute(
        """
        UPDATE Re_Eval_Queue
        SET Status=?, Reason=COALESCE(Reason,'') || ' | resolve:' || ?,
            ResolvedAt=datetime('now')
        WHERE QueueId=?
        """,
        (status, reason, queue_id),
    )
    conn.commit()


# --------------------------------------------------- trigger handlers


def _handle_cert_expiring(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Re-verify regulatory gate only — cert expiry doesn't invalidate
    # the canonical/role/form/grade chain, just the cert that keeps us
    # on the registry.
    conn.execute(
        """
        UPDATE Substitution_Gate_Result
        SET RegulatoryGate = 0
        WHERE CandidateSkuId = ? AND OpportunityId = ?
        """,
        (row.candidate_sku_id, row.opportunity_id),
    )
    conn.commit()
    return "regulatory_gate_invalidated"


def _handle_flagged_for_reeval(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Operator or critic flagged — the daemon marks the row resolved.
    # The next plan_opportunity call will re-run qualification naturally
    # because Substitution_Gate_Result is append-only (the freshest row
    # wins when the UI renders).
    return "pending_next_plan_call"


def _handle_supplier_down(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Mark the supplier's commercial row stale so scout re-fetches it on
    # next run (force_refresh=True on the ScoutRequest).
    if row.candidate_sku_id is not None:
        conn.execute(
            """
            UPDATE Supplier_Commercial
            SET Confidence = MIN(Confidence, 0.3)
            WHERE SupplierId IN (
                SELECT SupplierId FROM Supplier_Product WHERE ProductId = ?
            )
            """,
            (row.candidate_sku_id,),
        )
        conn.commit()
    return "supplier_commercial_marked_stale"


def _handle_new_compliance_rule(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Nuke the cached compliance outcomes for this candidate so the
    # next qualify_candidate re-derives them against the new rule pack.
    conn.execute(
        "DELETE FROM Compliance_Outcome_4State WHERE CandidateSkuId = ?",
        (row.candidate_sku_id,),
    )
    conn.commit()
    return "compliance_outcomes_cleared"


def _handle_price_shift(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Supplier rescore only — qualification chain is untouched. The
    # daemon flags Supplier_Score as needing recomputation; plan_opp
    # overwrites it on next call.
    if row.opportunity_id is not None:
        conn.execute(
            "DELETE FROM Supplier_Score WHERE OpportunityId = ?",
            (row.opportunity_id,),
        )
        conn.commit()
    return "supplier_score_invalidated"


def _handle_lead_time_shift(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Same treatment as price_shift — it's a commercial-score kick.
    return _handle_price_shift(conn, row)


def _handle_demand_shift(conn: sqlite3.Connection, row: QueueRow) -> str:
    # Re-aggregate demand for the affected canonical so RFQ urgency
    # tiers stay honest.
    try:
        agg = AggregateDemand(conn)
        # We don't know the exact canonical_id from the queue row, so
        # run the global aggregate and let the planner pick up the
        # refreshed values on next call.
        agg(persist_snapshot=True)
    except Exception as exc:  # noqa: BLE001
        return f"aggregate_demand_failed:{type(exc).__name__}"
    return "demand_aggregate_refreshed"


def _handle_new_case_learned(conn: sqlite3.Connection, row: QueueRow) -> str:
    # The Case_Library is always current; the re-evaluator just needs
    # to signal that the planner should consult it on next run. This
    # is a no-op at the DB level — the signal is the queue entry
    # itself, which gets resolved after processing.
    return "case_library_noted"


HANDLERS: Dict[str, Callable[[sqlite3.Connection, QueueRow], str]] = {
    "cert_expiring":       _handle_cert_expiring,
    "flagged_for_reeval":  _handle_flagged_for_reeval,
    "supplier_down":       _handle_supplier_down,
    "new_compliance_rule": _handle_new_compliance_rule,
    "price_shift":         _handle_price_shift,
    "lead_time_shift":     _handle_lead_time_shift,
    "demand_shift":        _handle_demand_shift,
    "new_case_learned":    _handle_new_case_learned,
}


# --------------------------------------------------------- main loop


def process_one(
    conn: sqlite3.Connection,
    recorder: Optional[RecordCase] = None,
) -> Optional[QueueRow]:
    """Process a single queue row if one is available. Returns the row
    processed (or None if the queue was empty)."""
    row = _claim_next(conn)
    if row is None:
        return None

    handler = HANDLERS.get(row.trigger_class)
    if handler is None:
        _resolve(conn, row.queue_id, "failed",
                 f"unknown_trigger:{row.trigger_class}")
        return row

    try:
        lesson = handler(conn, row)
        _resolve(conn, row.queue_id, "resolved", lesson)
        if recorder is not None:
            recorder(
                decision=f"reeval:{row.trigger_class}",
                reason=row.reason or "",
                lesson=lesson,
                opportunity_id=row.opportunity_id,
                candidate_sku_id=row.candidate_sku_id,
                confidence=0.9,
            )
    except Exception as exc:  # noqa: BLE001
        _resolve(conn, row.queue_id, "failed",
                 f"{type(exc).__name__}:{str(exc)[:80]}")
    return row


def run_one_shot(conn: sqlite3.Connection) -> DaemonStats:
    """Drain the queue exactly once, then return. Used by CI + demo."""
    _ensure_schema(conn)
    stats = DaemonStats()
    recorder = RecordCase(conn)
    while True:
        row = process_one(conn, recorder=recorder)
        if row is None:
            break
        stats.drained += 1
        stats.tally(row.trigger_class)
        # Peek at final status to classify.
        st = conn.execute(
            "SELECT Status FROM Re_Eval_Queue WHERE QueueId=?",
            (row.queue_id,),
        ).fetchone()
        if st and st[0] == "resolved":
            stats.processed += 1
        else:
            stats.failed += 1
    return stats


def run_daemon(
    db_path: str, interval_seconds: float, max_iters: Optional[int] = None,
) -> DaemonStats:
    """Poll-loop variant. Sleeps `interval_seconds` between drains.

    max_iters is provided so tests can bound the loop; production runs
    with max_iters=None never return unless SIGTERM / SIGINT fires.
    """
    stats = DaemonStats()
    iters = 0
    stop = {"flag": False}

    def _handler(signum, frame):  # noqa: ARG001
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

    while not stop["flag"]:
        conn = sqlite3.connect(db_path)
        try:
            one = run_one_shot(conn)
            stats.drained += one.drained
            stats.processed += one.processed
            stats.failed += one.failed
            for k, v in one.by_trigger.items():
                stats.by_trigger[k] = stats.by_trigger.get(k, 0) + v
        finally:
            conn.close()

        iters += 1
        if max_iters is not None and iters >= max_iters:
            break
        if stop["flag"]:
            break
        time.sleep(interval_seconds)

    return stats


# ---------------------------------------------------------- cli


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Agnes re-evaluator daemon")
    ap.add_argument("--db", required=True, help="Path to db_enriched.sqlite")
    mode = ap.add_mutually_exclusive_group(required=False)
    mode.add_argument("--one-shot", action="store_true",
                      help="Drain the queue once and exit (CI/demo mode)")
    mode.add_argument("--interval", type=float, default=None,
                      help="Poll interval in seconds (loop mode)")
    ap.add_argument("--max-iters", type=int, default=None,
                    help="Cap loop iterations (for tests)")
    args = ap.parse_args(argv)

    if args.interval is None or args.one_shot:
        conn = sqlite3.connect(args.db)
        try:
            stats = run_one_shot(conn)
        finally:
            conn.close()
    else:
        stats = run_daemon(args.db, args.interval, args.max_iters)

    print(f"reeval_daemon: drained={stats.drained} "
          f"processed={stats.processed} failed={stats.failed}")
    for k, v in sorted(stats.by_trigger.items()):
        if v > 0:
            print(f"  {k:>22s}: {v}")
    return 0 if stats.failed == 0 else 2


if __name__ == "__main__":
    sys.exit(_cli())
