# Agnes — Next Session Brief
**Date written:** 2026-04-18  
**Purpose:** Handoff context for the next PRD writing session. Read this before touching anything.

---

## Current DB State (verified 2026-04-18)

```
db_enriched.sqlite — schema v1.1, all phases run
  Ingredient_Canonical    250 rows  (7 new merges today)
  SKU_To_Canonical        854 rows
  BOM_Component_Quantity  515 rows  (93% have Amount+Unit)
  Product_Compliance      126 rows  (66 products, 9 cert types)
  Consolidation_Opportunity 123 rows (all scored, 0 proposals)
  Supplier_Commercial       0 rows  ← main enrichment gap
  Ingredient_Substitution   4 rows  (2 identical, 2 equivalent)
  Ingredient_Substitution_Rule 40 rows (38/40 skipped — name mismatch bug)

  SMILES coverage:     125/250 = 50.0%  (hit target today)
  UNII coverage:       135/250 = 54.0%
  CAS_Number:          123/250 = 49%
  Grade_Flag:            0/250 = 0%     ← ALL 'unknown', never populated
```

---

## The 4 Remaining Enrichment Gaps (priority order)

### 1. Grade_Flag — ZERO populated, no API key needed
**All 250 canonicals have Grade_Flag = 'unknown'.** This field was never filled.  
Required values: `supplement`, `excipient`, `food`, `sweetener`, `flavor`, `unknown`  
**Approach:** Keyword heuristic classifier on ingredient name + SMILES presence.  
- `excipient`: Cellulose, Silicon Dioxide, Magnesium Stearate, Croscarmellose Sodium, HPMC, Hypromellose, Methylcellulose, Starch, Talc
- `supplement`: anything with a SMILES + is a vitamin/mineral/amino acid (Vitamin C, Zinc, Magnesium Citrate, Biotin, etc.)
- `food`: proteins, fibers, gums, extracts (Gelatin, Whey Protein, Maltodextrin, Xanthan Gum, Sunflower Lecithin, Cocoa powder, Inulin)
- `sweetener`: Sucralose, Erythritol, Sorbitol, Stevia extract, Monk Fruit, Sucrose
- `flavor`: Natural and Artificial flavors, Artificial flavor, Virginia Dare entries

**File to create:** `enrichment/enrichers/grade_classifier.py`  
**Runs without any API key. Should be done before Phase 4 proposals.**

---

### 2. Supplier_Commercial pricing — needs MOLPORT_API_KEY
**0 rows. Every price/purity/spec column is empty.**  
The `Supplier_Commercial` table has the right schema:
- `Price_USD_Per_KG`, `Purity_Pct`, `MOQ_KG`, `Lead_Time_Days`, `Country_Shipping`, `Molport_Catalog_Id`

**Key facts:**
- Molport is FREE to register (molport.com → Profile → API Keys, ~24h provisioning)
- 10,000 requests/month free tier — enough for all 125 CAS/SMILES-bearing canonicals (~500 requests with caching)
- Coverage: ~125 discrete molecules with SMILES/CAS will resolve; ~125 extracts/polymers/proteins will not
- All prices are **research/lab-scale only** — set `Price_Type='retail_proxy'`, always disclaim in proposals
- The stub `enrichment/sources/molport.py` is already implemented and wired; it no-ops if key absent
- Run: `python enrichment/pipeline.py --phase 3` once key is in `.env` as `MOLPORT_API_KEY`

**Important note on existing supplier data:**  
`db.sqlite` already has 40 real industrial-scale suppliers (Cargill, ADM, Prinova, Ingredion, etc.) with 1,606 supplier→ingredient links in `Supplier_Product`. These have NO pricing — just relationships. Molport adds pricing proxies; it does NOT replace these real suppliers.

---

### 3. Ingredient_Substitution rules — name mismatch bug
**38/40 curated rules are silently skipped** because `Ingredient_Substitution_Rule.Name_A/B` uses names like "Cholecalciferol" while `Ingredient_Canonical.Name` stores "Vitamin D".

**Fix options (pick one):**
- A) Update the 40 rule rows to match exact canonical names in DB (SQL update)
- B) Change `substitution_graph.py` to use fuzzy matching instead of exact COLLATE NOCASE

Option A is safer — rules should be authoritative. Check each rule name against canonicals first.  
**File:** `reasoning/substitution_graph.py` + `Ingredient_Substitution_Rule` table rows.

---

