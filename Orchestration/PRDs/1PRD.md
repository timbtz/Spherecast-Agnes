# Agnes — Product Requirements Document

**Version:** 1.1  
**Date:** 2026-04-18  
**Status:** Active — supersedes all prior drafts  
**Owner:** timbtz

---

## 1. Executive Summary

Agnes is an AI-powered supply chain intelligence system built for the Spherecast Q-Hack challenge. It ingests a real-world CPG supplement procurement dataset — 61 companies, 1,025 SKUs, 149 bill-of-materials records, 40 suppliers, and 1,633 supplier-product mappings — and enriches it with external data from NIH DSLD, PubChem, USDA FoodData Central, Molport, and web sources to produce a polished analytical database that supports sourcing consolidation and substitution reasoning.

The core business problem is fragmented purchasing: the same ingredient (e.g., silicon dioxide) appears under different SKU slugs across companies, preventing procurement teams from seeing true combined volume and negotiating leverage. Agnes resolves ingredient identities across fragmented slugs, maps them to canonical chemical identities with regulatory cross-references (UNII, CAS, PubChem CID), enriches BOM quantities from supplement label databases, attaches commercial data (pricing, MOQ, lead times) from chemical marketplaces, and scores compliance requirements per product. On top of this enriched database, a reasoning layer proposes consolidation opportunities with evidence trails.

**MVP goal:** A fully-populated `db_enriched.sqlite` covering ≥ 70% of the 876 raw-material SKUs with canonical ingredient identity and ≥ 40% with at least one commercial data point, plus a set of ranked consolidation proposals with LLM-generated justifications — all presentable in a hackathon demo context.

---

## 2. Mission

**Agnes exists to make fragmented, incomplete CPG supply chain data actionable so that sourcing analysts can make defensible consolidation decisions with full evidence trails.**

### Core Principles

1. **Evidence over assertion** — every field written by Agnes carries `source` and `confidence`. No silent guesses.
2. **Idempotency** — any pipeline phase can re-run without corrupting prior results. `INSERT OR REPLACE` everywhere.
3. **External APIs are fallible** — cache all responses; never re-fetch what's stored; degrade gracefully to lower-confidence sources.
4. **Trustworthy recommendations** — a sourcing proposal is only as good as its weakest evidence link. Compliance gaps must be explicit, not hidden.
5. **No paid services** — the entire stack runs on free API tiers and open-source libraries.

---

## 3. Target Users

### Primary: Sourcing Analyst / Procurement Manager
- Works at a CPG company or central procurement hub
- Manages 30–200 raw material SKUs across multiple product lines
- Pain: can't see cross-company purchasing patterns; negotiates without volume leverage
- Needs: consolidated view of who buys what, at what price, under what compliance constraints
- Technical comfort: comfortable with dashboards and tabular data; not a developer

### Secondary: Hackathon Judges
- Evaluates reasoning quality, evidence trails, and business relevance
- Needs to see: clear problem framing, explainable AI outputs, defensible sourcing proposals
- Technical comfort: high — can inspect code, schemas, and model outputs

### Technical Operator (Internal)
- Runs pipeline phases, monitors enrichment quality
- Needs: clear phase-by-phase logging, confidence reports, re-run safety

---

## 4. MVP Scope

### ✅ In Scope

**Core Data Layer**
- ✅ Clone `db.sqlite` → `db_enriched.sqlite` with all original tables intact
- ✅ Apply `schema/enriched_schema.sql` to create all Agnes enrichment tables
- ✅ Phase 1: Resolve 876 raw-material SKUs to canonical ingredient identities (PubChem → DSLD → RxNorm → RapidFuzz)
- ✅ Phase 2: Enrich BOM quantities for ≥ 70% of matched finished goods via DSLD
- ✅ Phase 3: Attach commercial data (pricing, MOQ, lead time) from Molport for CAS-identified ingredients
- ✅ Phase 3: Attach compliance/certification data from DSLD label claims

**Schema Enrichment (v1.1 — see §7)**
- ✅ `Ingredient_Canonical` — canonical name, CAS, PubChem CID, UNII, SMILES, Molport ID, FDC ID, RxCUI, function tag, grade flag
- ✅ `SKU_To_Canonical` — mapping with match method, raw score, and calibrated confidence
- ✅ `Ingredient_Substitution` — substitution edges (identical/equivalent/partial/incompatible)
- ✅ `BOM_Component_Quantity` — serving amounts per BOM component with off-market flag
- ✅ `Supplier_Commercial` — price/MOQ/lead time/purity per supplier × canonical ingredient (Confidence as REAL)
- ✅ `Product_Compliance` — certification per finished product with off-market warning
- ✅ `Consolidation_Opportunity` — scored consolidation proposals with formula + LLM components
- ✅ `API_Response_Cache` — unified cache for all external API calls
- ✅ `Enrichment_Run_Log` — audit trail per phase step
- ✅ `Ingredient_Substitution_Rule` — curated substitution ground truth
- ✅ `Certification_Registry` — scraped NSF/USP/InformedSport records

**Reasoning Layer**
- ✅ Substitution graph builder (Phase 4)
- ✅ Consolidation scorer with hybrid formula + LLM justification (Option C, resolved)
- ✅ Proposal generator producing structured JSON + markdown narrative

**Pipeline Orchestration**
- ✅ `enrichment/pipeline.py` with `--phase 1/2/3/4` flags
- ✅ Per-phase enrichers and normalizers under `enrichment/`
- ✅ `enrichment/db_bootstrap.py` — clone + schema apply

### ❌ Out of Scope (MVP)

