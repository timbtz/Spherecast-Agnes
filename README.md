# Agnes — Contributor & Briefing Guide

**Project:** Spherecast Agnes  
**Type:** Hackathon MVP  
**Mission:** AI-powered supply chain intelligence for CPG supplement companies  
**Stack:** Python · SQLite · FastAPI · Claude API (Anthropic) · Google ADK · Vite + React

---

## What Is Agnes?

Agnes is an AI supply chain manager for CPG (consumer packaged goods) supplement brands. The core problem it solves: hundreds of supplement companies source the same canonical ingredients (Vitamin C, Vitamin D3, Magnesium Glycinate) from different suppliers at different prices, quality tiers, and compliance levels — but none of them know what the others are paying or who the better suppliers are.

Agnes ingests raw SKU and BOM data, enriches it against public ingredient databases and commercial APIs, scores consolidation opportunities across companies, and orchestrates AI agents to surface actionable proposals: *"12 companies in your network all buy Vitamin C. Here's a supplier switch that saves 23% and maintains NSF certification."*

The system is built in four stages:

```
Stage 1 — API Exploration & Schema Lock    [COMPLETE]
Stage 2 — Data Enrichment Pipeline         [COMPLETE through Phase 3]
Stage 3 — Agent Orchestration              [COMPLETE — FastAPI + YAML pipelines live]
Stage 4 — Frontend & Voice UI              [IN PROGRESS — Vite+React scaffolded at /ui]
```

Full workflow rationale lives in [`Orchestration/PRDs/meta-workflow.md`](Orchestration/PRDs/meta-workflow.md). Read it before writing any new Stage 3 or 4 code. Everything in this README is a summary of that document.

> **README self-maintenance rule:** After any meaningful change — phase run, new endpoint, UI feature, schema edit — update the relevant section of this file. This is a shared responsibility: every coding session that touches the repo should leave the README accurate.

---

## Repo Structure

