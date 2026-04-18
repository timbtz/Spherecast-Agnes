# Agnes — Meta Workflow & Implementation Plan

**Version:** 0.1  
**Date:** 2026-04-18  
**Status:** Living Document

---

## Purpose

This document defines *how we work*, not just *what we build*. It describes the four implementation stages in sequence, the agent structure within each stage, open design decisions, and how the layers connect to each other. Read this before any code is written in a new stage.

---

## The Four Stages at a Glance

```
Stage 1 — API Exploration & Schema Lock
  └─ Sub-agents research each API, produce guides + sample data
  └─ First final enriched schema locked from empirical evidence

Stage 2 — Data Enrichment Pipeline
  └─ Phases 1–3: ingredient identity, BOM quantities, commercial/compliance
  └─ Quality & supplier scoring baked into the schema (see open question below)
  └─ All output stored in db_enriched.sqlite with source + confidence

Stage 3 — Agent Orchestration Layer (Google ADK)
  └─ Reactive agents: supplier fallout → find alternative
  └─ Proactive agents: consolidation suggestions, order bulk-up
  └─ Research agents: new supplier discovery
  └─ Reasoning anchored by LLM-wiki for determinism + trust

Stage 4 — Frontend & Visualization
  └─ DAG executor makes agent reasoning inspectable
  └─ Per-proposal evidence trail UI
  └─ B2B trust layer: human-in-the-loop review flows
```

The stages are sequential at a coarse level — Stage 3 agents need Stage 2 data, Stage 4 visualizes Stage 3 reasoning. But within each stage, sub-agents and modules run in parallel.

---

## Stage 1 — API Exploration & Schema Lock

### Goal

Before any enrichment schema is finalized, every external API is called against a real sample from `db.sqlite`. The goal is empirical: discover what fields actually return, what's frequently null, what format normalization is needed, and which sources are worth building integrations for. This stage produces the evidence that locks the schema.

### How We Work Here

Each API gets its own **exploration sub-agent**. The sub-agent:
1. Samples 20–30 real ingredient slugs or product IDs from `db.sqlite`
2. Calls the API against those samples
3. Documents: fields returned, hit rate, null/missing rate, format quirks, data quality issues
4. Writes a reference guide to `Orchestration/References/` (e.g., `dsld-integration.md`)
5. Provides a **schema recommendation**: which fields are reliable enough to be non-nullable, which must be nullable-by-default, and which should be stored as raw JSON blobs

APIs to explore (one sub-agent each):
| API | Reference Guide Output |
|---|---|
| PubChem PUG REST | `Orchestration/References/pubchem-integration.md` |
| NIH DSLD v9 | `Orchestration/References/dsld-integration.md` |
| USDA FoodData Central | `Orchestration/References/usda-fdc-integration.md` |
| Molport v3 | `Orchestration/References/molport-integration.md` |
| RxNorm | `Orchestration/References/rxnorm-integration.md` |
| openFDA | `Orchestration/References/openfda-integration.md` |

Each guide must include:
- Endpoint(s) used
- Auth method
- Sample request + sample response (real data, not invented)
- Field coverage table: field name → hit rate on ingredient sample
- Format normalization notes (e.g., CAS number variants, unit inconsistencies)
- Rate limits and caching strategy
- Recommended confidence assignment per match type

### Schema Lock

Once all API exploration guides are complete, a single **schema finalization pass** reviews all recommendations together and produces the final `schema/enriched_schema.sql`. This file is locked after Stage 1 — no schema changes in later stages without an explicit decision log entry.

The schema lock also includes one end-to-end smoke test: clone `db.sqlite` → `db_enriched.sqlite`, create at least one Agnes-added table, populate it with a few real rows, and verify JOINs to the original tables work.

### Deliverables

- [ ] Reference guide per API in `Orchestration/References/`
- [ ] `schema/enriched_schema.sql` finalized with empirically-grounded nullability and field choices
- [ ] `db_enriched.sqlite` smoke test passes (clone + add table + JOIN)

---

## Stage 2 — Data Enrichment Pipeline

### Goal

Populate `db_enriched.sqlite` with all the data that Stage 3 agents will reason over. No agent reasoning happens here — only data collection and storage. Every stored field carries `source` (string) and `confidence` (float 0–1).

### Phases

