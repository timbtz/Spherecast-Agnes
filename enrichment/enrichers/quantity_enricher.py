"""Phase 2: BOM quantity enrichment.

Strategy (priority order):
  1. DSLD API — search finished product by name → extract Supplement Facts
  2. Retailer scraping — Playwright browser agent on product page
  3. Google ADK search — discover product page URL then browser agent
"""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.quantity_enricher")


class QuantityEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        finished_goods = conn.execute(
            """SELECT p.Id, p.SKU, p.CompanyId
               FROM Product p
               WHERE p.Type = 'finished-good'"""
        ).fetchall()
        conn.close()

        logger.info(f"Enriching BOM quantities for {len(finished_goods)} finished goods")

        for product_id, sku, company_id in finished_goods:
            self._enrich_product(product_id, sku)

        logger.info("Phase 2 quantity enrichment complete.")

    def _enrich_product(self, product_id: int, sku: str) -> None:
        from enrichment.sources.dsld import DSLDClient

        dsld = DSLDClient(self.db_path)

        # Extract product identifier from SKU for search
        product_name = self._sku_to_product_name(sku)
        if not product_name:
            self._log_skip(product_id, f"Could not parse product name from SKU: {sku}")
            return

        # Tier 1: DSLD
        hits = dsld.search_product(product_name, size=5)
        if hits and hits.get("hits"):
            for hit in hits["hits"]:
                label_id = hit.get("id")
                if not label_id:
                    continue
                label = dsld.get_label(label_id)
                if not label:
                    continue
                amounts = dsld.extract_ingredient_amounts(label)
                if amounts:
                    self._store_amounts(product_id, amounts)
                    return

        # Tier 2: Retailer browser scraping — TODO: implement in Phase 2 sprint
        logger.debug(f"DSLD miss for product_id={product_id} '{product_name}' — browser agent needed")
        self._log_skip(product_id, "DSLD miss — browser scraping not yet implemented")

    def _sku_to_product_name(self, sku: str) -> str | None:
        """Extract a searchable product name from a finished-good SKU."""
        # FG SKU format: FG-{retailer}-{product-identifier}
        # e.g. FG-iherb-10421, FG-walmart-5432, FG-thrive-market-671635734464
        if not sku.startswith("FG-"):
            return None
        parts = sku.split("-", 2)
        return parts[2].replace("-", " ") if len(parts) >= 3 else None

    def _store_amounts(self, product_id: int, amounts: list[dict]) -> None:
        conn = sqlite3.connect(self.db_path)
        boms = conn.execute(
            "SELECT Id FROM BOM WHERE ProducedProductId = ?", (product_id,)
        ).fetchall()

        for bom_row in boms:
            bom_id = bom_row[0]
            components = conn.execute(
                "SELECT ConsumedProductId FROM BOM_Component WHERE BOMId = ?", (bom_id,)
            ).fetchall()

            for comp_row in components:
                consumed_product_id = comp_row[0]
                # Match by canonical ingredient name — join via SKU_To_Canonical
                canonical = conn.execute(
                    """SELECT ic.Name FROM Ingredient_Canonical ic
                       JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
                       WHERE stc.ProductId = ?""",
                    (consumed_product_id,),
                ).fetchone()
                if not canonical:
                    continue

                canonical_name = canonical[0].lower()
                for amt in amounts:
                    if amt["ingredient_name"].lower() in canonical_name or \
                       canonical_name in amt["ingredient_name"].lower():
                        conn.execute(
                            """INSERT OR REPLACE INTO BOM_Component_Quantity
                               (BOMId, ConsumedProductId, Amount, Unit, PerServing,
                                ServingUnit, Source, Confidence)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                bom_id, consumed_product_id,
                                amt.get("amount"), amt.get("unit"),
                                amt.get("per_serving"), amt.get("serving_unit"),
                                amt.get("source", "dsld"), amt.get("confidence", 0.88),
                            ),
                        )
                        break

        conn.commit()
        conn.close()

    def _log_skip(self, product_id: int, reason: str) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO Enrichment_Run_Log
                   (ProductId, Phase, Step, Status, Confidence, Method, Error_Msg)
                   VALUES (?, 2, 'quantity_enrichment', 'skipped', 0.0, NULL, ?)""",
                (product_id, reason),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
