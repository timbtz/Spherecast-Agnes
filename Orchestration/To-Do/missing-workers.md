# Missing Workers — Implementation To-Do

> Investigated: 2026-04-18
> All 9 existing agents are wired correctly. These 3 workers are absent, blocking the self-improving quality loop.

---

## [ ] 1. RedTeamAgent
**Priority:** HIGH — quality-assurance gate; full implementation exists, just needs migration + wiring

**What it does:**
Generates 4+ adversarial test cases to deliberately try to break Agnes's gate/compliance/refusal chain.
Three attack families:
- Look-alike names (swap benign molecule for toxicologically-related one)
- Expired/mismatched certs (claim jurisdictional approvals the candidate doesn't hold)
- Silent grade downshifts (drop pharma→technical grade, same name/SMILES)

Runs each attack through `gate_engine → compliance_reasoner → refusal_engine`.
Logs failures (false positives/negatives) to `Case_Library` for the ReEvalDaemon to learn from.
Exit code 0 = all attacks caught; non-zero = at least one false-pass.

**Inputs:** Optional `canonical_id` to target; defaults to full adversarial sweep
**Output:** Attack results, pass/fail per case, summary logged to `Case_Library`

**Source to migrate:** `local-dev/reasoning/red_team.py` (385 lines — complete)
**Target:** `orchestration/agents/red_team_agent.py`
**Steps:**
1. Copy `local-dev/reasoning/red_team.py` → `orchestration/agents/red_team_agent.py`
2. Wrap `run_all()` + `summarize()` in an async `RedTeamAgent.run()` method matching DAG agent interface
3. Register `RedTeamAgent` in `orchestration/api/agent_registry.py`
4. Optional: create `red_team_qa.yaml` pipeline triggered manually or on schedule

---

## [ ] 2. ReEvalDaemon
**Priority:** HIGH — closes the feedback loop; full implementation exists, needs migration + async refactor

**What it does:**
Drains `Re_Eval_Queue` table (populated by `flag_for_reeval` tool and system events).
Supports 8 trigger classes, each with a different re-evaluation strategy:

| Trigger class | Strategy |
|---|---|
| `cert_expiring` | Re-verify regulatory gate only |
| `flagged_for_reeval` | Full re-run (operator or critic flagged it) |
| `supplier_down` | Mark commercial row stale, force refresh on scout re-fetch |
| `new_compliance_rule` | Nuke cached compliance outcomes, re-derive against new rule pack |
| `price_shift` | Re-score suppliers, skip qualification |
| `lead_time_shift` | Re-score suppliers, skip qualification |
| `demand_shift` | Recompute aggregate_demand, re-rank |
| `new_case_learned` | Re-run with updated Case_Library weights |

Atomically claims rows (`Status='in_progress'`) to prevent double-processing.
Writes audit tags via `record_case` so `Case_Library` learns from each re-eval outcome.

**Source to migrate:** `local-dev/Orchestration/reeval_daemon.py` (200+ lines — complete)
**Target:** `orchestration/agents/reeval_daemon.py`
**Steps:**
1. Copy `local-dev/Orchestration/reeval_daemon.py` → `orchestration/agents/reeval_daemon.py`
2. Refactor daemon-loop into a one-shot async `ReEvalDaemon.run()` (claim one row, process, return)
3. Register `ReEvalDaemon` in `orchestration/api/agent_registry.py`
4. Wire background scheduling via APScheduler or cron (daemon mode incompatible with DAG executor)
5. Decision needed: cron-based background task vs. event-triggered DAG node

**Note:** `Re_Eval_Queue` table may not yet exist in `db_enriched.sqlite` — confirm or add migration.

---

## [ ] 3. Critic / Calibrator
**Priority:** MEDIUM — no implementation exists; design phase required before any code

**What it does (inferred from references):**
Acts as a post-qualification review layer before proposals reach users.
Consumes `Case_Library` results (populated by RedTeamAgent + ReEvalDaemon) to detect systematic failure patterns.
Potentially downgrades high-confidence but ambiguous recommendations to human-review status.
Referenced in phase-4 docs as the "planner/critic double-pass loop."

**Open design questions (must resolve before implementation):**
1. Trigger: post-DAG validation layer, or integrated into qualification chain mid-run?
2. Failure mode: abort pipeline / flag for human review / adjust confidence scores?
3. Learning mechanism: from `Case_Library` only, or also from explicit user feedback?
4. Output: modified proposal with confidence adjustment, or separate audit record?

**Suggested next step:** Write a PRD or design doc in `Orchestration/PRDs/` before coding.
**Target (once designed):** `orchestration/agents/calibrator_agent.py`
**Registration:** Add `CalibratorAgent` to `orchestration/api/agent_registry.py`

---

## Dependency Graph

```
RedTeamAgent  ──────────────────────────┐
                                        ▼
                                  Case_Library
                                        │
ReEvalDaemon (drains Re_Eval_Queue) ──▶ │
                                        ▼
                             Critic / Calibrator
                             (learns from Case_Library)
```

RedTeamAgent and ReEvalDaemon are prerequisites for Calibrator — build in that order.
