# Agnes — Phase 4 Completion & Data Quality PRD

**File:** `Orchestration/PRDs/DATABASEFINETUNING.md`  
**Date:** 2026-04-18  
**Supersedes:** NextSessionBrief.md (handoff document — this is the authoritative spec)  
**Status:** Draft — ready for implementation

---

## 1. Executive Summary

Agnes has completed Phases 1–3: 250 canonical ingredients are identified, 515 BOM quantity rows are enriched, 126 compliance rows are populated, and 123 consolidation opportunities are scored. The pipeline is structurally sound but four data quality gaps prevent the system from being demo-ready for hackathon judges.

This PRD specifies the work required to close those gaps in priority order: (1) populate `Grade_Flag` for all 250 canonicals using a no-API heuristic classifier, (2) fix the 38/40 substitution rules that silently skip due to scientific-vs-common-name mismatch, (3) repair the compliance join in the judge-facing query that returns zero certs despite 126 rows of data, and (4) generate Phase 4 `Proposal_Text` narratives for the top-50 consolidation opportunities via the Claude API. A fifth gap — Molport commercial pricing — is gated on an external API key and is addressed as a conditional phase.

The MVP goal is a DB state where the hackathon judge query returns meaningful data across all columns: ingredient name, grade, SMILES presence, company count, consolidation score, priced suppliers (or disclaimer), and compliance certifications. Every scored consolidation opportunity in the top 10 must have a `Proposal_Text`.

---

## 2. Mission

**Make Agnes's SQLite knowledge graph demo-ready:** every enrichment column that judges will query must have signal, every proposal must have a narrative, and every data quality bug that would surface during a live demo must be fixed before the presentation.

### Core Principles

1. **No dark columns in the judge query** — `Grade_Flag`, `Proposal_Text`, and compliance cert counts must return real values for the top-10 opportunities.
2. **Idempotent fixes only** — every script must be safe to re-run without creating duplicates or overwriting manually corrected data.
3. **Evidence trails on everything** — any field set by a heuristic or LLM must record its `Source` and `Confidence`.
4. **Scientific names belong in rules, common names belong in canonicals** — substitution rules are updated to match canonical names, not the other way around.
5. **Proposals read Grade_Flag** — Grade_Flag must be populated before running the proposal generator so proposals can reference ingredient grade in their reasoning.

---

## 3. Target Users

### Primary User: Hackathon Judge / Demo Reviewer
- Queries the DB directly via SQL or through a frontend view
- Expects to see a populated `Consolidation_Opportunity` table with readable `Proposal_Text`
- Will run the judge query from `NextSessionBrief.md §4` — it must return non-zero `certs` and non-zero `priced_suppliers` (or clearly show the pricing gap is a key-gating issue)
- Technical comfort: can read SQL output, expects professional data quality

### Secondary User: Agnes Pipeline Developer (you, this session)
- Needs clear file-level specs: which file to create, what function signatures, what DB columns to write
- Needs to know which operations are safe to re-run and which are destructive
- Must not need to resolve ambiguities about canonical names — the PRD provides the mapping table

### Pain Points Observed
- `Grade_Flag = 'unknown'` for all 250 canonicals makes ingredient classification invisible
- 38/40 substitution rules fire no edges — substitution intelligence is effectively zero
- Judge query compliance join broken — 126 rows of certification data invisible in the judge view
- `Proposal_Text` = NULL for all 123 opportunities — the core deliverable is missing
- Canonical names inconsistently cased (`SILICON DIOXIDE` vs `Vitamin C` vs `folic acid`) — cosmetic but visible in demos

---

## 4. MVP Scope

### Core Functionality
- ✅ Grade_Flag heuristic classifier — populate all 250 canonicals
- ✅ Substitution rule name fix — update 38 rule rows to match canonical names
- ✅ Compliance join fix — repair the judge query so `certs` counts correctly
- ✅ Phase 4 proposals — generate `Proposal_Text` + `Proposal_JSON` for top-50 COs
- ✅ Canonical display name normalization — title-case all-caps entries (SILICON DIOXIDE → Silicon Dioxide)

