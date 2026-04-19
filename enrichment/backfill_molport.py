"""Batch Molport enrichment: populate Supplier_Commercial from Molport API for all CAS/SMILES canonicals."""
import logging
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_molport")


def _get_targets(conn: sqlite3.Connection) -> list[tuple]:
    """Return (id, name, cas, smiles) for canonicals with CAS/SMILES not yet in Molport.
    Ordered by SKU count descending so highest-impact ingredients are processed first.
    """
    return conn.execute(
        """SELECT ic.Id, ic.Name, ic.CAS_Number, ic.SMILES
           FROM Ingredient_Canonical ic
           WHERE (ic.CAS_Number IS NOT NULL OR ic.SMILES IS NOT NULL)
           AND NOT EXISTS (
               SELECT 1 FROM Supplier_Commercial sc
               WHERE sc.CanonicalIngredientId = ic.Id
                 AND sc.Price_Source = 'molport'
           )
           ORDER BY (
               SELECT COUNT(*) FROM SKU_To_Canonical stc
               WHERE stc.CanonicalId = ic.Id
           ) DESC"""
    ).fetchall()


def _upsert_supplier(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name) VALUES (?)", (name,))
    if cur.lastrowid:
        return cur.lastrowid
    return conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (name,)).fetchone()[0]


def _write_rows(conn: sqlite3.Connection, canonical_id: int, rows: list[dict]) -> int:
    written = 0
    for row in rows:
        supplier_name = (row.get("supplier_name") or "").strip()
        if not supplier_name:
            continue
        try:
            sid = _upsert_supplier(conn, supplier_name)
            conn.execute(
                """INSERT OR REPLACE INTO Supplier_Commercial
                   (SupplierId, CanonicalIngredientId,
                    Price_USD_Per_KG, Price_Qty_KG, MOQ_KG,
                    Lead_Time_Days, Country_Origin, Country_Shipping,
                    Price_Type, Price_Source, Confidence,
                    Grade_Unverified, Molport_Catalog_Id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'retail_proxy', 'molport', 0.70, 1, ?)""",
                (
                    sid, canonical_id,
                    row.get("price"), row.get("price_qty_kg"),
                    None,  # MOQ — not in flatten_suppliers output directly
                    row.get("delivery_days"),
                    row.get("country_origin"), row.get("country_shipping"),
                    row.get("molport_catalog_id"),
                )
            )
            written += 1
        except Exception as e:
            logger.warning(f"  Failed to write Molport row for {supplier_name!r}: {e}")
    return written


def run(limit: int | None = None) -> None:
    import os
    has_api_key = bool(os.getenv("MOLPORT_API_KEY"))
    scraper_enabled = os.getenv("MOLPORT_SCRAPER_ENABLED") == "1"
    fixtures_only = os.getenv("MOLPORT_FIXTURES_ONLY") == "1"

    if not has_api_key and not scraper_enabled and not fixtures_only:
        print("ERROR: No Molport access configured.")
        print("  Set MOLPORT_API_KEY for REST API, or MOLPORT_SCRAPER_ENABLED=1 for Playwright scraper.")
        return

    from enrichment.sources.molport import MolportClient
    client = MolportClient(ENRICHED_DB)

    conn = sqlite3.connect(ENRICHED_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    targets = _get_targets(conn)
    conn.close()

    if limit:
        targets = targets[:limit]

    logger.info(f"backfill_molport: {len(targets)} canonicals to enrich")
    print(f"Targets: {len(targets)} canonicals with no Molport rows")

    total_written = 0
    for canonical_id, name, cas, smiles in targets:
        rows = client.lookup_ingredient({"cas_number": cas, "smiles": smiles, "name": name})
        if not rows:
            logger.info(f"  {name}: no Molport results")
            continue

        conn = sqlite3.connect(ENRICHED_DB)
        conn.execute("PRAGMA journal_mode=WAL")
        n = _write_rows(conn, canonical_id, rows)
        conn.commit()
        conn.close()
        total_written += n
        print(f"  {name}: {len(rows)} rows → {n} written")
        time.sleep(0.5)  # polite rate-limiting between ingredients

    client.close()
    print(f"\nDone: {len(targets)} ingredients processed, {total_written} Molport rows written")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill Supplier_Commercial from Molport")
    parser.add_argument("--limit", type=int, default=None, help="Max ingredients to process")
    parser.add_argument("--scraper", action="store_true", help="Force MOLPORT_SCRAPER_ENABLED=1")
    args = parser.parse_args()
    if args.scraper:
        import os
        os.environ["MOLPORT_SCRAPER_ENABLED"] = "1"
    logging.basicConfig(level=logging.INFO)
    run(limit=args.limit)
