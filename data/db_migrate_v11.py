"""Idempotent v1.0 → v1.1 schema migration for db_enriched.sqlite."""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.db_migrate_v11")


def migrate_v11(conn: sqlite3.Connection) -> None:
    """Apply all v1.0 → v1.1 schema changes idempotently."""

    def _add_col(table: str, col: str, typedef: str) -> None:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            print(f"  + {table}.{col}")

    # Ingredient_Canonical
    _add_col("Ingredient_Canonical", "UNII_Code", "TEXT")
    _add_col("Ingredient_Canonical", "Molport_Id", "TEXT")
    _add_col("Ingredient_Canonical", "FDC_Id", "INTEGER")
    _add_col("Ingredient_Canonical", "RxCUI", "TEXT")
    _add_col("Ingredient_Canonical", "SMILES", "TEXT")
    _add_col("Ingredient_Canonical", "Grade_Flag", "TEXT DEFAULT 'unknown'")

    # SKU_To_Canonical
    _add_col("SKU_To_Canonical", "MatchScore", "REAL")

    # BOM_Component_Quantity (ServingsPerContainer only; DSLD_Label_Id + Off_Market already in v1.0)
    _add_col("BOM_Component_Quantity", "ServingsPerContainer", "REAL")

    # Supplier_Commercial — fix Confidence TEXT→REAL + add 7 new columns
    sc_cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(Supplier_Commercial)")}
    if sc_cols.get("Confidence") == "TEXT":
        # Verify the table is empty before DROP/RENAME (safe only with 0 rows)
        row_count = conn.execute("SELECT COUNT(*) FROM Supplier_Commercial").fetchone()[0]
        if row_count > 0:
            logger.warning(
                f"Supplier_Commercial has {row_count} rows — skipping Confidence type fix "
                "to avoid data loss. Run a manual migration."
            )
        else:
            conn.executescript("""
                CREATE TABLE Supplier_Commercial_new (
                    SupplierId              INTEGER NOT NULL,
                    CanonicalIngredientId   INTEGER NOT NULL,
                    Price_USD_Per_KG        REAL,
                    MOQ_KG                  REAL,
                    Lead_Time_Days          INTEGER,
                    Country_Origin          TEXT,
                    Price_Type              TEXT,
                    Price_Source            TEXT,
                    Confidence              REAL NOT NULL DEFAULT 0.0,
                    Source_URL              TEXT,
                    Last_Updated            TEXT,
                    Price_Qty_KG            REAL,
                    Purity_Pct              REAL,
                    Purity_Qualifier        TEXT,
                    Grade_Unverified        INTEGER NOT NULL DEFAULT 1,
                    Molport_Catalog_Id      TEXT,
                    Data_Freshness_Days     INTEGER,
                    Country_Shipping        TEXT,
                    PRIMARY KEY (SupplierId, CanonicalIngredientId),
                    FOREIGN KEY (SupplierId) REFERENCES Supplier(Id),
                    FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(Id)
                );
                INSERT INTO Supplier_Commercial_new
                    SELECT SupplierId, CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG,
                           Lead_Time_Days, Country_Origin, Price_Type, Price_Source,
                           0.0, Source_URL, Last_Updated,
                           NULL, NULL, NULL, 1, NULL, NULL, NULL
                    FROM Supplier_Commercial;
                DROP TABLE Supplier_Commercial;
                ALTER TABLE Supplier_Commercial_new RENAME TO Supplier_Commercial;
            """)
            print("  ✓ Supplier_Commercial rebuilt with Confidence REAL")
    else:
        # Already REAL — just add any missing new columns
        for col, typedef in [
            ("Price_Qty_KG", "REAL"),
            ("Purity_Pct", "REAL"),
            ("Purity_Qualifier", "TEXT"),
            ("Grade_Unverified", "INTEGER NOT NULL DEFAULT 1"),
            ("Molport_Catalog_Id", "TEXT"),
            ("Data_Freshness_Days", "INTEGER"),
            ("Country_Shipping", "TEXT"),
        ]:
            _add_col("Supplier_Commercial", col, typedef)

    # Product_Compliance
    _add_col("Product_Compliance", "Off_Market_Warning", "INTEGER NOT NULL DEFAULT 0")

    # Consolidation_Opportunity
    _add_col("Consolidation_Opportunity", "Unique_SKU_Count", "INTEGER DEFAULT 0")
    _add_col("Consolidation_Opportunity", "Score_Formula_Component", "REAL")
    _add_col("Consolidation_Opportunity", "Score_LLM_Adjustment", "REAL")
    _add_col("Consolidation_Opportunity", "Compliance_Feasible", "INTEGER")

    # Ingredient_Substitution
    _add_col("Ingredient_Substitution", "Caveats", "TEXT")

    # Views (CREATE VIEW IF NOT EXISTS is idempotent)
    conn.executescript("""
        DROP VIEW IF EXISTS v_product_channel;
        CREATE VIEW v_product_channel AS
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

        DROP VIEW IF EXISTS v_bom_signature;
        CREATE VIEW v_bom_signature AS
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
    """)
    print("  ✓ views v_product_channel, v_bom_signature created")

    conn.commit()

    try:
        conn.execute(
            """INSERT INTO Enrichment_Run_Log
               (ProductId, Phase, Step, Status, Confidence, Method)
               VALUES (NULL, 0, 'schema_migration_v11', 'success', 1.0, 'migration')"""
        )
        conn.commit()
    except Exception:
        pass

    print("Schema v1.1 migration complete.")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    conn = sqlite3.connect(ENRICHED_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate_v11(conn)
    conn.close()
