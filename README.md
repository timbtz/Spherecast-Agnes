# Agnes — Contributor & Briefing Guide

**Project:** Spherecast Agnes  
**Type:** Hackathon MVP  
**Mission:** AI-powered supply chain intelligence for CPG supplement companies  
**Stack:** Python · SQLite · Claude API (Anthropic) · Google ADK · Playwright

---

## What Is Agnes?

Agnes is an AI supply chain manager for CPG (consumer packaged goods) supplement brands. The core problem it solves: hundreds of supplement companies source the same canonical ingredients (Vitamin C, Vitamin D3, Magnesium Glycinate) from different suppliers at different prices, quality tiers, and compliance levels — but none of them know what the others are paying or who the better suppliers are.

Agnes ingests raw SKU and BOM data, enriches it against public ingredient databases and commercial APIs, scores consolidation opportunities across companies, and orchestrates AI agents to surface actionable proposals: *"12 companies in your network all buy Vitamin C. Here's a supplier switch that saves 23% and maintains NSF certification."*

The system is built in four stages:

```
Stage 1 — API Exploration & Schema Lock    [COMPLETE]
Stage 2 — Data Enrichment Pipeline         [COMPLETE through Phase 3]
Stage 3 — Agent Orchestration (Google ADK) [NEXT — open for contributors]
Stage 4 — Frontend & Visualization         [OPEN]
```

Full workflow rationale lives in [`Orchestration/PRDs/meta-workflow.md`](Orchestration/PRDs/meta-workflow.md). Read it before writing any new Stage 3 or 4 code. Everything in this README is a summary of that document.

---

## Repo Structure

```
Agnes/
├── .claude/                    # Claude Code skills and slash commands
│   ├── commands/               # /commit, /create-prd, /plan-feature, etc.
│   └── skills/                 # Reusable agent capabilities (browser, e2e-test)
│
├── Orchestration/
│   ├── PRDs/                   # Product requirements (messy storage — no strict order)
│   │   ├── PRD.md              # Full product requirements document
│   │   ├── SQLBackendPRD.md    # Backend stabilization PRD (v1.1 schema work)
│   │   └── meta-workflow.md    # HOW WE WORK — read this first
│   ├── Plans/                  # Step-by-step execution plans for specific tasks
│   ├── References/             # Integration guide documents (*-guide.md)
│   │   ├── dsld-integration-guide.md
│   │   ├── google-adk-search-guide.md
│   │   ├── molport-integration-guide.md
│   │   ├── claude-api-patterns-guide.md
│   │   ├── browser-automation-guide.md
│   │   └── ...                 # One guide per API or tooling concern
│   └── Data/
│       ├── llm-wiki.md         # LLM-wiki pattern (reference only — not on critical path)
│       └── Spherecast/         # Raw Spherecast business context
│
├── enrichment/                 # Stage 2 — data pipeline (Phases 1–3)
│   ├── pipeline.py             # Entry point: python pipeline.py --phase 1|2|3
│   ├── db_bootstrap.py         # Clone db.sqlite → db_enriched.sqlite + run migration
│   ├── db_migrate_v11.py       # Idempotent v1.1 schema migration
│   ├── backfill_phase1.py      # SMILES + UNII + MatchScore backfill
│   ├── run_dedup.py            # UNII deduplication + substitution seeding
│   ├── sources/                # API clients: pubchem.py, dsld.py, molport.py
│   ├── normalizers/            # ingredient_normalizer.py, fuzzy_matcher.py
│   ├── parsers/                # sku_parser.py
│   └── enrichers/              # quantity_enricher.py, commercial_enricher.py, compliance_enricher.py
│
├── reasoning/                  # Stage 2 Phase 4 — scoring and proposals
│   ├── consolidation_scorer.py # Formula-based opportunity scoring (129 rows)
│   ├── substitution_graph.py   # Ingredient substitution edge builder
│   └── proposal_generator.py   # LLM proposal generation (needs ANTHROPIC_API_KEY)
│
├── orchestration/              # Stage 3 — agent workflows (TO BUILD)
│   ├── agents/
│   │   ├── reactive_agent.py   # Supplier fallout → find alternative
│   │   ├── proactive_agent.py  # Consolidation opportunity runner
│   │   └── research_agent.py   # New supplier discovery
│   └── dag_executor.py         # DAG runner with per-step logging
│
├── frontend/                   # Stage 4 — UI (TO BUILD)
│
├── schema/
│   └── enriched_schema.sql     # v1.1 — canonical schema definition
│
├── db.sqlite                   # READ-ONLY source of truth (Spherecast raw data)
├── db_enriched.sqlite          # All Agnes output — writable
├── requirements.txt
├── .env.template               # Copy to .env, fill in API keys
└── CLAUDE.md                   # Agent self-maintained state log (current run status)
```

