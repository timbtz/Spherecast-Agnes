# Agnes — AI Supply Chain Intelligence for CPG Supplements

**Project:** Spherecast Agnes  
**Stack:** Python · SQLite · FastAPI · Claude API (Anthropic) · Google ADK (Gemini) · Vite + React

---

## What Agnes Does

Agnes is an AI supply chain manager for CPG supplement brands. The core problem: hundreds of supplement companies source the same canonical ingredients (Vitamin C, Vitamin D3, Magnesium Glycinate) from overlapping supplier pools at wildly different prices, quality tiers, and compliance levels — with no cross-company visibility.

Agnes ingests raw SKU and BOM data, enriches it against six public databases and commercial APIs, scores consolidation opportunities across all companies simultaneously, and dispatches AI agent pipelines to surface actionable proposals:

> *"12 companies in your network all buy Vitamin C. Switching to DSM (USP-certified, NL origin) saves 23% vs. your current supplier and maintains NSF certification. GLEIF-verified legal entity. RFQ formatted."*

Every recommendation is anchored to live enriched data, runs through a 4-state compliance gate across four jurisdictions, and is fully traceable via a structured event log.

---

## Architecture

Agnes is built in four stages, all complete and running:

```
Stage 1 — API Exploration & Schema Design     [complete]
Stage 2 — Data Enrichment Pipeline            [complete — all phases run]
Stage 3 — Agent Orchestration                 [complete — FastAPI + 7 YAML pipelines live]
Stage 4 — Voice + Chat UI                     [complete — React UI served at /]
```

### How it fits together

```
User message (voice/text)
        │
        ▼
┌──────────────────┐
│  Router Agent    │  Gemini 2.5-flash intent classifier
│  (compound-intent│  → primary pipeline + secondary_intents[]
│   aware)         │  → prefilter for injection attempts
└────────┬─────────┘
         │ pipeline name + params
         ▼
┌──────────────────────────────────────────────────────┐
│  DAG Executor   (dag_executor.py)                    │
│  • Topological sort → parallel layers (asyncio)      │
│  • Condition guards (14 named: when: clauses)        │
│  • Every node logged to orchestration.db             │
│  • Real-time SSE stream at /runs/{id}/stream         │
└──────┬───────────────────────────────────────────────┘
       │
  ┌────┴──────────────────────────────┐
  │                                   │
  ▼                                   ▼
Deterministic Tools (14)         AI Agents (8)
supplier_alternatives            ReactiveAgent      (Claude)
substitution_walker              ProactiveAgent     (Claude)
compliance_reasoner_tool         ResearchAgent      (Claude + Gemini web)
bom_impact                       ProposalWriter     (Claude)
price_benchmark                  PriceFetchAgent    (Gemini web search)
opportunity_ranker               PriceAlertWriter   (Gemini)
rfq_formatter                    RegulatoryDriftAgent (Gemini)
entity_verify (GLEIF)            RegulatoryResearchAgent (Gemini)
regulatory_drift_tool
price_staleness_checker
no_data_explainer
no_opportunity_explainer
_ingredient_resolver (shared)
       │
       ▼
┌──────────────────┐
│  db_enriched     │  SQLite — persistent enrichment + reasoning layer
│  .sqlite         │  Every Agnes-written field has source + confidence
└──────────────────┘
```

---

## Repo Structure

