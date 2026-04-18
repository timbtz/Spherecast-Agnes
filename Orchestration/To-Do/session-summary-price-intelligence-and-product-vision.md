# Agnes — Session Summary: Price Intelligence, Product Vision & Implementation State

**Session date:** 2026-04-18  
**Claude session:** Sonnet 4.6  
**Scope:** FDA enrichment execution + Supplier Price Intelligence implementation + product strategy

---

## What This Product Is

Agnes is an AI-native procurement intelligence layer for CPG (consumer packaged goods) supplement manufacturers. It sits on top of a proprietary SQLite database (`db_enriched.sqlite`) that has been enriched across four phases with ingredient identity, bill-of-materials quantities, commercial supplier data, and compliance certifications.

The core value proposition: **Agnes replaces weeks of manual sourcing research with minutes of voice-driven AI reasoning.** A procurement manager says "Find consolidation opportunities for Vitamin C" and Agnes runs a DAG of agents — some Claude-based (reasoning), some Gemini-based (search + narrative), some deterministic (SQL tools) — and returns a ranked proposal with compliance context, FDA exposure limits, and a prioritised supplier shortlist.

The database covers ~250 canonical ingredients used across 66 CPG products from multiple companies. Agnes knows: how many companies buy each ingredient, from how many suppliers, at what estimated price, with what compliance certifications, and what the FDA's inactive ingredient exposure limits are. This is the foundation on which all intelligence runs.

---

## Implementation Focus This Session

### Phase Executed: FDA Enrichment + Supplier Scoring (Plan 9)

Before this session, the Suppliers tab showed EmptyState for every ingredient — the `SupplierScorer` had nothing to rank because `Supplier_Commercial` was empty and the FDA data tables didn't exist yet.

**What was built and run:**
- `FDA_Inactive_Ingredient` table — 9,067 rows from the FDA IID CSV, 1,150 matched to canonical ingredients
- `openfda_adverse_event_count` column on `Ingredient_Canonical` — 135 canonicals backfilled via OpenFDA API
- `Scoring_Config` table — default weights (3.0/3.0/3.0) for Price / Lead Time / Quality
- `reasoning/supplier_scorer.py` — weighted scoring with per-field normalization; lower price/lead-time = better score
- `orchestration/api/routes/scoring.py` — GET/POST `/api/scoring/weights`, GET `/api/scoring/suppliers/{id}`
- Frontend `SuppliersView` — ingredient selector, 5-step `WeightSelector` sliders, ranked supplier table with `ScoreBar`
- `compliance_reasoner_tool.py` augmented — now returns `fda_iid_max_daily_mg`, `fda_iid_routes`, `fda_iid_data_available`

### Phase Executed: Supplier Price Intelligence (Plan 10 — current session)

The three-tier feature implemented in this session:

**Tier 1 — Supplier Web Enricher (Highest Value)**

The core gap: `Supplier_Commercial` is empty. Molport data requires a paid API key we don't have. The `search_sub_agent` (Gemini 2.5 Flash + Google Search grounding) already works and returns structured JSON — but its output was only written to `Agent_Log`, never persisted.

Built: `enrichment/enrichers/supplier_web_enricher.py` — an async enricher that calls `search_sub_agent.search()` per canonical ingredient, parses the JSON supplier array using the battle-tested `_parse_suppliers()` regex from `research_agent.py`, and upserts `Supplier` + `Supplier_Commercial` rows with `Price_Source='google_search'`, `Confidence=0.65`.

Run: `enrichment/backfill_supplier_web.py` (requires `GOOGLE_API_KEY` — not yet run in this session, but wired and ready).

**Tier 2 — Price Monitor Pipeline + Alerts (Medium Value)**

Built the full alerting loop:
- `enrichment/db_migrate_price_monitor.py` — creates `Price_Change_Alert` table (run successfully)
- `orchestration/tools/price_staleness_checker.py` — sync DAG tool; identifies UNII-bearing canonicals with no web prices or prices older than 7 days; returns up to 20 results per run
- `orchestration/agents/price_fetch_agent.py` — async DAG agent; calls `search_sub_agent` per stale ingredient; compares new vs. stored price; writes `Price_Change_Alert` row if Δ ≥ 15%; severity: `info` (5–14%), `warning` (15–29%), `critical` (≥30%)
- `orchestration/agents/price_alert_writer.py` — Gemini narrative agent; writes ≤200-word executive briefing summarising all detected changes per run; persists to `Price_Change_Alert.Alert_Narrative`
- `orchestration/pipelines/price_monitor.yaml` — 3-node pipeline: `find-stale → fetch-prices (when: has_stale_prices) → write-alert-narrative (when: has_price_alerts)`
- `orchestration/api/routes/alerts.py` — 4 endpoints: GET count (for TopBar badge), GET list (filterable by dismissed/severity), POST dismiss, GET per-ingredient
- Frontend `AlertsView.tsx` — severity-coded alert cards (red/amber/blue), TrendingDown/TrendingUp icons, price delta display, dismiss button with optimistic invalidation

