"""Phase 3: Commercial data enrichment — price, MOQ, lead time per Supplier × Ingredient.

Sources (priority order):
  1. Molport API  — chemical-grade bulk pricing
  2. PureBulk     — retail proxy pricing (browser scrape via Google ADK + Playwright)
  3. Alibaba       — bulk Chinese supplier listings (Google ADK search)
"""
import logging
import sqlite3
from pathlib import Path

from enrichment.sources.molport import MolportClient

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.commercial_enricher")


class CommercialEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        # Get all Supplier × Canonical Ingredient pairs from existing data
        pairs = conn.execute(
            """SELECT DISTINCT sp.SupplierId, stc.CanonicalId, ic.Name
               FROM Supplier_Product sp
               JOIN SKU_To_Canonical stc ON stc.ProductId = sp.ProductId
               JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
               WHERE NOT EXISTS (
                   SELECT 1 FROM Supplier_Commercial sc
                   WHERE sc.SupplierId = sp.SupplierId
                     AND sc.CanonicalIngredientId = stc.CanonicalId
               )"""
        ).fetchall()
        conn.close()

        logger.info(f"Fetching commercial data for {len(pairs)} supplier×ingredient pairs")

        for supplier_id, canonical_id, ingredient_name in pairs:
            self._enrich_pair(supplier_id, canonical_id, ingredient_name)

        logger.info("Phase 3 commercial enrichment complete.")

    def _enrich_pair(self, supplier_id: int, canonical_id: int, ingredient_name: str) -> None:
        conn = sqlite3.connect(self.db_path)
        canonical = conn.execute(
            "SELECT CAS_Number, SMILES FROM Ingredient_Canonical WHERE Id = ?",
            (canonical_id,)
        ).fetchone()
        conn.close()

        if not canonical:
            return

        cas, smiles = canonical
        molport = MolportClient(self.db_path)
        rows = molport.lookup_ingredient({"cas_number": cas, "smiles": smiles})

        if not rows:
            return

        conn = sqlite3.connect(self.db_path)
        for row in rows:
            supplier_name = row.get("supplier_name")
            if not supplier_name:
                continue

            existing = conn.execute(
                "SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)
            ).fetchone()
            if existing:
                molport_supplier_id = existing[0]
            else:
                # Supplier table schema is (Id, Name) — country lives on Supplier_Commercial
                cur = conn.execute(
                    "INSERT OR IGNORE INTO Supplier (Name) VALUES (?)",
                    (supplier_name,)
                )
                molport_supplier_id = cur.lastrowid or conn.execute(
                    "SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)
                ).fetchone()[0]

            conn.execute(
                """INSERT OR REPLACE INTO Supplier_Commercial
                   (SupplierId, CanonicalIngredientId,
                    Price_USD_Per_KG, Price_Qty_KG, MOQ_KG,
                    Lead_Time_Days, Country_Origin, Country_Shipping,
                    Price_Type, Price_Source, Confidence,
                    Grade_Unverified, Molport_Catalog_Id, Data_Freshness_Days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    molport_supplier_id, canonical_id,
                    row.get("price_usd"), row.get("price_qty_kg"), None,
                    row.get("delivery_days"), row.get("country_origin"), row.get("country_shipping"),
                    "retail_proxy", "molport", 0.70,
                    1, row.get("molport_catalog_id"), None,
                )
            )

        conn.commit()
        conn.close()
        logger.info(f"Commercial: {len(rows)} Molport rows stored for canonical_id={canonical_id} ({ingredient_name})")
