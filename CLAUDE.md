# Agnes — Agent Working Reference

> **Self-maintenance rule:** After any meaningful change — phase run, schema edit, new finding, bug fix — update the relevant section below. Max 3 lines per entry. No prose.

---

## Current State

| Layer | Status | Notes |
|---|---|---|
| `schema/enriched_schema.sql` | ✅ v1.1 | 15 new columns; Supplier_Commercial.Confidence TEXT→REAL fixed |
| `db_enriched.sqlite` | ✅ v1.1 — all phases run | 112 SMILES, 44 UNII codes, 19 dedup merges, 515 BOM rows, 126 compliance rows |
| Phase 1 — Ingredient Identity | ✅ Complete | Display name fix + Sucralose guard; SMILES/UNII backfill done |
| Phase 2 — BOM Quantities | ✅ Complete | 515 rows, 87/149 FG covered (58%); fingerprint match: brand+ingredient query + overlap≥2 |
| Phase 3 — Commercial/Compliance | ✅ Complete | 126 rows, 66 products, 9 cert types; fixed stmt.notes key + Phase 2 label reuse |
| Phase 4 — Reasoning/Proposals | ⏳ Not started | Blocked by Phases 2+3 + ANTHROPIC_API_KEY in .env |
| `enrichment/sources/pubchem.py` | ✅ Implemented | Added get_isomeric_smiles(); rate-limited (4.5 req/sec), cache-first |
| `enrichment/sources/dsld.py` | ✅ Implemented | DSLD v9, cached |
| `enrichment/sources/molport.py` | ✅ Stub | Graceful no-op if MOLPORT_API_KEY absent; CAS→SMILES→supplier chain |
| `enrichment/db_migrate_v11.py` | ✅ New | Idempotent v1.1 migration; called by db_bootstrap.py |
| `enrichment/backfill_phase1.py` | ✅ New | SMILES + UNII + MatchScore backfill; commits per-row to avoid DB lock |
| `enrichment/run_dedup.py` | ✅ New | UNII dedup + substitution seeding; run after backfill_unii |
| `enrichment/sources/rxnorm.py` | ❌ Missing | Low priority — narrow use (drug-class ingredients only) |
| `enrichment/sources/fdc.py` | ❌ Missing | Low priority — only useful for ~5 food-macro SKUs |
| `reasoning/consolidation_scorer.py` | ⚠️ Formula mismatch | Uses compliance_homogeneity weight; PRD §8 uses fragmentation + supplier_spread |

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

**[PENDING DSLD KEY]** Vitamin C (25 co.) and Ascorbic Acid (17 co.) are still two canonical rows — `dedup_by_unii()` is coded in `fuzzy_matcher.py` but needs UNII_Code populated first (requires DSLD_API_KEY + `backfill_phase1.py`).

**[FIXED]** Display name fix added to `ingredient_normalizer.py` Tier 1: DSLD common name overrides PubChem IUPAC if ≤60 chars. Will apply on next Phase 1 re-run.

**[OBSERVED]** Gelatin and Calcium have no CAS — Gelatin is a protein mixture (no single PubChem CID); Calcium is form-ambiguous (carbonate vs citrate). FDC can resolve Gelatin FDC_Id; Calcium needs slug-level form disambiguation.

**[OBSERVED]** Sucralose CID 56038-13-2 surfacing in cluster report — likely a Phase 1 parser artifact on a non-ingredient SKU slug. Needs spot-check in `sku_parser.py`.

**[KNOWN LIMIT]** FDC: useful only for food-grade raw materials (whey, collagen, gelatin, maltodextrin, inulin). Not a Phase 2 finished-good fallback — FDC has sparse branded supplement coverage and wrong unit structure for BOM enrichment.

**[KNOWN LIMIT]** RxNorm: narrow applicability in this dataset. CPG supplement SKUs are not drug-class. Defer implementation until Phase 1 coverage report shows unresolved drug-class ingredients.

**[KNOWN LIMIT]** Molport pricing is research/lab scale (`Price_Type='retail_proxy'`). Always include disclaimer in Proposal_Text: "pricing indicative at research quantities — production volume requires direct negotiation."

**[ACHIEVED]** Phase 2 coverage 58% (87/149 FG); above 55% threshold. Retailer scraper not needed.

**[FIXED]** Compliance enricher stmt.notes key bug (was stmt.text); Phase 2 label reuse for products with numeric IDs; fingerprint_match now uses brand+ingredient query. All fixes validated.

**[FIXED]** DSLD client: added load_dotenv() so API key loads from .env in direct script runs.

**[DESIGN DECISION]** Consolidation scoring: Option C chosen (formula baseline + LLM adjustment ±0.10 for top-50 only). Formula weights: company_score 0.40, bom_score 0.25, fragmentation 0.20, supplier_spread 0.15.

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