**Phase 1 — Ingredient Identity (most critical)**  
SKU parser → PubChem → DSLD → RapidFuzz → `SKU_To_Canonical` + `Ingredient_Canonical`  
Output: 876 SKUs mapped to canonical identities with confidence scores

**Phase 2 — BOM Quantity Enrichment**  
DSLD → Browser agent (retailer pages) → Google ADK → `BOM_Component_Quantity`  
Output: Supplement Facts amounts for ≥ 70% of BOM components

**Phase 3 — Commercial & Compliance**  
PureBulk / Alibaba / Molport → `Supplier_Commercial`  
DSLD label claims + NSF/USP/Informed Sport databases → `Product_Compliance`

### Open Design Decision: Quality & Supplier Scoring

> **This is not yet resolved. Choose an approach before implementing Phase 3.**

The system needs quality and supplier quality scores to support consolidation reasoning. Three approaches:

**Option A — Mathematical columns (deterministic)**  
Pre-defined formula columns computed from raw data fields (cert count, supplier age, geographic risk flags, price variance). Stored as floats. Fast, auditable, no LLM cost.

Pros: Reproducible, transparent, cheap to recompute  
Cons: Misses nuance that doesn't fit a formula; requires careful calibration

**Option B — Agent-computed scores with reasoning trace**  
An agent reads the enriched data for each canonical ingredient × supplier pair, reasons about quality signals, and writes a structured score + justification. Stored as float + markdown reasoning blob.

Pros: Captures soft signals, produces human-readable explanation  
Cons: LLM cost at scale (876 ingredients × 40 suppliers), non-deterministic on re-run

**Option C — Hybrid (recommended)**  
Mathematical columns compute a baseline score from hard data signals. A lightweight LLM pass then adjusts the score and adds a one-paragraph justification only for top-scoring consolidation candidates (top 50 by company count). The LLM never invents data — it only interprets what's already stored.

This keeps cost low, keeps reasoning explainable for the proposals that matter, and makes the scoring auditable at the formula level.

**Decision log entry required before coding the enrichers.**

### Quality/Compliance Dimensions to Score

Regardless of method chosen, these dimensions should be captured:

| Dimension | Signal Source | Table |
|---|---|---|
| Ingredient grade | DSLD label text, PubChem function field | `Ingredient_Canonical.Function` |
| Certification coverage | NSF/USP/Informed Sport lookup | `Product_Compliance` |
| Supplier commercial reliability | Price confidence, MOQ, lead time | `Supplier_Commercial.Confidence` |
| Compliance homogeneity across companies | Cert overlap across `Product_Compliance` rows | Computed at scoring time |
| Cross-company substitutability | Substitution type (identical/equivalent/partial) | `Ingredient_Substitution.Score` |

### Deliverables

- [ ] `enrichment/pipeline.py` with `--phase 1/2/3` flags
- [ ] All enrichment modules under `enrichment/sources/`, `enrichment/normalizers/`, `enrichment/enrichers/`
- [ ] `db_enriched.sqlite` populated meeting the thresholds in PRD §11
- [ ] Quality/compliance scoring decision documented and implemented

---

## Stage 3 — Agent Orchestration Layer (Google ADK)

### Goal

Build the agent workflows that sit on top of the enriched database and serve the operational use cases. These agents read from `db_enriched.sqlite`, call external services as needed (web search, browser), and write conclusions back to the database or produce structured output reports.

### Agent Architecture

Three agent types, each triggered differently:

#### 3A — Reactive Agents (Event-Triggered)
**Trigger:** External event (supplier fallout, certification lapse, price spike)  
**Example:** Supplier X drops out → find alternative supplier for all affected canonical ingredients

Workflow:
1. Receive trigger payload: `{supplier_id, reason, affected_ingredient_ids}`
2. Query `db_enriched.sqlite` for all companies affected, current substitution graph, compliance requirements
3. Google ADK search → find alternative suppliers for each ingredient
4. Browser agent → extract pricing/MOQ from supplier pages
5. LLM reasoning → rank alternatives by compliance fit, price, and substitution score
6. Write ranked alternatives back to a `Supplier_Alternative` table with evidence trail
7. Generate a structured alert report (markdown + JSON)