### Conditional (API-key gated)
- ✅ Molport commercial enrichment — Phase 3 re-run once `MOLPORT_API_KEY` is in `.env`
- ✅ Score_LLM_Adjustment — ±0.10 Claude adjustment for top-50 COs (part of proposal pass)

### Out of Scope
- ❌ RxNorm integration — narrow applicability, deferred
- ❌ USDA FDC integration — only 5 food macros affected, deferred
- ❌ Frontend / UI layer — out of scope per hackathon judging criteria ("UI polish is not a priority")
- ❌ Re-running Phase 1 ingredient normalizer — display name fix noted but not required for demo
- ❌ Scraping retailers for additional BOM data — Phase 2 at 58% coverage is above threshold
- ❌ ServingsPerContainer back-fill for null-unit BOM rows — data limitation of DSLD, not fixable without re-scraping

---

## 5. User Stories

**US-1: Grade classification**  
As a judge querying the knowledge graph, I want each ingredient to have a `Grade_Flag` (supplement / excipient / food / sweetener / flavor / unknown) so that I can filter consolidation opportunities by ingredient category and assess whether proposals make business sense.  
_Example: Vitamin C → `supplement`, Cellulose → `excipient`, Erythritol → `sweetener`, Gelatin → `food`._

**US-2: Substitution intelligence**  
As Agnes, I want substitution rules for Vitamin C forms (Ascorbic Acid / Sodium Ascorbate / Calcium Ascorbate) to resolve to actual canonical IDs so that `Ingredient_Substitution` edges are generated and proposals can reference viable substitutes.  
_Example: Rule 1 "Ascorbic Acid ↔ Sodium Ascorbate" should resolve to canonical IDs 3 and [SODIUM ASCORBATE id] and produce an edge in `Ingredient_Substitution`._

**US-3: Compliance visibility in proposals**  
As a demo viewer, I want the judge query to show how many certifications (GlutenFree, NSF, cGMP, etc.) are associated with each top-ranked ingredient so that compliance feasibility is visible alongside consolidation score.  
_Example: Vitamin C row should show `certs ≥ 1` because products containing Vitamin C have GlutenFree/NonGMO certs recorded in `Product_Compliance`._

**US-4: Proposal narrative generation**  
As a judge, I want to read a structured sourcing proposal for Vitamin C (top-ranked, score=0.893, 33 companies) that explains: how many companies buy it, what suppliers exist, what certifications are needed, what substitutes are available, and what the estimated consolidation value is.  
_Example: `Proposal_Text` in `Consolidation_Opportunity` row for Vitamin C should be a 2-3 paragraph narrative with evidence trail._

**US-5: Proposal JSON for programmatic use**  
As an agent consuming Agnes outputs, I want `Proposal_JSON` to contain a structured object with `ingredient`, `companies`, `suppliers`, `score`, `grade`, `substitutes`, `compliance_requirements`, and `recommended_action` keys so that downstream agents can parse proposals without NLP.

**US-6: Reliable re-runs**  
As a developer, I want every new script to be idempotent (safe to re-run) so that I can re-run individual phases after bug fixes without creating duplicate rows or corrupting existing data.

**US-7: Canonical name consistency**  
As a developer running SQL queries, I want canonical names to use consistent title-case so that `WHERE Name = 'Silicon Dioxide'` works without needing to handle the `SILICON DIOXIDE` variant.

---

## 6. Core Architecture & Patterns

### High-Level Approach
All changes write only to `db_enriched.sqlite`. `db.sqlite` remains read-only. Each new script follows the existing pattern: idempotent upsert, per-row commits, `Source` + `Confidence` on every written field.

### Directory Structure
```
enrichment/
  enrichers/
    grade_classifier.py        ← NEW: Step 1
    commercial_enricher.py     ← EXISTS: re-run after Molport key
    compliance_enricher.py     ← EXISTS
    quantity_enricher.py       ← EXISTS
reasoning/
  substitution_graph.py        ← PATCH: name resolution fix
  consolidation_scorer.py      ← EXISTS: already correct
  proposal_generator.py        ← EXISTS: verify + run
scripts/
  fix_substitution_rules.py    ← NEW: Step 2 — SQL update script
  fix_compliance_join.py       ← NEW: Step 3 — diagnose + patch judge query
  normalize_canonical_names.py ← NEW: Step 4 (optional, low priority)
```