**Frontend**
- ❌ Consolidation dashboard UI (Stage 4)
- ❌ Proposal detail view
- ❌ DAG execution visualizer
- ❌ Wiki browser UI

**Agent Orchestration**
- ❌ Google ADK reactive agent (supplier fallout event handling)
- ❌ Google ADK proactive agent (scheduled consolidation runs)
- ❌ Research agent (new supplier discovery)
- ❌ LLM-wiki compound reasoning layer

**Data Sources (deferred)**
- ❌ Retailer scraping (iHerb, Walmart, Target) — Playwright fallback only if DSLD misses > 45%
- ❌ PureBulk / BulkSupplements scraping for pricing
- ❌ Alibaba supplier data
- ❌ Paid APIs (Apify, ChemAnalyst, ImportGenius, AWS Textract)

---

## 5. User Stories

### US-1: Ingredient Identity Resolution
**As a sourcing analyst**, I want Agnes to tell me that "silicon-dioxide," "silica," and "fumed-silica" across 17 companies are all the same ingredient (SiO₂, CAS 7631-86-9), so that I can see the true combined purchasing volume and negotiate accordingly.

*Implementation:* Phase 1 resolves SKU slugs → canonical name via PubChem CAS lookup → DSLD UNII cross-reference → RapidFuzz cluster merge.

### US-2: BOM Quantity Enrichment
**As a sourcing analyst**, I want to know how much Vitamin D3 is in each BOM component across all products using it, so that I can assess whether a cheaper supplier's product meets formulation requirements.

*Implementation:* Phase 2 queries DSLD for each finished-good product → extracts `ingredientRows` amounts → stores in `BOM_Component_Quantity` with serving size and unit.

### US-3: Commercial Data Attachment
**As a sourcing analyst**, I want to see market pricing and minimum order quantities for each canonical ingredient from at least one supplier, so that I can estimate potential savings from consolidation.

*Implementation:* Phase 3 looks up each ingredient's PubChem SMILES → queries Molport SMILES search → extracts supplier pricing tiers → stores in `Supplier_Commercial` with confidence level.

### US-4: Compliance Gap Detection
**As a sourcing analyst**, I want to know which certifications a finished product claims (NSF, USP, Kosher, Organic) so that any recommended supplier substitution can be validated against those requirements.

*Implementation:* Phase 3 parses DSLD `claims[]` and `statements[]` for finished products → stores per-product certifications in `Product_Compliance`.

### US-5: Consolidation Proposal
**As a sourcing analyst**, I want a ranked list of ingredients where consolidating suppliers across companies would yield the highest savings and is commercially feasible, so that I can prioritize my negotiation efforts.

*Implementation:* Phase 4 `ConsolidationScorer` computes hybrid score (company count × BOM count × supplier diversity × price spread) and `ProposalGenerator` writes LLM-justified markdown narrative per top-50 candidates.

### US-6: Substitution Validation
**As a sourcing analyst**, I want to know if Ingredient A can substitute for Ingredient B in a given product context, with a confidence score and evidence trail, so that I don't recommend a non-compliant switch.

*Implementation:* `Ingredient_Substitution` table populated by curated rules + Phase 1 UNII-cluster inference + Phase 4 LLM reasoning over form variants.

### US-7: Evidence Auditability
**As a hackathon judge**, I want to inspect exactly which source produced each data field in the enriched database — whether it came from PubChem, DSLD, Molport, or manual review — so that I can assess the trustworthiness of the sourcing proposals.

*Implementation:* Every Agnes-written field carries `source` (string enum) and `confidence` (float). `Enrichment_Run_Log` records every pipeline step attempt with method, status, and confidence.

---

## 6. Core Architecture & Patterns

### High-Level Architecture

```
db.sqlite (READ-ONLY source)
    │
    ▼
db_bootstrap.py ──── clone ──── db_enriched.sqlite
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                 ▼
              Phase 1             Phase 2           Phase 3
         Ingredient Identity   BOM Quantities   Commercial+Compliance
         PubChem/DSLD/RxNorm     DSLD labels     Molport/DSLD claims
                    │                │                 │
                    └────────────────┴─────────────────┘
                                     │
                                     ▼
                               Phase 4: Reasoning
                      SubstitutionGraph + ConsolidationScorer
                              + ProposalGenerator
                                     │
                                     ▼
                          Consolidation_Opportunity table
                          (ranked proposals, LLM narratives)
```

### Directory Structure

```
Agnes/
├── db.sqlite                        — READ-ONLY original dataset
├── db_enriched.sqlite               — All Agnes output (clone + enrich)
├── schema/
│   └── enriched_schema.sql          — DDL for Agnes-added tables (v1.1)
├── enrichment/
│   ├── db_bootstrap.py              — Clone db.sqlite + apply schema
│   ├── pipeline.py                  — Phase orchestrator (--phase 1/2/3/4)
│   ├── parsers/
│   │   └── sku_parser.py            — Slug → human-readable name
│   ├── normalizers/
│   │   ├── ingredient_normalizer.py — Phase 1 orchestrator
│   │   └── fuzzy_matcher.py         — RapidFuzz cluster builder
│   ├── sources/
│   │   ├── dsld.py                  — DSLD v9 client + cache
│   │   ├── pubchem.py               — PubChem PUG REST client + cache
│   │   └── [fdc.py, molport.py, rxnorm.py]  — Phase 3 sources
│   └── enrichers/
│       ├── quantity_enricher.py     — Phase 2
│       ├── commercial_enricher.py   — Phase 3 commercial
│       └── compliance_enricher.py   — Phase 3 compliance
├── reasoning/
│   ├── substitution_graph.py        — Phase 4: build substitution edges
│   ├── consolidation_scorer.py      — Phase 4: score consolidation candidates
│   └── proposal_generator.py        — Phase 4: LLM narrative generation
├── Orchestration/
│   ├── PRDs/
│   │   ├── PRD.md                   — This document
│   │   └── meta-workflow.md         — Implementation workflow guide
│   ├── References/                  — API integration guides (live-tested)
│   └── Data/
│       └── Spherecast/              — Challenge brief + README
└── requirements.txt
```

