"""Phase 2: BOM quantity enrichment via DSLD supplement label data.

Strategy (priority order):
  1. Slug-path  — extract product name from readable SKU → DSLD brand+name search
  2. Fingerprint — ingredient overlap matching for numeric-ID SKUs
"""
import logging
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from enrichment.sources.dsld import DSLDClient
from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.quantity_enricher")


class QuantityEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self._dsld = DSLDClient(self.db_path)
        self._fuzzy = FuzzyMatcher(self.db_path)
        self._apply_schema_migrations()

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT p.Id, p.SKU, c.Name AS company_name
            FROM Product p
            JOIN Company c ON c.Id = p.CompanyId
            WHERE p.Type = 'finished-good'
        """).fetchall()
        conn.close()

        logger.info(f"Enriching BOM quantities for {len(rows)} finished goods")

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda r: self._enrich_product(*r), rows))

        self._report()
        logger.info("Phase 2 quantity enrichment complete.")

    def _enrich_product(self, product_id: int, sku: str, company_name: str) -> None:
        brand, product_name = self._parse_fg_sku(sku, company_name)

        conn = sqlite3.connect(self.db_path)
        boms = conn.execute(
            "SELECT Id FROM BOM WHERE ProducedProductId=?", (product_id,)
        ).fetchall()
        conn.close()

        if not boms:
            return

        match = None
        if product_name:
            match = self._dsld.find_label(brand, product_name)
        if not match:
            bom_id = boms[0][0]
            conn2 = sqlite3.connect(self.db_path)
            match = self._fingerprint_match(conn2, company_name, bom_id)
            conn2.close()

        if not match:
            self._log_skip(product_id, f"No DSLD match for '{brand} {product_name}'")
            return

        ingredients = self._dsld.extract_label_ingredients(match["dsld_id"])
        if not ingredients:
            self._log_skip(product_id, f"Empty ingredients for DSLD label {match['dsld_id']}")
            return

        self._store_amounts(product_id, boms, ingredients, match)

    def _parse_fg_sku(self, sku: str, company_name: str) -> tuple[str, str | None]:
        """Return (brand, product_name_or_None) for DSLD search."""
        if not sku.startswith("FG-"):
            return company_name, None
        rest = sku[3:]

        for prefix in ("iherb-", "walmart-", "amazon-", "target-", "vitacost-",
                       "vitamin-shoppe-", "walgreens-", "cvs-", "costco-",
                       "sams-club-", "gnc-", "thrive-market-"):
            if rest.startswith(prefix):
                slug = rest[len(prefix):]
                if re.match(r'^\d+$', slug) or re.match(r'^[A-Z0-9\-]+$', slug):
                    return company_name, None
                product_name = slug.replace("-", " ").strip()
                return company_name, product_name
        return company_name, None

    def _fingerprint_match(self, conn: sqlite3.Connection, company_name: str,
                           bom_id: int) -> dict | None:
        """Match a finished good to DSLD by ingredient overlap."""
        bom_ingredients = conn.execute("""
            SELECT ic.Name FROM Ingredient_Canonical ic
            JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
            JOIN BOM_Component bc ON bc.ConsumedProductId = stc.ProductId
            WHERE bc.BOMId = ?
        """, (bom_id,)).fetchall()

        if not bom_ingredients:
            return None

        bom_names = {r[0].lower() for r in bom_ingredients}

        data = self._dsld._search({"q": company_name, "size": 10})
        if not data or not data.get("hits"):
            return None

        best, best_overlap = None, 0
        for hit in data["hits"]:
            src = hit.get("_source", {})
            dsld_ingredients = {i["name"].lower() for i in src.get("allIngredients", [])}
            overlap = len(bom_names & dsld_ingredients)
            if overlap > best_overlap:
                best_overlap = overlap
                best = {
                    "dsld_id": hit["_id"],
                    "confidence": min(0.65 + overlap * 0.05, 0.85),
                    "off_market": src.get("offMarket", "1"),
                    "brand_name": src.get("brandName"),
                    "full_name": src.get("fullName"),
                }

        return best if best_overlap >= 3 else None

    def _store_amounts(self, product_id: int, boms: list, ingredients: list[dict],
                       match: dict) -> None:
        conn = sqlite3.connect(self.db_path)
        stored = 0
        for bom_row in boms:
            bom_id = bom_row[0]
            components = conn.execute(
                "SELECT ConsumedProductId FROM BOM_Component WHERE BOMId=?", (bom_id,)
            ).fetchall()
            for comp_row in components:
                consumed_id = comp_row[0]
                canonical = conn.execute("""
                    SELECT ic.Id, ic.Name FROM Ingredient_Canonical ic
                    JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
                    WHERE stc.ProductId = ?
                """, (consumed_id,)).fetchone()
                if not canonical:
                    continue
                _, canonical_name = canonical

                best_amt = self._match_ingredient_to_amounts(canonical_name, ingredients)
                if not best_amt:
                    continue

                conn.execute("""
                    INSERT OR REPLACE INTO BOM_Component_Quantity
                    (BOMId, ConsumedProductId, Amount, Unit, PerServing, ServingUnit,
                     DSLD_Label_Id, Off_Market, Source, Confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bom_id, consumed_id,
                    best_amt.get("amount"), best_amt.get("unit"),
                    best_amt.get("per_serving"), best_amt.get("serving_unit"),
                    str(match["dsld_id"]),
                    1 if match.get("off_market") == "1" else 0,
                    "dsld", best_amt.get("confidence", match["confidence"]),
                ))
                stored += 1

        conn.commit()
        conn.close()
        logger.info(f"product_id={product_id} → stored {stored} quantities from DSLD label {match['dsld_id']}")

    def _match_ingredient_to_amounts(self, canonical_name: str,
                                     amounts: list[dict]) -> dict | None:
        """Find best-matching ingredient in DSLD amounts list via rapidfuzz."""
        from rapidfuzz import fuzz, process as fuzz_process
        dsld_names = [a["ingredient_name"] for a in amounts]
        best = fuzz_process.extractOne(canonical_name, dsld_names, scorer=fuzz.token_set_ratio)
        if best and best[1] >= 70:
            idx = dsld_names.index(best[0])
            return amounts[idx]
        return None

    def _report(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            total_bom = conn.execute("SELECT COUNT(*) FROM BOM_Component").fetchone()[0]
            enriched = conn.execute("SELECT COUNT(*) FROM BOM_Component_Quantity").fetchone()[0]
            fg_total = conn.execute(
                "SELECT COUNT(*) FROM Product WHERE Type='finished-good'"
            ).fetchone()[0]
            fg_enriched = conn.execute("""
                SELECT COUNT(DISTINCT b.ProducedProductId) FROM BOM b
                JOIN BOM_Component_Quantity bcq ON bcq.BOMId = b.Id
            """).fetchone()[0]
            conn.close()
            pct_bom = enriched / total_bom * 100 if total_bom else 0
            pct_fg = fg_enriched / fg_total * 100 if fg_total else 0
            logger.info(
                f"Phase 2 coverage: {enriched}/{total_bom} BOM components ({pct_bom:.1f}%), "
                f"{fg_enriched}/{fg_total} finished goods ({pct_fg:.1f}%)"
            )
        except Exception as e:
            logger.warning(f"Report failed: {e}")

    def _apply_schema_migrations(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        for col, typedef in [("DSLD_Label_Id", "TEXT"), ("Off_Market", "INTEGER")]:
            try:
                conn.execute(
                    f"ALTER TABLE BOM_Component_Quantity ADD COLUMN {col} {typedef}"
                )
            except Exception:
                pass
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