### Key Design Patterns

**Pattern 1: Heuristic classifier with fallthrough**  
Grade classifier tries rules in priority order; first match wins; `unknown` is the explicit fallthrough (not an error).

**Pattern 2: SQL UPDATE not INSERT for rule fixes**  
`fix_substitution_rules.py` uses `UPDATE Ingredient_Substitution_Rule SET Name_A = ? WHERE Id = ?` — never deletes rule rows, just corrects the name fields.

**Pattern 3: Proposal generator reads before it writes**  
`proposal_generator.py` must query Grade_Flag, SMILES, substitution edges, and compliance certs before constructing the Claude prompt. All context goes into the prompt; no hallucinated data.

**Pattern 4: Score_LLM_Adjustment is bounded**  
Claude may only adjust `Consolidation_Score` by ±0.10. Final score = `Score_Formula_Component + Score_LLM_Adjustment`, clamped to [0.0, 1.0].

---

## 7. Features / Tool Specifications

### Feature 1: Grade Classifier (`enrichment/enrichers/grade_classifier.py`)

**Purpose:** Populate `Ingredient_Canonical.Grade_Flag` for all 250 rows using name + SMILES heuristics. No API calls.

**Classification rules (priority order):**

| Grade | Match Condition |
|---|---|
| `flavor` | Name contains: "flavor", "flavour", "Virginia Dare", "artificial flavor", "natural flavor" |
| `sweetener` | Name matches: Sucralose, Erythritol, Sorbitol, Stevia, Monk Fruit, Sucrose, Xylitol, Maltitol, Saccharin, Aspartame |
| `excipient` | Name contains any of: Cellulose, Silicon Dioxide, Magnesium Stearate, Croscarmellose, HPMC, Hypromellose, Methylcellulose, Starch (when not "Potato Starch Extract"), Talc, Silica, Hydroxypropyl, Carrageenan, Carnauba, Shellac, Titanium Dioxide, Rice Flour (filler context) |
| `food` | Name contains any of: Protein, Gelatin, Collagen, Maltodextrin, Inulin, Lecithin, Pectin, Xanthan, Guar Gum, Sunflower Oil, Coconut Oil, MCT, Cocoa, Whey, Casein, Rice Bran |
| `supplement` | Has SMILES present AND name contains any vitamin/mineral/amino acid keyword: Vitamin, Zinc, Magnesium, Calcium, Iron, Potassium, Selenium, Chromium, Copper, Manganese, Iodine, Acid (as suffix in amino acid names), Cobalamin, Folate, Biotin, Niacin, Thiamin, Riboflavin, Pantothenic |
| `supplement` | Name is a known amino acid: Glycine, Lysine, Leucine, Isoleucine, Valine, Methionine, Phenylalanine, Tryptophan, Threonine, Histidine, Arginine, Glutamine, Taurine, Carnitine, Creatine, Beta-Alanine, Citrulline |
| `unknown` | No rule matched |

**Function signature:**
```python
def classify_grade(name: str, smiles: str | None) -> tuple[str, float]:
    """Returns (grade, confidence). Confidence=0.9 for keyword match, 0.7 for SMILES-only supplement."""
```

**DB write:**
```python
UPDATE Ingredient_Canonical SET Grade_Flag = ?, Source_Grade = 'heuristic', Confidence_Grade = ? WHERE Id = ?
```
Note: if `Source_Grade` / `Confidence_Grade` columns don't exist in schema, write only `Grade_Flag` and add a comment in the script. Check schema first.

**Validation query:**
```sql
SELECT Grade_Flag, COUNT(*) cnt FROM Ingredient_Canonical GROUP BY Grade_Flag ORDER BY cnt DESC;
-- Expect: < 50 'unknown' rows (20% threshold)
```

---

### Feature 2: Substitution Rule Name Fix (`scripts/fix_substitution_rules.py`)

