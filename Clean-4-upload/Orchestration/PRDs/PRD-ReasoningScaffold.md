# Agnes — Reasoning Scaffold PRD (Clean-4)

**Status:** Draft v1 — paired with the `Clean-4 → master` pull request
**Owner:** Gursagar (scaffold), Tim (pipeline + orchestration integration)
**Scope:** What the Clean-4 branch delivers on top of Tim's master HEAD
**Parents:** `Orchestration/PRDs/meta-workflow.md`, `Orchestration/PRDs/PRD.md`,
`Orchestration/PRDs/SQLBackendPRD.md`
**Goal date:** Hackathon demo (TUM.ai × Spherecast), end of current sprint

---

## 1. Problem

Agnes can already enrich raw SKU + BOM data (Stage 2, complete on master) and
has a working ADK multi-agent layer (Stage 3 stubs on master:
`orchestration/agents/`). What it cannot yet do is produce an **auditable,
refusable, substitution-grade** recommendation. Today a consolidation
proposal is:

- a formula score,
- plus an LLM-written paragraph.

For the demo — and for any real buyer — that is not enough. A supplement
brand replacing magnesium stearate with an alternative flow agent needs to
see:

1. Why the alternative is *chemically* a substitute (canonical identity, role
   in formulation, form, grade, morphology).
2. Why it is *regulatorily* a substitute across every jurisdiction the SKU
   ships to (not just "US-compliant").
3. Why the system is *confident* — and an explicit refusal when it is not.
4. The exact evidence rows (DSLD ingredient record, certification source,
   supplier spec sheet) that each claim leans on.

Clean-4 ships the reasoning layer that turns a scored opportunity into a
recommendation with all four of those properties.

## 2. Non-goals

- No new external API integrations. Works against what master already caches
  in `db_enriched.sqlite`.
- No UI work. Stage 4 owns that.
- No new orchestrator. Router, proactive, reactive, research, proposal
  writer, search sub-agent, and `_adk_runner` are already on master.
- No paid data sources. Free-tier APIs only (PubChem, DSLD, USDA FDC,
  openFDA, RxNorm; Molport free tier).
- No retraining or fine-tuning. Reasoning is deterministic rules + Claude as
  a narration and adjudication layer, not as the decision-maker.

## 3. Users and primary use cases

| User                | Primary job Clean-4 unblocks                                    |
| ------------------- | --------------------------------------------------------------- |
| Supplement brand PM | "Can I switch supplier X for ingredient Y and keep NSF + EU?"   |
| Procurement lead    | "Which of these 12 substitution edges are actually drop-ins?"   |
| Agnes (ReactiveAgent) | Supplier fallout → which alternatives are safe to shortlist?  |
| Agnes (ProactiveAgent) | Consolidation opportunity → which proposals can I write?     |
| Hackathon demo      | Run the magnesium-stearate anchor case end-to-end on stage.    |

## 4. Architecture overview

The scaffold is a set of pure Python modules under `reasoning/` that every
agent call routes through before a proposal is written. The ToolResult
contract below is the seam.

```
┌────────────────────────────────────────────────────────────────────┐
│ orchestration/agents/*                 (Tim — already on master)   │
│   router_agent / proactive / reactive / research / proposal_writer │
└───────────────────────────┬────────────────────────────────────────┘
                            │ calls qualify_candidate(…)
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ reasoning/qualify_candidate.py          (Clean-4 seam)             │
│   returns ToolResult{result, confidence, evidence_ids, refusal}    │
└───────┬──────────────┬──────────────┬──────────────┬───────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
 gate_engine   compliance_reasoner  refusal_engine  evidence_ledger
 (6 gates)     (4-state outcome)    (0.60 floor)    (append-only)
        │              │              │              │
        └────────┬─────┴──────────────┴──────────────┘
                 ▼
         db_enriched.sqlite (schema v1.2 additive)
```

## 5. Functional requirements

### 5.1 ToolResult contract
Every reasoning function exposed to the agents returns:

```python
ToolResult = {
    "result": <payload>,                 # domain object or None
    "confidence": float,                 # 0.0–1.0
    "evidence_ids": list[int],           # FK into Evidence_Ledger
    "refusal": Optional[RefusalReason],  # None unless refusal fired
}
```

Agents **must not** consume a bare payload — they consume the wrapper.
This is what makes the reasoning auditable: the ledger ids are written into
the proposal record, so the UI (Stage 4) and any reviewer can replay the
decision.