#### 3B — Proactive Agents (Scheduled or On-Demand)
**Trigger:** User request or scheduled run  
**Examples:**
- Bulk order optimization: "Which ingredients should we consolidate orders for this quarter?"
- Supplier quality improvement: "Flag any supplier with declining confidence scores vs. last run"
- Price arbitrage: "Find ingredients where a cheaper compliant supplier exists but isn't being used"

Workflow:
1. Read all `Consolidation_Opportunity` rows sorted by score
2. For top N opportunities, deepen the reasoning: pull latest commercial data via search if stale
3. Generate or refresh `Proposal_Text` in `Consolidation_Opportunity`
4. Output a ranked proposal report

#### 3C — Research Agents (New Supplier Discovery)
**Trigger:** On-demand or as fallback when reactive agent finds no alternatives  
**Goal:** Discover net-new suppliers not currently in `db.sqlite`

Workflow:
1. Google ADK search → "{canonical ingredient name} bulk supplier certificate NSF"
2. Browser agent → extract contact, pricing, certifications from supplier page
3. LLM → extract structured `{name, country, price_range, certifications, url}` record
4. Store in a `Discovered_Supplier` table (flagged as "unverified" until human-reviewed)

### LLM-Wiki Integration for Deterministic Reasoning

A key B2B trust requirement: users need to understand *why* the agent made a recommendation. For every high-stakes agent decision (supplier switch, consolidation proposal), the reasoning must be:
1. **Anchored** to documented criteria — not improvised each run
2. **Inspectable** — the reasoning steps are stored and queryable
3. **Consistent** — the same inputs produce equivalent reasoning across runs

We implement this via the **LLM-wiki pattern** (see `Orchestration/Data/llm-wiki.md`):

- A wiki directory at `Orchestration/Wiki/` stores LLM-maintained reasoning pages per ingredient cluster, supplier, and proposal
- When an agent reasons about a consolidation decision, it first reads the relevant wiki pages (existing context, prior decisions, known constraints) before generating a new recommendation
- After generating a recommendation, the agent updates the wiki pages to reflect the new conclusion, flagging any contradictions with prior reasoning
- This means reasoning *compounds* — the second time an agent reasons about Vitamin D3 consolidation, it starts from an already-rich context page, not from scratch
- The wiki is the persistent reasoning layer; the database is the persistent data layer

Wiki structure:
```
Orchestration/Wiki/
├── index.md              — all pages with one-line summaries
├── log.md                — append-only log of agent actions
├── ingredients/
│   └── vitamin-d3.md     — canonical identity, cluster summary, open questions
├── suppliers/
│   └── prinova-usa.md    — supplier profile, reliability signals, proposal history
└── proposals/
    └── proposal-001.md   — full evidence trail, decision rationale, human review status
```

### DAG Executor for Deterministic Agent Flows

For workflows that must be auditable (e.g., "supplier fallout → find alternative"), the agent steps are structured as a DAG (directed acyclic graph) rather than a free-form LLM loop:

```
Node 1: QueryAffectedIngredients(supplier_id) → ingredient_list
Node 2: QueryComplianceRequirements(ingredient_list) → cert_requirements  [depends on 1]
Node 3: SearchAlternativeSuppliers(ingredient_list) → candidate_list      [depends on 1]
Node 4: FilterByCertification(candidates, cert_requirements) → filtered   [depends on 2,3]
Node 5: RankByScore(filtered) → ranked_list                               [depends on 4]
Node 6: GenerateProposal(ranked_list) → proposal_text                     [depends on 5]
Node 7: UpdateWiki(proposal_text) → wiki_updated                          [depends on 6]
```

Each node's inputs, outputs, and LLM call (if any) are logged to `log.md`. The user can inspect exactly which step produced which conclusion.

### Deliverables

- [ ] `orchestration/agents/reactive_agent.py` — supplier fallout workflow
- [ ] `orchestration/agents/proactive_agent.py` — consolidation opportunity runner
- [ ] `orchestration/agents/research_agent.py` — new supplier discovery
- [ ] `orchestration/wiki/` directory initialized with `index.md` and `log.md`
- [ ] `orchestration/dag_executor.py` — simple DAG runner with step logging
- [ ] At least one full end-to-end reactive agent run documented in `Wiki/log.md`

---

## Stage 4 — Frontend & Visualization

### Goal

A lightweight, trust-oriented interface for sourcing analysts (the primary B2B user). UI polish is not the priority — reasoning transparency and decision auditability are.