```
Agnes/
├── Orchestration/              # Planning & reference artefacts (uppercase — not code)
│   ├── PRDs/                   # Product requirements; meta-workflow.md is canonical
│   ├── Plans/                  # Step-by-step execution plans per task
│   ├── References/             # Integration guides per API / tooling concern
│   └── Data/
│       ├── supplier_wiki/      # Grade scoring context: supplements.md, excipients.md, food.md
│       └── Spherecast/         # Raw Spherecast business context
│
├── enrichment/                 # Stage 2 — data pipeline (Phases 1–4)
│   ├── pipeline.py             # Entry point: python pipeline.py --phase 1|2|3
│   ├── db_bootstrap.py         # Clone db.sqlite → db_enriched.sqlite + migrate
│   ├── db_migrate_v11.py       # Idempotent v1.1 schema migration
│   ├── backfill_phase1.py      # SMILES + UNII + MatchScore backfill (PubChem)
│   ├── backfill_openfda.py     # Adverse event counts from openFDA
│   ├── backfill_supplier_curated.py  # Curated bulk pricing (239/250 ingredients covered)
│   ├── run_dedup.py            # UNII-based deduplication + substitution seeding
│   ├── sources/                # pubchem.py, dsld.py, molport.py, fda_iid.py, openfda.py
│   ├── normalizers/            # ingredient_normalizer.py, fuzzy_matcher.py
│   ├── parsers/                # sku_parser.py
│   └── enrichers/              # quantity_enricher.py, commercial_enricher.py,
│                               # compliance_enricher.py, grade_classifier.py,
│                               # role_classifier.py, supplier_web_enricher.py
│
├── reasoning/                  # Stage 2 Phase 4 — scoring and proposals
│   ├── base.py                 # ToolResult, Tool ABC, compound_confidence()
│   ├── role_inferrer.py        # ROLE_RULES — maps ingredient names to functional roles
│   ├── compliance_reasoner.py  # 4-state gate + JURISDICTION_PACKS (US-FDA, EU, CA, JP)
│   ├── refusal_engine.py       # RefusalEngine — CONFIDENCE_FLOOR=0.50
│   ├── consolidation_scorer.py # Formula scoring: 129 opportunities ranked
│   ├── substitution_graph.py   # Substitution edges (32 edges, rapidfuzz fallback)
│   └── proposal_generator.py   # Claude-based proposal generation (14 proposals written)
│
├── orchestration/              # Stage 3 — agent orchestration (live)
│   ├── api/
│   │   ├── main.py             # FastAPI; uvicorn orchestration.api.main:app --port 8000
│   │   ├── dag_executor.py     # Topological layer executor — asyncio.gather + SSE
│   │   ├── pipeline_loader.py  # YAML → Pipeline/PipelineNode dataclasses
│   │   ├── conditions.py       # 14 named condition guards for YAML when: clauses
│   │   ├── db.py               # orchestration.db event log
│   │   ├── event_bus.py        # SSE publish/subscribe
│   │   ├── agent_registry.py   # 14 tools + 8 agents registered
│   │   ├── agnes_context.py    # Shared run context passed through every DAG node
│   │   └── routes/             # chat · pipelines · data · data_update · scoring · alerts
│   ├── agents/
│   │   ├── router_agent.py     # Gemini 2.5-flash compound-intent classifier
│   │   ├── reactive_agent.py   # Supplier fallout → alternatives + proposal
│   │   ├── proactive_agent.py  # Portfolio consolidation scan
│   │   ├── research_agent.py   # New supplier discovery (web search)
│   │   ├── proposal_writer.py  # Claude narrative proposal generation
│   │   ├── price_fetch_agent.py        # Gemini web search → price updates
│   │   ├── price_alert_writer.py       # Gemini → price alert narratives
│   │   ├── regulatory_research_agent.py # FDA quarterly change log downloader
│   │   ├── regulatory_drift_agent.py    # Drift narrative + DB flag writer
│   │   └── search_sub_agent.py         # Google ADK web search sub-agent
│   ├── tools/                  # 14 deterministic tools (no LLM calls)
│   │   ├── supplier_alternatives.py    # 3-stage ingredient resolution + supplier lookup
│   │   ├── compliance_reasoner_tool.py # 4-state compliance gate (persists to Refusal_Log)
│   │   ├── substitution_walker.py      # Walk substitution graph from seed ingredient
│   │   ├── bom_impact.py               # BOM exposure calculation for supplier change
│   │   ├── price_benchmark.py          # Market price benchmarking
│   │   ├── opportunity_ranker.py       # Score-ranked consolidation opportunity list
│   │   ├── rfq_formatter.py            # RFQ drafts for top alternative suppliers
│   │   ├── entity_verify.py            # GLEIF LEI lookup — supplier legal entity KYC
│   │   ├── regulatory_drift_tool.py    # FDA IID quarterly drift detection + severity
│   │   ├── price_staleness_checker.py  # Portfolio-wide stale price detection
│   │   ├── no_data_explainer.py        # Graceful fallback when substitutes not found
│   │   ├── no_opportunity_explainer.py # Graceful fallback when no opportunities found
│   │   └── _ingredient_resolver.py     # Shared 3-stage resolver (exact→synonyms→fuzzy)
│   ├── pipelines/              # 7 YAML pipeline definitions
│   │   ├── supplier_fallout.yaml
│   │   ├── proactive_consolidation.yaml
│   │   ├── substitution_discovery.yaml
│   │   ├── new_ingredient_research.yaml
│   │   ├── price_audit.yaml
│   │   ├── price_monitor.yaml
│   │   └── regulatory_drift_alert.yaml
│   └── ui/                     # Stage 4 — React UI (served at / by FastAPI)
│       ├── src/
│       │   ├── components/     # VoiceOrb (ElevenLabs WebGL), DagGraphView, SuppliersView,
│       │   │                   # ComplianceView, RegulatoryAlertsView, TradeRoutesView, ...
│       │   ├── hooks/          # useAgnes, useAgnesVoice, usePriceAlerts, useRunStream, ...
│       │   ├── store/          # agnesStore (Zustand) — run state, compound intent fan-out
│       │   └── types/          # agnes.ts — full typed API surface
│       └── dist/               # Built output served as SPA by FastAPI
│
├── schema/
│   └── enriched_schema.sql     # v1.1 — canonical schema definition (locked)
│
├── db.sqlite                   # READ-ONLY source of truth (Spherecast raw data, immutable)
├── db_enriched.sqlite          # All enrichment output — writable
├── orchestration.db            # Agent run event log and SSE source
├── requirements.txt
└── .env.template               # Copy to .env; fill in API keys
```

