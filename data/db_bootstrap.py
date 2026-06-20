"""Bootstrap: clone db.sqlite → db_enriched.sqlite and apply enriched schema + seed data."""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE_DB = ROOT / "db.sqlite"
ENRICHED_DB = ROOT / "db_enriched.sqlite"
SCHEMA_FILE = ROOT / "schema" / "enriched_schema.sql"

# Confidence values per source/method — single source of truth for the whole pipeline
CONFIDENCE_MATRIX = {
    "pubchem_exact_cas": 0.97,
    "pubchem_no_cas": 0.80,
    "dsld_ingredient": 0.88,
    "dsld_product": 0.85,
    "rxnorm": 0.82,
    "fuzzy_90_plus": 0.80,
    "fuzzy_85_89": 0.73,
    "fuzzy_below_85": 0.60,
    "manual": 1.0,
    "vision_high_res": 0.88,
    "vision_low_res": 0.65,
    "retail_price_proxy": 0.60,
    "molport_quote": 0.78,
    "dsld_cert_claim": 0.72,
    "retailer_badge": 0.80,
    "nsf_registry_confirmed": 0.97,
    "usp_registry_confirmed": 0.97,
}

# Curated substitution rules — expert-authored, never LLM-generated
# Columns: Name_A, Name_B, Rule_Type, Confidence, Justification, Caveats
SUBSTITUTION_RULES = [
    # Vitamin C forms
    ("Ascorbic Acid", "Sodium Ascorbate", "equivalent", 0.92,
     "Both deliver vitamin C activity; sodium ascorbate is the buffered form with identical antioxidant function.",
     "Adds ~131mg sodium per 1000mg dose; not suitable for sodium-restricted formulas"),
    ("Ascorbic Acid", "Calcium Ascorbate", "equivalent", 0.90,
     "Calcium-buffered vitamin C; equivalent antioxidant activity to ascorbic acid.",
     "Adds calcium load; dose recalculation for elemental Ca content"),
    ("Ascorbic Acid", "Magnesium Ascorbate", "equivalent", 0.88,
     "Magnesium-buffered vitamin C; equivalent vitamin C activity.",
     "Adds magnesium; review total Mg intake"),
    # Vitamin D forms
    ("Cholecalciferol", "Ergocalciferol", "partial", 0.72,
     "Both are vitamin D forms; D3 (cholecalciferol) is ~87% more potent than D2 per IU by weight.",
     "D3 significantly more bioavailable; dose adjustment required; D2 is vegan-compatible"),
    # Vitamin E forms
    ("d-Alpha Tocopherol", "dl-Alpha Tocopherol", "partial", 0.78,
     "Natural (d-) vs synthetic (dl-) vitamin E. Natural form is 1.36x more bioavailable per IU.",
     "Dose adjustment required; natural form preferred by clean-label brands"),
    ("d-Alpha Tocopherol", "Mixed Tocopherols", "partial", 0.74,
     "Mixed tocopherols include alpha, beta, gamma, delta forms; broader vitamin E profile.",
     "Different alpha-tocopherol content; label claim adjustment needed"),
    # Folate forms
    ("Folic Acid", "Methylfolate", "partial", 0.82,
     "5-MTHF (methylfolate) is the metabolically active form; bypasses MTHFR enzyme conversion step.",
     "Preferred for MTHFR variant carriers; higher cost; no synthetic folic acid concerns"),
    ("Folic Acid", "5-MTHF", "partial", 0.82,
     "5-Methyltetrahydrofolate is the active form of folate; functionally superior for some populations.",
     "Requires dose conversion; more expensive"),
    # B12 forms
    ("Cyanocobalamin", "Methylcobalamin", "partial", 0.83,
     "Both vitamin B12 forms; methylcobalamin is the active neurological form with better retention.",
     "Higher cost; neurologically preferred; no cyanide group"),
    ("Cyanocobalamin", "Adenosylcobalamin", "partial", 0.78,
     "Adenosylcobalamin is the mitochondrial active form of B12.",
     "Less common; higher cost; combined with methylcobalamin in some formulas"),
    # Magnesium forms
    ("Magnesium Oxide", "Magnesium Citrate", "partial", 0.72,
     "Magnesium citrate has higher bioavailability (~30%) vs oxide (~4%); gentler GI profile.",
     "Different elemental Mg%; dose recalculation required; citrate has laxative effect at high doses"),
    ("Magnesium Oxide", "Magnesium Glycinate", "partial", 0.70,
     "Magnesium glycinate is chelated; highly bioavailable and gentlest on GI tract.",
     "Lower elemental Mg% by weight; highest cost of Mg forms"),
    ("Magnesium Citrate", "Magnesium Glycinate", "partial", 0.74,
     "Both well-absorbed forms; glycinate preferred for sensitive consumers and sleep support.",
     "Different amino acid carrier; slightly different bioavailability profile"),
    ("Magnesium Oxide", "Magnesium Malate", "partial", 0.70,
     "Magnesium malate well absorbed; malic acid cofactor may support energy metabolism.",
     "Different elemental Mg%; dose adjustment needed"),
    # Calcium forms
    ("Calcium Carbonate", "Calcium Citrate", "partial", 0.76,
     "Calcium citrate absorbs without stomach acid; preferable for achlorhydria or PPI users.",
     "Citrate has lower elemental Ca% (21% vs 40%); dose adjustment needed; higher cost"),
    ("Calcium Carbonate", "Calcium Phosphate", "partial", 0.73,
     "Both provide calcium; phosphate form also contributes dietary phosphorus.",
     "Different elemental Ca%; phosphorus addition may be undesirable in some formulas"),
    # Zinc forms
    ("Zinc Oxide", "Zinc Citrate", "partial", 0.74,
     "Zinc citrate has higher bioavailability than zinc oxide.",
     "Different elemental Zn%; dose recalculation needed; higher cost"),
    ("Zinc Oxide", "Zinc Gluconate", "partial", 0.73,
     "Zinc gluconate well tolerated; standard OTC form.",
     "Lower elemental Zn% (14.3%); dose adjustment needed"),
    ("Zinc Oxide", "Zinc Picolinate", "partial", 0.75,
     "Zinc picolinate reported to have superior bioavailability.",
     "Higher cost; lower elemental Zn%; dose recalculation needed"),
    # Iron forms
    ("Ferrous Sulfate", "Ferrous Gluconate", "partial", 0.76,
     "Ferrous gluconate is gentler on GI tract; similar bioavailability to sulfate.",
     "Different elemental Fe%; dose adjustment needed"),
    ("Ferrous Sulfate", "Ferrous Fumarate", "partial", 0.77,
     "Ferrous fumarate has higher elemental Fe content (33%) than sulfate (20%).",
     "May cause GI discomfort at high doses; dose conversion required"),
    ("Ferrous Sulfate", "Ferric Pyrophosphate", "partial", 0.65,
     "Ferric pyrophosphate is a non-constipating form; lower absorption rate.",
     "Lower bioavailability; typically used in fortification; dose adjustment required"),
    # Omega-3 sources
    ("Fish Oil", "Algal Oil", "equivalent", 0.87,
     "Algal oil is the plant-based primary source of DHA/EPA; equivalent omega-3 delivery.",
     "Vegan-compatible; DHA:EPA ratio may differ by strain; higher cost"),
    ("Fish Oil", "Krill Oil", "partial", 0.78,
     "Krill oil provides EPA/DHA in phospholipid form; reportedly higher bioavailability.",
     "Different concentration; astaxanthin content; shellfish allergen; higher cost"),
    # Excipients — identical compounds, different naming
    ("Magnesium Stearate", "Vegetable Magnesium Stearate", "identical", 0.98,
     "Same compound (CAS 557-04-0); 'vegetable' qualifier specifies plant-derived source (palm/coconut), not chemistry.",
     None),
    ("Silicon Dioxide", "Silica", "identical", 0.99,
     "Same compound (CAS 7631-86-9); IUPAC vs common name.",
     None),
    ("Microcrystalline Cellulose", "MCC", "identical", 0.99,
     "Standard abbreviation for microcrystalline cellulose (CAS 9004-34-6).",
     None),
    ("Hydroxypropyl Methylcellulose", "HPMC", "identical", 0.99,
     "Standard abbreviation; used for vegetarian capsule shells.",
     None),
    ("Hydroxypropyl Methylcellulose", "Hypromellose", "identical", 0.99,
     "Hypromellose is the INN/USAN name for HPMC; identical compound.",
     None),
    # Capsule materials
    ("Gelatin", "Bovine Gelatin", "equivalent", 0.95,
     "Same compound; 'bovine' specifies species source — functionally identical for encapsulation.",
     "Not vegan/halal/kosher without certification; source matters for label claims"),
    ("Gelatin", "Porcine Gelatin", "equivalent", 0.93,
     "Porcine gelatin is equivalent for encapsulation; different species source.",
     "Not halal/kosher; allergen disclosure may be required"),
    ("Gelatin", "Vegetarian Capsule", "partial", 0.60,
     "HPMC or pullulan capsules are vegan alternatives to gelatin; same function.",
     "Different dissolution profile in some pH ranges; enables vegan/vegetarian label claim; higher cost"),
    # Sweeteners / bulking agents
    ("Dextrose", "Glucose", "identical", 0.99,
     "Dextrose is the common name for D-glucose; identical compound.",
     None),
    ("Fructooligosaccharides", "FOS", "identical", 0.99,
     "Standard abbreviation for fructooligosaccharides; same compound.",
     None),
    ("Inulin", "Fructooligosaccharides", "equivalent", 0.85,
     "FOS is a short-chain inulin; both are prebiotic fibers with equivalent function.",
     "Chain length difference; FOS slightly sweeter; inulin has longer fermentation time"),
    # Coenzyme Q10
    ("Coenzyme Q10", "CoQ10", "identical", 0.99,
     "Standard abbreviation for coenzyme Q10 (ubiquinone); identical compound.",
     None),
    ("Coenzyme Q10", "Ubiquinol", "partial", 0.80,
     "Ubiquinol is the reduced/active form of CoQ10; reportedly higher bioavailability.",
     "Different molecular form; dose conversion typically 1:1 for label claim; higher cost"),
    # Potassium
    ("Potassium Chloride", "Potassium Citrate", "partial", 0.73,
     "Both provide potassium; citrate is alkalizing and gentler; chloride is cheaper.",
     "Different anion; citrate alters urinary pH; different elemental K%"),
    # Curcumin forms
    ("Curcumin", "Curcuma Longa Extract", "equivalent", 0.85,
     "Curcuma longa (turmeric) extract standardised to curcuminoids; curcumin is the primary active.",
     "Standardisation percentage must match; ensure equivalent curcumin content per dose"),
    ("Curcumin", "Turmeric Extract", "equivalent", 0.84,
     "Turmeric extract standardised to curcuminoids; functionally equivalent if standardisation is specified.",
     "Must verify curcumin % on CoA; unstandardised extracts are not equivalent"),
]


