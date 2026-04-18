-- Agnes Enriched Database Schema v1.1
-- Applied by enrichment/db_bootstrap.py on top of a cloned db.sqlite.
-- All original tables (Company, Product, BOM, BOM_Component, Supplier, Supplier_Product)
-- are already present after the clone — this file creates only the enrichment tables.

-- ── Phase 1: Ingredient Identity ────────────────────────────────────────────

-- Canonical ingredient identity (resolves company-specific SKUs to shared identities)
CREATE TABLE IF NOT EXISTS Ingredient_Canonical (
    Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    Name                TEXT NOT NULL,           -- "Magnesium Stearate"
    CAS_Number          TEXT,                    -- "557-04-0"
    PubChem_CID         INTEGER,
    IUPAC_Name          TEXT,
    Molecular_Formula   TEXT,
    Function            TEXT,                    -- "excipient:lubricant" | "nutrient:mineral" etc.
    Confidence          REAL    NOT NULL DEFAULT 0.0,   -- 0.0–1.0
    Sources             TEXT    NOT NULL DEFAULT '[]',  -- JSON array of source strings
    UNII_Code           TEXT,                    -- FDA UNII identifier
    Molport_Id          TEXT,                    -- Molport compound ID
    FDC_Id              INTEGER,                 -- USDA FDC ID
    RxCUI               TEXT,                    -- RxNorm CUI
    SMILES              TEXT,                    -- IsomericSMILES from PubChem
    Grade_Flag          TEXT    DEFAULT 'unknown' -- food|pharma|reagent|unknown
);

-- Maps original Product SKUs → canonical ingredient
CREATE TABLE IF NOT EXISTS SKU_To_Canonical (
    ProductId           INTEGER NOT NULL,
    CanonicalId         INTEGER NOT NULL,
    ExtractedName       TEXT,                    -- human-readable name parsed from slug
    MatchMethod         TEXT,                    -- pubchem|dsld|rxnorm|fuzzy|manual
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    MatchScore          REAL,                    -- raw rapidfuzz score (0–100) for fuzzy matches
    CreatedAt           TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ProductId),
    FOREIGN KEY (ProductId)   REFERENCES Product(Id),
    FOREIGN KEY (CanonicalId) REFERENCES Ingredient_Canonical(Id)
);

-- Substitution edges between canonical ingredients (Phase 1 seed + Phase 4 extensions)
CREATE TABLE IF NOT EXISTS Ingredient_Substitution (
    IngredientAId       INTEGER NOT NULL,
    IngredientBId       INTEGER NOT NULL,
    SubstitutionType    TEXT    NOT NULL,        -- identical|equivalent|partial|incompatible
    Score               REAL    NOT NULL DEFAULT 0.0,   -- 0.0–1.0
    Notes               TEXT,
    Sources             TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    Caveats             TEXT,
    PRIMARY KEY (IngredientAId, IngredientBId),
    FOREIGN KEY (IngredientAId) REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (IngredientBId) REFERENCES Ingredient_Canonical(Id)
);

-- ── Phase 2: BOM Quantity Enrichment ────────────────────────────────────────

-- Ingredient amounts per BOM component, enriched from DSLD / retailer label scraping
CREATE TABLE IF NOT EXISTS BOM_Component_Quantity (
    BOMId               INTEGER NOT NULL,
    ConsumedProductId   INTEGER NOT NULL,
    Amount              REAL,                    -- numeric value
    Unit                TEXT,                    -- mg|IU|mcg|g|%DV|CFU|ml
    PerServing          REAL,                    -- servings per container
    ServingUnit         TEXT,                    -- "capsule"|"tablet"|"scoop"|"ml"
    DSLD_Label_Id       TEXT,                    -- DSLD label ID used as source
    ServingsPerContainer REAL,                   -- total servings in the container
    Off_Market          INTEGER,                 -- 0=current, 1=off-market label
    Source              TEXT,                    -- dsld|iherb|walmart|target|vitacost|manual
    Source_URL          TEXT,
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (BOMId, ConsumedProductId),
    FOREIGN KEY (BOMId)             REFERENCES BOM(Id),
    FOREIGN KEY (ConsumedProductId) REFERENCES Product(Id)
);

-- ── Phase 3: Commercial & Compliance Enrichment ─────────────────────────────