**Purpose:** Update `Ingredient_Substitution_Rule.Name_A` and `Name_B` to exactly match `Ingredient_Canonical.Name` so `substitution_graph.py`'s COLLATE NOCASE lookup resolves them.

**Approach:** The script builds a mapping of scientific/alternate name → canonical name by:
1. Querying all canonical names
2. Applying a known-alias lookup table (hardcoded, see below)
3. Running UPDATE statements for each matched rule

**Known alias mapping (hardcoded in script):**

| Rule name | Canonical name |
|---|---|
| Ascorbic Acid | Vitamin C |
| Cholecalciferol | Vitamin D |
| Ergocalciferol | Vitamin D2 (verify exists, else skip) |
| d-Alpha Tocopherol | Tocopherols (verify — may need separate canonical) |
| dl-Alpha Tocopherol | Tocopherols |
| Mixed Tocopherols | Tocopherols |
| Folic Acid | folic acid (already matches — skip) |
| 5-MTHF | Folate |
| Methylfolate | Folate |
| Cyanocobalamin | Vitamin B12 (verify canonical name) |
| Methylcobalamin | Methylcobalamin (verify exists) |
| Adenosylcobalamin | Adenosylcobalamin (verify exists) |
| Magnesium Oxide | MAGNESIUM CARBONATE (verify — or skip if no oxide canonical) |
| Magnesium Citrate | Trimagnesium dicitrate (verify) |
| Magnesium Glycinate | MAGNESIUM GLYCINATE |
| Magnesium Malate | Magnesium malate |
| Calcium Carbonate | CALCIUM CARBONATE |
| Calcium Citrate | Calcium citrate |
| Zinc Gluconate | Zinc dust (verify — elemental vs salt) |
| Zinc Bisglycinate | Zinc glycinate (verify) |
| Pyridoxine HCl | Pyridoxine HCl (may already match) |
| Pyridoxal-5-Phosphate | (verify canonical exists) |
| Thiamine HCl | (verify canonical exists) |
| Thiamine Mononitrate | (verify canonical exists) |
| Riboflavin | (verify — may already match) |
| Niacinamide | Niacinamide (may already match) |
| Nicotinic Acid | (verify canonical) |

**Script behavior:**
- For each rule row, look up Name_A and Name_B in canonicals (COLLATE NOCASE exact match first)
- If match found → no change needed, skip
- If no match → look up in alias table → if alias resolves to a known canonical → UPDATE the rule row
- If alias table has no entry and no canonical match → log as UNRESOLVED, do not update
- Print a summary: `N rules updated, M rules already correct, K rules unresolved`
- Unresolved rules: print the Name_A/B so a human can add them to the alias table

**After running this script, re-run Phase 4 substitution graph:**
```bash
python enrichment/pipeline.py --phase 4 --step substitution
```

**Validation query:**
```sql
SELECT COUNT(*) FROM Ingredient_Substitution WHERE SubstitutionType IN ('identical','equivalent','partial');
-- Expect: > 10
```

---

### Feature 3: Compliance Join Fix

**Problem:** The judge query returns `certs=0` for every ingredient despite 126 `Product_Compliance` rows across 66 products.

**Diagnosis required:** Before writing any fix, the script must verify the join chain:
```sql
-- Step 1: Does SKU_To_Canonical.ProductId match Product_Compliance.ProductId type/format?
SELECT stc.ProductId, stc.CanonicalId, pc.ProductId, pc.Certification
FROM SKU_To_Canonical stc
JOIN Product_Compliance pc ON pc.ProductId = stc.ProductId
LIMIT 5;

-- Step 2: What are the ProductId formats in each table?
SELECT ProductId FROM SKU_To_Canonical LIMIT 3;
SELECT ProductId FROM Product_Compliance LIMIT 3;
```

**Likely fix:** The `Product_Compliance.ProductId` column may store a different ID than `SKU_To_Canonical.ProductId`. Check whether `Product_Compliance` joins to `Product.Id` or `Product.ExternalId` or `BOM.FinishedGoodId`. Trace the correct join path and update the judge query in `NextSessionBrief.md` and in `proposal_generator.py`.

