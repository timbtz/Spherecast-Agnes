# Phase 4 scaffold — reasoning + orchestration

This branch (`phase-4`) adds the reasoning lattice on top of Tim's
enrichment spine (Phases 1-3). Nothing in `enrichment/` that Tim has
already shipped is touched; everything here is additive.

## Folder map

```
schema/
  migration_v12.sql              # additive sqlite schema (v1.1 -> v1.2)

enrichment/
  db_migrate_v12.py              # PRAGMA-guarded migration runner
  scout/                         # supplier discovery
    scout.py
    directories.py               # thomasnet / dsld / seed adapters
  logistics/                     # lane cost
    map_logistics.py             # seed lane data
    compute_lane_cost.py         # landed cost lookup w/ 2-leg fallback

reasoning/                       # all decision logic, no LLM in hot path
  base.py                        # Tool contract + ToolResult + compound_confidence
  evidence_ledger.py             # append-only Evidence_Ledger writer
  role_inferrer.py               # functional role inference (rule-based)
  gate_engine.py                 # six-gate substitution check
  compliance_reasoner.py         # dual-rule, four-state outcome
  refusal_engine.py              # recommend / refuse / human-review
  supplier_scorer.py             # S = w_Q·Q + w_C·C + w_L·L − w_R·R
  justification.py               # markdown trace per decision

Orchestration/                   # glue
  tool_runtime.py                # ToolRegistry for planner integration
  qualify_candidate.py           # one (incumbent, candidate) end-to-end
  rfq.py                         # draft RFQ, never auto-send
  planner.py                     # full opportunity flow
  sims/
    anchor_case.py               # demo fixture (sucralose -> sucralose/stevia)
    stress_injector.py           # mutators for each failure mode
    sim_runners.py               # CLI demo harness
```

## How to run the demo end-to-end

```bash
# 1. Apply Phase 4 schema additions to Tim's enriched DB.
python -m enrichment.db_migrate_v12 --db ./db_enriched.sqlite

# 2. Walk anchor case + 5 stress scenarios through the full lattice.
python -m Orchestration.sims.sim_runners --db ./db_enriched.sqlite --verbose
```

Expected output: six labeled verdicts, drafted RFQ rows in the `RFQ`
table (Status='draft' until a human flips them to 'sent'), and full
audit trails in `Substitution_Gate_Result`, `Compliance_Outcome_4State`,
`Refusal_Record`, and `Supplier_Score`.

## Design rules I'm holding the line on

- **Every tool returns a `ToolResult`.** Never a raw dict, never an
  exception. Exceptions in `_run` are converted to refusals at the
  `Tool.__call__` wrapper.
- **Confidence is multiplicative across the chain.** `<0.60` triggers
  auto-refusal at the refusal engine. Empty inputs return 0.0, not 1.0.
- **No LLM in the hot path.** The justification renderer is rule-based
  so the demo is reproducible and we can show "no hallucination" with a
  straight face. LLM polish can layer on top of `justification_md`.
- **Append-only evidence ledger.** No update, no delete. Every assertion
  the gates / compliance / scoring touches references EvidenceIds.
- **RFQs are never auto-sent.** Status starts at 'draft'. The UI flips
  it to 'sent' only after a human confirms.

## What's left after this branch

- Wire the reasoning tools into Tim's ADK runner via
  `Orchestration.tool_runtime.build_default_registry()`.
- Replace the seed `JURISDICTION_PACKS` with real FDA FCS / EFSA data
  pulled by Tim's enrichment layer.
- Replace seed lane costs with Freightos/Xeneta when the API key lands.
- UI surface for the verdict (Eng3) — drafted-RFQ panel + per-gate
  trace from `justification_md`.

## What this scaffold does NOT do

- Does not modify Tim's existing tables (only ALTERs add columns; no
  UPDATEs or DROPs anywhere).
- Does not call the network in tests (every adapter has a seed
  fallback).
- Does not auto-send RFQs, auto-accept compliance verdicts, or hide
  refusals from the audit log.
