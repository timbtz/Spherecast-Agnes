"""Phase 3: Commercial data enrichment — price, MOQ, lead time per Supplier × Ingredient.

Sources (priority order):
  1. Molport API  — chemical-grade bulk pricing
  2. PureBulk     — retail proxy pricing (browser scrape via Google ADK + Playwright)
  3. Alibaba       — bulk Chinese supplier listings (Google ADK search)
"""
import logging
import sqlite3
from pathlib import Path

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
        # TODO Phase 3 sprint: implement Molport lookup, then PureBulk, then Alibaba
        logger.debug(f"Commercial enrichment not yet implemented for '{ingredient_name}'")
