# Missing Tools — Implementation To-Do

> Investigated: 2026-04-18
> All 11 existing tools are wired correctly. These 5 are absent but have partial or full logic in `local-dev/`.

---

## [ ] 1. QualifyCandidateTool
**Priority:** CRITICAL — blocks end-to-end supplier evaluation in all pipelines

**What it does:**
Runs the full 6-gate qualification chain on individual (incumbent, candidate) supplier pairs:
Role inference → substitution gate → compliance reasoning → refusal engine.
Persists results to `Substitution_Gate_Result` and `Compliance_Outcome_4State`.

**Inputs:** `canonical_id`, `incumbent_sku_id`, `candidate_sku_id`, `use_class`, `jurisdictions`
**Output:** `QualificationOutcome` — decision (`recommend` / `refuse` / `defer_human_review`), `compound_confidence`, `justification_md`

**Where to insert in pipelines:**
- `supplier_fallout.yaml` — between `gate-compliance` and `format-rfqs`
- `proactive_consolidation.yaml` — between `scan-opportunities` and `write-proposals`
- `new_ingredient_research.yaml` — after `gate-compliance`

**Source to migrate:** `local-dev/Orchestration/qualify_candidate.py`
**Target:** `orchestration/tools/qualify_candidate_tool.py`
**Registration:** Add `QualifyCandidateTool` entry to `orchestration/api/agent_registry.py`

---

## [ ] 2. SupplierScorerTool
**Priority:** HIGH — needed to rank qualified suppliers before RFQ generation

**What it does:**
Scores surviving (qualified) suppliers using weighted features: Price (P), Lead-time (L), Quality (Q), Compliance (C).
Pulls features from `Supplier_Commercial` table + landed cost from `ComputeLaneCostTool` (see below).
Returns top-N ranked suppliers for RFQ draft input.

**Inputs:** List of `SupplierFeatures` (supplier_id, price, lead_time, quality_metrics, compliance_pass)
**Output:** Ranked supplier list with scores and grade guidelines

**Source to adapt:** `reasoning/supplier_scorer.py` (exists) + `local-dev/Orchestration/planner.py` (caller logic)
**Target:** `orchestration/tools/supplier_scorer_tool.py`
**Registration:** Add `SupplierScorerTool` to `orchestration/api/agent_registry.py`

---

## [ ] 3. ComputeLaneCostTool
**Priority:** HIGH — feeds into SupplierScorerTool; needed for accurate landed cost

**What it does:**
Looks up freight lane from `Lane_Cost` table for (origin_country, destination_country) pair.
Falls back to 2-leg hub route (via US or DE) with 1.15× cost penalty if no direct lane exists.
Returns `LandedCost`: cost_usd_per_kg, lead_time_days, mode, via (hub), confidence (0.55–0.85).

**Inputs:** `supplier_country_origin`, `destination_country`, `preferred_mode` (optional)
**Output:** `LandedCost` struct

**Source to migrate:** `local-dev/enrichment/logistics/compute_lane_cost.py`
**Target:** `orchestration/tools/compute_lane_cost_tool.py`
**Registration:** Add `ComputeLaneCostTool` to `orchestration/api/agent_registry.py`

---

## [ ] 4. SendRfqTool
**Priority:** MEDIUM — completes the RFQ workflow; `RfqFormatterTool` drafts but never dispatches

**What it does:**
Takes draft RFQ IDs output by `RfqFormatterTool`, flips `Status='sent'`, stamps `SentAt` timestamp.
Stub email/API dispatch acceptable for MVP; `record_response()` handler for incoming quotes optional.

**Inputs:** List of draft RFQ IDs
**Output:** Count of RFQs sent, any dispatch errors

**Source to adapt:** `local-dev/Orchestration/rfq.py` (`mark_sent()`, `record_response()`)
**Target:** `orchestration/tools/send_rfq_tool.py`
**Registration:** Add `SendRfqTool` to `orchestration/api/agent_registry.py`

---

## [ ] 5. MapLogisticsTool
**Priority:** LOW — one-time seeding; low frequency; not blocking any active pipeline

**What it does:**
Idempotent seeding of `Lane_Cost` table with indicative country-level freight rates (ocean/air/truck/rail).
Optionally accepts custom lane records (hook for future Freightos/Xeneta adapters).

**Inputs:** Optional list of custom lane dicts (origin, destination, mode, lead_time_days, cost_usd_per_kg)
**Output:** Count of lanes inserted/updated

**Source to migrate:** `local-dev/enrichment/logistics/map_logistics.py` (`seed_lane_costs()`)
**Target:** `orchestration/tools/map_logistics_tool.py`
**Registration:** Add `MapLogisticsTool` to `orchestration/api/agent_registry.py`; trigger on `data_update`

---

## Suggested Implementation Order

```
ComputeLaneCostTool  →  QualifyCandidateTool  →  SupplierScorerTool  →  SendRfqTool  →  MapLogisticsTool
```
(ComputeLaneCostTool first because SupplierScorerTool depends on it; SendRfqTool last as it requires a dispatch layer decision.)


Regulatory Drift Plan — added a "Current Status" block at the top:                                                                                         
  - All code is complete (migration, CSV loader, drift tool, both agents, pipeline, conditions, API endpoint, opportunity_ranker integration)                
  - Data is loaded: 187 rows, 27 matched to canonicals                                                                                                       
  - Not yet run: the pipeline has never been triggered — 0 opportunities are actually flagged                                                                
  - Outstanding: trigger the pipeline once, add a dedicated Regulatory tab to the Sidebar, improve synonym matching to boost the 27/187 match rate           
                                                                                                                                                             
  Supplier Price Intelligence Plan — added a "Current Status" block at the top:                                                                              
  - All 20 tasks are complete — every file from the plan exists and is registered                                                                            
  - Critical gap: Supplier_Commercial has 0 rows — backfill_supplier_web.py needs to run with GOOGLE_API_KEY to populate it                                  
  - Price_Change_Alert has 0 rows — price_monitor pipeline needs a first run to establish baselines, then alerts appear on the second run                  
  - Small missing piece: usePriceAlerts.ts hook + TopBar badge weren't created (the GET /api/alerts/count endpoint exists, just needs a React hook and badge)
  - Phase 4 proposals, extending proactive_consolidation to 5 nodes, and the Molport API key are the other outstanding item