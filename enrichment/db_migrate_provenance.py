"""Idempotent migration: provenance + tier columns, URL blocklist, Supplier_Master.

Adds to Supplier_Commercial:
  - Provenance_Confidence  TEXT  (one of: vendor_verified, website_explicit,
                                  directory_listing, model_inferred, unknown)
  - Evidence_Snippet       TEXT  (first ~200 chars of the model's supporting text)
  - URL_Archetype          TEXT  (directory_listing, manufacturer_direct,
                                  distributor, lab_reagent, unknown)
  - URL_Health             TEXT  (ok, stale, unreachable, not_checked)
  - Corroboration_Score    INTEGER  (count of distinct runs × distinct domains
                                     the supplier was seen across)

Adds to Ingredient_Canonical:
  - Category   TEXT  (commodity_excipient, vitamin, mineral, api, botanical,
                      protein, unknown) — drives per-category staleness TTL
  - Usage_Tier INTEGER  (1 = top 50 by BOM appearance, 2 = next 50, 3 = rest)

New tables:
  - URL_Blocklist    (hostname text PK, reason text, added_at text)
  - Supplier_Master  (SupplierId PK, DUNS, LEI, Vetted, Vetted_Source, Vetted_At)

Backfills Usage_Tier from BOM appearance count and Category from the existing
Function column using a curated mapping.
"""
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.migrate_provenance")