**Tier 3 — Scheduler + Supplier Intelligence Wiki (Lower Value)**

- FastAPI `lifespan` background task — fires `price_monitor` every 24h if `GOOGLE_API_KEY` is set; starts 60s after server boot; gracefully cancelled on shutdown
- `Orchestration/Data/supplier_wiki/` — three grade-keyed markdown files (`supplements.md`, `excipients.md`, `food.md`) with typical B2B price ranges, quality flag rules, lead time norms, and red flags
- `reasoning/supplier_guidelines.py` — reads the appropriate wiki file for an ingredient's grade; injected into `score_suppliers_with_context()` as grounding context
- `reasoning/supplier_scorer.py` — augmented with `score_suppliers_with_context()` (non-breaking addition; existing `score_suppliers()` unchanged)

---

## Key Architectural Decisions Made

**`search_sub_agent` isolation:** The `google_search` tool cannot be mixed with other tools in the same `LlmAgent` instance (ADK constraint). `price_fetch_agent.py` calls `search_sub_agent.search()` as a Python coroutine — it has no `LlmAgent` itself. This is intentional and documented. Never add `google_search` to another agent's `tools=[]`.

**`price_fetch_agent` as pure-Python agent:** Agents in the DAG registry do not need to contain LLM calls. `price_fetch_agent` is registered as `agent_class: PriceFetchAgent` in YAML but its `run(ctx)` is pure Python logic (search → parse → compare → write). The LLM call is separated into `price_alert_writer`.

**First-run zero alerts:** On the first backfill run, all `Supplier_Commercial` rows are new — there is no previous price to compare against. `price_fetch_agent` will write 0 `Price_Change_Alert` rows on the first run. Alerts begin appearing on the second+ run. This is correct behaviour, not a bug.

**Web price confidence:** `Confidence=0.65` for Google Search-sourced prices (vs. Molport `0.70`). The wiki files and `price_alert_writer` system prompt explicitly flag web prices as "indicative only — production volume requires direct RFQ negotiation."

**`INSERT OR REPLACE` on Supplier_Commercial:** PK is `(SupplierId, CanonicalIngredientId)`. Re-running the backfill or price monitor overwrites old prices in place. `Price_Change_Alert` captures the historical diff before the overwrite — the table is append-only (no deletes except dismiss flag).

**Pydantic v2 field validation:** `confloat(ge=1.0, le=5.0)` is deprecated in Pydantic ≥2.7. Use `Annotated[float, Field(ge=1.0, le=5.0)]` — confirmed working in `scoring.py`.

**React Query v5:** `onSuccess` in `useQuery` was removed in v5. Use `useEffect(() => { if (data) setPending(data); }, [data])` instead. `useMutation` uses `isPending` not `isLoading`.

---

## Files Created or Modified This Session

### New Files
| File | Purpose |
|---|---|
| `enrichment/db_migrate_price_monitor.py` | Price_Change_Alert table migration |
| `enrichment/enrichers/supplier_web_enricher.py` | Web-based Supplier_Commercial enricher |
| `enrichment/backfill_supplier_web.py` | Batch runner for web enrichment |
| `orchestration/tools/price_staleness_checker.py` | Sync DAG tool: staleness detection |
| `orchestration/agents/price_fetch_agent.py` | Async DAG agent: price comparison + alerts |
| `orchestration/agents/price_alert_writer.py` | Async DAG agent: Gemini narrative |
| `orchestration/pipelines/price_monitor.yaml` | 3-node price monitor pipeline |
| `orchestration/api/routes/alerts.py` | Alert CRUD endpoints |
| `orchestration/ui/src/components/views/AlertsView.tsx` | Price Alerts frontend tab |
| `reasoning/supplier_guidelines.py` | Grade-keyed wiki reader |
| `Orchestration/Data/supplier_wiki/supplements.md` | Supplement pricing + quality guidelines |
| `Orchestration/Data/supplier_wiki/excipients.md` | Excipient pricing + quality guidelines |
| `Orchestration/Data/supplier_wiki/food.md` | Food-grade pricing + quality guidelines |

### Modified Files
| File | Change |
|---|---|
| `schema/enriched_schema.sql` | Added Price_Change_Alert table + indexes |
| `orchestration/api/conditions.py` | Added `has_stale_prices`, `has_price_alerts` |
| `orchestration/api/agent_registry.py` | Registered PriceFetchAgent, PriceAlertWriter, PriceStalenesCheckerTool |
| `orchestration/api/main.py` | Added alerts router + 24h scheduler in lifespan |
| `orchestration/ui/src/types/agnes.ts` | Added PriceAlert, AlertCount interfaces |
| `orchestration/ui/src/lib/agnesApi.ts` | Added alertCount(), listAlerts(), dismissAlert() |
| `orchestration/ui/src/components/layout/Sidebar.tsx` | Added "alerts" TabKey + Bell icon entry |
| `orchestration/ui/src/pages/Index.tsx` | Added AlertsView tab render + TAB_TITLES entry |
| `reasoning/supplier_scorer.py` | Added score_suppliers_with_context() |

