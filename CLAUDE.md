# Agnes — Agent Working Reference

> **Self-maintenance rule:** After any meaningful change — phase run, schema edit, new finding, bug fix — update the relevant section below. Max 3 lines per entry. No prose.
>
> **README self-maintenance rule:** After any meaningful change — new endpoint, pipeline, UI feature, DB state change — update `README.md` to match. This applies to every coding session working in this repo.

---

## Voice / UI Layer

| Component | Status | Notes |
|---|---|---|
| `orchestration/ui/` | ✅ Active (Lovable) | git subtree from `timbtz/agnes-ai-navigator`; served at `/` by FastAPI; build: `cd orchestration/ui && bun run build` |
| `orchestration/ui_legacy/` | ❌ Inactive | Original hand-built Vite+React UI; archived as fallback; see `README_INACTIVE.md` |
| `pull-ui.sh` | ✅ Script | `./pull-ui.sh` — pulls latest from Lovable repo, rebuilds dist |
| `orchestration/ui/.env` | ✅ Local only | `VITE_AGNES_API_URL=http://localhost:8000`, `VITE_ELEVENLABS_API_KEY`, `VITE_ELEVENLABS_VOICE_ID` |
| `REF-ELEVENLABS-ORB-UI.md` | ✅ Reference written | ElevenLabs WebGL Orb component — props, patterns, color palettes per pipeline |
| `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` | ✅ Reference written | Full integration guide: STT→/chat→SSE→TTS, Orb state machine, Option 1 (custom) + Option 2 (Conversational AI agent) |

**Lovable sync workflow:** iterate in Lovable → push to `timbtz/agnes-ai-navigator` → run `./pull-ui.sh` here → restart FastAPI

---

## Orchestration Layer (NEW)

| Component | Status | Notes |
|---|---|---|
| `orchestration/api/main.py` | ✅ Live | FastAPI; start: `PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000` |
| `orchestration/api/dag_executor.py` | ✅ Complete | Topological layers, asyncio.gather(), `orchestration.db` event log, SSE publish |
| `orchestration/api/pipeline_loader.py` | ✅ Complete | YAML → Pipeline/PipelineNode dataclasses; 7 pipelines loaded |
| `orchestration/api/conditions.py` | ✅ Complete | 9 named condition guards incl. `has_stale_prices`, `has_price_alerts` |
| `orchestration/agents/router_agent.py` | ✅ Complete | Claude-Haiku chat classifier → pipeline name + params JSON |
| `orchestration/agents/{reactive,proactive,research,proposal_writer,price_fetch_agent,price_alert_writer}` | ✅ Complete | All Claude/Gemini-based; search_sub_agent wired |
| `orchestration/tools/` | ✅ Complete | 10 deterministic tools: + regulatory_drift_tool |
| `orchestration/pipelines/` | ✅ 7 pipelines | + regulatory_drift_alert (data_update trigger) |
| **Endpoints** | ✅ 17 endpoints | + GET /api/data/regulatory-alerts |

---

## Current State