```
Agnes/
├── .claude/                    # Claude Code skills and slash commands
│   ├── commands/               # /commit, /create-prd, /plan-feature, etc.
│   └── skills/                 # Reusable agent capabilities (browser, e2e-test)
│
├── Orchestration/              # Planning & reference artefacts (uppercase — not code)
│   ├── PRDs/                   # Product requirements; meta-workflow.md is canonical
│   ├── Plans/                  # Step-by-step execution plans for specific tasks
│   ├── References/             # Integration guides (*-guide.md) per API / tooling concern
│   │   ├── APIS/               # dsld, molport, fdc, free-apis integration guides
│   │   ├── Tech/General/       # FastAPI, SSE-streaming guides
│   │   └── Tech/Orchestration/ # ADK, YAML pipeline schema, DAG canvas, ElevenLabs refs
│   └── Data/
│       ├── llm-wiki.md         # LLM-wiki pattern (optional Stage 4 export format)
│       └── Spherecast/         # Raw Spherecast business context
│
├── enrichment/                 # Stage 2 — data pipeline (Phases 1–3)
│   ├── pipeline.py             # Entry point: python pipeline.py --phase 1|2|3
│   ├── db_bootstrap.py         # Clone db.sqlite → db_enriched.sqlite + run migration
│   ├── db_migrate_v11.py       # Idempotent v1.1 schema migration
│   ├── backfill_phase1.py      # SMILES + UNII + MatchScore backfill
│   ├── run_dedup.py            # UNII deduplication + substitution seeding
│   ├── sources/                # API clients: pubchem.py, dsld.py, molport.py, fda_iid.py, openfda.py
│   ├── normalizers/            # ingredient_normalizer.py, fuzzy_matcher.py
│   ├── parsers/                # sku_parser.py
│   └── enrichers/              # quantity_enricher.py, commercial_enricher.py, compliance_enricher.py, grade_classifier.py, role_classifier.py
│
├── reasoning/                  # Stage 2 Phase 4 — scoring, compliance, and proposals
│   ├── base.py                 # ToolResult, Tool ABC, compound_confidence()
│   ├── role_inferrer.py        # RoleInferrer, ROLE_RULES, covers_roles()
│   ├── compliance_reasoner.py  # 4-state ComplianceReasoner + JURISDICTION_PACKS (US-FDA, EU, CA, JP)
│   ├── refusal_engine.py       # RefusalEngine, CONFIDENCE_FLOOR=0.50
│   ├── consolidation_scorer.py # Formula-based opportunity scoring (129 rows)
│   ├── substitution_graph.py   # Ingredient substitution edge builder (32 edges, rapidfuzz fallback)
│   └── proposal_generator.py   # LLM proposal generation (ANTHROPIC_API_KEY set — needs running)
│
├── orchestration/              # Stage 3 — agent orchestration (LIVE)
│   ├── api/
│   │   ├── main.py             # FastAPI app; start: uvicorn orchestration.api.main:app --reload --port 8000
│   │   ├── dag_executor.py     # Topological layer executor with asyncio.gather + SSE publish
│   │   ├── pipeline_loader.py  # YAML → Pipeline/PipelineNode dataclasses; 5 pipelines
│   │   ├── conditions.py       # 6 named condition guards for YAML when: clauses
│   │   ├── db.py               # orchestration.db event log
│   │   ├── event_bus.py        # SSE event bus
│   │   ├── agent_registry.py   # Agent registration
│   │   ├── agnes_context.py    # Shared context helpers
│   │   └── routes/             # chat.py · pipelines.py · data.py · data_update.py · scoring.py
│   ├── agents/
│   │   ├── router_agent.py     # Claude Haiku chat classifier → pipeline name + params
│   │   ├── reactive_agent.py   # Supplier fallout → find alternatives
│   │   ├── proactive_agent.py  # Consolidation opportunity runner
│   │   ├── research_agent.py   # New supplier discovery
│   │   ├── proposal_writer.py  # LLM proposal generation agent
│   │   └── search_sub_agent.py # Google ADK / Gemini web search sub-agent
│   ├── tools/                  # 8 deterministic tools (no LLM)
│   │   ├── supplier_alternatives.py
│   │   ├── compliance_gate.py      # legacy binary gate (still registered)
│   │   ├── compliance_reasoner_tool.py  # 4-state gate: outcome/jurisdiction/above_floor
│   │   ├── substitution_walker.py
│   │   ├── bom_impact.py
│   │   ├── price_benchmark.py
│   │   ├── opportunity_ranker.py
│   │   └── rfq_formatter.py
│   ├── pipelines/              # YAML pipeline definitions
│   │   ├── supplier_fallout.yaml
│   │   ├── proactive_consolidation.yaml
│   │   ├── new_ingredient_research.yaml
│   │   ├── substitution_discovery.yaml
│   │   └── price_audit.yaml
│   └── ui/                     # Stage 4 — Vite + React frontend (served at /ui)
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/     # VoiceOrb, DagPanel, NodeCard, DataExplorer, PipelineBadge, tabs/
│       │   ├── hooks/          # useAgnesVoice.ts · useData.ts · useRunStream.ts
│       │   ├── store/
│       │   └── types/
│       └── dist/               # Built output (served as static files by FastAPI)
│
├── schema/
│   └── enriched_schema.sql     # v1.1 — canonical schema definition
│
├── db.sqlite                   # READ-ONLY source of truth (Spherecast raw data)
├── db_enriched.sqlite          # All Agnes enrichment output — writable
├── orchestration.db            # Orchestration event log and run state
├── requirements.txt
└── .env.template               # Copy to .env, fill in API keys
```

**Rule:** `db.sqlite` is never modified. All Agnes enrichment writes go to `db_enriched.sqlite`. Agent run state goes to `orchestration.db`.

---

## Current Database State

`db_enriched.sqlite` is at schema v1.1 with all enrichment phases run:

| Table | Rows | Notes |
|---|---|---|
| `Ingredient_Canonical` | 250 | 125 SMILES (50%), 135 UNII codes (54%), 239/250 Grade_Flag classified; 135 adverse_event_count backfilled |
| `SKU_To_Canonical` | 854 | MatchScore backfilled |
| `BOM_Component_Quantity` | 515 | 87/149 finished goods (58% coverage) |
| `Product_Compliance` | 126 | 66 products, 9 cert types |
| `Supplier_Commercial` | 0 | Stub ready — no-ops without MOLPORT_API_KEY |
| `Consolidation_Opportunity` | 123 | Scored; top: Vitamin C (25 cos, score=0.893); Proposal_Text empty (needs ANTHROPIC_API_KEY) |
| `Ingredient_Substitution` | 32 edges | Fuzzy fallback added to graph builder; 18 rules still unresolved |
| `FDA_Inactive_Ingredient` | 9,067 | From IIR_OCOMM.csv; 1,150 rows matched to canonical ingredients by UNII |
| `Scoring_Config` | 3 | Default weights: price=3.0, lead_time=3.0, quality=3.0 |

