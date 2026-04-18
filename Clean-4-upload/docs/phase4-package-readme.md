# Agnes Phase 4 — Drop-in Package for Tim

**From:** Gursagar (`phase-4` branch)
**What this is:** everything you need to run the Phase 4 reasoning chain end-to-end against `db_enriched.sqlite`, plus a spec for the enrichment fields Phase 4 still needs.

---

## Contents

```
tim-package/
├── README.md                       ← you are here
├── 01-integration-handoff.md       ← what's new in Phase 4, what you owe us
├── 02-missing-data-schema.md       ← exact columns / tables we need from enrichment
├── 03-run-instructions.md          ← copy-paste setup & run
├── example-output.md               ← frozen markdown report from a real run
├── patches/
│   ├── gate_engine.py              → replaces reasoning/gate_engine.py
│   ├── compliance_reasoner.py      → replaces reasoning/compliance_reasoner.py
│   ├── refusal_engine.py           → replaces reasoning/refusal_engine.py
│   └── qualify_candidate.py        → replaces Orchestration/qualify_candidate.py
└── Orchestration/
    └── demo_real.py                → new file, drop into Orchestration/
```

---

## Reading order

1. **`03-run-instructions.md`** — get the demo running first. ~5 min, produces a markdown report for Magnesium Stearate with 3 drafted RFQs.
2. **`02-missing-data-schema.md`** — read this next. It enumerates every enrichment-side field / table / backfill the reasoning chain expects. Three items are marked 🔴 blocker.
3. **`01-integration-handoff.md`** — background on what I changed and why.

---

## What's running today

- Six-gate substitution chain with curated-graph fallback
- Dual-rule compliance across US-FDA + EU (121 canonical keys covered)
- Refusals persisted with failing gate + evidence IDs → `Refusal_Record`
- Supplier scoring Q/C/L/R → `Supplier_Score`
- RFQs drafted Status='draft' → `RFQ`

For Magnesium Stearate (`opp 263`) and Vegetable Magnesium Stearate (`opp 306`): 4 candidates pass, Ashland scored 0.402, 3 RFQs drafted each.

For sparse-enrichment opportunities (e.g. Calcium citrate), candidates refuse at `role_missing_one_side` because `Ingredient_Canonical.Function` is empty on 258/260 rows. Refusals are still logged with full per-gate trace.

---

## The three blockers

1. 🔴 **`SubstitutionGraphBuilder` case-insensitive lookup** — 10 LOC. Fixes 38/40 silent rule failures. Biggest single unlock.
2. 🔴 **~30 rows of `Supplier_Commercial`** — even hand-curated. Unblocks supplier scoring.
3. 🔴 **`Ingredient_Canonical.Function` backfill** on top 30 canonicals — free text, `RoleInferrer` normalizes.

Items 1–3 take the demo from 2 working opportunities to 30+ with meaningful supplier scores and RFQs. Full spec in `02-missing-data-schema.md`.