# Function → Category mapping. Granular on purpose so per-category TTL can
# actually differ. Unknown functions fall through to 'unknown'.
_FUNCTION_TO_CATEGORY = {
    "mineral-fortificant": "mineral",
    "vitamin-fortificant": "vitamin",
    "functional-botanical": "botanical",
    "protein-source": "protein",
    "thickener": "commodity_excipient",
    "excipient": "commodity_excipient",
    "lubricant": "commodity_excipient",
    "acidulant": "commodity_excipient",
    "antioxidant": "commodity_excipient",
    "sweetener": "commodity_excipient",
    "colorant": "commodity_excipient",
    "preservative": "commodity_excipient",
    "emulsifier": "commodity_excipient",
    "flavour": "commodity_excipient",
    "api": "api",
    "active": "api",
}


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _add_column_if_missing(conn, table, col, ddl):
    if not _column_exists(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        logger.info(f"  + added {table}.{col}")


def migrate(conn: sqlite3.Connection) -> dict:
    stats = {"columns_added": 0, "rows_backfilled_tier": 0,
             "rows_backfilled_category": 0, "blocklist_seeded": 0}

    # --- Supplier_Commercial additions ---
    for col, ddl in [
        ("Provenance_Confidence", "TEXT DEFAULT 'unknown'"),
        ("Evidence_Snippet",      "TEXT"),
        ("URL_Archetype",         "TEXT DEFAULT 'unknown'"),
        ("URL_Health",            "TEXT DEFAULT 'not_checked'"),
        ("Corroboration_Score",   "INTEGER DEFAULT 0"),
    ]:
        if not _column_exists(conn, "Supplier_Commercial", col):
            conn.execute(f"ALTER TABLE Supplier_Commercial ADD COLUMN {col} {ddl}")
            stats["columns_added"] += 1
            logger.info(f"  + Supplier_Commercial.{col}")

    # --- Ingredient_Canonical additions ---
    for col, ddl in [
        ("Category",   "TEXT DEFAULT 'unknown'"),
        ("Usage_Tier", "INTEGER DEFAULT 3"),
    ]:
        if not _column_exists(conn, "Ingredient_Canonical", col):
            conn.execute(f"ALTER TABLE Ingredient_Canonical ADD COLUMN {col} {ddl}")
            stats["columns_added"] += 1
            logger.info(f"  + Ingredient_Canonical.{col}")

    # --- URL_Blocklist ---
    conn.execute("""CREATE TABLE IF NOT EXISTS URL_Blocklist (
        Hostname  TEXT PRIMARY KEY,
        Reason    TEXT NOT NULL,
        Added_At  TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    # Seed with known non-supplier domains. These are sources that can show up
    # in Google search grounding but aren't legitimate B2B supplier listings.
    _seed_blocklist = [
        ("wikipedia.org",       "reference_site"),
        ("en.wikipedia.org",    "reference_site"),
        ("reddit.com",          "forum"),
        ("www.reddit.com",      "forum"),
        ("old.reddit.com",      "forum"),
        ("quora.com",           "forum"),
        ("www.quora.com",       "forum"),
        ("stackexchange.com",   "forum"),
        ("stackoverflow.com",   "forum"),
        ("researchgate.net",    "academic"),
        ("www.researchgate.net","academic"),
        ("pubmed.ncbi.nlm.nih.gov", "academic"),
        ("pubs.acs.org",        "academic"),
        ("sciencedirect.com",   "academic"),
        ("nih.gov",             "reference_site"),
        ("fda.gov",             "reference_site"),
        ("www.fda.gov",         "reference_site"),
        ("example.com",         "placeholder"),
        ("example.org",         "placeholder"),
        ("placeholder.com",     "placeholder"),
        ("linkedin.com",        "social"),
        ("www.linkedin.com",    "social"),
        ("facebook.com",        "social"),
        ("twitter.com",         "social"),
        ("x.com",               "social"),
        ("youtube.com",         "media"),
        ("medium.com",          "blog"),
        # Grounding-API redirects: vertexaisearch emits short-lived redirect
        # URLs through its own domain. They aren't the real source and expire
        # quickly; a row whose Source_URL is vertex is effectively unverifiable.
        ("vertexaisearch.cloud.google.com", "grounding_redirect"),
    ]
    for host, reason in _seed_blocklist:
        cur = conn.execute(
            "INSERT OR IGNORE INTO URL_Blocklist (Hostname, Reason) VALUES (?, ?)",
            (host, reason)
        )
        stats["blocklist_seeded"] += cur.rowcount or 0

    # --- Supplier_Master ---
    conn.execute("""CREATE TABLE IF NOT EXISTS Supplier_Master (
        SupplierId      INTEGER PRIMARY KEY,
        DUNS            TEXT,
        LEI             TEXT,
        OpenCorporatesId TEXT,
        Country_Verified TEXT,
        Vetted          INTEGER NOT NULL DEFAULT 0,
        Vetted_Source   TEXT,
        Vetted_At       TEXT,
        Notes           TEXT,
        FOREIGN KEY (SupplierId) REFERENCES Supplier(Id)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_supplier_master_vetted
                    ON Supplier_Master(Vetted)""")

    # --- Backfill Usage_Tier from BOM appearance ---
    # top 50 by BOM appearance = tier 1, next 50 = tier 2, rest = tier 3.
    appearance_rows = conn.execute("""
        SELECT stc.CanonicalId, COUNT(DISTINCT bc.BOMId) AS bom_count
        FROM SKU_To_Canonical stc
        JOIN BOM_Component bc ON bc.ConsumedProductId = stc.ProductId
        GROUP BY stc.CanonicalId
        ORDER BY bom_count DESC
    """).fetchall()
    for i, (cid, _cnt) in enumerate(appearance_rows):
        tier = 1 if i < 50 else (2 if i < 100 else 3)
        conn.execute(
            "UPDATE Ingredient_Canonical SET Usage_Tier = ? WHERE Id = ?",
            (tier, cid)
        )
        stats["rows_backfilled_tier"] += 1

    # --- Backfill Category from Function ---
    for fn, cat in _FUNCTION_TO_CATEGORY.items():
        cur = conn.execute(
            "UPDATE Ingredient_Canonical SET Category = ? WHERE LOWER(Function) = LOWER(?) AND Category = 'unknown'",
            (cat, fn)
        )
        stats["rows_backfilled_category"] += cur.rowcount or 0

    # --- Index for cheap tier-aware staleness queries ---
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ingredient_tier ON Ingredient_Canonical(Usage_Tier)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ingredient_category ON Ingredient_Canonical(Category)")

    # Log the migration itself.
    conn.execute("""INSERT INTO Enrichment_Run_Log
        (ProductId, Phase, Step, Status, Confidence, Method)
        VALUES (NULL, 0, 'migrate_provenance', 'success', 1.0, 'migration')""")
    conn.commit()
    logger.info("Provenance migration complete: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    conn = sqlite3.connect(str(ENRICHED_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    result = migrate(conn)
    conn.close()
    print(f"\n{result}")