**What's blocked / what to build next:**

1. **Proposals** — `ANTHROPIC_API_KEY` is set; run `PYTHONPATH=. python3 reasoning/proposal_generator.py` to populate `Proposal_Text` for top-50 consolidation candidates.
2. **Supplier commercial data** — `MOLPORT_API_KEY` is blank; register at molport.com or seed proxy prices manually for top-10 ingredients.
3. **Voice UI** — ElevenLabs key is set (`ELEVENLABS_API_KEY`); `useAgnesVoice.ts` + `VoiceOrb.tsx` scaffold exists; test end-to-end with `pnpm dev`.

---

## Tech Stack

### Data Layer
- **SQLite** (`db_enriched.sqlite`) — all persistent enrichment data, all API cache
- **SQLite** (`orchestration.db`) — agent run state, event log, SSE source
- **Schema** defined in `schema/enriched_schema.sql` (v1.1, locked)
- Every field Agnes writes carries `source` (string) and `confidence` (float 0–1)

### Enrichment Pipeline (Stage 2 — Python)
- `enrichment/pipeline.py --phase 1|2|3` runs each phase idempotently
- Sources: PubChem (no key), DSLD (key required), Molport (key optional), USDA FDC (key optional)
- Normalizers: RapidFuzz for fuzzy ingredient matching, `sentence-transformers` for semantic fallback
- Browser: Playwright + BeautifulSoup for retailer supplement facts pages

### Orchestration API (Stage 3 — FastAPI)
- **FastAPI** (`orchestration/api/main.py`) — 8 REST + SSE endpoints
- **YAML pipelines** (`orchestration/pipelines/`) — 5 pipelines; `pipeline_loader.py` parses into DAG dataclasses
- **DAG executor** (`orchestration/api/dag_executor.py`) — topological layers, `asyncio.gather()`, per-step event log, SSE publish
- **Deterministic tools** (`orchestration/tools/`) — 8 tools (no LLM calls); compose into pipeline DAG nodes; `compliance_reasoner_tool` replaces binary `compliance_gate` in `supplier_fallout` and `substitution_discovery` pipelines
- **AI agents** (`orchestration/agents/`) — Claude-based reasoning (router, reactive, proactive, research, proposal writer); Google ADK / Gemini for web search

#### API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Natural language → router agent → pipeline trigger |
| POST | `/pipelines/run/{name}` | Direct pipeline trigger with params |
| GET | `/pipelines` | List all loaded pipeline definitions |
| GET | `/runs` | List recent agent run records |
| GET | `/runs/{id}` | Single run detail |
| GET | `/runs/{id}/stream` | SSE stream for live run events |
| GET | `/proposals` | Consolidation proposals from DB |
| POST | `/data-update` | Trigger data refresh |
| GET | `/api/data/regulatory-alerts` | FDA IID quarterly drift alerts grouped by ChangeId |
| GET | `/ui` | Serve React frontend (from `orchestration/ui/dist/` if built) |
| GET | `/health` | Health check |

### Frontend (Stage 4 — Vite + React)
- Located at `orchestration/ui/`; served at `/ui` by the FastAPI app
- Components: `VoiceOrb`, `DagPanel`, `NodeCard`, `DataExplorer`, `PipelineBadge`
- Hooks: `useAgnesVoice` (ElevenLabs voice), `useData` (REST), `useRunStream` (SSE)
- Build: `cd orchestration/ui && pnpm build` → outputs to `dist/`, auto-served by FastAPI

### Reasoning Layer (Stage 2 Phase 4)
- **Formula scoring** — `consolidation_scorer.py`: `company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15`
- **LLM adjustment** — `proposal_generator.py`: Claude adjusts top-50 scores ±0.10, writes `Proposal_Text` (ready to run)
- **Substitution graph** — `substitution_graph.py`: 32 equivalence edges; rapidfuzz fuzzy fallback for rule name resolution
- **4-state compliance** — `compliance_reasoner.py` + `refusal_engine.py`: jurisdiction-aware (US-FDA, EU, CA, JP); outcomes: pass-global / fork-recommended / human-review / refuse
- **Role inference** — `role_inferrer.py`: maps ingredient names to functional roles (lubricant, mineral-fortificant, etc.); `Function` column fully populated

---

## APIs

All keys go in `.env` (copy from `.env.template`):