### 4. Phase 4 Proposals — needs ANTHROPIC_API_KEY
**0 proposals generated.** 123 CO rows are scored and ranked, waiting.  
Formula scorer is working: Vitamin C at top (score=0.893, 33 companies).  
LLM pass (Option C from design decision): top-50 get ±0.10 score adjustment + Proposal_Text narrative.  
**File:** `reasoning/proposal_generator.py` (check if exists or needs creation).  
Run: set `ANTHROPIC_API_KEY` in `.env`, then trigger Phase 4.

---

## What the Next PRD Should Specify

The SQLBackendPRD.md covered Phases 1–3 completion. The next PRD should cover:

**Title suggestion:** "Agnes — Phase 4 Completion & Data Quality PRD"

**Scope:**
1. Grade_Flag classification (Step 1 — no API, implement immediately)
2. Molport commercial enrichment (Step 2 — when key arrives)
3. Substitution rule name fix (Step 3 — SQL + code)
4. Proposal generator spec (Step 4 — LLM pass over top-50 COs)
5. Agent orchestration readiness check (Step 5 — what does an agent need to query to answer a sourcing question?)

**Key design decision to make in the PRD:**  
The proposal generator needs a spec: what does a good `Proposal_Text` look like? What fields does it read (CO score, Grade_Flag, BOM amounts, compliance gaps, Molport pricing, substitution alternatives)? What JSON schema goes in `Proposal_JSON`?

**Validation queries to define:**
```sql
-- Grade_Flag populated
SELECT Grade_Flag, COUNT(*) FROM Ingredient_Canonical GROUP BY Grade_Flag;
-- Expect: no 'unknown' rows, or < 20% unknown

-- Substitution rules firing
SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType IN ('identical','equivalent');
-- Expect: > 10

-- Proposals generated  
SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL;
-- Expect: >= 10 (top-10 at minimum for MVP demo)

-- Full enrichment view (the judge query)
SELECT ic.Name, ic.Grade_Flag, ic.SMILES IS NOT NULL as has_smiles,
       co.Company_Count, co.Consolidation_Score,
       COUNT(DISTINCT sc.SupplierId) as priced_suppliers,
       COUNT(DISTINCT pc.Certification) as certs
FROM Ingredient_Canonical ic
LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
LEFT JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
    SELECT ProductId FROM SKU_To_Canonical WHERE CanonicalId = ic.Id
)
GROUP BY ic.Id ORDER BY co.Consolidation_Score DESC LIMIT 10;
```

---

## Key Files the PRD Author Should Read

| File | Why |
|---|---|
| `Orchestration/PRDs/SQLBackendPRD.md` | Completed scope — don't re-spec what's done |
| `Orchestration/PRDs/PRD.md` | Full Agnes PRD, Phase 4 spec in §8-9 |
| `reasoning/consolidation_scorer.py` | Formula already implemented; PRD should build on it |
| `reasoning/substitution_graph.py` | Seeding logic; name mismatch bug here |
| `enrichment/sources/molport.py` | Already implemented; just needs key |
| `enrichment/pipeline.py` | Understand how phases are invoked |
| `schema/enriched_schema.sql` | Know what columns exist before speccing new ones |
| `CLAUDE.md` | Current state table + Arcs (known bugs and decisions) |

---

## Non-Obvious Facts That Will Save Time

1. **`Supplier_Product` in `db.sqlite` ≠ `Supplier_Commercial` in `db_enriched.sqlite`.**  
   `Supplier_Product` = 40 real CPG suppliers, relationship only, no price.  
   `Supplier_Commercial` = Molport pricing, currently empty.  
   Both matter. Don't confuse them.

2. **The CAS_Number column in Ingredient_Canonical sometimes stores UNII codes**, not real CAS numbers. This happened during the UNII backfill. Verify with `SELECT CAS_Number FROM Ingredient_Canonical WHERE CAS_Number NOT LIKE '%-%-_'` — anything that doesn't match CAS format `NNNNN-NN-N` is a misclassified UNII.

3. **dedup_by_unii() is now idempotent AND field-copying.** Fixed today: merged rows now copy PubChem_CID, SMILES, CAS_Number from dropped row to kept row. Safe to re-run after any new UNII backfill pass.

4. **BOM amounts are per-serving, not per-container.** `Amount + Unit` = e.g. "20 mg per tablet". `ServingsPerContainer` tells you how many tablets. To get total ingredient per SKU: `Amount × ServingsPerContainer`.

5. **The 3 remaining UNII dups are intentional.** Chrome/Chromium nicotinate, Magnesium/Magnesia, Zinc/Zinc glycinate — all have CAS mismatch so the guard correctly skips them. Do not attempt to force-merge.

6. **Vitamin C shows 33 companies, not 42.** After dedup, many companies were buying both "Vitamin C" and "l-ascorbic acid" from the same supplier — they deduplicated to 33 unique companies, not 25+17=42. This is correct.
