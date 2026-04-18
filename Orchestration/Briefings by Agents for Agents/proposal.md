# Agnes Phase 4 — Agent Progress Report

*TUM.ai × Spherecast hackathon  •  phase-4 branch  •  April 18, 2026*

---

## 1. Summary

Agnes is a supply-chain reasoning system that ingests a CPG company's bill of materials, normalizes every ingredient to a canonical molecule, and then recommends concrete consolidation actions with full auditability — who to buy from, why, and why not an alternative.

Phase 4 is the reasoning layer that turns Tim's enriched data (Stage 2: 260 canonical ingredients, 1,025 products, 1,633 supplier links, 129 pre-scored consolidation opportunities) into per-decision verdicts: recommend, refuse, or human-review. Every decision is backed by a six-gate substitution check, a dual-rule compliance reasoner across multiple jurisdictions, and a refusal engine with a hard 0.60 confidence floor. No LLM is in the decision hot path; the LLM writes a narrative polish on top of a deterministic audit trail.

The phase-4 branch on timbtz/Spherecast-Agnes now contains the full reasoning scaffold (pushed April 18) plus a fix commit for the justification renderer. End-to-end sims against a stub database pass; the next commit wires the planner against real `db_enriched.sqlite` opportunities.

---

## 2. Architecture

The system is layered so each concern is testable in isolation and the reasoning chain stays deterministic:

- **Stage 1 — Schema Lock** (`db.sqlite`, v1.1 schema). Spherecast's raw ERP tables. Read-only.
- **Stage 2 — Enrichment** (Tim). `Ingredient_Canonical`, `Supplier_Commercial`, `Product_Compliance`, `SKU_To_Canonical`. Outputs: `db_enriched.sqlite`.
- **Stage 3 — Agent Layer** (in progress). ReactiveAgent, ProactiveAgent, ResearchAgent wired via Google ADK + Claude API.
- **Stage 4 — Reasoning Layer** (Phase 4 scaffold, just pushed). Six-gate engine + dual-rule compliance + refusal + supplier score + RFQ drafter.
- **Stage 5 — Frontend** (next week). HTMX/Flask surface that reads the decision lattice out of `db_enriched.sqlite`.

Everything writes through a uniform `ToolResult` contract: `{ result, confidence, evidence_ids, refusal }`. Confidence below 0.60 anywhere in the chain triggers a refusal with a logged reason. Evidence IDs reference a persistent `Evidence_Ledger`, so every claim the system makes can be traced back to the source row that justified it.

---

## 3. Agent and Tool Inventory

| Agent / Tool | Layer | Status | Primary output |
|---|---|---|---|
| RoleInferrer | Reasoning | Built | Functional role string (+ confidence) |
| GateEngine (6-gate) | Reasoning | Built | Pass/fail + per-gate trace + compound confidence |
| ComplianceReasoner | Reasoning | Built | pass-global / fork-recommended / refuse / human-review |
| RefusalEngine | Reasoning | Built | recommend / refuse_* / defer_human_review |
| SupplierScorer | Reasoning | Built | Ranked supplier list with Q/C/L/R components |
| SubstitutionGraphBuilder | Enrichment | Built (Tim) | `Ingredient_Substitution` edges |
| ConsolidationScorer | Enrichment | Built (Tim) | 129 scored opportunities |
| ProposalGenerator | Enrichment | Built (Tim, needs API key) | `Proposal_Text` markdown + JSON |
| plan_opportunity | Orchestration | Built | `OpportunityVerdict` (qualifications + suppliers + RFQs) |
| qualify_candidate | Orchestration | Built | `QualificationOutcome` + justification markdown |
| draft_rfq | Orchestration | Built | RFQ row (status='draft', human must confirm send) |
| ToolRegistry | Orchestration | Built | JSON-schema tool list for ADK planner |
| ReactiveAgent | Stage 3 | Pending | Alternative suppliers for fallout events |
| ProactiveAgent | Stage 3 | Pending | Consolidation proposals on schedule |
| ResearchAgent | Stage 3 | Pending | Net-new supplier discovery via web search |