| API | Key Required | What It Does | Where to Get Key | Rate Limit |
|---|---|---|---|---|
| **Anthropic Claude** | Yes | Stage 3 routing/reasoning + Stage 4 proposals | console.anthropic.com | Per-token |
| **Google ADK / Gemini** | Yes | Web search in research agent | aistudio.google.com (free) | Free tier |
| **NIH DSLD v9** | Yes | Ingredient UNII codes + BOM amounts | dsld.od.nih.gov/api-guide | Undocumented |
| **PubChem PUG REST** | No | CAS numbers, SMILES, canonical names | — | 5 req/sec, 400/min |
| **Molport v3** | No (stub) | Chemical supplier pricing | molport.com | 10k req/month |
| **USDA FoodData Central** | No (key for higher limits) | Food-grade ingredient lookup | fdc.nal.usda.gov | 1000/hr |
| **openFDA** | No (key for higher limits) | Drug/supplement adverse events | open.fda.gov | 40/min anon |
| **RxNorm** | No | Drug-class ingredient IDs | — | Undocumented |

Integration guides for each API are in `Orchestration/References/`.

**Cost note:** PubChem, DSLD, USDA FDC, RxNorm, openFDA are free. Molport free tier only. Claude API costs are limited to routing + proposal generation for top-50 consolidation candidates.

---

## Getting Started

### Setup

```bash
git clone <repo>
cd "Spherecast Agnes"
pip install -r requirements.txt
playwright install chromium          # for browser agent

cp .env.template .env
# Fill in ANTHROPIC_API_KEY, GOOGLE_API_KEY, DSLD_API_KEY at minimum
```

### Run the enrichment pipeline (already done — safe to re-run idempotently)

```bash
python enrichment/db_bootstrap.py    # Creates db_enriched.sqlite if missing
python enrichment/pipeline.py --phase 1
python enrichment/backfill_phase1.py
python enrichment/run_dedup.py
python enrichment/pipeline.py --phase 2
python enrichment/pipeline.py --phase 3
python reasoning/consolidation_scorer.py
```

### Start the orchestration API

```bash
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000
```

The FastAPI server starts at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.  
The React UI is served at `http://localhost:8000/ui` (from `orchestration/ui/dist/` if built, otherwise `orchestration/ui/`).

### Build the UI (optional — for production-like serving)

```bash
cd orchestration/ui
pnpm install
pnpm build
```

### Validate current state

```sql
-- Open db_enriched.sqlite with any SQLite client and run:

SELECT COUNT(*) AS total, SUM(CASE WHEN Confidence >= 0.65 THEN 1 END) AS resolved
FROM SKU_To_Canonical;
-- Expected: ~854 total, ~700+ resolved

SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Confidence >= 0.65;
-- Expected: 515

SELECT COUNT(DISTINCT CanonicalIngredientId) FROM Supplier_Commercial;
-- Phase 3 commercial enrichment (0 without MOLPORT_API_KEY)

SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Score IS NOT NULL;
-- Expected: 123
```

---

## How Agnes Orchestrates Agents

The key design principle: **agents must be auditable, not free-form**. For every high-stakes decision (supplier switch, consolidation proposal), the reasoning is:

1. **Anchored** to live data in `db_enriched.sqlite` — no stale pages
2. **Structured** as a YAML-defined DAG of steps with logged inputs/outputs
3. **Persistent** — conclusions are written back to the DB so the next agent run starts richer

### Pipeline Architecture

Each pipeline in `orchestration/pipelines/*.yaml` defines a directed acyclic graph of nodes. `pipeline_loader.py` deserializes these into `Pipeline`/`PipelineNode` dataclasses. `dag_executor.py` runs them in topological layers using `asyncio.gather()` for parallelism within a layer.

Each DAG node maps to either a **deterministic tool** (`orchestration/tools/`) or an **AI agent** (`orchestration/agents/`). Every node execution is logged to `orchestration.db` and streamed via SSE at `/runs/{id}/stream`.

### Example: Supplier Fallout Pipeline

```yaml
# orchestration/pipelines/supplier_fallout.yaml (simplified)
nodes:
  - id: find-alternatives
    tool_class: SupplierAlternativesTool
  - id: gate-compliance
    tool_class: ComplianceReasonerTool   # 4-state: pass-global|fork-recommended|human-review|refuse
    depends_on: [find-alternatives]
    when: has_alternatives
  - id: bom-impact
    tool_class: BomImpactTool
    depends_on: [find-alternatives]
  - id: format-rfqs
    tool_class: RfqFormatterTool
    depends_on: [gate-compliance, bom-impact]
    when: compliance_reasoner_feasible
  - id: write-proposal
    agent_class: ReactiveAgent
    depends_on: [format-rfqs, bom-impact]
```