### Core Views

**1 — Consolidation Dashboard**  
Table of all `Consolidation_Opportunity` rows, sortable by score. Click any row to open the full proposal view.

**2 — Proposal Detail View**  
For a given consolidation opportunity:
- Ingredient identity card (canonical name, CAS, cluster companies)
- Evidence trail (source by source, confidence per field)
- Compliance delta (certs required vs. confirmed for proposed supplier)
- Agent reasoning trace (DAG steps, wiki page links)
- Human review action: Approve / Flag / Reject with notes

**3 — Agent Execution View**  
When a reactive agent runs (e.g., supplier fallout):
- Live DAG visualization: nodes light up as they complete
- Per-node output panel: what data came in, what decision was made, what was written
- LLM call viewer: prompt sent, response received (collapsed by default, expandable)

**4 — Wiki Browser**  
Browse `Orchestration/Wiki/` pages in-app. Search by ingredient, supplier, or proposal ID. Shows last-updated timestamp and which agent last modified each page.

### Technology

TBD — could be a simple Flask/FastAPI + HTMX single-page app, or a lightweight React app. Given the hackathon context, a server-rendered approach with minimal JS is preferred. The backend reads directly from `db_enriched.sqlite` and the `Orchestration/Wiki/` directory.

### Deliverables

- [ ] Backend API: `/proposals`, `/proposals/{id}`, `/agents/{run_id}`, `/wiki/{page}`
- [ ] Consolidation dashboard view
- [ ] Proposal detail view with evidence trail
- [ ] Agent execution DAG view
- [ ] Wiki browser

---

## Cross-Cutting Concerns

### Evidence & Confidence
Every data field written by Agnes at any stage carries:
```python
{"value": ..., "source": "pubchem|dsld|agent|manual", "confidence": 0.0–1.0}
```
No silent failures. Low-confidence fields are stored with `confidence < 0.5` and `flag = "manual_review"`.

### Idempotency
Every pipeline run and agent execution is idempotent. Re-running appends/updates without destroying prior results. `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE` everywhere.

### Caching
All external API responses are cached in `db_enriched.sqlite`. All Google ADK search results and browser agent page extractions are cached by URL. Never re-fetch what's already stored.

### Rate Limiting
- PubChem: max 5 req/sec, 400 req/min
- Browser agent: minimum 1–2 second delay between requests
- Exponential backoff on HTTP 429

### No Paid Services
PubChem, DSLD, USDA FDC, RxNorm, openFDA, Molport free tier only. No Apify, ChemAnalyst, ImportGenius, or AWS Textract.

---

## Open Decisions Log

| Decision | Status | Owner | Notes |
|---|---|---|---|
| Quality/supplier scoring approach (Option A/B/C) | **Open** | — | Must decide before Phase 3 enrichers are coded |
| Frontend framework | Open | — | Flask+HTMX vs. minimal React; decide at Stage 4 start |
| Wiki storage format | Open | — | Plain markdown files vs. SQLite-backed pages |
| DAG executor library | Open | — | Custom vs. lightweight lib (e.g., `dagster`-lite, `prefect`) |

---

## File Map

```
Agnes/
├── Orchestration/
│   ├── PRDs/
│   │   ├── PRD.md                       — Full product requirements
│   │   └── meta-workflow.md             — This file
│   ├── References/                      — API integration guides (Stage 1 output)
│   ├── Wiki/                            — LLM-maintained reasoning pages (Stage 3+)
│   │   ├── index.md
│   │   ├── log.md
│   │   ├── ingredients/
│   │   ├── suppliers/
│   │   └── proposals/
│   └── Data/
│       ├── llm-wiki.md                  — LLM wiki pattern reference
│       └── Spherecast/
├── enrichment/                          — Stage 2 pipeline (Phases 1–3)
├── reasoning/                           — Stage 2 Phase 4 reasoning layer
├── orchestration/                       — Stage 3 agent workflows
│   ├── agents/
│   │   ├── reactive_agent.py
│   │   ├── proactive_agent.py
│   │   └── research_agent.py
│   └── dag_executor.py
├── frontend/                            — Stage 4
│   ├── app.py
│   └── templates/
├── schema/
│   └── enriched_schema.sql
├── db.sqlite                            — READ-ONLY source of truth
└── db_enriched.sqlite                   — All Agnes output
```