**Rule:** `db.sqlite` is never modified. All Agnes enrichment writes to `db_enriched.sqlite`. Agent run state goes to `orchestration.db`.

---

## Current Database State

`db_enriched.sqlite` at schema v1.1 with all enrichment phases complete:

| Table | Rows | Notes |
|---|---|---|
| `Ingredient_Canonical` | 250 | 125 SMILES (50%), 135 UNII codes (54%), 239/250 Grade_Flag classified, 135 adverse event counts, 177 Function roles populated |
| `SKU_To_Canonical` | 854 | MatchScore backfilled; ≥700 resolved at confidence ≥0.65 |
| `BOM_Component_Quantity` | 515 | 87/149 finished goods (58% coverage) |
| `Product_Compliance` | 126 | 66 products, 9 cert types (NSF, USP, Informed-Sport, ...) |
| `Supplier_Commercial` | 239 | 95.6% ingredient coverage; curated pricing + web-enriched |
| `Consolidation_Opportunity` | 129 | Scored; top: Vitamin C (25 cos, score=0.893); 14 proposals written |
| `Claim_Citation` | 112 | Citations extracted from proposals (Claude Haiku) |
| `Refusal_Log` | 4+ | Demo trap refusals seeded; live refusals appended per run |
| `Ingredient_Substitution` | 32 edges | Fuzzy fallback in graph builder; 18 rules still unresolved |
| `Ingredient_Substitution_Rule` | 38 | Raw rules; 20 aliases resolved via fix_substitution_rules.py |
| `FDA_Inactive_Ingredient` | 9,067 | From IIR_OCOMM.csv; 1,150 matched to canonicals by UNII |
| `FDA_IID_Change_Log` | 187 | Quarterly change log; 27 matched canonicals; 4 HIGH-severity drift flags |
| `Price_Change_Alert` | — | Written by price_fetch_agent when ≥15% price change detected |
| `Supplier_Master` | — | GLEIF LEI cache (30-day TTL); populated by entity_verify tool |
| `Scoring_Config` | 3 | Default weights: price=3.0, lead_time=3.0, quality=3.0 |