### SQLite Reasoning Pattern

`db_enriched.sqlite` is the persistent reasoning layer. Before an agent reasons about a decision, it queries the DB for live context. After making a decision, it writes results back into existing tables and logs the run.

**Context query example (Vitamin C opportunity):**
```sql
SELECT ic.Name, ic.SMILES, ic.Grade_Flag, ic.UNII_Code,
       co.Consolidation_Score, co.Company_Count, co.Proposal_Text,
       GROUP_CONCAT(pc.Certification) AS Certs
FROM Ingredient_Canonical ic
JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
    SELECT s.ProductId FROM SKU_To_Canonical s WHERE s.CanonicalId = ic.Id
)
WHERE ic.Name = 'Vitamin C'
GROUP BY ic.Id;
```

---

## Contribution Guidelines

### Who owns what

| Area | Owner | Notes |
|---|---|---|
| Pipeline (Stage 2) | timbtz | Phases 1–3 complete; Phase 4 proposals blocked on ANTHROPIC_API_KEY |
| Supply chain scoring model | Supply chain expert | Formula weights open for revision — see `reasoning/consolidation_scorer.py` |
| Orchestration API (Stage 3) | timbtz | Live at port 8000; 5 pipelines, 8 endpoints |
| Voice UI (Stage 4) | Open | VoiceOrb + useAgnesVoice scaffold exists; ElevenLabs integration guide written |

### Supply chain expert: what you can change

The quality/compliance scoring dimensions (`reasoning/consolidation_scorer.py`) were defined with limited domain input. The current formula:

```
score = company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15
```

The weights and dimensions are open for revision. The schema has `Score_Formula_Component` and `Score_LLM_Adjustment` columns ready for a hybrid approach.

### Adding a new pipeline

1. Add `orchestration/pipelines/<name>.yaml` — define nodes, tools, and `when:` conditions
2. Available tools: `supplier_alternatives`, `compliance_gate`, `compliance_reasoner_tool`, `substitution_walker`, `bom_impact`, `price_benchmark`, `opportunity_ranker`, `rfq_formatter`
3. Available conditions: see `orchestration/api/conditions.py` (7 named guards incl. `compliance_reasoner_feasible`)
4. Test via `POST /pipelines/run/<name>` with params JSON
5. Update the pipeline list in the CLAUDE.md Orchestration Layer table

### Adding a new API or data source

1. Add the client to `enrichment/sources/<api_name>.py`
2. Add a guide to `Orchestration/References/<api_name>-integration-guide.md`
3. Wire it into the appropriate enricher in `enrichment/enrichers/`
4. Add the key to `.env.template` and update the API table above
5. Update `CLAUDE.md` Current State table and this README's DB State table

---

## Key Files to Read First

1. [`Orchestration/PRDs/meta-workflow.md`](Orchestration/PRDs/meta-workflow.md) — four-stage implementation plan, agent architecture, open decisions
2. [`CLAUDE.md`](CLAUDE.md) — live current state: what's run, what's broken, what's blocked
3. [`schema/enriched_schema.sql`](schema/enriched_schema.sql) — locked v1.1 schema; understand this before writing any SQL
4. [`Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md`](Orchestration/References/Tech/Orchestration/REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md) — full voice pipeline integration guide (STT → /chat → SSE → TTS)
5. [`Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md`](Orchestration/References/Tech/Orchestration/REF-YAML-PIPELINE-SCHEMA.md) — YAML pipeline node schema reference

---

## Design Principles

- **Evidence everywhere.** Every Agnes-written field has `source` and `confidence`. No silent failures.
- **Idempotent always.** Every pipeline run and agent execution is safe to repeat. `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE` everywhere.
- **Cache first.** All external API responses are cached in `db_enriched.sqlite`. Never re-fetch what's stored.
- **No paid services.** Free tiers only. No Apify, no ChemAnalyst, no ImportGenius.
- **Auditable reasoning.** Every agent decision is traceable to its DAG steps in `orchestration.db`. The user can always ask "why did Agnes recommend this?"
- **Pricing disclaimer.** Molport pricing is research/lab scale. Always include in proposals: *"pricing indicative at research quantities — production volume requires direct negotiation."*