### Key Design Patterns

**Tiered Resolution:** Every enrichment step tries sources in priority order, stops at a confidence threshold (0.85), and falls back gracefully. Never fails silently — always records attempt in `Enrichment_Run_Log`.

**Cache-First:** All external API responses stored in `API_Response_Cache` keyed by `(Source, Cache_Key)`. Re-runs hit the cache; only stale entries (past TTL_Days) trigger network calls.

**Source + Confidence on Every Field:** Agnes never writes a value without tagging it. Every `INSERT` includes `source` and `confidence`.

**Idempotent Writes:** All `INSERT` statements use `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE`. Running a phase twice produces the same result.

---

## 7. Enriched Schema — Full Specification (v1.1)

This section is the authoritative schema design. `schema/enriched_schema.sql` must match this spec exactly.

### Original Tables (Read-Only Reference)

```
Company         — 61 rows   (Id, Name)
Product         — 1025 rows (Id, SKU, CompanyId, Type)
                  Type = 'raw-material' | 'finished-good'
BOM             — 149 rows  (Id, ProducedProductId)
BOM_Component   — 1528 rows (BOMId, ConsumedProductId)
Supplier        — 40 rows   (Id, Name)
Supplier_Product — 1633 rows (SupplierId, ProductId)
```

Raw-material products: 876 (Type='raw-material')  
Finished-good products: 149 (Type='finished-good', each has a BOM)

### Phase 1: Ingredient Identity Tables

#### `Ingredient_Canonical`

```sql
CREATE TABLE IF NOT EXISTS Ingredient_Canonical (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    Name                TEXT    NOT NULL,
    CAS_Number          TEXT,                      -- "557-04-0"; from PubChem synonyms
    PubChem_CID         INTEGER,                   -- 11177
    UNII_Code           TEXT,                      -- FDA UNII from DSLD (e.g. "ETJ7Z6XBU4")
    Molport_Id          TEXT,                      -- "Molport-000-871-563"; populated Phase 1
    FDC_Id              INTEGER,                   -- USDA FDC fdcId (food-grade only)
    RxCUI               TEXT,                      -- RxNorm concept ID (drug-class only)
    IUPAC_Name          TEXT,
    Molecular_Formula   TEXT,
    SMILES              TEXT,                      -- canonical SMILES from PubChem; required for Molport
    Function            TEXT,                      -- "excipient:lubricant|nutrient:vitamin|nutrient:mineral|protein|botanical"
    Grade_Flag          TEXT DEFAULT 'unknown',    -- "food|pharma|reagent|unknown"
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    Sources             TEXT    NOT NULL DEFAULT '[]'
);
```

**SMILES is critical:** Molport's primary search is SMILES-based. Must be populated in Phase 1 alongside PubChem CID — not deferred to Phase 3.

**UNII_Code:** FDA's authoritative cross-reference. Resolves "silicon-dioxide" vs "silica" (both → `ETJ7Z6XBU4`). Sourced from DSLD `ingredientRows[].uniiCode`.

#### `SKU_To_Canonical`

```sql
CREATE TABLE IF NOT EXISTS SKU_To_Canonical (
    ProductId           INTEGER NOT NULL,
    CanonicalId         INTEGER NOT NULL,
    ExtractedName       TEXT,
    MatchMethod         TEXT,                      -- pubchem|dsld|rxnorm|fdc|fuzzy|manual
    MatchScore          REAL,                      -- raw similarity score before calibration
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    CreatedAt           TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ProductId),
    FOREIGN KEY (ProductId)   REFERENCES Product(Id),
    FOREIGN KEY (CanonicalId) REFERENCES Ingredient_Canonical(Id)
);
```

#### `Ingredient_Substitution`

```sql
CREATE TABLE IF NOT EXISTS Ingredient_Substitution (
    IngredientAId       INTEGER NOT NULL,
    IngredientBId       INTEGER NOT NULL,
    SubstitutionType    TEXT    NOT NULL,  -- identical|equivalent|partial|incompatible
    Score               REAL    NOT NULL DEFAULT 0.0,
    Notes               TEXT,
    Caveats             TEXT,             -- bioavailability, grade, form differences
    Sources             TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (IngredientAId, IngredientBId),
    FOREIGN KEY (IngredientAId) REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (IngredientBId) REFERENCES Ingredient_Canonical(Id)
);
```

Substitution type semantics:
- `identical`: Same chemical, different name/slug only
- `equivalent`: Same function, different form; requires compliance review
- `partial`: Functional overlap but context-dependent; requires formulator sign-off
- `incompatible`: Confirmed non-substitutable

### Phase 2: BOM Quantity Table

#### `BOM_Component_Quantity`