**Rule:** `db.sqlite` is never modified. All Agnes writes go to `db_enriched.sqlite`.

---

## Current Database State

`db_enriched.sqlite` is at schema v1.1 with all enrichment phases run:

| Table | Rows | Notes |
|---|---|---|
| `SKU_To_Canonical` | 854 | MatchScore backfilled |
| `Ingredient_Canonical` | ~180 | 112 SMILES, 44 UNII codes |
| `BOM_Component_Quantity` | 515 | 87/149 finished goods (58% coverage) |
| `Product_Compliance` | 126 | 66 products, 9 cert types |
| `Supplier_Commercial` | ~40 | Via Molport stub (no-ops without MOLPORT_API_KEY) |
| `Consolidation_Opportunity` | 129 | Scored; top: Vitamin C (25 cos, score=0.893) |
| `Ingredient_Substitution` | 4 edges | 38/40 rules skipped due to name mismatch — needs fix |

**What's missing / what to build next:**

1. **SQL Backend cleanup** — see [`Orchestration/Plans/4sql-backend-completion-phase2.md`](Orchestration/Plans/4sql-backend-completion-phase2.md) for the exact task list. Key gaps: `Ingredient_Substitution_Rule` names need to match canonical names exactly; consolidation scorer produces formula scores but `Proposal_Text` is empty (needs `ANTHROPIC_API_KEY`).

2. **Stage 3 agents** — none of `orchestration/agents/` exists yet. This is the core work for the hackathon.

3. **Agent_Log table** — already in schema. Agents write one row per DAG node; the log is queryable SQLite, not a markdown file.

---

## Tech Stack

### Data Layer
- **SQLite** (`db_enriched.sqlite`) — all persistent data, all agent output, all API cache
- **Schema** defined in `schema/enriched_schema.sql` (v1.1, locked)
- Every field Agnes writes carries `source` (string) and `confidence` (float 0–1)

### Enrichment Pipeline (Stage 2 — Python)
- `enrichment/pipeline.py --phase 1|2|3` runs each phase idempotently
- Sources: PubChem (no key), DSLD (key required), Molport (key optional), USDA FDC (key optional)
- Normalizers: RapidFuzz for fuzzy ingredient matching, `sentence-transformers` for semantic fallback
- Browser: Playwright + BeautifulSoup for retailer supplement facts pages

### Agent Layer (Stage 3 — Google ADK + Claude)
- **Google ADK** (`google-adk`) — web search via Gemini 2.5 Flash; handles search + browser tool use
- **Claude API** (`anthropic`) — reasoning, proposal generation, structured data extraction
- **DAG executor** (`orchestration/dag_executor.py` — to build) — structured agent workflows with per-step logging to `Agent_Log`
- **SQLite reasoning layer** — agents query live DB for context and write results back to existing tables; no stale markdown pages

The agent architecture has three types (all in `orchestration/agents/`):

| Agent | Trigger | Purpose |
|---|---|---|
| **ReactiveAgent** | Supplier fallout event | Find alternative suppliers for all affected ingredients |
| **ProactiveAgent** | Scheduled / on-demand | Run consolidation opportunity ranking, refresh proposals |
| **ResearchAgent** | On-demand or reactive fallback | Discover net-new suppliers not in the database |

### Reasoning Layer (Stage 2 Phase 4)
- **Formula scoring** — `consolidation_scorer.py`: `company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15`
- **LLM adjustment** — `proposal_generator.py`: Claude adjusts top-50 scores ±0.10, writes `Proposal_Text`
- **Substitution graph** — `substitution_graph.py`: ingredient equivalence edges for cross-company substitution proposals

### Frontend (Stage 4 — TBD)
Flask/FastAPI + HTMX or lightweight React. Reads `db_enriched.sqlite` directly. Decision deferred to Stage 4 start. The LLM-wiki pattern (`Orchestration/Data/llm-wiki.md`) is available as an optional human-readable export layer at this stage — generate markdown from DB queries rather than maintaining it as a primary store.

---

## APIs

All keys go in `.env` (copy from `.env.template`):

