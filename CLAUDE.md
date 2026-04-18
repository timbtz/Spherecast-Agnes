# Agnes — Agent Working Reference

> **Self-maintenance rule:** After any meaningful change — phase run, schema edit, new finding, bug fix — update the relevant section below. Max 3 lines per entry. No prose.

---

## Voice / UI Layer (Planned)

| Component | Status | Notes |
|---|---|---|
| `REF-ELEVENLABS-ORB-UI.md` | ✅ Reference written | ElevenLabs WebGL Orb component — props, patterns, color palettes per pipeline |
| `REF-ELEVENLABS-VOICE-PIPELINE-INTEGRATION.md` | ✅ Reference written | Full integration guide: STT→/chat→SSE→TTS, Orb state machine, Option 1 (custom) + Option 2 (Conversational AI agent) |
| `orchestration/ui/voice/` | ⏳ Not built | Recommended: Vite+React page; Orb + useAgnesVoice hook; served at `/voice` from FastAPI |

---

## Orchestration Layer (NEW)

| Component | Status | Notes |
|---|---|---|
| `orchestration/api/main.py` | ✅ Live | FastAPI; start: `PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000` |
| `orchestration/api/dag_executor.py` | ✅ Complete | Topological layers, asyncio.gather(), `orchestration.db` event log, SSE publish |
| `orchestration/api/pipeline_loader.py` | ✅ Complete | YAML → Pipeline/PipelineNode dataclasses; 5 pipelines loaded |
| `orchestration/api/conditions.py` | ✅ Complete | 6 named condition guards for YAML `when:` clauses |
| `orchestration/agents/router_agent.py` | ✅ Complete | Claude-Haiku chat classifier → pipeline name + params JSON |
| `orchestration/agents/{reactive,proactive,research,proposal_writer}` | ✅ Complete | All Claude-based; ADK/Gemini path in search_sub_agent.py (needs Gemini API enabled) |
| `orchestration/tools/` | ✅ Complete | 7 deterministic tools (no LLM): supplier_alternatives, compliance_gate, substitution_walker, bom_impact, price_benchmark, opportunity_ranker, rfq_formatter |
| `orchestration/pipelines/` | ✅ 5 pipelines | supplier_fallout, proactive_consolidation, new_ingredient_research, substitution_discovery, price_audit |
| **Endpoints** | ✅ 8 endpoints | POST /chat, POST /pipelines/run/{name}, GET /pipelines, GET /runs, GET /runs/{id}, GET /runs/{id}/stream (SSE), GET /proposals, POST /data-update |

---

## Current State

| Layer | Status | Notes |
|---|---|---|
| `schema/enriched_schema.sql` | ✅ v1.1 | 15 new columns; Supplier_Commercial.Confidence TEXT→REAL fixed |
| `db_enriched.sqlite` | ✅ v1.1 — all phases run | 125 SMILES (50.0%), 135 UNII (54.0%), 250 canonicals, 515 BOM, 126 compliance, 123 CO rows; Vitamin C → 33 cos |
| Phase 1 — Ingredient Identity | ✅ Complete | CID gap backfill: 20 new CIDs via UNII/name lookup; 2nd dedup pass merged 7 more pairs; dedup merge bug fixed |
| Phase 2 — BOM Quantities | ✅ Complete | 515 rows, 87/149 FG covered (58%); fingerprint match: brand+ingredient query + overlap≥2 |
| Phase 3 — Commercial/Compliance | ✅ Complete | 126 rows, 66 products, 9 cert types; fixed stmt.notes key + Phase 2 label reuse |
| Phase 4 — Reasoning/Proposals | ⏳ Phase A fixes done, proposals blocked | 123 CO rows; scorer correct; proposals need ANTHROPIC_API_KEY; Grade_Flag populated, substitution edges=30, compliance filter fixed |
| Phase A — Data Quality Fixes | ✅ Complete | Grade_Flag: 239/250 classified (11 unknown); substitution edges: 4→30; compliance status filter fixed ('implied' added); proposals TARGET=50 |
| `enrichment/sources/pubchem.py` | ✅ Implemented | get_isomeric_smiles() + get_unii_from_synonyms() + get_cid_by_name(); rate-limited (4.5 req/sec), cache-first |
| `enrichment/sources/dsld.py` | ✅ Implemented | DSLD v9, cached |
| `enrichment/sources/molport.py` | ✅ Stub | Graceful no-op if MOLPORT_API_KEY absent; CAS→SMILES→supplier chain |
| `enrichment/db_migrate_v11.py` | ✅ New | Idempotent v1.1 migration; called by db_bootstrap.py |
| `enrichment/backfill_phase1.py` | ✅ New | SMILES + UNII + MatchScore backfill; commits per-row to avoid DB lock |
| `enrichment/run_dedup.py` | ✅ New | UNII dedup + substitution seeding; run after backfill_unii |
| `enrichment/sources/rxnorm.py` | ❌ Missing | Low priority — narrow use (drug-class ingredients only) |
| `enrichment/sources/fdc.py` | ❌ Missing | Low priority — only useful for ~5 food-macro SKUs |
| `reasoning/consolidation_scorer.py` | ✅ Fixed + run | Formula: company×0.40 + bom×0.25 + fragmentation×0.20 + supplier_spread×0.15; 129 rows scored |
| `reasoning/substitution_graph.py` | ✅ Re-run | 30 edges (18 rules); fix_substitution_rules.py updated 20 Name_A/B aliases; 18 still unresolved (no canonical match) |
| `enrichment/enrichers/grade_classifier.py` | ✅ New + run | Heuristic classifier; 239/250 classified; supplement:117, food:62, excipient:32, sweetener:15, flavor:13, unknown:11 |
| `scripts/fix_substitution_rules.py` | ✅ New + run | Alias-table UPDATE for Ingredient_Substitution_Rule; 20 updated, 2 already-correct, 18 unresolved |
| `enrichment/enrichers/commercial_enricher.py` | ✅ _enrich_pair wired | MolportClient integration complete; no-ops when MOLPORT_API_KEY absent |

---

## Pipeline Sequence

```
db_bootstrap.py → Phase 1 → Phase 2 → Phase 3 → Phase 4
```
Each phase is idempotent. Re-run any phase safely. Cache hit rate ≥ 90% on second run.

---

## Schema Delta: v1.0 → v1.1 (not yet applied)

Fields to add per PRD §7:
- `Ingredient_Canonical`: `UNII_Code`, `Molport_Id`, `FDC_Id`, `RxCUI`, `SMILES`, `Grade_Flag`
- `SKU_To_Canonical`: `MatchScore`
- `Supplier_Commercial`: fix `Confidence TEXT→REAL`; add `Price_Qty_KG`, `Purity_Pct`, `Purity_Qualifier`, `Grade_Unverified`, `Molport_Catalog_Id`, `Data_Freshness_Days`, `Country_Shipping`
- `BOM_Component_Quantity`: `ServingsPerContainer`, `OffMarket`, `DSLD_Label_Id`
- `Consolidation_Opportunity`: `Unique_SKU_Count`, `Score_Formula_Component`, `Score_LLM_Adjustment`, `Compliance_Feasible`
- `Product_Compliance`: `Off_Market_Warning`
- `Ingredient_Substitution`: `Caveats`

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