### 5.2 Six-gate substitution engine (`reasoning/gate_engine.py`)
A candidate substitution passes only if every gate passes. Each gate returns
its own sub-confidence, and the engine returns the min.

| # | Gate          | What it checks                                                        | Data source                       |
| - | ------------- | --------------------------------------------------------------------- | --------------------------------- |
| 1 | Canonical     | Same `CanonicalIngredientId` or marked-equivalent in Substitution_Rule | `Ingredient_Canonical`, `Ingredient_Substitution_Rule` |
| 2 | Role          | Same functional role (flow agent / binder / disintegrant / API)        | `Ingredient_Canonical.Role`       |
| 3 | Form          | Compatible form (powder / granular / liquid / capsule fill)            | `BOM_Component_Quantity.Form`     |
| 4 | Grade         | Meets the destination SKU's minimum grade (USP / FCC / GMP / lab)      | `Supplier_Commercial.Grade`       |
| 5 | Morphology    | Particle size / solubility close enough for the formulation            | `Ingredient_Canonical.Morphology` |
| 6 | Regulatory    | Passes `compliance_reasoner` in every destination jurisdiction         | `Product_Compliance`, Jurisdiction_Pack |

Each gate's decision carries one or more `evidence_ids` and a human-readable
reason. Failures short-circuit to a refusal.

### 5.3 Compliance reasoner (`reasoning/compliance_reasoner.py`)
Applies the **dual-rule** model per jurisdiction: `(allow-list, deny-list)`.
Returns one of four outcomes:

- `pass-global` — allowed in every destination jurisdiction.
- `fork-recommended` — allowed in subset; suggests per-jurisdiction SKU fork.
- `refuse` — denied in any mandatory jurisdiction with no fork path.
- `human-review` — data gap prevents a decision.

Initial jurisdiction packs: **US + EU**. Must ship **CA + JP** before demo
(currently a known gap; see §9).

### 5.4 Refusal engine (`reasoning/refusal_engine.py`)
Hard floor: if overall confidence < 0.60, the scaffold returns a refusal
regardless of what any individual gate said. Refusal reasons are typed so
the proposal writer can surface them instead of silently suggesting a weak
substitute.

Refusal reason enum:
`LowConfidence | MissingCompliance | MissingGrade | ConflictingEvidence |
GateFail:<n> | JurisdictionGap`

### 5.5 Evidence ledger (`reasoning/evidence_ledger.py`)
Append-only table keyed by `evidence_id`. Every row captures:

```
evidence_id, source_api, source_url, snapshot_hash, retrieved_at,
claim_type, claim_value, confidence, cited_by_tool
```

`qualify_candidate` appends rows from its tool calls; nothing downstream
mutates them. The Wiki log (`Orchestration/Wiki/log.md`) references ledger
ids so the on-stage demo can show the raw source for any recommendation.

### 5.6 Supplier scoring (reused, not new)
`Q · C · L · R` (Quality · Compliance · Logistics · Reliability) — already
defined in `reasoning/consolidation_scorer.py`. Clean-4 does not change the
formula; it only wraps it in a ToolResult so agents receive evidence ids.

### 5.7 Demo spine — magnesium stearate anchor case
The canonical walkthrough the demo hits live:

1. Network has 12+ brands buying magnesium stearate from 4 suppliers.
2. Proactive agent asks the scaffold to qualify "swap to X" on a US+EU SKU.
3. Gates 1–5 pass (0.82). Gate 6 refuses for EU on one supplier (deny-list).
4. Compliance reasoner returns `fork-recommended` with US-only ok.
5. Proposal writer frames the fork and cites the exact DSLD + EFSA evidence
   rows that drove the decision.

This is the single deterministic path Clean-4 must not break.

## 6. Data / schema changes (v1.2, additive only)

Non-breaking migration `schema/migrations/v12_reasoning_scaffold.sql`:

| Change                        | Why                                                    |
| ----------------------------- | ------------------------------------------------------ |
| `Evidence_Ledger` table (new) | Append-only audit trail keyed by `evidence_id`.        |
| `Proposal.evidence_ids TEXT`  | JSON array of ledger ids on each proposal.             |
| `Ingredient_Canonical.Role`   | Gate 2 needs role — currently sparse. Default `NULL`.  |
| `Ingredient_Canonical.Morphology` | Gate 5 needs morphology. Default `NULL`.           |
| `Ingredient_Substitution_Rule.Jurisdictions TEXT` | Scoped allow-lists. |
| `ToolResult_Log` view (new)   | Convenience view for replaying an agent turn.          |