| API | Key Required | What It Does | Where to Get Key | Rate Limit |
|---|---|---|---|---|
| **Anthropic Claude** | Yes | Stage 4 proposals, wiki maintenance | console.anthropic.com | Per-token |
| **Google ADK / Gemini** | Yes | Web search in Stage 3 agents | aistudio.google.com (free) | Free tier |
| **NIH DSLD v9** | Yes | Ingredient UNII codes + BOM amounts | dsld.od.nih.gov/api-guide | Undocumented |
| **PubChem PUG REST** | No | CAS numbers, SMILES, canonical names | — | 5 req/sec, 400/min |
| **Molport v3** | No (stub) | Chemical supplier pricing | molport.com | 10k req/month |
| **USDA FoodData Central** | No (key for higher limits) | Food-grade ingredient lookup | fdc.nal.usda.gov | 1000/hr |
| **openFDA** | No (key for higher limits) | Drug/supplement adverse events | open.fda.gov | 40/min anon |
| **RxNorm** | No | Drug-class ingredient IDs | — | Undocumented |

Integration guides for each API are in `Orchestration/References/*-guide.md`.

**Cost note:** PubChem, DSLD, USDA FDC, RxNorm, openFDA are free. Molport free tier only. No paid scraping services. Claude API costs are limited to proposal generation for top-50 consolidation candidates.

---

## How Agnes Orchestrates Agents

The key design principle: **agents must be auditable, not free-form**. For every high-stakes decision (supplier switch, consolidation proposal), the reasoning is:

1. **Anchored** to documented criteria in `Orchestration/Wiki/` pages
2. **Structured** as a DAG of steps with logged inputs/outputs
3. **Persistent** — conclusions are written back to the wiki so the next agent run starts richer

### DAG Executor Pattern

```
Node 1: QueryAffectedIngredients(supplier_id) → ingredient_list
Node 2: QueryComplianceRequirements(ingredient_list) → cert_requirements  [depends: 1]
Node 3: SearchAlternativeSuppliers(ingredient_list) → candidate_list      [depends: 1]
Node 4: FilterByCertification(candidates, cert_requirements) → filtered   [depends: 2,3]
Node 5: RankByScore(filtered) → ranked_list                               [depends: 4]
Node 6: GenerateProposal(ranked_list) → proposal_text                     [depends: 5]
Node 7: WriteToDatabase(proposal_text) → Consolidation_Opportunity row updated  [depends: 6]
```

Each node writes one row to `Agent_Log` (Run_Id, Agent, Node, Status, Input_JSON, Output_JSON). Query the log with SQL to audit any step.

### SQLite Reasoning Pattern

`db_enriched.sqlite` is the persistent reasoning layer. Before an agent reasons about a decision, it queries the DB for live context — no stale pages, no re-sync overhead. After making a decision, it writes results back into existing tables (`Proposal_Text`, `Score_LLM_Adjustment`, `Supplier_Commercial`, etc.) and logs the run to `Agent_Log`.

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

This is always current, composable, and requires no wiki-page maintenance. Reasoning compounds because every agent run enriches the same tables the next run queries.

The LLM-wiki pattern (`Orchestration/Data/llm-wiki.md`) is available as an *optional Stage 4 output format* — generate human-readable markdown from DB queries for stakeholder review, not as a primary store.

### Agent Function Stack (to build)

The following are the core functions Stage 3 needs to implement:

```python
# Research functions
search_web(query: str) -> list[SearchResult]          # Google ADK
scrape_supplier_page(url: str) -> SupplierRecord      # Playwright browser agent
extract_structured_data(html: str, schema) -> dict    # Claude API

# DB context functions — agents build prompts from live queries, not static pages
query_ingredient_context(canonical_id: int) -> dict   # Ingredient_Canonical + Consolidation_Opportunity
query_compliance_requirements(ingredient_ids: list) -> list[dict]  # Product_Compliance
query_substitution_edges(canonical_id: int) -> list[dict]          # Ingredient_Substitution

# Supply chain evaluation
find_alternative_suppliers(ingredient_id) -> list[SupplierCandidate]
evaluate_compliance_fit(supplier, required_certs) -> ComplianceDelta
score_consolidation_opportunity(canonical_id) -> float

# Proposal generation + DB writes
generate_proposal(opportunity_id) -> ProposalText     # writes to Consolidation_Opportunity
upsert_supplier_commercial(supplier_id, canonical_id, data) -> None

# Agent logging
log_agent_step(run_id, agent, node, status, input_json, output_json, **fk_ids)
    # → INSERT INTO Agent_Log; one call per DAG node
```

These should be implemented as:
- **MCP tools** for the Google ADK agent (tool use interface)
- Or as **Claude API tool_use blocks** if using Claude directly for orchestration
- Reference: `Orchestration/References/claude-api-patterns-guide.md` and `Orchestration/References/google-adk-search-guide.md`

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

### Validate current state