**Document the corrected judge query here once verified:**
```sql
-- CORRECTED judge query (fill in after diagnosis):
SELECT ic.Name, ic.Grade_Flag, ic.SMILES IS NOT NULL as has_smiles,
       co.Company_Count, co.Consolidation_Score,
       COUNT(DISTINCT sc.SupplierId) as priced_suppliers,
       COUNT(DISTINCT pc.Certification) as certs
FROM Ingredient_Canonical ic
LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
LEFT JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
    -- TODO: correct join path to be determined by diagnosis
    SELECT [correct_fk] FROM [correct_table] WHERE [canonical_link] = ic.Id
)
GROUP BY ic.Id ORDER BY co.Consolidation_Score DESC LIMIT 10;
```

---

### Feature 4: Phase 4 Proposal Generator (`reasoning/proposal_generator.py`)

**Status:** File exists (~228 lines). Verify it reads Grade_Flag, substitution edges, and compliance certs before running. If any of these are missing from the context-building query, patch before running.

**Context the generator must assemble per CO:**
```python
{
  "ingredient": {
    "name": ic.Name,
    "grade": ic.Grade_Flag,          # must be populated first
    "smiles": ic.SMILES,
    "unii": ic.UNII_Code,
    "cas": ic.CAS_Number,
  },
  "consolidation": {
    "company_count": co.Company_Count,
    "sku_count": co.Unique_SKU_Count,
    "formula_score": co.Score_Formula_Component,
    "bom_count": co.BOM_Count,
    "current_supplier_count": co.Current_Supplier_Count,
  },
  "suppliers": [
    {"name": s.Name, "country": s.Country, "price_usd_kg": sc.Price_USD_Per_KG}
    for each Supplier_Commercial row  # may be empty if Molport key absent
  ],
  "real_suppliers": [
    {"name": s.Name}
    for each Supplier_Product row linking this ingredient
  ],
  "compliance": {
    "certifications": [list of distinct Certification values from Product_Compliance],
    "cert_count": int,
  },
  "substitutes": [
    {"name": ic2.Name, "type": is.SubstitutionType, "score": is.Score, "caveats": is.Caveats}
    for each Ingredient_Substitution edge
  ],
}
```

**Proposal_Text format (Claude output):**
- 2–3 paragraphs, plain text (no markdown inside)
- Paragraph 1: What this ingredient is, who buys it, consolidation opportunity size
- Paragraph 2: Recommended action — which suppliers to consolidate to, compliance requirements to maintain
- Paragraph 3: Substitution alternatives (if any), compliance caveats, pricing disclaimer if Molport data absent

**Proposal_JSON schema:**
```json
{
  "ingredient": "Vitamin C",
  "grade": "supplement",
  "company_count": 33,
  "consolidation_score": 0.8929,
  "recommended_action": "consolidate",
  "recommended_suppliers": ["Prinova", "Ingredion"],
  "compliance_requirements": ["GlutenFree", "NonGMO"],
  "substitutes": [
    {"name": "Sodium Ascorbate", "type": "equivalent", "caveats": "adds 131mg Na per 1000mg dose"}
  ],
  "pricing_available": false,
  "pricing_disclaimer": "No Molport pricing data; production volume pricing requires direct supplier negotiation.",
  "evidence_sources": ["PubChem", "DSLD", "db.sqlite Supplier_Product"]
}
```

**Model:** `claude-sonnet-4-6` (already configured in existing file — verify, do not downgrade to haiku for proposals)

**Run scope:** Top-50 by `Consolidation_Score`. Skip rows where `Proposal_Text IS NOT NULL` (idempotent).

**DB write:**
```sql
UPDATE Consolidation_Opportunity
SET Proposal_Text = ?, Proposal_JSON = ?, Score_LLM_Adjustment = ?, Generated_At = ?
WHERE Id = ?;
```

**Validation query:**
```sql
SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL;
-- Expect: >= 10 (top-10 minimum for MVP demo)
```

---

### Feature 5: Canonical Name Normalization (Optional, low priority)

**Problem:** `SILICON DIOXIDE`, `MAGNESIUM STEARATE`, `CALCIUM CARBONATE` are all-caps IUPAC artifacts. Looks unprofessional in demos.