Every new column is `NULL`-able. No existing query breaks.

## 7. Acceptance criteria

The PR from `Clean-4` → `master` ships when all of the following hold:

- [ ] `python -m reasoning.gate_engine --run-scenarios` passes **6/6**.
- [ ] `qualify_candidate` returns a well-formed `ToolResult` for the
      magnesium-stearate anchor case; `refusal is None` on US-only SKU,
      `refusal.type == GateFail:6` on EU-mandatory SKU.
- [ ] `compliance_reasoner` returns `fork-recommended` on at least one
      proactive output with both US + EU demanded.
- [ ] Every proposal row written during a full ProactiveAgent run has
      non-empty `evidence_ids` that dereference to live `Evidence_Ledger` rows.
- [ ] `refusal_engine` fires on a constructed low-confidence scenario and
      prevents a proposal from being written.
- [ ] `schema/migrations/v12_reasoning_scaffold.sql` is idempotent — running
      twice is a no-op.
- [ ] No `.env`, no SQLite binaries, no `__pycache__/` in the diff.
- [ ] `README-phase-4.md` accurately describes the directory tree.

## 8. Risks and mitigations

| Risk                                                      | Likelihood | Impact | Mitigation                                                   |
| --------------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------ |
| Jurisdiction packs only cover US + EU at demo             | Medium     | High   | CA + JP packs queued as must-ship-before-demo items (§9).    |
| `qualify_candidate` still reads stub rows, not real DB    | High today | High   | First task after PR — wire against `db_enriched.sqlite`.     |
| LLM proposal writer fabricates evidence ids               | Medium     | High   | Proposal writer receives ids as tool arguments, not free-text. |
| Evidence ledger grows unbounded                           | Low        | Low    | Append-only is intentional; drop snapshots older than 30d in post-demo cleanup. |
| Confidence floor (0.60) is too conservative / too loose   | Medium     | Med    | Expose as config; calibrate against the 6-scenario test set. |
| Merge conflicts on PR because master keeps moving         | Medium     | Med    | Clean-4 branches off latest master + cherry-picks only phase-4's `reasoning/`. |

## 9. Known gaps at PR time (work-in-progress, tracked after merge)

1. **Wire `qualify_candidate` against real `db_enriched.sqlite`.** Today it
   returns fixture rows.
2. **CA + JP jurisdiction packs** for `compliance_reasoner`.
3. **Router arbitration** in `orchestration/agents/router_agent.py` for the
   reactive/proactive/research branching — scaffold supports it; router
   doesn't yet dispatch.
4. **Wiki initialization** — `Orchestration/Wiki/index.md` and `log.md` need
   to exist before Stage 3 agents write. Stub in first ProactiveAgent run.
5. **Key rotation.** Old `.env` is in phase-4 history; treat all keys as
   exposed.

## 10. Out-of-scope (explicit non-goals re-stated)

- Substitution suggestions that require running new chemistry — only lookups
  against what's already enriched.
- Proactive re-pricing / negotiation. Clean-4 informs proposals; it does not
  transact.
- Any frontend.

## 11. Open decisions

| Decision                                 | Options                                        | Owner  | Blocks?        |
| ---------------------------------------- | ---------------------------------------------- | ------ | -------------- |
| Confidence-floor value                   | 0.55 vs 0.60 vs 0.65                           | Tim+Gur| No — config    |
| Evidence snapshot storage                | Inline JSON vs content-addressed blobs         | Gur    | No             |
| Jurisdiction-pack format                 | JSON schema vs YAML                            | Gur    | No             |
| LLM in compliance reasoner               | Rules only vs rules + Claude tie-break         | Gur+Tim| Yes for demo   |
| ADK vs Claude-only orchestration         | Already decided — ADK top-level, Claude tools  | Tim    | Closed         |

## 12. References

- `Orchestration/PRDs/meta-workflow.md` — four-stage implementation plan
- `Orchestration/PRDs/PRD.md` — product-level PRD
- `Orchestration/PRDs/SQLBackendPRD.md` — v1.1 schema work
- `Orchestration/Data/llm-wiki.md` — persistent-reasoning pattern
- `schema/enriched_schema.sql` — locked v1.1 schema
- `docs/integration-handoff.md` — Tim's integration notes (phase-4 origin)
- `docs/missing-data-schema.md` — gaps Tim flagged pre-scaffold