```sql
CREATE TABLE IF NOT EXISTS BOM_Component_Quantity (
    BOMId               INTEGER NOT NULL,
    ConsumedProductId   INTEGER NOT NULL,
    Amount              REAL,
    Unit                TEXT,                      -- mg|IU|mcg|g|%DV|CFU|ml
    PerServing          REAL,
    ServingUnit         TEXT,                      -- "capsule"|"tablet"|"scoop"|"ml"
    ServingsPerContainer REAL,
    OffMarket           INTEGER,                   -- 0|1 from DSLD; 1 = label may be discontinued
    DSLD_Label_Id       TEXT,                      -- DSLD label ID used; enables re-fetch
    Source              TEXT,                      -- dsld|iherb|walmart|vitacost|manual
    Source_URL          TEXT,
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (BOMId, ConsumedProductId),
    FOREIGN KEY (BOMId)             REFERENCES BOM(Id),
    FOREIGN KEY (ConsumedProductId) REFERENCES Product(Id)
);
```

`OffMarket=1` labels are valid for Phase 2 quantity enrichment (formulations rarely change) but must NOT be used for Phase 3 compliance status.

### Phase 3: Commercial & Compliance Tables

#### `Supplier_Commercial`

```sql
CREATE TABLE IF NOT EXISTS Supplier_Commercial (
    SupplierId              INTEGER NOT NULL,
    CanonicalIngredientId   INTEGER NOT NULL,
    Price_USD_Per_KG        REAL,
    Price_Qty_KG            REAL,                  -- quantity tier at which price was quoted
    MOQ_KG                  REAL,
    Lead_Time_Days          INTEGER,
    Country_Origin          TEXT,                  -- ISO 3166-1 alpha-2
    Country_Shipping        TEXT,
    Purity_Pct              REAL,                  -- e.g. 98.0 for ">98%"
    Purity_Qualifier        TEXT,                  -- ">"|"~"|"="|null
    Grade_Unverified        INTEGER NOT NULL DEFAULT 1,  -- 1 until COA confirms grade
    Price_Type              TEXT,                  -- retail_proxy|wholesale|spot|quoted
    Price_Source            TEXT,                  -- molport|purebulk|alibaba|bulksupplements|manual
    Confidence              REAL    NOT NULL DEFAULT 0.0,  -- NOTE: was TEXT in v1.0 (bug fix)
    Source_URL              TEXT,
    Molport_Catalog_Id      TEXT,
    Data_Freshness_Days     INTEGER,               -- days since Molport "Last Update Date"
    Last_Updated            TEXT,
    PRIMARY KEY (SupplierId, CanonicalIngredientId),
    FOREIGN KEY (SupplierId)            REFERENCES Supplier(Id),
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);
```

**Bug fix from v1.0:** `Confidence` was `TEXT` — corrected to `REAL`.

All Molport prices tagged as `Price_Type='retail_proxy'`. Purity data tagged `Grade_Unverified=1` by default.

#### `Product_Compliance`

```sql
CREATE TABLE IF NOT EXISTS Product_Compliance (
    ProductId           INTEGER NOT NULL,
    Certification       TEXT    NOT NULL,
    -- NSF|USP|InformedSport|BSCG|Organic|NonGMO|Kosher|GlutenFree|Vegan|Halal|cGMP
    Status              TEXT,
    -- confirmed|claimed|implied|not_required|unknown
    Evidence_URL        TEXT,
    Verified_Date       TEXT,
    Source              TEXT,   -- dsld_claims|dsld_statements|retailer_badge|label_text|manual
    Off_Market_Warning  INTEGER NOT NULL DEFAULT 0,  -- 1 if sourced from offMarket=1 label
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (ProductId, Certification),
    FOREIGN KEY (ProductId) REFERENCES Product(Id)
);
```

### Phase 4: Reasoning & Proposals

#### `Consolidation_Opportunity`

```sql
CREATE TABLE IF NOT EXISTS Consolidation_Opportunity (
    Id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId       INTEGER NOT NULL,
    Company_Count               INTEGER NOT NULL DEFAULT 0,
    BOM_Count                   INTEGER NOT NULL DEFAULT 0,
    Current_Supplier_Count      INTEGER NOT NULL DEFAULT 0,
    Unique_SKU_Count            INTEGER NOT NULL DEFAULT 0,   -- distinct slugs pre-canonicalization
    Consolidation_Score         REAL    NOT NULL DEFAULT 0.0, -- 0.0–1.0 hybrid score
    Score_Formula_Component     REAL,
    Score_LLM_Adjustment        REAL,                         -- delta in [-0.10, +0.10]
    Recommended_SupplierId      INTEGER,
    Estimated_Savings_Narrative TEXT,
    Compliance_Gap              TEXT,                         -- JSON array of unmet cert requirements
    Compliance_Feasible         INTEGER,                      -- 1=feasible|0=blocked|null=unassessed
    Proposal_Text               TEXT,                         -- LLM markdown narrative
    Proposal_JSON               TEXT,                         -- structured JSON proposal
    Generated_At                TEXT,
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (Recommended_SupplierId) REFERENCES Supplier(Id)
);
```

### Infrastructure Tables

#### `API_Response_Cache`

```sql
CREATE TABLE IF NOT EXISTS API_Response_Cache (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Source      TEXT    NOT NULL,  -- pubchem|dsld|fdc|rxnorm|openfda|molport|google_search
    Cache_Key   TEXT    NOT NULL,
    Response    TEXT,              -- raw JSON (NULL = confirmed no-match)
    Fetched_At  TEXT    NOT NULL DEFAULT (datetime('now')),
    TTL_Days    INTEGER NOT NULL DEFAULT 30,
    UNIQUE (Source, Cache_Key)
);
```

#### `Enrichment_Run_Log`