-- Commercial data per Supplier × Canonical Ingredient
CREATE TABLE IF NOT EXISTS Supplier_Commercial (
    SupplierId              INTEGER NOT NULL,
    CanonicalIngredientId   INTEGER NOT NULL,
    Price_USD_Per_KG        REAL,
    MOQ_KG                  REAL,
    Lead_Time_Days          INTEGER,
    Country_Origin          TEXT,
    Price_Type              TEXT,                -- retail_proxy|wholesale|spot|quoted
    Price_Source            TEXT,                -- purebulk|alibaba|molport|bulksupplements|manual
    Confidence              REAL    NOT NULL DEFAULT 0.0,
    Source_URL              TEXT,
    Last_Updated            TEXT,
    Price_Qty_KG            REAL,                -- quantity tier the price applies to
    Purity_Pct              REAL,                -- purity percentage from supplier
    Purity_Qualifier        TEXT,                -- ">98%", "≥99%", etc.
    Grade_Unverified        INTEGER NOT NULL DEFAULT 1,  -- 1=grade not confirmed
    Molport_Catalog_Id      TEXT,                -- Molport catalog entry ID
    Data_Freshness_Days     INTEGER,             -- days since last Molport update
    Country_Shipping        TEXT,                -- ISO country code for shipping origin
    PRIMARY KEY (SupplierId, CanonicalIngredientId),
    FOREIGN KEY (SupplierId)            REFERENCES Supplier(Id),
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);

-- Compliance / certification per finished product
CREATE TABLE IF NOT EXISTS Product_Compliance (
    ProductId           INTEGER NOT NULL,
    Certification       TEXT    NOT NULL,        -- NSF|USP|InformedSport|BSCG|Organic|NonGMO|Kosher|GlutenFree|Vegan
    Status              TEXT,                    -- confirmed|claimed|implied|not_required
    Evidence_URL        TEXT,
    Verified_Date       TEXT,
    Source              TEXT,                    -- dsld|retailer_badge|label_text|manual
    Confidence          REAL    NOT NULL DEFAULT 0.0,
    Off_Market_Warning  INTEGER NOT NULL DEFAULT 0,  -- 1=cert from off-market label only
    PRIMARY KEY (ProductId, Certification),
    FOREIGN KEY (ProductId) REFERENCES Product(Id)
);

-- ── Phase 4: Reasoning & Proposals ──────────────────────────────────────────

-- Consolidation opportunity scores (one row per canonical ingredient that qualifies)
CREATE TABLE IF NOT EXISTS Consolidation_Opportunity (
    Id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId       INTEGER NOT NULL,
    Company_Count               INTEGER NOT NULL DEFAULT 0,
    BOM_Count                   INTEGER NOT NULL DEFAULT 0,
    Current_Supplier_Count      INTEGER NOT NULL DEFAULT 0,
    Consolidation_Score         REAL    NOT NULL DEFAULT 0.0,   -- 0.0–1.0
    Recommended_SupplierId      INTEGER,
    Estimated_Savings_Narrative TEXT,
    Compliance_Gap              TEXT,
    Proposal_Text               TEXT,            -- LLM-generated markdown narrative
    Proposal_JSON               TEXT,            -- structured JSON proposal
    Generated_At                TEXT,
    Unique_SKU_Count            INTEGER DEFAULT 0,
    Score_Formula_Component     REAL,            -- formula-computed score component
    Score_LLM_Adjustment        REAL,            -- LLM ±0.10 adjustment (top-50 only)
    Compliance_Feasible         INTEGER,         -- 1=all required certs achievable
    regulatory_drift_flag       INTEGER DEFAULT 0, -- 1=affected by FDA IID quarterly drift
    regulatory_drift_reason     TEXT,            -- set by regulatory_drift_alert pipeline
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);

-- ── Operational / Infrastructure Tables ─────────────────────────────────────

-- API response cache: avoids redundant external calls across pipeline runs
-- TTL_Days = 0 means never expires (e.g. CAS mappings); positive value triggers refresh
CREATE TABLE IF NOT EXISTS API_Response_Cache (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    Source      TEXT    NOT NULL,                -- pubchem|dsld|fdc|rxnorm|openfda|molport
    Cache_Key   TEXT    NOT NULL,                -- normalised query string or URL
    Response    TEXT,                            -- raw JSON response body (NULL = confirmed no-match)
    Fetched_At  TEXT    NOT NULL DEFAULT (datetime('now')),
    TTL_Days    INTEGER NOT NULL DEFAULT 30,     -- days until stale; 0 = permanent
    UNIQUE (Source, Cache_Key)
);