---

## Tech Stack

### Data Layer
- **SQLite** (`db_enriched.sqlite`) — all persistent enrichment data, all API response cache
- **SQLite** (`orchestration.db`) — agent run event log, SSE source of truth
- **Schema** in `schema/enriched_schema.sql` (v1.1, locked)
- Every Agnes-written field carries `source` (string) and `confidence` (float 0–1)

### Enrichment Pipeline (Stage 2 — Python)
- `enrichment/pipeline.py --phase 1|2|3` — idempotent; safe to re-run; cache hit rate ≥90% on second run
- **Phase 1 — Ingredient Identity:** PubChem PUG REST (CAS, SMILES, UNII), DSLD v9, USDA FDC; RapidFuzz + sentence-transformers for name normalization; UNII-based deduplication with CAS-differs guard
- **Phase 2 — BOM Quantities:** DSLD BOM amounts; fingerprint matching (brand+ingredient query, ≥2 overlap)
- **Phase 3 — Commercial & Compliance:** Molport v3 supplier catalogue (stub + 1.65 GB local SMILES index); compliance enricher (9 cert types); openFDA adverse event counts
- **Phase 4 — Scoring & Proposals:** Formula-based consolidation scoring (129 rows); substitution graph with rapidfuzz fallback; Claude-based proposal generation (top-50 candidates)

### Orchestration Engine (Stage 3 — FastAPI)
- **FastAPI** with CORS + SPA fallback; background `price_monitor` scheduler (every 24h)
- **YAML pipelines** — 7 declarative pipeline definitions; `pipeline_loader.py` parses into typed dataclasses
- **DAG executor** — Kahn's topological sort, `asyncio.gather()` parallelism within layers, per-node event logging, SSE publish on every state change
- **14 deterministic tools** — no LLM calls; compose into pipeline nodes; results are structured, typed dicts
- **8 AI agents** — Claude (Anthropic API) for reasoning/proposals; Gemini 2.5-flash (Google ADK) for routing, web search, and price/regulatory narratives

### Reasoning Cross-References
Agnes agents cross-reference multiple enrichment layers before reaching a conclusion:

| Decision | Cross-references |
|---|---|
| Supplier switch recommendation | `Supplier_Commercial` (price/lead) + `Product_Compliance` (certs) + `BOM_Component_Quantity` (exposure) + `Supplier_Master` (GLEIF legal entity) |
| Substitution proposal | `Ingredient_Substitution` graph + `Ingredient_Canonical` (SMILES/grade) + `FDA_Inactive_Ingredient` (max daily dose/routes) + compliance gate |
| Consolidation opportunity | `Consolidation_Opportunity` (formula score) + `SKU_To_Canonical` (company spread) + `Ingredient_Canonical` (function/grade) + `Scoring_Config` (weights) |
| Regulatory drift alert | `FDA_IID_Change_Log` (before/after MDE) + `Ingredient_Canonical` (UNII match) + `Consolidation_Opportunity` (flags affected rows) |
| Refusal | `Refusal_Log` (prior decisions) + `compliance_reasoner` (jurisdiction pack) + `RefusalEngine` (CONFIDENCE_FLOOR=0.50) |

### Compliance Reasoning (4-state gate)
`compliance_reasoner_tool.py` implements jurisdiction-aware compliance evaluation:

```
pass-global         — no restrictions across all jurisdictions
fork-recommended    — compliant in primary, restrictions elsewhere; propose jurisdiction split
human-review        — confidence below floor or conflicting signals; escalate
refuse              — ingredient banned or exceeds FDA IID max daily dose; log to Refusal_Log
```

Jurisdiction packs: US-FDA, EU, CA (Canada), JP (Japan). Results persisted to `Refusal_Log` so repeat queries are consistent.

### API Endpoints (17 total)

| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Natural language → router → pipeline trigger; returns `secondary_runs[]` for compound intents |
| GET | `/runs` | List recent agent run records |
| GET | `/runs/{id}` | Single run detail with node outputs |
| GET | `/runs/{id}/stream` | SSE stream — live `node_started/completed/skipped/failed` events |
| POST | `/pipelines/run/{name}` | Direct pipeline trigger with params JSON |
| GET | `/pipelines` | List all loaded pipeline definitions |
| GET | `/api/data/opportunities` | Scored consolidation opportunities |
| GET | `/api/data/ingredients` | Canonical ingredient list with enrichment fields |
| GET | `/api/data/suppliers` | Supplier commercial data with provenance + GLEIF fields |
| GET | `/api/data/compliance` | Product compliance records |
| GET | `/api/data/proposals` | Written consolidation proposals |
| GET | `/api/data/proposals/{id}/citations` | Citations for a specific proposal |
| GET | `/api/data/refusals` | Refusal log entries |
| GET | `/api/data/regulatory-alerts` | FDA IID quarterly drift alerts grouped by ChangeId |
| GET | `/api/alerts/count` | Price alert count (polled by UI every 60s) |
| POST | `/api/data-update` | Trigger proactive_consolidation pipeline |
| GET | `/health` | Health check |
| GET | `/api/scoring/weights` | Current scoring dimension weights |
| POST | `/api/scoring/weights` | Update scoring weights |
| GET | `/api/scoring/suppliers/{id}` | Scored supplier ranking for an ingredient |

### Frontend (Stage 4 — React + ElevenLabs)
- Located at `orchestration/ui/` (git subtree from `timbtz/agnes-ai-navigator`); served as SPA at `/`
- Built with Vite + React + TypeScript + Tailwind; state via Zustand
- **Voice:** ElevenLabs WebGL orb component; WebGL failure renders CSS gradient fallback; STT → `/chat` → SSE → TTS pipeline
- **Views:** Suppliers (7-col grid with Trust column: GLEIF vetted stamp, provenance badge, URL health, corroboration score), Compliance (search + filter + cert derivation tooltip), Regulatory Alerts (severity-filtered with before/after MDE snapshot), Trade Routes (lane table with mode icons + Landed Cost Index), DAG canvas (live node execution with collapsible output panels)
- **Compound intent:** `useAgnes` subscribes to each SSE stream in `secondary_runs[]`; store tracks fan-out runs; UI shows `+N more` pill when parallel pipelines are active
- Build: `cd orchestration/ui && bun run build`; update from Lovable: `./pull-ui.sh`

---

## APIs

All keys in `.env` (copy from `.env.template`):

| API | Key Required | What It Does | Rate Limit |
|---|---|---|---|
| **Anthropic Claude** | Yes | Agent reasoning, proposal generation, compliance analysis | Per-token |
| **Google ADK / Gemini** | Yes | Intent routing (2.5-flash), web search, price/regulatory narratives | Free tier |
| **NIH DSLD v9** | Yes | Ingredient UNII codes + BOM amounts | Undocumented |
| **PubChem PUG REST** | No | CAS numbers, SMILES, canonical names, UNII synonyms | 5 req/sec, 400/min |
| **openFDA** | No | Adverse event counts, drug/supplement label search | 40/min anon |
| **GLEIF LEI API** | No | Supplier legal entity verification (30-day cache) | Free, undocumented |
| **Molport v3** | No (stub) | Chemical supplier catalogue + pricing | 10k req/month |
| **USDA FoodData Central** | No | Food-grade ingredient lookup (5 food macros) | 1000/hr |
| **RxNorm** | No | Drug-class ingredient IDs (deferred — narrow dataset coverage) | Undocumented |

All API responses are cached in `db_enriched.sqlite`. No external call is made if a cached result is present.

---

## Getting Started

### Setup

```bash
git clone <repo>
cd "Spherecast Agnes"
pip install -r requirements.txt

cp .env.template .env
# Fill in ANTHROPIC_API_KEY, GOOGLE_API_KEY, DSLD_API_KEY at minimum
```