**Fix:** `scripts/normalize_canonical_names.py` — title-cases names that are fully uppercase.

```python
# Rule: if name == name.upper() and len(name) > 3 → title_case it
# Exception: preserve acronyms like "HPMC", "MCT", "IU"
```

**This script must NOT be run before substitution rule fixes** — normalization changes canonical names, which would re-break any rule fixes that used the pre-normalization names.

---

## 8. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Database | SQLite | via `sqlite3` stdlib |
| LLM API | Anthropic Claude | `claude-sonnet-4-6` |
| Anthropic SDK | `anthropic` | latest in requirements.txt |
| Supplier pricing | Molport v3 API | (stub exists, key pending) |
| Environment | python-dotenv | `.env` file |

**No new dependencies required for Steps 1–3.** Step 4 (proposals) requires `ANTHROPIC_API_KEY` in `.env`. Step 5 (Molport) requires `MOLPORT_API_KEY`.

---

## 9. Security & Configuration

### Environment Variables Required
```bash
# .env (copy from .env.template)
ANTHROPIC_API_KEY=sk-ant-...      # Required for Phase 4 proposals
MOLPORT_API_KEY=...               # Required for Supplier_Commercial fill
DSLD_API_KEY=...                  # Already set (not needed for this PRD's scope)
```

### Configuration Notes
- `db.sqlite` is **read-only** — never open it with write mode
- All writes go to `db_enriched.sqlite` only
- Grade classifier and substitution rule fix scripts have **no API key dependency** — safe to run immediately
- Proposal generator must check for `ANTHROPIC_API_KEY` presence and exit gracefully with a clear error if absent (not silently skip)

### Security Scope
- ✅ No credentials in source code — all via `.env`
- ✅ No user-facing endpoints in this PRD (pure pipeline scripts)
- ❌ No auth/authz needed — local SQLite, no network exposure

---

## 10. API Specification

### Anthropic API (proposal_generator.py)