-- Enrichment audit log: tracks every attempted enrichment for idempotency + debugging
CREATE TABLE IF NOT EXISTS Enrichment_Run_Log (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ProductId   INTEGER,                         -- NULL for non-product operations
    Phase       INTEGER NOT NULL,                -- 1|2|3|4
    Step        TEXT    NOT NULL,                -- e.g. "pubchem_lookup", "dsld_search"
    Status      TEXT    NOT NULL,                -- success|cache_hit|fallback|skipped|error
    Confidence  REAL,
    Method      TEXT,                            -- which tier resolved the data
    Error_Msg   TEXT,
    Run_At      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Curated substitution rules: expert-authored; seeded by db_bootstrap.py; not LLM-generated
-- Used by Phase 4 substitution graph builder as ground-truth edges
CREATE TABLE IF NOT EXISTS Ingredient_Substitution_Rule (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Name_A          TEXT    NOT NULL,            -- must match Ingredient_Canonical.Name (case-insensitive)
    Name_B          TEXT    NOT NULL,
    Rule_Type       TEXT    NOT NULL,            -- identical|equivalent|partial
    Confidence      REAL    NOT NULL,            -- pre-assigned confidence value
    Justification   TEXT    NOT NULL,            -- human-readable rationale
    Caveats         TEXT,                        -- known limitations (e.g. bioavailability difference)
    Source          TEXT    NOT NULL DEFAULT 'curated'
);

-- Agent action log: append-only record of every agent step across all runs.
-- Replaces a markdown log file — queryable, structured, idempotent.
-- Agents write one row per DAG node execution; humans and agents query for context.
CREATE TABLE IF NOT EXISTS Agent_Log (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Run_Id          TEXT    NOT NULL,                -- UUID shared by all steps in one agent run
    Agent           TEXT    NOT NULL,                -- reactive|proactive|research|proposal
    Node            TEXT    NOT NULL,                -- DAG node name, e.g. "QueryAffectedIngredients"
    Status          TEXT    NOT NULL,                -- success|skipped|error
    Input_JSON      TEXT,                            -- JSON snapshot of node inputs
    Output_JSON     TEXT,                            -- JSON snapshot of node outputs (or error detail)
    Related_IngredientId INTEGER,                    -- FK to Ingredient_Canonical when applicable
    Related_SupplierId   INTEGER,                    -- FK to Supplier when applicable
    Related_OpportunityId INTEGER,                   -- FK to Consolidation_Opportunity when applicable
    Logged_At       TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (Related_IngredientId)    REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (Related_SupplierId)      REFERENCES Supplier(Id),
    FOREIGN KEY (Related_OpportunityId)   REFERENCES Consolidation_Opportunity(Id)
);

-- Certification registry: stores scraped NSF/USP/InformedSport databases locally
CREATE TABLE IF NOT EXISTS Certification_Registry (
    Id              INTEGER PRIMARY KEY AUTOINCREMENT,
    Certifier       TEXT    NOT NULL,            -- NSF|USP|InformedSport|BSCG
    Entity_Name     TEXT    NOT NULL,            -- product or supplier name as listed
    Entity_Type     TEXT    NOT NULL,            -- product|supplier|ingredient
    Cert_Id         TEXT,                        -- certifier's own ID/number
    Verified_At     TEXT    NOT NULL DEFAULT (datetime('now')),
    Source_URL      TEXT,
    Raw_Data        TEXT                         -- JSON blob of scraped record
);

-- FDA Inactive Ingredient Database (IID) — max daily exposure limits per route/form
CREATE TABLE IF NOT EXISTS FDA_Inactive_Ingredient (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    IngredientName          TEXT NOT NULL,
    UNII                    TEXT,
    CAS_Number              TEXT,
    Route                   TEXT NOT NULL,
    DosageForm              TEXT NOT NULL,
    MaxPotencyAmount        REAL,
    MaxPotencyUnit          TEXT,
    MaxDailyExposure        REAL,
    MaxDailyExposureUnit    TEXT,
    RecordUpdated           TEXT,
    CanonicalIngredientId   INTEGER,
    Source                  TEXT DEFAULT 'fda_iid_csv',
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
);
CREATE INDEX IF NOT EXISTS idx_fda_iid_unii       ON FDA_Inactive_Ingredient(UNII);
CREATE INDEX IF NOT EXISTS idx_fda_iid_canonical  ON FDA_Inactive_Ingredient(CanonicalIngredientId);

-- FDA IID quarterly change log — detects drift (C=corrected, D=deleted, R=revised)
-- Loaded by enrichment/backfill_iid_changelog.py; updated by regulatory_drift_alert pipeline
CREATE TABLE IF NOT EXISTS FDA_IID_Change_Log (
    Id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ChangeId              INTEGER NOT NULL,
    SnapshotDate          TEXT NOT NULL,     -- 'Q1 2026' | 'Q2 2026' etc.
    IngredientName        TEXT NOT NULL,
    Route                 TEXT,
    DosageForm            TEXT,
    MaxPotencyPerUnit     TEXT,              -- stored as TEXT (mixed: numeric, '%w/v', 'NA', blank)
    MaxDailyExposure      TEXT,              -- stored as TEXT (same reason)
    MaxDailyExposureUOM   TEXT,
    Status                TEXT NOT NULL CHECK(Status IN ('C','D','R')),
    CanonicalIngredientId INTEGER,
    MatchMethod           TEXT,             -- 'exact' | 'fuzzy'
    MatchScore            REAL,
    IngestedAt            TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
    UNIQUE(ChangeId, SnapshotDate, Route, DosageForm)
);
CREATE INDEX IF NOT EXISTS idx_iid_cl_canonical ON FDA_IID_Change_Log(CanonicalIngredientId);
CREATE INDEX IF NOT EXISTS idx_iid_cl_status    ON FDA_IID_Change_Log(Status);
CREATE INDEX IF NOT EXISTS idx_iid_cl_changeid  ON FDA_IID_Change_Log(ChangeId);

-- Scoring configuration — user-adjustable weights for supplier ranking
CREATE TABLE IF NOT EXISTS Scoring_Config (
    Key     TEXT PRIMARY KEY,
    Value   REAL NOT NULL
);
-- Default rows inserted by migration script

-- Price change alerts — detected by price_monitor pipeline
CREATE TABLE IF NOT EXISTS Price_Change_Alert (
    Id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId   INTEGER NOT NULL,
    SupplierId              INTEGER,
    Ingredient_Name         TEXT NOT NULL,
    Supplier_Name           TEXT,
    Previous_Price_USD      REAL,
    New_Price_USD           REAL,
    Change_Pct              REAL,           -- signed: negative = drop, positive = increase
    Direction               TEXT NOT NULL,  -- 'up' | 'down'
    Severity                TEXT NOT NULL DEFAULT 'info',  -- 'info' (5-14%) | 'warning' (15-29%) | 'critical' (>=30%)
    Alert_Narrative         TEXT,           -- filled by PriceAlertWriterAgent
    Dismissed               INTEGER NOT NULL DEFAULT 0,
    Detected_At             TEXT NOT NULL DEFAULT (datetime('now')),
    Run_Id                  TEXT,
    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id),
    FOREIGN KEY (SupplierId) REFERENCES Supplier(Id)
);
CREATE INDEX IF NOT EXISTS idx_price_alert_canonical ON Price_Change_Alert(CanonicalIngredientId);
CREATE INDEX IF NOT EXISTS idx_price_alert_dismissed ON Price_Change_Alert(Dismissed, Detected_At);