### Run the enrichment pipeline

All phases are already run against the included `db_enriched.sqlite`. Re-running is idempotent:

```bash
python enrichment/db_bootstrap.py    # creates db_enriched.sqlite if missing
python enrichment/pipeline.py --phase 1
python enrichment/backfill_phase1.py
python enrichment/run_dedup.py
python enrichment/pipeline.py --phase 2
python enrichment/pipeline.py --phase 3
python reasoning/consolidation_scorer.py
python reasoning/proposal_generator.py  # generates Proposal_Text for top-50 candidates
```

### Start the orchestration API

```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
```

FastAPI at `http://localhost:8000`. Swagger docs at `/docs`. React UI at `/`.

### Build the UI

```bash
cd orchestration/ui
bun install
bun run build
```

To pull the latest Lovable build: `./pull-ui.sh`

### Validate enrichment state

```sql
-- Open db_enriched.sqlite in any SQLite client:

SELECT COUNT(*) AS total, SUM(CASE WHEN Confidence >= 0.65 THEN 1 END) AS resolved
FROM SKU_To_Canonical;
-- Expected: ~854 total, ~700+ resolved

SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Confidence >= 0.65;
-- Expected: 515

SELECT COUNT(DISTINCT CanonicalIngredientId) FROM Supplier_Commercial;
-- Expected: 239

SELECT Name, Company_Count, Score FROM Consolidation_Opportunity
ORDER BY Score DESC LIMIT 5;
-- Expected: Vitamin C at top (25 companies, score=0.893)
```

---

## How Agnes Reasons

The key design principle: **decisions must be auditable, not free-form.** For every recommendation:

1. **Anchored** to live enriched data in `db_enriched.sqlite` — no stale context
2. **Structured** as a YAML-defined DAG of steps with logged inputs and outputs
3. **Cross-referenced** — tools pull from multiple enrichment layers before passing context to agents
4. **Persistent** — conclusions write back to the DB so the next agent run starts richer

### Pipeline Execution Example: Supplier Fallout

```yaml
# orchestration/pipelines/supplier_fallout.yaml (simplified)
nodes:
  - id: find-alternatives
    tool_class: SupplierAlternativesTool     # 3-stage name resolution → DB lookup
  - id: web-research
    agent_class: ResearchAgent              # Gemini web search for recent supplier news
    depends_on: [find-alternatives]
    when: has_alternatives
  - id: verify-entity
    tool_class: EntityVerifyTool            # GLEIF LEI lookup → vetted/legal_name
    depends_on: [find-alternatives]
    when: has_alternatives
  - id: gate-compliance
    tool_class: ComplianceReasonerTool      # 4-state: pass-global|fork|human-review|refuse
    depends_on: [find-alternatives]
    when: has_alternatives
  - id: bom-impact
    tool_class: BomImpactTool               # BOM exposure across all affected products
    depends_on: [find-alternatives]
  - id: format-rfqs
    tool_class: RfqFormatterTool            # Draft RFQs for top 3 alternatives
    depends_on: [gate-compliance, bom-impact]
    when: compliance_reasoner_feasible
  - id: write-proposal
    agent_class: ReactiveAgent              # Claude narrative: context → recommendation
    depends_on: [format-rfqs, verify-entity, bom-impact]
```

`find-alternatives`, `verify-entity`, `gate-compliance`, and `bom-impact` run in parallel (same topological layer). The proposal writer receives all their outputs merged into `AgnesContext.node_outputs`.

### Compound Intent Routing

The router agent handles multi-intent queries:

> *"Our Magnesium supplier fell through AND I want to check if we're overpaying on Vitamin D3"*

Returns:
```json
{
  "pipeline": "supplier_fallout",
  "params": {"ingredient_name": "Magnesium"},
  "secondary_intents": [
    {"pipeline": "price_audit", "params": {"ingredient_name": "Vitamin D3"}}
  ]
}
```