```sql
-- Open db_enriched.sqlite with any SQLite client and run:

SELECT COUNT(*) AS total, SUM(CASE WHEN Confidence >= 0.65 THEN 1 END) AS resolved
FROM SKU_To_Canonical;
-- Expected: ~854 total, ~700+ resolved

SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Confidence >= 0.65;
-- Expected: 515

SELECT COUNT(DISTINCT CanonicalIngredientId) FROM Supplier_Commercial;
-- Phase 3 commercial enrichment

SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Score IS NOT NULL;
-- Expected: 129
```

---

## Contribution Guidelines

### Who owns what

| Area | Owner | Notes |
|---|---|---|
| Pipeline (Stage 2) | timbtz | Phases 1–3 complete; Phase 4 proposals blocked on `ANTHROPIC_API_KEY` |
| Supply chain scoring model | Supply chain expert | Formula weights and quality dimensions are open for revision — see `reasoning/consolidation_scorer.py` |
| Stage 3 agents | Open | `orchestration/agents/` directory does not exist yet — start here |
| Stage 4 frontend | Open | `frontend/` directory does not exist yet |
| Wiki content | Shared | Agents write; humans review via Wiki browser (Stage 4) |

### Supply chain expert: what you can change

The quality/compliance scoring dimensions (`reasoning/consolidation_scorer.py`) were defined with limited domain input. The current formula:

```
score = company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15
```

The weights and dimensions are open for revision. If you have a better model of what makes a consolidation opportunity valuable (MOQ thresholds, geographic risk, certification tiers, price elasticity), define it here and update the formula. The schema has `Score_Formula_Component` and `Score_LLM_Adjustment` columns ready for a hybrid approach.

The `Product_Compliance` table also has a `Caveats` column (schema v1.1) for adding domain-specific compliance notes. `Ingredient_Substitution` has a `Caveats` column for substitution edge quality notes. Both are open for population.

### Adding a new API or data source

1. Add the client to `enrichment/sources/<api_name>.py`
2. Add a guide to `Orchestration/References/<api_name>-integration-guide.md`
3. Wire it into the appropriate enricher in `enrichment/enrichers/`
4. Add the key to `.env.template` and update the API table above
5. Update `CLAUDE.md` Current State table

### Adding a new agent

1. Add the agent file to `orchestration/agents/<name>_agent.py`
2. Define its DAG as a list of nodes (see meta-workflow.md §3 for the pattern)
3. Register its MCP tools or tool_use schemas
4. Document the trigger, inputs, DB tables it reads, and DB tables it writes
5. Every DAG node must call `log_agent_step()` → one `Agent_Log` row per step

### Open decisions (need resolution before implementing)

| Decision | Options | Status |
|---|---|---|
| Frontend framework | Flask+HTMX vs. lightweight React | Open — decide at Stage 4 start |
| Reasoning persistence | SQLite vs. markdown wiki | **Closed — SQLite** (`Agent_Log` + existing tables) |
| DAG executor library | Custom vs. `prefect`-lite vs. `dagster` | Open — custom is simplest for MVP |
| MCP tool interface | Google ADK tool use vs. Claude tool_use | Open — depends on primary agent LLM |

---

## Key Files to Read First

1. [`Orchestration/PRDs/meta-workflow.md`](Orchestration/PRDs/meta-workflow.md) — four-stage implementation plan, agent architecture, open decisions
2. [`CLAUDE.md`](CLAUDE.md) — live current state: what's run, what's broken, what's blocked
3. [`schema/enriched_schema.sql`](schema/enriched_schema.sql) — locked v1.1 schema; understand this before writing any SQL
4. [`Orchestration/References/google-adk-search-guide.md`](Orchestration/References/google-adk-search-guide.md) — how to use Google ADK for web search in agents
5. [`Orchestration/References/claude-api-patterns-guide.md`](Orchestration/References/claude-api-patterns-guide.md) — Claude tool_use patterns for structured DB writes

---

## Design Principles

- **Evidence everywhere.** Every Agnes-written field has `source` and `confidence`. No silent failures.
- **Idempotent always.** Every pipeline run and agent execution is safe to repeat. `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE` everywhere.
- **Cache first.** All external API responses are cached in `db_enriched.sqlite`. Never re-fetch what's stored.
- **No paid services.** Free tiers only. No Apify, no ChemAnalyst, no ImportGenius.
- **Auditable reasoning.** Every agent decision is traceable to its DAG steps and wiki pages. The user can always ask "why did Agnes recommend this?"
- **Pricing disclaimer.** Molport pricing is research/lab scale. Always include in proposals: *"pricing indicative at research quantities — production volume requires direct negotiation."*