-- ── Cross-cutting Views ──────────────────────────────────────────────────────

-- Channel tag extracted from SKU prefix; NULL for non-finished-good rows.
CREATE VIEW IF NOT EXISTS v_product_channel AS
SELECT
    Id, SKU, CompanyId, Type,
    CASE
        WHEN Type != 'finished-good'             THEN NULL
        WHEN SKU LIKE 'FG-walmart-%'             THEN 'walmart'
        WHEN SKU LIKE 'FG-target-%'              THEN 'target'
        WHEN SKU LIKE 'FG-cvs-%'                 THEN 'cvs'
        WHEN SKU LIKE 'FG-walgreens-%'           THEN 'walgreens'
        WHEN SKU LIKE 'FG-costco-%'              THEN 'costco'
        WHEN SKU LIKE 'FG-sams-%'                THEN 'sams-club'
        WHEN SKU LIKE 'FG-amazon-%'              THEN 'amazon'
        WHEN SKU LIKE 'FG-iherb-%'               THEN 'iherb'
        WHEN SKU LIKE 'FG-the-vitamin-shoppe-%'  THEN 'vitamin-shoppe'
        WHEN SKU LIKE 'FG-thrive%'               THEN 'thrive-market'
        WHEN SKU LIKE 'FG-vitacost-%'            THEN 'vitacost'
        WHEN SKU LIKE 'FG-gnc-%'                 THEN 'gnc'
        ELSE NULL
    END AS Channel
FROM Product;

-- BOM identity: one row per finished-good BOM with a sorted component signature.
-- DISTINCT (CompanyId, bom_sig) is the canonical-product dedup key used in scoring.
CREATE VIEW IF NOT EXISTS v_bom_signature AS
SELECT
    b.Id      AS BOMId,
    p.CompanyId,
    p.Id      AS ProductId,
    GROUP_CONCAT(bc.ConsumedProductId ORDER BY bc.ConsumedProductId) AS bom_sig
FROM BOM b
JOIN Product p  ON p.Id  = b.ProducedProductId
JOIN BOM_Component bc ON bc.BOMId = b.Id
WHERE p.Type = 'finished-good'
GROUP BY b.Id, p.CompanyId, p.Id;
