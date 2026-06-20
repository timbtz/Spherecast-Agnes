"""Phase 3: Compliance enrichment — certifications per finished product.

Sources (priority order):
  1. DSLD label claims[] — extract certification signals via LLM
  2. Retailer badge parsing — Playwright scrape of product page cert badges
  3. NSF / USP / Informed Sport registries — browser agent on certification DBs
"""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.compliance_enricher")

CERT_SIGNAL_MAP: dict[str, str] = {
    "nsf": "NSF", "nsf certified": "NSF", "nsf international": "NSF", "nsf/ansi": "NSF",
    "usp verified": "USP", "usp dietary supplement": "USP", "usp": "USP",
    "informed sport": "InformedSport", "informed-sport": "InformedSport",
    "informed choice": "InformedSport",
    "bscg": "BSCG", "certified for sport": "BSCG", "banned substance": "BSCG",
    "organic": "Organic", "usda organic": "Organic", "certified organic": "Organic",
    "non-gmo": "NonGMO", "non gmo": "NonGMO", "non-gmo project": "NonGMO",
    "gluten-free": "GlutenFree", "gluten free": "GlutenFree",
    "gluten-free certified": "GlutenFree",
    "vegan": "Vegan", "certified vegan": "Vegan", "vegan society": "Vegan",
    "halal": "Halal",
    "cgmp": "cGMP", "gmp": "cGMP", "current good manufacturing": "cGMP",
    "kosher": "Kosher", "kosher certified": "Kosher",
}


class ComplianceEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        products = conn.execute(
            "SELECT Id, SKU FROM Product WHERE Type = 'finished-good'"
        ).fetchall()
        conn.close()

        logger.info(f"Enriching compliance for {len(products)} finished goods")

        for product_id, sku in products:
            self._enrich_product(product_id, sku)

        logger.info("Phase 3 compliance enrichment complete.")

    def _enrich_product(self, product_id: int, sku: str) -> None:
        from enrichment.sources.dsld import DSLDClient

        dsld = DSLDClient(self.db_path)

        # Tier 1: reuse DSLD label already matched in Phase 2 (most reliable)
        conn = sqlite3.connect(self.db_path)
        phase2_label = conn.execute(
            """SELECT DISTINCT bcq.DSLD_Label_Id FROM BOM_Component_Quantity bcq
               JOIN BOM b ON b.Id = bcq.BOMId
               WHERE b.ProducedProductId = ? AND bcq.DSLD_Label_Id IS NOT NULL
               LIMIT 1""",
            (product_id,)
        ).fetchone()
        conn.close()

        if phase2_label and phase2_label[0]:
            label = dsld.get_label(phase2_label[0])
            if label:
                self._extract_and_store_certs(product_id, label)
                return

        # Tier 2: extract product name from SKU slug and search DSLD
        slug = sku.split("-", 2)[-1] if sku.startswith("FG-") else sku
        # Strip retailer prefix (iherb-, walmart-, etc.)
        for prefix in ("iherb-", "walmart-", "amazon-", "target-", "vitacost-",
                       "vitamin-shoppe-", "walgreens-", "cvs-", "costco-",
                       "sams-club-", "gnc-", "thrive-market-"):
            if slug.startswith(prefix):
                slug = slug[len(prefix):]
                break
        # Skip pure numeric/barcode slugs
        import re
        if re.match(r'^[\d\-]+$', slug) or re.match(r'^[A-Z0-9\-]+$', slug):
            return

        product_name = slug.replace("-", " ").strip()
        hits = dsld.search_product(product_name, size=3)
        if not hits or not hits.get("hits"):
            return

        for hit in hits["hits"]:
            label_id = hit.get("_id") or hit.get("id")
            if not label_id:
                continue
            label = dsld.get_label(label_id)
            if not label:
                continue
            self._extract_and_store_certs(product_id, label)
            return

    def _extract_and_store_certs(self, product_id: int, label: dict) -> None:
        """Scan DSLD label fields for certification signals using two-tier scan."""
        off_market = 1 if label.get("offMarket") in ("1", True, 1) else 0
        found: dict[str, tuple[str, float, int]] = {}  # cert → (status, confidence, off_market_warning)

        # Tier 1: claims[].langualCodeDescription (confidence 0.85)
        for claim in label.get("claims", []):
            desc = str(
                claim.get("langualCodeDescription", claim) if isinstance(claim, dict) else claim
            ).lower()
            for signal, cert in CERT_SIGNAL_MAP.items():
                if signal in desc and cert not in found:
                    found[cert] = ("claimed", 0.85, off_market)

        # Tier 2: statements[].notes or statements[].text (DSLD uses "notes" key, fallback to "text")
        for stmt in label.get("statements", []):
            if isinstance(stmt, dict):
                text = str(stmt.get("notes") or stmt.get("text") or "").lower()
            else:
                text = str(stmt).lower()
            for signal, cert in CERT_SIGNAL_MAP.items():
                if signal in text and cert not in found:
                    found[cert] = ("implied", 0.65, off_market)

        if not found:
            return  # No certs found — do not insert placeholder rows

        conn = sqlite3.connect(self.db_path)
        for cert, (status, confidence, off_mkt_warning) in found.items():
            conn.execute(
                """INSERT OR REPLACE INTO Product_Compliance
                   (ProductId, Certification, Status, Source, Confidence, Off_Market_Warning)
                   VALUES (?, ?, ?, 'dsld', ?, ?)""",
                (product_id, cert, status, confidence, off_mkt_warning),
            )
        conn.commit()
        conn.close()