| Layer | Status | Notes |
|---|---|---|
| `schema/enriched_schema.sql` | ✅ v1.1 | 15 new columns; Supplier_Commercial.Confidence TEXT→REAL fixed |
| `db_enriched.sqlite` | ✅ v1.1 + FDA/Scoring — all phases run | 9067 FDA IID rows (1150 matched), Scoring_Config defaults, 135 AE counts; 125 SMILES, 250 canonicals, 515 BOM, 126 compliance, 123 CO rows |
| Phase 1 — Ingredient Identity | ✅ Complete | CID gap backfill: 20 new CIDs via UNII/name lookup; 2nd dedup pass merged 7 more pairs; dedup merge bug fixed |
| Phase 2 — BOM Quantities | ✅ Complete | 515 rows, 87/149 FG covered (58%); fingerprint match: brand+ingredient query + overlap≥2 |
| Phase 3 — Commercial/Compliance | ✅ Complete | 126 rows, 66 products, 9 cert types; fixed stmt.notes key + Phase 2 label reuse |
| Phase 4 — Reasoning/Proposals | ✅ Complete | 14 proposals generated + 112 citations extracted (Haiku); 4 demo trap refusals seeded; `reasoning/proposal_generator.py` now loads .env |
| Phase A — Data Quality Fixes | ✅ Complete | Grade_Flag: 239/250 classified (11 unknown); substitution edges: 4→32 (fuzzy fallback added); compliance status filter fixed; Function column populated via role_classifier |
| `enrichment/sources/pubchem.py` | ✅ Implemented | get_isomeric_smiles() + get_unii_from_synonyms() + get_cid_by_name(); rate-limited (4.5 req/sec), cache-first |
| `enrichment/sources/dsld.py` | ✅ Implemented | DSLD v9, cached |
| `enrichment/sources/molport.py` | ✅ Stub | Graceful no-op if MOLPORT_API_KEY absent; CAS→SMILES→supplier chain |
| `enrichment/db_migrate_v11.py` | ✅ New | Idempotent v1.1 migration; called by db_bootstrap.py |
| `enrichment/backfill_phase1.py` | ✅ New | SMILES + UNII + MatchScore backfill; commits per-row to avoid DB lock |
| `enrichment/run_dedup.py` | ✅ New | UNII dedup + substitution seeding; run after backfill_unii |
| `enrichment/sources/fda_iid.py` | ✅ Complete | Loads IIR_OCOMM.csv → FDA_Inactive_Ingredient; 9067 rows, 1150 canonical matches |
| `enrichment/sources/openfda.py` | ✅ Complete | OpenFDAClient: adverse_event_count() + search_labels(); rate-limited 0.26s/req; cached 7d |
| `enrichment/backfill_openfda.py` | ✅ Complete + run | Populates openfda_adverse_event_count on 135 UNII-bearing canonicals |
| `enrichment/db_migrate_fda_scoring.py` | ✅ Complete + run | Creates FDA_Inactive_Ingredient, Scoring_Config tables; adds openfda_adverse_event_count column |
| `enrichment/db_migrate_iid_changelog.py` | ✅ Complete + run | Creates FDA_IID_Change_Log (187 rows, 27 matched); adds regulatory_drift_flag/reason to Consolidation_Opportunity |
| `enrichment/sources/fda_iid_changelog.py` | ✅ Complete + run | Loads Change_Log_Data.csv → FDA_IID_Change_Log; fuzzy name matching; accepts optional csv_path |
| `enrichment/backfill_iid_changelog.py` | ✅ Complete + run | Top-level runner: migrate + CSV load; idempotent |
| `orchestration/tools/regulatory_drift_tool.py` | ✅ Complete | Pairs C rows, assigns severity HIGH/MEDIUM/LOW, cross-refs Consolidation_Opportunity |
| `orchestration/agents/reactive_agent.py` | ✅ Fixed | Bug fixed: was reading `gate-qualify` (wrong key), now reads `gate-compliance`; also consumes `web-research` output |
| `orchestration/pipelines/supplier_fallout.yaml` | ✅ Updated | Added `web-research` (ResearchAgent) node gated by `needs_supplier_research`; `write-proposal` now depends on it |
| `orchestration/api/conditions.py` | ✅ Updated | Added `needs_supplier_research`: fires when DB alternatives < 3 or all have no Lead_Time_Days |
| `orchestration/agents/regulatory_research_agent.py` | ✅ Complete | Searches FDA quarterly change log; downloads CSV if found; graceful fallback on failure |
| `orchestration/agents/regulatory_drift_agent.py` | ✅ Complete | Gemini narrative for drift alerts; writes regulatory_drift_flag to DB |
| `orchestration/pipelines/regulatory_drift_alert.yaml` | ✅ Complete | 4-node: fetch-latest-changes → scan-drift → find-alternatives → write-alerts |
| `enrichment/db_migrate_price_monitor.py` | ✅ Complete + run | Creates Price_Change_Alert table + indexes; idempotent |
| `enrichment/enrichers/supplier_web_enricher.py` | ✅ New | Async; calls search_sub_agent, parses JSON, upserts Supplier_Commercial; Price_Source='google_search' |
| `enrichment/backfill_supplier_web.py` | ✅ New | Batch script; requires GOOGLE_API_KEY; run to populate Supplier_Commercial from web |
| `enrichment/backfill_supplier_curated.py` | ✅ Complete + run | Curated bulk pricing for 117 missing ingredients + backfill 31 null prices; Supplier_Commercial now 239/250 (95.6%) covered |
| `orchestration/tools/price_staleness_checker.py` | ✅ New | Sync DAG tool; finds UNII canonicals with missing/stale web prices (>7d) |
| `orchestration/agents/price_fetch_agent.py` | ✅ New | Async DAG agent; fetches prices via search_sub_agent; writes Price_Change_Alert on >=15% change |
| `orchestration/agents/price_alert_writer.py` | ✅ New | Async DAG agent; Gemini narrative; persists to Price_Change_Alert.Alert_Narrative |
| `orchestration/api/routes/alerts.py` | ✅ New | GET count/list, POST dismiss, GET per-ingredient |
| `orchestration/api/routes/data.py` | ✅ Updated | Product name fallback (company #id), title-case fix, CERT_IMPLICATIONS hierarchy, GET /proposals/{id}/citations, GET /refusals |
| `reasoning/supplier_scorer.py` | ✅ Complete + score_suppliers_with_context() | Returns grade guidelines alongside ranked supplier list |
| `reasoning/supplier_guidelines.py` | ✅ New | Reads Orchestration/Data/supplier_wiki/{grade}.md for scoring context |
| `Orchestration/Data/supplier_wiki/` | ✅ New | supplements.md, excipients.md, food.md — price ranges, quality flags, lead time norms |
| `orchestration/api/routes/scoring.py` | ✅ Complete | GET/POST /api/scoring/weights, GET /api/scoring/suppliers/{id} |
| `orchestration/tools/compliance_reasoner_tool.py` | ✅ Augmented | Returns fda_iid_max_daily_mg, fda_iid_routes; persists refuse/defer to Refusal_Log |
| `enrichment/db_migrate_citation_refusal.py` | ✅ Complete + run | Claim_Citation + Refusal_Log tables; 4 demo trap seeds; idempotent |
| `orchestration/ui/src/components/views/RegulatoryAlertsView.tsx` | ✅ New | Severity-filtered alert cards with before/after MDE snapshots |
| `orchestration/ui/src/components/dag/DagGraphView.tsx` | ✅ Overhauled | Node cards show humanized class name + `when` condition; output panel moves BELOW canvas (no clipping); `alert_narrative` recognized as prose; collapsible array fields |
| `orchestration/ui/src/components/views/ComplianceView.tsx` | ✅ Improved | Search input + All/Confirmed/Implied filter; "Confirmed" legend label; tooltip on cells explaining implied derivation |
| `orchestration/ui/src/components/views/SuppliersView.tsx` | ✅ Reworked | 7-col grid: +Trust col (provenance badge, corroboration dots, URL health dot, vetted stamp); weighted score col shows overall + Price/Lead/Quality mini bars; hover tooltip with sub-score breakdown + provenance notes |
| `orchestration/ui/src/components/views/TradeRoutesView.tsx` | ✅ New | Filterable lane table: Origin→Dest, Mode (icons), Lead Time, Cost, Landed Cost Index bar; mock data via agnesApi.lanes(); TODO: wire to /api/data/lanes |
| `orchestration/ui/src/types/agnes.ts` | ✅ Extended | Added ProvenanceConfidence, UrlHealth, Lane types; ScoredSupplier extended with provenance_confidence, corroboration_score, url_health, vetted, url_archetype |
| `orchestration/ui/src/components/orb/VoiceOrb.tsx` | ✅ Fixed | OrbErrorBoundary wraps Canvas; WebGL failure renders CSS gradient fallback instead of crashing app |
| `orchestration/ui/src/hooks/usePriceAlerts.ts` | ✅ New | `usePriceAlertCount()` — polls /api/alerts/count every 60s |
| `enrichment/sources/rxnorm.py` | ❌ Missing | Low priority — narrow use (drug-class ingredients only) |
| `enrichment/sources/fdc.py` | ❌ Missing | Low priority — only useful for ~5 food-macro SKUs |
| `reasoning/consolidation_scorer.py` | ✅ Fixed + run | Formula: company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15; 129 rows scored |
| `reasoning/substitution_graph.py` | ✅ Re-run | 32 edges; fuzzy fallback (_canonical_id rapidfuzz≥85) added; 18 rules still unresolved (Fish Oil, Ergocalciferol, etc.) |
| `reasoning/base.py` | ✅ New | ToolResult, Tool ABC, compound_confidence() — lifted from local-dev |
| `reasoning/role_inferrer.py` | ✅ New | RoleInferrer, ROLE_RULES, covers_roles() — lifted from local-dev |
| `reasoning/compliance_reasoner.py` | ✅ New | ComplianceReasoner, JURISDICTION_PACKS (US-FDA, EU, CA, JP, US-USP) — lifted from local-dev |
| `reasoning/refusal_engine.py` | ✅ New | RefusalEngine, CONFIDENCE_FLOOR=0.50 — lifted from local-dev; _persist() no-op'd for DAG thread safety |
| `enrichment/enrichers/grade_classifier.py` | ✅ New + run | Heuristic classifier; 239/250 classified; supplement:117, food:62, excipient:32, sweetener:15, flavor:13, unknown:11 |
| `enrichment/enrichers/role_classifier.py` | ✅ New + run | Heuristic Function classifier; 0 NULL rows; 177 non-unknown roles populated |
| `orchestration/tools/compliance_reasoner_tool.py` | ✅ New | 4-state DAG tool: reads canonical_id → ComplianceReasoner → RefusalEngine → returns outcome/per_jurisdiction/above_floor |
| `scripts/fix_substitution_rules.py` | ✅ New + run | Alias-table UPDATE for Ingredient_Substitution_Rule; 20 updated, 2 already-correct, 18 unresolved |
| `enrichment/enrichers/commercial_enricher.py` | ✅ _enrich_pair wired | MolportClient integration complete; no-ops when MOLPORT_API_KEY absent |

---

## Pipeline Sequence

```
db_bootstrap.py → Phase 1 → Phase 2 → Phase 3 → Phase 4
```
Each phase is idempotent. Re-run any phase safely. Cache hit rate ≥ 90% on second run.

---

## Schema: v1.1 (applied ✅)

All v1.1 fields are live in `db_enriched.sqlite`. `enrichment/db_migrate_v11.py` applied idempotently. No pending schema changes.

---

## Arcs — Problems, Findings, Limitations

**[FIXED]** Vitamin C (33 co.) merged from Vitamin C (25 co.) + l-ascorbic acid (17 co.) via PubChem synonym UNII backfill. `get_unii_from_synonyms()` added to PubChemClient; 88/90 CID-bearing canonicals populated. dedup_by_unii() got CAS-differs guard to block false positives (elemental Zn/Mg/Cr UNIIs shared with chelated forms).

**[FIXED]** Display name fix added to `ingredient_normalizer.py` Tier 1: DSLD common name overrides PubChem IUPAC if ≤60 chars. Will apply on next Phase 1 re-run.

**[OBSERVED]** Gelatin and Calcium have no CAS — Gelatin is a protein mixture (no single PubChem CID); Calcium is form-ambiguous (carbonate vs citrate). FDC can resolve Gelatin FDC_Id; Calcium needs slug-level form disambiguation.

**[OBSERVED]** Sucralose CID 56038-13-2 surfacing in cluster report — likely a Phase 1 parser artifact on a non-ingredient SKU slug. Needs spot-check in `sku_parser.py`.

**[KNOWN LIMIT]** FDC: useful only for food-grade raw materials (whey, collagen, gelatin, maltodextrin, inulin). Not a Phase 2 finished-good fallback — FDC has sparse branded supplement coverage and wrong unit structure for BOM enrichment.

**[KNOWN LIMIT]** RxNorm: narrow applicability in this dataset. CPG supplement SKUs are not drug-class. Defer implementation until Phase 1 coverage report shows unresolved drug-class ingredients.

**[KNOWN LIMIT]** Molport pricing is research/lab scale (`Price_Type='retail_proxy'`). Always include disclaimer in Proposal_Text: "pricing indicative at research quantities — production volume requires direct negotiation."

**[ACHIEVED]** Phase 2 coverage 58% (87/149 FG); above 55% threshold. Retailer scraper not needed.

**[FIXED]** Compliance enricher stmt.notes key bug (was stmt.text); Phase 2 label reuse for products with numeric IDs; fingerprint_match now uses brand+ingredient query. All fixes validated.

**[FIXED]** DSLD client: added load_dotenv() so API key loads from .env in direct script runs.

**[FIXED]** Consolidation scorer formula: replaced compliance_homogeneity (placeholder 0.5) + inverted supplier_concentration with fragmentation (unique_sku_count/max, W=0.20) + supplier_spread (supplier_count/max, W=0.15). 129 rows scored; Vitamin C top-ranked (25 cos, score=0.893). Also fixed _upsert_opportunity to DELETE+INSERT (no UNIQUE constraint on CanonicalIngredientId — INSERT OR REPLACE was creating duplicates on re-run).

**[DESIGN DECISION]** Consolidation scoring: Option C chosen (formula baseline + LLM adjustment ±0.10 for top-50 only). Formula weights: company_score 0.40, bom_score 0.25, fragmentation 0.20, supplier_spread 0.15.

**[FIXED]** SubstitutionGraphBuilder: `scripts/fix_substitution_rules.py` updated 20 Name_A/B aliases (e.g. Cholecalciferol→Vitamin D, Ascorbic Acid→Vitamin C). Edges: 4→30. 18 rules still unresolved (no canonical match — Ergocalciferol, Methylcobalamin, Fish Oil, etc.).

**[FIXED]** `proposal_generator.py` compliance filter: added `'implied'` to Status IN clause (all 126 compliance rows use `'implied'`). Vitamin C now returns 8 certs in context. Grade_Flag and SMILES added to opportunity fetch and prompt.

**[NEW]** `enrichment/enrichers/grade_classifier.py`: heuristic no-API classifier populates Grade_Flag for 239/250 canonicals. Unknown=11 (branded blends: Aquamin, EpiCor, ConcenTrace, etc. — acceptable).

**[FIXED]** UNII backfill: PubChem synonym extraction (`get_unii_from_synonyms()`) replaced DSLD path. 88/90 CID-bearing canonicals populated. UNII coverage: 44→129 (17%→50.2%). DSLD UNII backfill deprecated for this dataset (DSLD has sparse uniiCode on excipients/trade-name ingredients).

**[FIXED]** dedup_by_unii() now copies PubChem_CID, CAS_Number, SMILES, Molport_Id, FDC_Id, RxCUI from dropped row to kept row before deletion. Prevents CID loss on merge (was root cause of Vitamin C losing CID after l-ascorbic acid merge). Second dedup pass after new UNII backfill merged 7 more pairs (nicotinamide, Vitamin K2, D-Sorbitol, Pyridoxine HCl, Natrium, retinol, Alpha-Tocopherol).

**[FIXED]** backfill_cid_gaps() added to backfill_phase1.py: tries UNII→CID then CAS→CID then name→CID for all 146 no-CID canonicals. Found 20 new CIDs (Vitamin C, Niacinamide, Erythritol, Vitamin K2, Vitamin E, Vitamin B6, Folate, etc.). SMILES went 111→125 (43%→50.0%). Added get_cid_by_name() to PubChemClient.

**[KNOWN LIMIT]** 3 UNII duplicate pairs intentionally skipped by CAS-differs guard: Chrome/Chromium nicotinate (7440-47-3 vs 64452-96-6), Magnesium sheet/Magnesia (7439-95-4 vs 1309-48-4), Zinc dust/Zinc glycinate (7440-66-6 vs 14281-83-5). PubChem assigns elemental UNII to both elemental and compound forms — dedup guard correct.

---

## Key Validation Queries

```sql
-- Phase 1 coverage
SELECT COUNT(*) AS total,
  SUM(CASE WHEN Confidence >= 0.65 THEN 1 END) AS resolved
FROM SKU_To_Canonical;

-- Duplicate canonical check (UNII dedup)
SELECT UNII_Code, COUNT(*) FROM Ingredient_Canonical
WHERE UNII_Code IS NOT NULL GROUP BY UNII_Code HAVING COUNT(*) > 1;

-- Phase 2 coverage
SELECT COUNT(*) FROM BOM_Component_Quantity WHERE Confidence >= 0.65;

-- Phase 3 commercial
SELECT COUNT(DISTINCT CanonicalIngredientId) FROM Supplier_Commercial;

-- Phase 4 proposals
SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL;
```

---

## External APIs

| API | Key location | Primary use | Limit |
|---|---|---|---|
| NIH DSLD v9 | `.env` `DSLD_API_KEY` | Phase 1 UNII + Phase 2 BOM amounts | Undocumented |
| PubChem PUG REST | No key | Phase 1 CAS/SMILES | 5/sec, 400/min |
| Molport v3 | `.env` `MOLPORT_API_KEY` (pending) | Phase 3 pricing | 10k/month |
| Anthropic | `.env` `ANTHROPIC_API_KEY` | Phase 4 proposals (top-50 LLM pass) | Per-token |
| USDA FDC | `.env` `FDC_API_KEY` | Phase 1 tier-4 fallback (5 food macros only) | 1000/hr |
| RxNorm | No key | Phase 1 tier-3 fallback (drug-class only) | Undocumented |