```sql
CREATE TABLE IF NOT EXISTS Enrichment_Run_Log (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ProductId   INTEGER,
    Phase       INTEGER NOT NULL,
    Step        TEXT    NOT NULL,  -- "pubchem_lookup"|"dsld_search"|"molport_smiles"|...
    Status      TEXT    NOT NULL,  -- success|cache_hit|fallback|skipped|error|no_match
    Confidence  REAL,
    Method      TEXT,
    Error_Msg   TEXT,
    Run_At      TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

#### `Ingredient_Substitution_Rule`

```sql
CREATE TABLE IF NOT EXISTS Ingredient_Substitution_Rule (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Name_A          TEXT    NOT NULL,
    Name_B          TEXT    NOT NULL,
    Rule_Type       TEXT    NOT NULL,  -- identical|equivalent|partial
    Confidence      REAL    NOT NULL,
    Justification   TEXT    NOT NULL,
    Caveats         TEXT,
    Source          TEXT    NOT NULL DEFAULT 'curated'
);
```

#### `Certification_Registry`

```sql
CREATE TABLE IF NOT EXISTS Certification_Registry (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Certifier       TEXT    NOT NULL,  -- NSF|USP|InformedSport|BSCG
    Entity_Name     TEXT    NOT NULL,
    Entity_Type     TEXT    NOT NULL,  -- product|supplier|ingredient
    Cert_Id         TEXT,
    Verified_At     TEXT    NOT NULL DEFAULT (datetime('now')),
    Source_URL      TEXT,
    Raw_Data        TEXT
);
```

---

## 8. Enrichment Pipeline — Phase Specifications

### Phase 1: Ingredient Identity (most critical)

**Input:** All Products with `Type='raw-material'` (876 rows)  
**Output:** `Ingredient_Canonical` + `SKU_To_Canonical` populated

**Resolution tier order:**

| Tier | Source | Confidence | When to use |
|---|---|---|---|
| 1 | PubChem | 0.97 (CAS) / 0.80 (name only) | Always try first |
| 2 | NIH DSLD v9 | 0.88 (UNII) / 0.65–0.84 (name) | When PubChem < 0.85 |
| 3 | RxNorm | 0.85 | Drug-class ingredients |
| 4 | USDA FDC | 0.55–0.70 | Food-grade macroingredients only |
| 5 | RapidFuzz | 0.70 | Against already-resolved canonicals |
| 6 | Manual flag | 0.0–0.30 | Complex botanicals, proprietary blends |

**Stop condition:** First tier returning confidence ≥ 0.85 wins. Log all attempted tiers.

**SMILES population:** Immediately after PubChem returns a CID, fetch and cache `IsomericSMILES` in `Ingredient_Canonical.SMILES`. Required for Phase 3 Molport lookups — do not defer.

**Expected coverage:** ~75–80% of 876 raw-material SKUs mapped with confidence ≥ 0.65.

### Phase 2: BOM Quantity Enrichment

**Input:** 149 BOMs (finished goods) × their BOM_Component rows (1,528)  
**Output:** `BOM_Component_Quantity` for ≥ 70% of matched components

**Strategy:**
1. For each BOM, look up Company name + Product name
2. Search DSLD with `{brand} {product}` via `score_dsld_hit()` (partial_ratio brand 0.4 + token_set_ratio name 0.6)
3. If score ≥ 0.65: extract `ingredientRows` → match to BOM components by canonical name
4. Use `offMarket=0` labels preferentially; accept `offMarket=1` with `Off_Market_Warning=1`
5. If DSLD misses: log `dsld_no_match`; browser-scraping fallback only if total DSLD coverage < 55%

Known brand name variants in DSLD: `NOW Foods → NOW`, `Thorne → Thorne FX`.

**Expected DSLD coverage:** ~55–65% of 149 finished goods have a DSLD match.

### Phase 3: Commercial & Compliance Enrichment

#### Commercial (Molport → `Supplier_Commercial`)

**Lookup chain per CAS-identified ingredient:**
```
1. Check API_Response_Cache (source='molport') — use if fresh (< 30 days)
2. Try CAS-based load: GET /api/molecule/load?molecule={cas}&apikey=...
3. If CAS fails: fetch SMILES from Ingredient_Canonical; POST /api/chemical-search/search
4. GET /api/molecule/load for Molport ID → full supplier + pricing
5. Flatten Suppliers[].Catalogue[].Packings[] → Supplier_Commercial rows
6. Fuzzy-match Molport supplier names vs Agnes Supplier.Name (partial_ratio ≥ 70)
7. Convert all prices to USD; store Purity_Pct + Purity_Qualifier; tag Grade_Unverified=1
8. Compute Data_Freshness_Days from Catalogue[].Last Update Date
```

**Note:** Molport field names use Title Case with spaces ("Supplier Name", "Delivery Days"). Do not assume snake_case.

#### Compliance (DSLD claims → `Product_Compliance`)

Certification signal map:
```python
CERT_SIGNAL_MAP = {
    "nsf": "NSF",
    "usp verified": "USP",
    "informed sport": "InformedSport",
    "informed choice": "InformedSport",
    "bscg": "BSCG",
    "organic": "Organic",
    "non-gmo": "NonGMO",
    "kosher": "Kosher",
    "gluten-free": "GlutenFree",
    "vegan": "Vegan",
    "halal": "Halal",
    "cgmp": "cGMP",
}
```

Source priority: `dsld_claims` (from `claims[].langualCodeDescription`) → `dsld_statements` (from `statements[].text` via Claude extraction) → `manual`.

Filter to `offMarket=0` labels only for compliance; `offMarket=1` labels may have lapsed certifications.

### Phase 4: Reasoning & Proposals — Hybrid Scoring (Option C, resolved)

**Decision log:** Option C chosen. Formula gives deterministic baseline; LLM adds small adjustment and one-paragraph justification for top-50 candidates only.

**Formula sub-score:**
```python
def formula_score(company_count, bom_count, supplier_count, sku_count) -> float:
    company_score  = min(company_count / 20, 1.0)   # 20+ companies = max
    bom_score      = min(bom_count / 50, 1.0)
    fragmentation  = min(sku_count / max(company_count, 1) / 2, 1.0)
    supplier_spread = min(supplier_count / 5, 1.0)
    return (
        0.40 * company_score +
        0.25 * bom_score +
        0.20 * fragmentation +
        0.15 * supplier_spread
    )