def bootstrap(force: bool = False) -> None:
    if not SOURCE_DB.exists():
        print(f"ERROR: Source DB not found at {SOURCE_DB}", file=sys.stderr)
        sys.exit(1)

    if ENRICHED_DB.exists() and not force:
        print("db_enriched.sqlite already exists — skipping clone. Use --force to overwrite.")
    else:
        if ENRICHED_DB.exists():
            ENRICHED_DB.unlink()
        shutil.copy(SOURCE_DB, ENRICHED_DB)
        print(f"Cloned {SOURCE_DB.name} → {ENRICHED_DB.name}")

    conn = sqlite3.connect(ENRICHED_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    schema_sql = SCHEMA_FILE.read_text()
    conn.executescript(schema_sql)
    conn.commit()
    print("Enriched schema applied.")

    from enrichment.db_migrate_v11 import migrate_v11
    migrate_v11(conn)

    _seed_substitution_rules(conn)
    _seed_confidence_matrix(conn)

    conn.commit()
    conn.close()

    _validate(ENRICHED_DB)
    print("Bootstrap complete.")


def _seed_substitution_rules(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM Ingredient_Substitution_Rule").fetchone()[0]
    if existing > 0:
        print(f"Substitution rules already seeded ({existing} rows) — skipping.")
        return

    conn.executemany(
        """INSERT INTO Ingredient_Substitution_Rule
           (Name_A, Name_B, Rule_Type, Confidence, Justification, Caveats, Source)
           VALUES (?, ?, ?, ?, ?, ?, 'curated')""",
        SUBSTITUTION_RULES,
    )
    print(f"Seeded {len(SUBSTITUTION_RULES)} curated substitution rules.")


def _seed_confidence_matrix(conn: sqlite3.Connection) -> None:
    """Store confidence matrix as a named key-value record for pipeline reference."""
    conn.execute(
        """INSERT OR REPLACE INTO API_Response_Cache (Source, Cache_Key, Response, TTL_Days)
           VALUES ('config', 'confidence_matrix', ?, 0)""",
        (json.dumps(CONFIDENCE_MATRIX),),
    )
    print("Confidence matrix stored in cache config.")


def _validate(db_path: Path) -> None:
    """Spot-check that original tables + enrichment tables are all present."""
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    required = {
        "Company", "Product", "BOM", "BOM_Component", "Supplier", "Supplier_Product",
        "Ingredient_Canonical", "SKU_To_Canonical", "Ingredient_Substitution",
        "BOM_Component_Quantity", "Supplier_Commercial", "Product_Compliance",
        "Consolidation_Opportunity", "API_Response_Cache", "Enrichment_Run_Log",
        "Ingredient_Substitution_Rule", "Certification_Registry",
    }
    missing = required - tables
    if missing:
        print(f"WARNING: Missing tables after bootstrap: {missing}", file=sys.stderr)
    else:
        print(f"Validation passed — all {len(required)} tables present.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bootstrap db_enriched.sqlite")
    parser.add_argument("--force", action="store_true",
                        help="Re-clone and overwrite existing db_enriched.sqlite")
    args = parser.parse_args()
    bootstrap(force=args.force)