**Model:** `claude-sonnet-4-6`  
**Pattern:** Single-turn completion per ingredient (no streaming needed for DB writes)

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system="""You are Agnes, an AI supply chain analyst for CPG supplements.
Generate a sourcing consolidation proposal based on the structured data provided.
Output a JSON object matching the Proposal_JSON schema, followed by "---PROPOSAL---" and then
a 2-3 paragraph plain-text Proposal_Text narrative.
Never invent CAS numbers, prices, or supplier names not present in the input data.
If pricing data is absent, state this explicitly in the proposal.""",
    messages=[{"role": "user", "content": json.dumps(ingredient_context)}]
)
```

**Parse strategy:** Split on `---PROPOSAL---` delimiter; JSON before, text after.  
**Rate limiting:** 50 proposals × ~800 tokens each ≈ 40k tokens total. No rate-limit concerns.

### Molport API (commercial_enricher.py — existing stub)
Already implemented. See `Orchestration/References/APIS/molport-integration-guide.md`.  
Run trigger: `python enrichment/pipeline.py --phase 3` after setting `MOLPORT_API_KEY`.

---

## 11. Success Criteria

### MVP Success Definition
The hackathon judge can run the judge query and see:
- Non-null `Grade_Flag` for top-10 ingredients
- Non-null `Proposal_Text` for Vitamin C (rank 1)
- Non-zero `certs` count for at least 5 of the top-10 ingredients
- `Ingredient_Substitution` has > 10 edges (up from current 4)

### Functional Requirements
- ✅ `Grade_Flag != 'unknown'` for ≥ 80% of 250 canonicals (200+ rows)
- ✅ `Ingredient_Substitution` has ≥ 10 edges after rule name fix + re-run
- ✅ Judge query returns `certs > 0` for ingredients that have compliance-certified products
- ✅ `Proposal_Text IS NOT NULL` for ≥ 10 top-ranked consolidation opportunities
- ✅ `Proposal_JSON` is valid JSON parseable by `json.loads()`
- ✅ All scripts are idempotent (re-runnable without side effects)
- ✅ No `ANTHROPIC_API_KEY` hardcoded anywhere

### Quality Indicators
- Grade classifier unknown rate < 20% (< 50 of 250)
- Substitution rules unresolved < 10 (< 10 of 40)
- Proposal_Text for Vitamin C mentions: company count (33), grade (supplement), and at least one substitute
- No NULL `Consolidation_Score` rows after scorer re-run

---

## 12. Implementation Phases

### Phase A — No-API Fixes (run immediately, ~2 hours)

**Goal:** Close all data quality gaps that don't require external API keys.

**Deliverables:**
- ✅ `enrichment/enrichers/grade_classifier.py` created and run → Grade_Flag populated for 200+ canonicals
- ✅ `scripts/fix_substitution_rules.py` created and run → ≥ 25 rules updated to match canonical names
- ✅ Phase 4 substitution graph re-run → `Ingredient_Substitution` has ≥ 10 edges
- ✅ Compliance join diagnosed → root cause identified and documented
- ✅ Compliance join fixed in judge query + proposal_generator.py context builder

**Validation:**
```sql
SELECT Grade_Flag, COUNT(*) FROM Ingredient_Canonical GROUP BY Grade_Flag;
SELECT COUNT(*) FROM Ingredient_Substitution;
-- Run corrected judge query and verify certs > 0 for Vitamin C row
```

---

### Phase B — Proposal Generation (requires ANTHROPIC_API_KEY, ~1 hour)

**Goal:** Generate `Proposal_Text` + `Proposal_JSON` for top-50 consolidation opportunities.

**Pre-condition:** Phase A complete (Grade_Flag populated, compliance join fixed).

**Deliverables:**
- ✅ `proposal_generator.py` context builder verified to include Grade_Flag, substitutes, certs
- ✅ Proposal generator run for top-50 COs
- ✅ `Consolidation_Opportunity.Proposal_Text` populated for ≥ 50 rows
- ✅ `Score_LLM_Adjustment` populated (±0.10 per Claude assessment)
- ✅ Markdown report written to `outputs/proposals_[date].md`

**Validation:**
```sql
SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL;
-- Expect: >= 50
SELECT Name, co.Consolidation_Score, co.Proposal_Text IS NOT NULL as has_proposal
FROM Ingredient_Canonical ic JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
ORDER BY co.Consolidation_Score DESC LIMIT 5;
```

---

### Phase C — Commercial Enrichment (requires MOLPORT_API_KEY, ~1 hour)

**Goal:** Populate `Supplier_Commercial` with Molport pricing proxies for the 125 SMILES/CAS-bearing canonicals.

**Pre-condition:** `MOLPORT_API_KEY` obtained from molport.com (free registration, ~24h provisioning).

**Deliverables:**
- ✅ `MOLPORT_API_KEY` added to `.env`
- ✅ `python enrichment/pipeline.py --phase 3` run → `Supplier_Commercial` populated
- ✅ Judge query `priced_suppliers` column returns > 0 for molecules with CAS numbers
- ✅ Phase B proposals re-run (optional) to incorporate pricing into Proposal_Text

**Validation:**
```sql
SELECT COUNT(*) FROM Supplier_Commercial;
SELECT ic.Name, sc.Price_USD_Per_KG, sc.Price_Type FROM Supplier_Commercial sc
JOIN Ingredient_Canonical ic ON ic.Id = sc.CanonicalIngredientId LIMIT 10;
```

---

### Phase D — Optional Polish (~30 min)

**Goal:** Cosmetic improvements for demo quality.

**Deliverables:**
- ✅ `scripts/normalize_canonical_names.py` created and run → all-caps names title-cased
- ✅ Substitution rule aliases table complete (0 unresolved rules)
- ✅ `CLAUDE.md` updated with new DB state counts and phase completion status

---

## 13. Future Considerations

### Post-MVP (post-hackathon)

- **Agent orchestration layer (Stage 3):** FastAPI + Google ADK search agent that answers sourcing questions by querying Agnes's DB. The `Proposal_JSON` schema designed in this PRD is the structured output that agent would consume.
- **Frontend dashboard (Stage 4):** DAG canvas view (Alpine.js + SSE streaming) showing ingredient network, substitution graph edges, and consolidation opportunity rankings. See `REF-DAG-CANVAS-ALPINEJS.md`.
- **Score_LLM_Adjustment calibration:** After generating 50 proposals, analyze the distribution of LLM adjustments. If > 30% of adjustments are at the ±0.10 ceiling, widen the band to ±0.15.
- **RxNorm integration:** Only warranted if a Phase 1 coverage report shows > 10 unresolved drug-class ingredients. Current data is supplement-focused; defer.
- **USDA FDC integration:** Useful for Gelatin (FDC_Id), Whey Protein, Maltodextrin. Narrow but would fix the 5 food-macro no-CID canonicals. Low ROI for hackathon.

### Scaling Considerations
- `API_Response_Cache` table already exists — all PubChem/DSLD responses are cached. Proposal text should also be cached (check if `proposal_generator.py` uses the cache or re-generates on every run).
- If dataset grows beyond 250 canonicals, the grade classifier keyword list will need a vector-similarity fallback for novel ingredient names.

---

## 14. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| ANTHROPIC_API_KEY not available before demo | Medium | High | Phase A (grade + substitution fix) delivers visible improvement without it. Demo can show Vitamin C score + substitution edges even without Proposal_Text. |
| Compliance join unfixable without schema change | Low | Medium | Fallback: expose compliance data via a separate query in the demo, not the judge query. Document the join limitation clearly. |
| Grade classifier misclassifies > 20% | Low | Medium | Add a manual override table in the script (10-20 hardcoded corrections for known-tricky ingredients like "Protein" (food vs supplement)). |
| Substitution rule aliases still skip rules after fix | Medium | Low | 38 rules → even if 10 remain unresolved, the remaining 28 firing will produce 50+ edges, which is sufficient for demo. |
| Molport key takes > 24h to provision | Medium | Low | Gated to Phase C — doesn't block Phases A or B. Proposals include pricing disclaimer when data absent. |

---

## 15. Appendix

### Related Documents

| Document | Purpose |
|---|---|
| `Orchestration/PRDs/PRD.md` | Full Agnes PRD v1.1 — authoritative requirements |
| `Orchestration/PRDs/SQLBackendPRD.md` | Phases 1–3 completed scope |
| `Orchestration/Briefings by Agents for Agents/NextSessionBrief.md` | Handoff context (this PRD supersedes it) |
| `CLAUDE.md` | Current state table, known bugs, design decisions |
| `Orchestration/References/APIS/molport-integration-guide.md` | Molport API reference |
| `Orchestration/References/Tech/claude-api-patterns-guide.md` | Claude API patterns (prompt caching, tool use) |

### Key Validation Query (Judge Query — post-fix)

After completing all phases, this query must return meaningful data for every column:

```sql
SELECT ic.Name, ic.Grade_Flag, ic.SMILES IS NOT NULL as has_smiles,
       co.Company_Count, co.Consolidation_Score,
       co.Proposal_Text IS NOT NULL as has_proposal,
       COUNT(DISTINCT sc.SupplierId) as priced_suppliers,
       COUNT(DISTINCT pc.Certification) as certs
FROM Ingredient_Canonical ic
LEFT JOIN Consolidation_Opportunity co ON co.CanonicalIngredientId = ic.Id
LEFT JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
LEFT JOIN Product_Compliance pc ON pc.ProductId IN (
    -- Corrected join path (to be determined in Phase A Step 3)
    SELECT DISTINCT b.FinishedGoodId
    FROM BOM b
    JOIN BOM_Component bc ON bc.BOMId = b.Id
    JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
    WHERE stc.CanonicalId = ic.Id
)
GROUP BY ic.Id
ORDER BY co.Consolidation_Score DESC
LIMIT 10;
```

### Expected Final DB State (post all phases)

```
Ingredient_Canonical    250 rows  Grade_Flag: < 50 'unknown'
Ingredient_Substitution  50+ rows (up from 4)
Consolidation_Opportunity 123 rows, 50+ with Proposal_Text
Supplier_Commercial      100+ rows (after Molport key)
Product_Compliance       126 rows (unchanged, join fixed)
```