```

**LLM adjustment (Claude, top-50 only):**
- Read enriched data for the canonical ingredient from `db_enriched.sqlite`
- Prompt: interpret price spread, compliance homogeneity, supplier geographic risk
- Output: delta float ∈ [-0.10, +0.10] + one-paragraph justification (stored in `Proposal_Text`)
- Final score = `formula_score + llm_adjustment` (clamped [0, 1])
- Store both components separately for auditability

**Proposal content per top-10 opportunity:**
- Ingredient identity card (name, CAS, function, UNII)
- Cluster summary (company count, BOM count, SKU variant count)
- Current supplier landscape (from `Supplier_Product` + `Supplier_Commercial`)
- Recommended supplier (from `Supplier_Commercial` — best price/confidence/lead time)
- Compliance delta (certs required by products in cluster vs confirmed for recommended supplier)
- Evidence citations (source + confidence per data point)
- Risk flags (off-market warnings, unverified grade, stale Molport data)

---

## 9. Technology Stack

### Backend / Pipeline

| Component | Library | Purpose |
|---|---|---|
| Language | Python 3.11+ | Pipeline, enrichers, reasoning |
| Database | SQLite (stdlib) | `db.sqlite` (RO) + `db_enriched.sqlite` |
| HTTP | `requests` + `urllib3.Retry` | All external API calls |
| Fuzzy matching | `rapidfuzz` ≥ 3.0 | Ingredient name clustering |
| LLM | `anthropic` SDK (claude-sonnet-4-6) | Phase 4 proposals + compliance extraction |
| Env | `python-dotenv` | `.env` loading |

### Fallback / Optional

| Component | Library | When needed |
|---|---|---|
| Browser scraping | `playwright` + `beautifulsoup4` | DSLD coverage < 55% |
| PDF extraction | `pdfplumber` | Supplement fact PDFs |
| Agent search | `google-adk` | Stage 3 (post-MVP) |

### External APIs

| API | Auth | Primary Use | Rate Limit |
|---|---|---|---|
| NIH DSLD v9 | API key (`X-Api-Key` header) | Labels, UNII codes, amounts | Undocumented |
| PubChem PUG REST | None | CAS, IUPAC, SMILES | 5/sec, 400/min |
| USDA FDC | Free key (`?api_key=`) | Food-grade nutrient profiles | 1000/hour |
| Molport v3 | Free account (`?apikey=`) | Bulk pricing, suppliers | 10k/month |
| RxNorm | None | Drug-class name normalization | Undocumented |
| Anthropic | API key | LLM reasoning + extraction | Per-token |

---

## 10. Security & Configuration

### Environment Variables (`.env`)

```bash
# Phase 1+2
DSLD_API_KEY=...          # dsld.od.nih.gov
FDC_API_KEY=...           # fdc.nal.usda.gov/api-key-signup

# Phase 3
MOLPORT_API_KEY=...       # molport.com → Profile → API Keys
ANTHROPIC_API_KEY=...     # console.anthropic.com

