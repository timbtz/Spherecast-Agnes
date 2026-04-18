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

# Certification keywords to scan for in label text / DSLD claims
CERT_KEYWORDS: dict[str, list[str]] = {
    "NSF": ["nsf certified", "nsf international", "nsf/ansi"],
    "USP": ["usp verified", "usp dietary supplement"],
    "InformedSport": ["informed sport", "informed-sport", "informed choice"],
    "BSCG": ["bscg certified", "banned substance"],
    "Organic": ["usda organic", "certified organic"],
    "NonGMO": ["non-gmo", "non gmo verified", "non-gmo project"],
    "Kosher": ["kosher certified", "kosher"],
    "GlutenFree": ["gluten free", "gluten-free certified"],
    "Vegan": ["vegan certified", "vegan society"],
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
        product_name = sku.split("-", 2)[-1].replace("-", " ") if sku.startswith("FG-") else sku

        hits = dsld.search_product(product_name, size=3)
        if not hits or not hits.get("hits"):
            return

        for hit in hits["hits"]:
            label_id = hit.get("id")
            if not label_id:
                continue
            label = dsld.get_label(label_id)
            if not label:
                continue
            self._extract_and_store_certs(product_id, label)
            return

    def _extract_and_store_certs(self, product_id: int, label: dict) -> None:
        """Scan DSLD label fields for certification signals."""
        text_fields = []
        for claim in label.get("claims", []):
            text_fields.append(str(claim).lower())
        for stmt in label.get("statements", []):
            text_fields.append(str(stmt.get("text", "")).lower())

        full_text = " ".join(text_fields)
        found: dict[str, tuple[str, float]] = {}

        for cert, keywords in CERT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in full_text:
                    found[cert] = ("claimed", 0.72)
                    break

        if not found:
            found["none_identified"] = ("not_required", 0.60)

        conn = sqlite3.connect(self.db_path)
        for cert, (status, confidence) in found.items():
            conn.execute(
                """INSERT OR REPLACE INTO Product_Compliance
                   (ProductId, Certification, Status, Source, Confidence)
                   VALUES (?, ?, ?, 'dsld', ?)""",
                (product_id, cert, status, confidence),
            )
        conn.commit()
        conn.close()