The `/chat` endpoint fans out to parallel pipeline executions. The UI subscribes to each SSE stream independently.

### Ingredient Resolution (3-stage)

`_ingredient_resolver.py` is the shared utility used by `supplier_alternatives` and `substitution_walker`:

1. **Exact match** — direct `Name` or `CAS_Number` lookup in `Ingredient_Canonical`
2. **Synonym table** — 80+ curated aliases (`"vitamin d3"` → `"Cholecalciferol"`, `"MCC"` → `"Microcrystalline Cellulose"`)
3. **Fuzzy match** — RapidFuzz `token_set_ratio ≥ 85` across all canonical names

Without this, partial names and trade names would fail silently. With it, user queries like `"vit c"` or `"mag stearate"` resolve correctly.

---

## Design Principles

- **Evidence everywhere.** Every Agnes-written field has `source` and `confidence`. No silent failures.
- **Idempotent always.** Every pipeline and enrichment script is safe to re-run. `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE` throughout.
- **Cache first.** All external API responses are cached in `db_enriched.sqlite`. Never re-fetch what's stored.
- **Free services where possible.** PubChem, DSLD, USDA FDC, RxNorm, openFDA, GLEIF are all free. Molport free tier only. Claude API costs limited to proposal generation for top-50 candidates.
- **Auditable reasoning.** Every agent decision is traceable to its DAG steps in `orchestration.db`. The user can always ask "why did Agnes recommend this?"
- **Graceful degradation.** Every pipeline has fallback nodes (`no_data_explainer`, `no_opportunity_explainer`) for empty results. GLEIF lookups cache for 30 days. Molport stub no-ops cleanly when key is absent.
- **Pricing disclaimer.** Molport and web-sourced pricing is at research/lab scale. Agnes always includes in proposals: *"pricing indicative at research quantities — production volume requires direct negotiation."*

---

## Contributing

### Who owns what

| Area | Owner | Notes |
|---|---|---|
| Enrichment pipeline (Stage 2) | timbtz | All phases complete; idempotent re-run safe |
| Scoring model weights | Supply chain expert | Formula open for revision — `reasoning/consolidation_scorer.py` |
| Orchestration API (Stage 3) | timbtz | 7 pipelines, 17 endpoints live |
| Voice + Chat UI (Stage 4) | timbtz | Lovable-managed; sync via `./pull-ui.sh` |

### Scoring formula

```
score = company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15
```

Weights are open for revision. `Scoring_Config` table and `/api/scoring/weights` endpoint support runtime weight updates without code changes. `Score_LLM_Adjustment` column (±0.10) is written by `proposal_generator.py` for the top-50 candidates.

### Adding a new pipeline

1. Add `orchestration/pipelines/<name>.yaml` — declare nodes, tools, `when:` conditions
2. Available tools: see `orchestration/tools/` (14 total)
3. Available conditions: see `orchestration/api/conditions.py` (14 named guards)
4. Test via `POST /pipelines/run/<name>` with params JSON
5. Register the pipeline name in `router_agent.py` `_VALID_PIPELINES` and `_SYSTEM` prompt
6. Update CLAUDE.md

### Adding a new data source

1. Add client to `enrichment/sources/<name>.py`
2. Add integration guide to `Orchestration/References/<name>-integration-guide.md`
3. Wire into enricher in `enrichment/enrichers/`
4. Add key to `.env.template`
5. Update the API table above and CLAUDE.md

---

## Key Files to Read First

1. [`Orchestration/PRDs/meta-workflow.md`](Orchestration/PRDs/meta-workflow.md) — four-stage plan, agent architecture, open decisions
2. [`CLAUDE.md`](CLAUDE.md) — live current state: every component, every known limit
3. [`schema/enriched_schema.sql`](schema/enriched_schema.sql) — v1.1 locked schema; read before writing any SQL
4. [`Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md`](Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md) — pipeline node schema reference
5. [`Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md`](Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md) — full voice pipeline: STT → /chat → SSE → TTS