---

## Current System State

| Capability | Status |
|---|---|
| Ingredient identity (250 canonicals) | ✅ Complete |
| BOM quantities (515 rows, 58% FG coverage) | ✅ Complete |
| Compliance certifications (126 rows, 9 cert types) | ✅ Complete |
| FDA IID limits (9,067 rows, 1,150 matched) | ✅ Complete |
| OpenFDA adverse events (135 AE counts) | ✅ Complete |
| Consolidation scoring (123 CO rows) | ✅ Complete |
| Regulatory drift alerting pipeline | ✅ Complete |
| Supplier scoring UI (weights, ranked table) | ✅ Complete |
| Supplier_Commercial population from web | ⏳ Ready — needs GOOGLE_API_KEY + backfill run |
| Price monitor pipeline | ✅ Wired — alerts accumulate from 2nd run onward |
| Price Alerts frontend tab | ✅ Complete |
| LLM proposals (Proposal_Text) | ⏳ Pending — run `reasoning/proposal_generator.py` |

---

## Intended Further Developments

### Near-term (unblocked by this session)

**1. Run the web backfill.** Once `GOOGLE_API_KEY` is confirmed in `.env`, run:
```bash
PYTHONPATH=. python3 enrichment/backfill_supplier_web.py
```
This is the single highest-leverage action — it populates `Supplier_Commercial` and unblocks the Suppliers tab from EmptyState for all UNII-bearing canonicals (~129 ingredients).

**2. Run LLM proposals.** `reasoning/proposal_generator.py` needs to be run to populate `Proposal_Text` on the 123 `Consolidation_Opportunity` rows. `ANTHROPIC_API_KEY` is already set.

**3. Second price monitor run.** After the backfill, trigger `price_monitor` a second time (via API or Agnes voice). First run writes baseline prices; second run detects changes and populates `Price_Change_Alert`.

### Medium-term Extensions

**LLWiki loop closure:** The supplier wiki is currently static markdown. A `WikiUpdateAgent` could receive `price_alert_writer` output and update the relevant wiki file with a new price benchmark entry — closing the LLWiki feedback loop so the wiki grows richer over time with every pipeline run.

**Molport integration:** When `MOLPORT_API_KEY` becomes available, `commercial_enricher.py` already has the integration wired. Molport data (`Confidence=0.70`, `Price_Type='retail_proxy'`) would supplement the Google Search data and provide more structured pricing with catalog IDs.

**RFQ generation:** `rfq_formatter.py` is already a registered DAG tool. A natural extension is a "generate RFQ" flow triggered from the Suppliers tab — selecting a supplier + ingredient triggers a `ProposalWriter`-style agent that outputs a formatted RFQ document.

**Supplier trust scoring:** Currently `Confidence` is binary (Molport 0.70, web 0.65). A richer trust model would factor in: number of independent web mentions, price stability across runs, country-of-origin risk tier, certification presence.

**Multi-run price trend chart:** `Price_Change_Alert` accumulates over time. A simple trend chart (ingredient × time × avg price) would surface seasonal patterns and long-term cost trajectories — high value for annual contract negotiations.

**Alert → Slack/email push:** The dismiss endpoint is built; the next step is a push notification bridge. A Make.com scenario or a simple FastAPI background task on alert creation could POST to a Slack webhook or send an email summary.

### Longer-term Vision

Agnes is designed as an always-on procurement co-pilot, not a one-shot analysis tool. The full vision:

- **Voice-first:** Procurement managers speak to Agnes the same way they'd speak to a junior buyer — "What's the best price for Vitamin D3 right now?", "Which of our suppliers for Magnesium are at risk of fallout?", "Generate an RFQ for Zinc Glycinate."
- **Proactive surface:** Agnes monitors prices, regulatory drift, and supplier compliance without being asked. The `price_monitor` + `regulatory_drift_alert` pipelines run on schedule; the user is notified when something material changes.
- **Compounding intelligence:** Each run enriches the database. Each enrichment makes the next LLM reasoning pass more grounded. The supplier wiki grows as Agnes discovers new price benchmarks. The substitution graph expands as research agents find new equivalence edges. This is the LLWiki principle applied to procurement.
- **Multi-tenant:** The Company layer in the schema supports multiple CPG companies. Agnes can become a shared intelligence platform where each company's sourcing data is isolated but the ingredient knowledge graph (canonicals, substitutions, FDA limits, supplier benchmarks) is shared.

---

## Next Commands to Run

```bash
# 1. Populate Supplier_Commercial (highest priority)
PYTHONPATH=. python3 enrichment/backfill_supplier_web.py

# 2. Generate LLM proposals
PYTHONPATH=. python3 reasoning/proposal_generator.py

# 3. Start the server and verify all tabs
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000

# 4. Smoke-test alert endpoints
curl -s http://localhost:8000/api/alerts/count | python3 -m json.tool
curl -s "http://localhost:8000/api/alerts/" | python3 -m json.tool
curl -s -X POST http://localhost:8000/pipelines/run/price_monitor | python3 -m json.tool
```