---

## 4. Reasoning Layer — Phase 4 scaffold

These are deterministic tools — no LLM in the decision path. They live in the `reasoning/` package on the `phase-4` branch and expose a uniform `Tool` contract. Each one can be invoked directly or through the `ToolRegistry` (which emits JSON schemas consumable by Google ADK or the Claude API's `tool_use`).

### 4.1 RoleInferrer

Decides what functional role an ingredient plays in a recipe slot. Two SKUs can share a molecule but play different roles — citric acid as acidulant vs. chelator vs. preservative-aid — and the gate chain must compare like-for-like.

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `ingredient_name: str`<br>`recipe_slot_hint: Optional[str]` | Rule-based lookup on ~40 curated ingredient→role mappings. Multi-role resolution (e.g. ascorbic acid → antioxidant / acidulant / vitamin-fortificant) via slot hint. Never invents a role: unknown returns `'unknown'` with low confidence. | `role: str` (or `'unknown'`)<br>`confidence: float ∈ [0,1]`<br>refusal reason if empty input or unresolvable multi-role | Consumed by GateEngine (role gate). Consumed by `qualify_candidate` when `SkuProfile.role` is missing. |

### 4.2 GateEngine — six-gate substitution check

The core of Agnes's substitution logic. Runs an incumbent + candidate `SkuProfile` through six strict gates in order. Any gate failure short-circuits with a logged reason. Per-gate confidences multiply into a compound score; the 0.60 floor gates all recommendations.

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `incumbent: SkuProfile` (sku_id, canonical_id, smiles, unii, role, form, grade, psd_bucket, surface_area, bulk_density, jurisdictions_approved, use_class)<br>`candidate: SkuProfile` (same shape)<br>`jurisdiction: str` (e.g. `'US-FDA'`, `'EU'`)<br>`evidence_ids: List[int]` (optional) | **Canonical gate** — SMILES exact, UNII exact, canonical_id match, or curated `Ingredient_Substitution` edge (upcoming patch). **Role gate** — exact role match required. **Form gate** — whitelisted form pairs (powder / granular / crystal all compatible; liquid is its own lane). **Grade gate** — never silently downshifts pharma → food → feed. **Morphology gate** — PSD bucket match or surface area within 2×. **Regulatory gate** — candidate must be pre-approved in the target jurisdiction. | `passed: bool`<br>`failed_gate: Optional[str]` (first failure)<br>`notes: Dict[gate, str]` (full six-line trace)<br>`per_gate_confidence: Dict[gate, float]`<br>`compound_confidence: float` | Upstream of ComplianceReasoner (only gate-passing candidates are evaluated). Output persisted to `Substitution_Gate_Result` table. Read by `justification.render()` for the UI panel. |

### 4.3 ComplianceReasoner — dual-rule, 4-state

Every (candidate, jurisdiction) pair gets two parallel checks: the `CATEGORY_BASELINE` (regulatory floor for that market + use class) and the `IMPLICIT_STANDARD` (whether trusted incumbents already use this ingredient in that jurisdiction). Their intersection produces one of four outcomes — this is the proposal's signature `fork-recommended` state for products that ship in both US and EU but would need different substitutes per market.

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `candidate_name: str`<br>`use_class: 'food' \| 'beverage' \| 'supplement'`<br>`jurisdictions: List[str]`<br>`incumbent_precedents: Dict[jurisdiction → bool]` (derived from `Product_Compliance`) | Jurisdiction packs with banned / allowed / requires_gras flags. Four-state aggregation (pass-global, fork-recommended, refuse, human-review). Weakest-jurisdiction-wins aggregation (min confidence across markets). Treats missing rules as pessimistic (`baseline_missing_rule` → refuse), not optimistic. | `outcome: 4-state string`<br>`reason: 'baseline_ok;implicit_ok_all'` etc.<br>`per_jurisdiction: List[{jurisdiction, baseline_ok, implicit_ok, reason, confidence}]` | Upstream of RefusalEngine. Output persisted to `Compliance_Outcome_4State` table. Fork-recommended outcomes feed into planner's per-market RFQ drafts. |

### 4.4 RefusalEngine

The chokepoint. Wraps gate + compliance results into a single decision and logs every refusal to `Refusal_Record` with the full evidence trail. This is the mechanism that backs Agnes's "auditable-refusal" promise — we never silently drop a candidate.

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `opportunity_id: int`<br>`candidate_sku_id: Optional[int]`<br>`gate_result` + `gate_confidence`<br>`compliance_result` + `compliance_confidence`<br>`evidence_ids: List[int]` | Compound confidence = `gate_conf × compliance_conf`. Hard 0.60 floor triggers `refuse_low_confidence`. Gate failures propagate as `refuse_gate_fail:<failing_gate>`. Compliance `refuse` state propagates as `refuse_compliance`. `human-review` state defers without refusing. | `decision`: `recommend` \| `refuse_gate_fail` \| `refuse_compliance` \| `refuse_low_confidence` \| `defer_human_review`<br>`compound_confidence: float`<br>`Refusal_Record` INSERT (`OpportunityId`, `Reason`, `CompoundConfidence`, `FailingGate`, `EvidenceIds`) | Only `recommend` and `defer_human_review` pass to SupplierScorer. Refusals logged for UI "why we refused" panel. |

### 4.5 SupplierScorer

Ranks suppliers within an already-qualified opportunity using the `Q·C·L·R` formula from the proposal. Quality / Cost / Logistics / Risk each mapped to `[0,1]`. Default weights 0.35 / 0.30 / 0.20 / 0.15 — tunable per ingredient class (pharma weights Q higher).

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `opportunity_id: int`<br>`suppliers: List[SupplierFeatures]` (supplier_id, supplier_name, Q, C, L, R, compliance_pass, evidence_ids) | Weighted sum: `S = w_Q·Q + w_C·C + w_L·L − w_R·R`. Non-compliance-passing suppliers persisted with S=0 (not ranked). Top-supplier score becomes the `ToolResult.confidence` — weak winners look weak. | Ranked list: `[{supplier_id, supplier_name, score, components, weights, evidence_ids}]`<br>`Supplier_Score` INSERTs (one per supplier, incl. compliance-fail rows for audit) | Top-N suppliers handed to `draft_rfq`. Rank visible in justification markdown (ranked supplier shortlist). |

---

## 5. Enrichment Layer — Tim's modules (Phase 4 part a)

Tim's three additional reasoning modules live alongside the scaffold on the `phase-4` branch. They run opportunity-level work: scoring, substitution-edge construction, and LLM-backed proposal narratives. The reasoning layer consumes their outputs.

### 5.1 SubstitutionGraphBuilder

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `db_enriched.sqlite` connection<br>`Ingredient_Substitution_Rule` rows (40 curated)<br>`Ingredient_Canonical` rows (CAS numbers) | Translates curated rules into edge pairs (both directions). Adds identical edges for canonicals sharing a CAS number. Skips rules whose names don't resolve to canonicals (documented gap: 38/40 currently miss). | `Ingredient_Substitution` INSERTs (`identical` \| `equivalent` \| `partial`). Edge score + JSON source trail. | Read by GateEngine's curated-fallback canonical gate (upcoming patch). Read by `plan_opportunity` to enumerate candidates per opportunity. |

### 5.2 ConsolidationScorer

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `db_enriched.sqlite`<br>`SKU_To_Canonical`, `Product`, `Company`, `BOM_Component` tables | Formula score: `company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15`. Normalizes denominators against the DB-wide max. Skips canonicals used by fewer than 2 companies (no consolidation opportunity). | `Consolidation_Opportunity` UPSERTs (129 rows in current DB). Top-10 console report. | Opportunities consumed by `plan_opportunity` and ProposalGenerator. Ranked list read by Stage 3 ProactiveAgent. |

### 5.3 ProposalGenerator

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| Top opportunities (score ≥ 0.30, company_count ≥ 2, top-10 by default)<br>`ANTHROPIC_API_KEY`<br>Context: companies using the ingredient, existing suppliers | Claude API call per opportunity. Structured JSON + markdown narrative. LLM score adjustment in ±0.10 range. | `Consolidation_Opportunity.Proposal_Text` + `Proposal_JSON`. Markdown report across all opportunities. | Proposal text rendered by Stage 4 frontend. JSON consumed by `plan_opportunity`'s summary builder. |

---

## 6. Orchestration Wrappers — Phase 4 scaffold

Ties together the reasoning tools into an end-to-end planner flow per consolidation opportunity. Blocking (no async) so the demo is easy to step through.

### 6.1 qualify_candidate

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| db connection<br>`opportunity_id`, incumbent + candidate `SkuProfile`s<br>`incumbent_name`, `candidate_name`<br>`use_class`, `jurisdictions`, `incumbent_precedents` | Sequences role inference → gates → compliance → refusal. Persists to `Substitution_Gate_Result` + `Compliance_Outcome_4State`. Renders a markdown justification via `reasoning.justification.render()`. | `QualificationOutcome` (decision, compound_confidence, full trace, `justification_md`)<br>DB INSERTs for gate + compliance + refusal tables | Called per-candidate by `plan_opportunity`. Output rendered under each shortlisted recommendation in the UI. |

### 6.2 plan_opportunity

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| db connection<br>`opportunity_id`, `incumbent_profile`, `incumbent_name`<br>`use_class`, `jurisdictions`<br>`candidates: List[CandidateBundle]`<br>`rfq_top_n` (default 3) | Qualifies every candidate independently. Scores the compliance-passing suppliers. Drafts RFQs for the top-N (status='draft', never auto-sent). Composes a short opportunity summary. | `OpportunityVerdict` (qualifications, ranked_suppliers, drafted_rfq_ids, summary_md) | Called per-opportunity by `demo_real.py` and (eventually) ProactiveAgent. Output surfaces in the Stage 4 frontend. |

### 6.3 draft_rfq

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `opportunity_id`<br>`candidate_supplier_name`<br>`canonical_ingredient_id`<br>`RfqSpec` (name, SMILES, UNII, role, form, grade, PSD, target markets, quantity band, required certifications, notes) | Serializes the spec as JSON. INSERT into `RFQ` with `Status='draft'`. Never auto-sends — a human must click through to flip `Status='sent'`. | RFQ row id (int). Full JSON spec persisted in `SpecJson` column. | Reviewed by buyer in Stage 4 UI. `mark_sent` and `record_response` called later when supplier replies. |

### 6.4 ToolRegistry (tool_runtime)

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| `Tool` instances + `args_schema` + descriptions | Uniform `register` / `get` / `invoke` interface. `to_planner_schema()` emits JSON schemas consumable by Google ADK and Claude API `tool_use` blocks. `build_default_registry(conn)` wires all five reasoning tools in one call. | `ToolResult` from any registered tool. `List[JSON schema]` for an LLM planner's tool list. | Used by Stage 3 agents when Tim wires ADK — not needed inside Phase 4 where `planner.py` calls tools directly. |

---

## 7. Stage 3 Agents (next up)

The three top-level agents the hackathon delivery plan calls for. None is implemented yet; this section defines what they'll request, what they'll do, and what they'll output once the orchestration harness is wired.

### 7.1 ReactiveAgent — supplier-fallout responder

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| Trigger: supplier-fallout event (manual or alert-driven). Affected `supplier_id`. Optional: priority ingredients list. | Queries all ingredients affected by the fallout. For each, enumerates curated substitutes + alternative suppliers in DB. Falls back to ResearchAgent if no in-DB candidates survive gates. Drafts RFQs for top surviving alternatives. | List of `OpportunityVerdict`s (one per affected ingredient). Prioritized RFQ queue for buyer review. Wiki entry summarizing the response plan. | `plan_opportunity` (per affected ingredient). ResearchAgent (fallback when DB candidates insufficient). Wiki writer for the response log. |

### 7.2 ProactiveAgent — scheduled consolidation runner

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| Trigger: schedule (weekly) or on-demand. Optional: minimum score threshold. Target jurisdictions (default US-FDA + EU). | Pulls top-N opportunities from `Consolidation_Opportunity`. Runs `plan_opportunity` for each. Writes results to wiki with week-over-week deltas. | Ranked proposal list with drafted RFQs. Weekly consolidation digest (wiki page). Email summary (via stage-4 surface). | `plan_opportunity` (per opportunity). ProposalGenerator (LLM narrative polish on top). Wiki writer for the digest page. |

### 7.3 ResearchAgent — net-new supplier discovery

| Requests (inputs) | Features (capabilities) | Outputs | Delegates to |
|---|---|---|---|
| Trigger: on-demand from buyer, or fallback from ReactiveAgent. Target ingredient (`canonical_id`). Required certifications + target markets. | Google ADK web search for suppliers not in DB. Playwright-driven scrape of candidate supplier pages. Claude API extracts structured records from unstructured HTML. Gate-checks discovered suppliers before surfacing. | List of `SupplierCandidate` records (name, country, certifications, contact, evidence URLs). INSERTs to `Supplier` + `Supplier_Product` (after human approval). | Google ADK (search + browsing). Claude API (structured extraction). GateEngine (compliance pre-filter before adding to DB). |

---

## 8. Delegation flow

A single consolidation opportunity walks this path from enriched data to buyer-reviewable RFQ draft:

1. **ConsolidationScorer** ranks `Consolidation_Opportunity` rows by score.
2. **ProactiveAgent** (or the demo runner) picks the top-N and hands each one to `plan_opportunity`.
3. **plan_opportunity** enumerates candidates via `Ingredient_Substitution` edges.
4. For each candidate, `plan_opportunity` calls **qualify_candidate**.
5. **qualify_candidate** runs RoleInferrer → GateEngine → ComplianceReasoner → RefusalEngine in sequence.
6. **RefusalEngine** decides: `recommend` / `refuse_*` / `defer_human_review`. Refusals persist to `Refusal_Record` with evidence.
7. Surviving candidates pass to **SupplierScorer**, which ranks the compliance-passing suppliers and persists all rows (incl. compliance-fails) for audit.
8. Top-N suppliers hand over to **draft_rfq**. RFQ rows land with `Status='draft'`.
9. **reasoning.justification.render()** produces a markdown panel for each verdict showing the full six-gate trace, compliance per-jurisdiction breakdown, and supplier shortlist.
10. **Stage 4 frontend** reads `db_enriched.sqlite` and renders the verdicts + RFQ drafts with a "Send" button. Only the human can flip `Status='sent'`.

---

## 9. Current progress

- Phase 4 scaffold pushed to `timbtz/Spherecast-Agnes:phase-4` (commit `2503f9b`).
- Cosmetic marker bug in justification renderer fixed and pushed (commit `72f8580`).
- End-to-end sims pass against a stub database (6 scenarios covering each refusal state).
- Root-level `reasoning/` and `Orchestration/` merged cleanly with Tim's pre-existing upload.
- `db_enriched.sqlite` inventoried: 260 canonical ingredients, 1,025 products, 40 suppliers, 1,633 supplier links, 854 SKU→canonical maps, 129 scored opportunities, 40 substitution rules.

---

## 10. Next steps

- Wire `plan_opportunity` against real `db_enriched.sqlite` opportunities (adapter in progress).
- Extend GateEngine canonical gate with a curated `Ingredient_Substitution` fallback so equivalent-salt subs don't reject on SMILES mismatch.
- Extend ComplianceReasoner jurisdiction packs to cover the ~40 dietary-supplement ingredients in Tim's real data.
- Build Stage 3 ReactiveAgent + ProactiveAgent on top of `plan_opportunity` (hackathon-critical work).
- Rotate committed `.env` secrets and add to `.gitignore` (outstanding security item).
