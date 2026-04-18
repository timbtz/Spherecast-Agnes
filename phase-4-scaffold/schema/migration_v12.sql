-- Phase 4 additive migration. v1.1 -> v1.2.
-- Additive only: never UPDATE or DROP Tim's existing data.
-- Apply via enrichment/db_migrate_v12.py for PRAGMA-guarded re-run safety.

BEGIN TRANSACTION;

-- 1. Extend Ingredient_Canonical with form/grade/morphology slots.
ALTER TABLE Ingredient_Canonical ADD COLUMN Form TEXT;             -- 'powder'|'granular'|'liquid'|'flake'|'crystal'|'unknown'
ALTER TABLE Ingredient_Canonical ADD COLUMN Processing TEXT;       -- 'spray-dried'|'micronized'|'granulated'|'unknown'
ALTER TABLE Ingredient_Canonical ADD COLUMN PSD_Bucket TEXT;       -- '<50um'|'50-200um'|'200-500um'|'>500um'|'unknown'
ALTER TABLE Ingredient_Canonical ADD COLUMN Surface_Area_m2g REAL;
ALTER TABLE Ingredient_Canonical ADD COLUMN Bulk_Density_gmL REAL;

-- 2. Consolidation_Opportunity: attach incumbent/candidate role labels used by gate engine.
ALTER TABLE Consolidation_Opportunity ADD COLUMN IncumbentRole TEXT;
ALTER TABLE Consolidation_Opportunity ADD COLUMN CandidateRole TEXT;

-- 3. Phase 4 tables.
CREATE TABLE IF NOT EXISTS Substitution_Gate_Result (
    GateRunId INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId INTEGER NOT NULL,
    IncumbentSkuId INTEGER NOT NULL,
    CandidateSkuId INTEGER NOT NULL,
    CanonicalGate INTEGER NOT NULL,
    RoleGate INTEGER NOT NULL,
    FormGate INTEGER NOT NULL,
    GradeGate INTEGER NOT NULL,
    MorphologyGate INTEGER NOT NULL,
    RegulatoryGate INTEGER NOT NULL,
    OverallPass INTEGER NOT NULL,
    FailedGate TEXT,
    CompoundConfidence REAL NOT NULL,
    EvidenceIds TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Compliance_Outcome_4State (
    ComplianceRunId INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId INTEGER NOT NULL,
    CandidateSkuId INTEGER NOT NULL,
    Jurisdiction TEXT NOT NULL,
    ImplicitStandard TEXT,
    CategoryBaseline TEXT,
    Outcome TEXT NOT NULL,                  -- pass-global|fork-recommended|refuse|human-review
    Reason TEXT,
    Confidence REAL NOT NULL,
    EvidenceIds TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Supplier_Score (
    ScoreId INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId INTEGER NOT NULL,
    SupplierId INTEGER NOT NULL,
    Q_Quality REAL NOT NULL,
    C_Cost REAL NOT NULL,
    L_Logistics REAL NOT NULL,
    R_Risk REAL NOT NULL,
    W_Q REAL NOT NULL,
    W_C REAL NOT NULL,
    W_L REAL NOT NULL,
    W_R REAL NOT NULL,
    S_Total REAL NOT NULL,
    CompliancePass INTEGER NOT NULL,
    EvidenceIds TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Refusal_Record (
    RefusalId INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId INTEGER,
    CandidateSkuId INTEGER,
    Reason TEXT NOT NULL,                   -- below_threshold|gate_fail|jurisdiction_unresolved|...
    CompoundConfidence REAL,
    FailingGate TEXT,
    EvidenceIds TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS RFQ (
    RfqId INTEGER PRIMARY KEY AUTOINCREMENT,
    OpportunityId INTEGER,
    CandidateSupplierName TEXT NOT NULL,
    CanonicalIngredientId INTEGER NOT NULL,
    SpecJson TEXT NOT NULL,
    TargetMarkets TEXT,                     -- JSON array
    QuantityBandKg TEXT,
    Status TEXT NOT NULL,                   -- draft|sent|response_received|cancelled
    SentAt TEXT,
    ResponseJson TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Lane_Cost (
    LaneId INTEGER PRIMARY KEY AUTOINCREMENT,
    OriginCountry TEXT NOT NULL,
    DestCountry TEXT NOT NULL,
    Mode TEXT NOT NULL,                     -- ocean|air|truck|rail
    LeadTimeDays REAL NOT NULL,
    CostUSDPerKg REAL NOT NULL,
    LastUpdated TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Scout_Candidate (
    CandidateId INTEGER PRIMARY KEY AUTOINCREMENT,
    CanonicalIngredientId INTEGER NOT NULL,
    SupplierName TEXT NOT NULL,
    SourceDirectory TEXT NOT NULL,
    SourceUrl TEXT,
    CountryCode TEXT,
    CertificationsRaw TEXT,
    QualifyStatus TEXT,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Evidence_Ledger (
    EvidenceId INTEGER PRIMARY KEY AUTOINCREMENT,
    Source TEXT NOT NULL,                   -- pubchem|dsld|scout:thomasnet|internal:bom|...
    Url TEXT,
    Claim TEXT NOT NULL,
    RawExcerpt TEXT,
    Confidence REAL,
    FetchedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