# Stage 3 (post-MVP)
GOOGLE_API_KEY=...        # aistudio.google.com
GOOGLE_GENAI_USE_VERTEXAI=false
```

`.env` is gitignored. `.env.template` documents all required keys with descriptions.

### Security Scope (MVP)

**In scope:**
- API keys in `.env` only; never hardcoded
- `db.sqlite` opened read-only in all enrichers
- No user-facing auth (internal CLI tool)

**Out of scope for MVP:**
- Encryption at rest, network ACLs, multi-user auth

---

## 11. Success Criteria

### MVP Success Definition

A hackathon judge can:
1. Run `python enrichment/pipeline.py` and see it complete
2. Query `db_enriched.sqlite` for one ingredient and see companies, BOMs, suppliers, prices, and compliance in one JOIN view
3. Read a `Consolidation_Opportunity` proposal with specific supplier recommendation, savings estimate, compliance gap, and source citations

### Functional Requirements

**Phase 1**
- ✅ ≥ 75% of 876 raw-material SKUs resolved with confidence ≥ 0.65
- ✅ ≥ 50% have confirmed CAS from PubChem
- ✅ ≥ 40% have UNII code from DSLD
- ✅ ≥ 50% have SMILES populated (Molport prerequisite)
- ✅ Top-20 consolidation candidates identifiable via cluster report

**Phase 2**
- ✅ ≥ 60% of 149 finished goods matched to DSLD label (confidence ≥ 0.65)
- ✅ ≥ 70% of matched BOM components have amount + unit in `BOM_Component_Quantity`

**Phase 3**
- ✅ ≥ 40% of CAS-identified ingredients have ≥ 1 `Supplier_Commercial` row
- ✅ ≥ 50% of DSLD-matched products have ≥ 1 `Product_Compliance` row
- ✅ All Molport prices tagged `Price_Type='retail_proxy'`
- ✅ All purity values tagged `Grade_Unverified=1` by default

**Phase 4**
- ✅ Top-20 `Consolidation_Opportunity` rows have `Consolidation_Score` populated
- ✅ Top-10 have `Proposal_Text` with source citations
- ✅ `Compliance_Gap` populated for all top-20
- ✅ `Compliance_Feasible` assessed for all top-20

**Infrastructure**
- ✅ All phases idempotent (re-run safe)
- ✅ `API_Response_Cache` hit rate ≥ 90% on second run
- ✅ `Enrichment_Run_Log` records every step (no silent failures)
- ✅ Schema matches PRD v1.1 (all new fields present)

### Quality Indicators

- No `None` stored silently — always `NULL` + corresponding log entry
- Confidence distribution: < 10% of resolved ingredients have confidence < 0.50
- Pipeline runtime: Phase 1 < 30 min, Phases 2+3 < 20 min each (warm cache: < 5 min total)

---

## 12. Implementation Phases

### Phase A — Schema Finalization & Bootstrap (Day 1 morning)

**Goal:** Lock enriched schema v1.1 and verify clone + JOIN round-trip.

- ✅ Update `schema/enriched_schema.sql` to v1.1:
  - Add `UNII_Code`, `Molport_Id`, `FDC_Id`, `RxCUI`, `SMILES`, `Grade_Flag` to `Ingredient_Canonical`
  - Add `MatchScore` to `SKU_To_Canonical`
  - Fix `Confidence` type TEXT→REAL in `Supplier_Commercial`
  - Add `ServingsPerContainer`, `OffMarket`, `DSLD_Label_Id` to `BOM_Component_Quantity`
  - Add `Price_Qty_KG`, `Country_Shipping`, `Purity_Pct`, `Purity_Qualifier`, `Grade_Unverified`, `Molport_Catalog_Id`, `Data_Freshness_Days` to `Supplier_Commercial`
  - Add `Off_Market_Warning` to `Product_Compliance`
  - Add `Unique_SKU_Count`, `Score_Formula_Component`, `Score_LLM_Adjustment`, `Compliance_Feasible` to `Consolidation_Opportunity`
- ✅ Run `db_bootstrap.py` → verify `db_enriched.sqlite` with all tables
- ✅ Smoke test: JOIN `SKU_To_Canonical` → `Ingredient_Canonical` → `Product` returns rows

**Validation:** `python enrichment/db_bootstrap.py` exits 0; all enrichment tables exist.

### Phase B — Phase 1: Ingredient Identity (Day 1 afternoon)

**Goal:** Resolve ≥ 75% of 876 raw-material SKUs.

- ✅ Verify/fix `enrichment/parsers/sku_parser.py` — handles `FG-`, `RM-`, numeric suffixes, dosage suffixes
- ✅ Implement `enrichment/sources/pubchem.py` — name → CID → CAS → SMILES chain
- ✅ Implement DSLD tier in `ingredient_normalizer.py` (UNII from `ingredientRows`)
- ✅ Implement RxNorm tier
- ✅ Implement FDC tier (food-grade macroingredients: whey, collagen, maltodextrin, inulin, dextrose only)
- ✅ Implement RapidFuzz cluster merge
- ✅ Run: `python enrichment/pipeline.py --phase 1`
- ✅ Verify cluster report: top-20 candidates by company count

**Validation:** `SELECT COUNT(*) FROM SKU_To_Canonical WHERE Confidence >= 0.65` ≥ 657.

### Phase C — Phases 2+3: Enrichment (Day 1 evening – Day 2 morning)

**Goal:** Populate BOM quantities and commercial/compliance data.

- ✅ Implement/verify `quantity_enricher.py` — DSLD label lookup per finished good
- ✅ Implement `enrichment/sources/molport.py` — CAS-first → SMILES fallback → supplier flatten
- ✅ Implement `commercial_enricher.py` — Molport → `Supplier_Commercial`
- ✅ Implement `compliance_enricher.py` — DSLD claims → `Product_Compliance`
- ✅ Run phases 2+3: `python enrichment/pipeline.py --phase 2 && python enrichment/pipeline.py --phase 3`

**Validation:**
- `BOM_Component_Quantity` ≥ 500 rows
- `Supplier_Commercial` ≥ 200 rows
- `Product_Compliance` ≥ 70 rows

### Phase D — Phase 4: Reasoning & Proposals (Day 2 afternoon)

**Goal:** Generate ranked consolidation proposals with evidence trails.

- ✅ `reasoning/substitution_graph.py` — populate `Ingredient_Substitution` from rules + UNII clusters
- ✅ `reasoning/consolidation_scorer.py` — formula score + LLM adjustment for top-50
- ✅ `reasoning/proposal_generator.py` — Claude narrative per top-10 opportunities
- ✅ Run: `python enrichment/pipeline.py --phase 4`

**Validation:** `SELECT COUNT(*) FROM Consolidation_Opportunity WHERE Proposal_Text IS NOT NULL` ≥ 10.

---

## 13. Future Considerations

### Stage 3: Agent Orchestration (post-MVP)

- Google ADK reactive agent: supplier fallout → find alternatives (DAG-structured, auditable)
- Proactive agent: scheduled consolidation opportunity refreshes
- Research agent: net-new supplier discovery via Google search + browser extraction
- LLM-wiki reasoning: compound knowledge pages per ingredient cluster, supplier, and proposal
- `Discovered_Supplier` and `Supplier_Alternative` tables

### Stage 4: Frontend (post-MVP)

- Flask/FastAPI + HTMX (preferred for hackathon simplicity over React)
- Consolidation dashboard — sortable `Consolidation_Opportunity` table
- Proposal detail view — evidence trail, compliance delta, agent reasoning trace
- DAG execution viewer
- Wiki browser

### Data Coverage Improvements

- Retailer scraping fallback (iHerb, Vitacost) when DSLD misses
- NSF / USP / Informed Sport certification database scraping
- PureBulk / BulkSupplements pricing to supplement Molport
- Historical procurement data for pricing ground truth

### Schema Extensions

- `Discovered_Supplier` — agent-found suppliers, flagged unverified
- `Supplier_Alternative` — reactive agent output
- `Price_History` — track Molport pricing over multiple runs

---

## 14. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Molport API key not yet obtained; live response format unconfirmed | High | All Molport schemas in references are inferred from docs. First implementor must validate field names vs real response and update `molport-integration.md`. Fall back to manual price proxy if key unavailable before demo. |
| DSLD coverage < 55% for finished goods | Medium | Before browser scraping: run RapidFuzz name-matching on DSLD's full ingredient index. Track hit rate per brand in `Enrichment_Run_Log`. Brands like NOW, Jarrow, Thorne, Nature Made are well-covered — prioritize those. |
| PubChem slug → name parsing fails on complex SKU formats | Medium | `sku_parser.py` must handle: hyphen-separated slugs, `FG-`/`RM-` prefixes, numeric UPC suffixes, dosage suffixes (`5000-iu`, `400mg`). Test against 50-slug sample before full run. |
| LLM hallucination in Phase 4 proposals | Medium | `ProposalGenerator` prompt must cite only fields from database queries. Each claim in `Proposal_Text` includes the field name and confidence. Instruct Claude: "only interpret stored data, do not invent facts." |
| Molport pricing is research-scale, not production-scale | Low | Always tag `Price_Type='retail_proxy'`. `Estimated_Savings_Narrative` must state: "pricing is indicative at research/lab quantities — production-volume pricing requires direct supplier negotiation." |

---

## 15. Appendix

### Key SQL Verification Queries

```sql
-- Phase 1 coverage
SELECT
    COUNT(*)                        AS total_rm_skus,
    SUM(CASE WHEN stc.Confidence >= 0.65 THEN 1 ELSE 0 END) AS resolved,
    ROUND(100.0 * SUM(CASE WHEN stc.Confidence >= 0.65 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_resolved
FROM Product p
LEFT JOIN SKU_To_Canonical stc ON stc.ProductId = p.Id
WHERE p.Type = 'raw-material';

-- Top consolidation candidates
SELECT
    ic.Name, ic.CAS_Number, ic.Function,
    COUNT(DISTINCT p.CompanyId)    AS companies,
    COUNT(DISTINCT bc.BOMId)       AS boms,
    COUNT(DISTINCT sp.SupplierId)  AS suppliers,
    COUNT(DISTINCT stc.ProductId)  AS sku_variants
FROM Ingredient_Canonical ic
JOIN SKU_To_Canonical stc  ON stc.CanonicalId = ic.Id
JOIN Product p             ON p.Id = stc.ProductId
LEFT JOIN BOM_Component bc ON bc.ConsumedProductId = p.Id
LEFT JOIN Supplier_Product sp ON sp.ProductId = p.Id
GROUP BY ic.Id
ORDER BY companies DESC, boms DESC
LIMIT 20;

-- Commercial + compliance summary per ingredient
SELECT
    ic.Name,
    COUNT(DISTINCT sc.SupplierId) AS commercial_suppliers,
    MIN(sc.Price_USD_Per_KG)      AS min_price_usd_kg,
    MAX(sc.Price_USD_Per_KG)      AS max_price_usd_kg,
    (SELECT COUNT(*) FROM Product_Compliance pc
     JOIN SKU_To_Canonical s ON s.ProductId = pc.ProductId
     WHERE s.CanonicalId = ic.Id) AS compliance_records
FROM Ingredient_Canonical ic
JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
GROUP BY ic.Id
ORDER BY commercial_suppliers DESC;
```

### Confidence Calibration Reference

| Source | Typical Confidence | Notes |
|---|---|---|
| PubChem (CAS confirmed) | 0.97 | Gold standard for chemical identity |
| PubChem (name only, no CAS) | 0.80 | Acceptable; CAS extraction sometimes fails |
| DSLD (UNII match) | 0.88 | Supplement-authoritative |
| DSLD (name-only hit) | 0.65–0.84 | Flag `low_confidence_dsld` |
| RxNorm | 0.85 | Drug-class only |
| FDC Branded | 0.65 | Self-reported; use `ingredients` field to confirm purity |
| FDC SR Legacy | 0.55 | Food-matrix context only |
| RapidFuzz cluster | 0.70 | Inferred; spot-check top clusters manually |
| Molport commercial | 0.80 | Pricing indicative at research scale |
| Manual | 0.30 | Requires human review before use in proposals |

### Related Documents

| Document | Purpose |
|---|---|
| `Orchestration/PRDs/meta-workflow.md` | Stage-by-stage implementation workflow |
| `Orchestration/References/dsld-integration.md` | Live-tested DSLD v9 guide |
| `Orchestration/References/usda-fdc-integration.md` | Live-tested FDC guide |
| `Orchestration/References/molport-integration.md` | Inferred Molport guide (validate before coding) |
| `Orchestration/References/free-apis.md` | Quick API reference |
| `Orchestration/References/google-adk-search.md` | Google ADK (Stage 3) |
| `Orchestration/References/browser-automation.md` | Playwright + Claude vision patterns |
| `Orchestration/Data/Spherecast/Overview.md` | Original challenge brief |
