"""Phase 4: Score and rank consolidation opportunities per canonical ingredient."""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.consolidation_scorer")

# Scoring weights — must sum to 1.0
W_COMPANY_COUNT = 0.40
W_BOM_COUNT = 0.25
W_SUPPLIER_CONCENTRATION = 0.20
W_COMPLIANCE_HOMOGENEITY = 0.15


class ConsolidationScorer:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        ingredients = conn.execute(
            "SELECT Id, Name FROM Ingredient_Canonical"
        ).fetchall()

        # Normalisation denominators
        max_companies = conn.execute(
            """SELECT MAX(c) FROM (
               SELECT COUNT(DISTINCT p.CompanyId) AS c
               FROM SKU_To_Canonical stc
               JOIN Product p ON p.Id = stc.ProductId
               GROUP BY stc.CanonicalId)"""
        ).fetchone()[0] or 1

        max_boms = conn.execute(
            """SELECT MAX(c) FROM (
               SELECT COUNT(DISTINCT bc.BOMId) AS c
               FROM SKU_To_Canonical stc
               JOIN BOM_Component bc ON bc.ConsumedProductId = stc.ProductId
               GROUP BY stc.CanonicalId)"""
        ).fetchone()[0] or 1

        scored = 0
        for canonical_id, name in ingredients:
            stats = self._get_stats(conn, canonical_id)
            if stats["company_count"] < 2:
                continue  # No consolidation opportunity with only 1 company

            score = self._compute_score(stats, max_companies, max_boms)
            self._upsert_opportunity(conn, canonical_id, stats, score)
            scored += 1

        conn.commit()
        conn.close()
        logger.info(f"Scored {scored} consolidation opportunities")
        self._print_top(10)

    def _get_stats(self, conn: sqlite3.Connection, canonical_id: int) -> dict:
        company_count = conn.execute(
            """SELECT COUNT(DISTINCT p.CompanyId)
               FROM SKU_To_Canonical stc
               JOIN Product p ON p.Id = stc.ProductId
               WHERE stc.CanonicalId = ?""",
            (canonical_id,),
        ).fetchone()[0]

        bom_count = conn.execute(
            """SELECT COUNT(DISTINCT bc.BOMId)
               FROM SKU_To_Canonical stc
               JOIN BOM_Component bc ON bc.ConsumedProductId = stc.ProductId
               WHERE stc.CanonicalId = ?""",
            (canonical_id,),
        ).fetchone()[0]

        supplier_count = conn.execute(
            """SELECT COUNT(DISTINCT sp.SupplierId)
               FROM SKU_To_Canonical stc
               JOIN Supplier_Product sp ON sp.ProductId = stc.ProductId
               WHERE stc.CanonicalId = ?""",
            (canonical_id,),
        ).fetchone()[0]

        # Find supplier already covering most companies for this ingredient
        best_supplier = conn.execute(
            """SELECT sp.SupplierId, COUNT(DISTINCT p.CompanyId) AS cov
               FROM SKU_To_Canonical stc
               JOIN Supplier_Product sp ON sp.ProductId = stc.ProductId
               JOIN Product p ON p.Id = stc.ProductId
               WHERE stc.CanonicalId = ?
               GROUP BY sp.SupplierId
               ORDER BY cov DESC
               LIMIT 1""",
            (canonical_id,),
        ).fetchone()

        return {
            "company_count": company_count,
            "bom_count": bom_count,
            "supplier_count": supplier_count,
            "best_supplier_id": best_supplier[0] if best_supplier else None,
            "best_supplier_coverage": best_supplier[1] if best_supplier else 0,
        }

    def _compute_score(self, stats: dict, max_companies: int, max_boms: int) -> float:
        company_score = stats["company_count"] / max_companies
        bom_score = stats["bom_count"] / max_boms

        # Supplier concentration: fewer suppliers covering more companies = higher score
        if stats["supplier_count"] > 0:
            supplier_score = 1.0 - (stats["supplier_count"] / max(stats["company_count"], 1))
            supplier_score = max(0.0, min(1.0, supplier_score))
        else:
            supplier_score = 0.0

        # Compliance homogeneity: placeholder 0.5 until Phase 3 data available
        compliance_score = 0.5

        return (
            W_COMPANY_COUNT * company_score
            + W_BOM_COUNT * bom_score
            + W_SUPPLIER_CONCENTRATION * supplier_score
            + W_COMPLIANCE_HOMOGENEITY * compliance_score
        )

    def _upsert_opportunity(self, conn: sqlite3.Connection, canonical_id: int,
                             stats: dict, score: float) -> None:
        conn.execute(
            """INSERT OR REPLACE INTO Consolidation_Opportunity
               (CanonicalIngredientId, Company_Count, BOM_Count, Current_Supplier_Count,
                Consolidation_Score, Recommended_SupplierId)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                canonical_id,
                stats["company_count"],
                stats["bom_count"],
                stats["supplier_count"],
                round(score, 4),
                stats["best_supplier_id"],
            ),
        )

    def _print_top(self, n: int) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT ic.Name, co.Company_Count, co.BOM_Count,
                      co.Current_Supplier_Count, co.Consolidation_Score
               FROM Consolidation_Opportunity co
               JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
               ORDER BY co.Consolidation_Score DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        conn.close()

        logger.info(f"\n── Top {n} Consolidation Opportunities ───────────────────────")
        logger.info(f"{'Ingredient':<40} {'Cos':>4} {'BOMs':>5} {'Supp':>5} {'Score':>7}")
        logger.info("─" * 66)
        for name, cos, boms, supps, score in rows:
            logger.info(f"{name:<40} {cos:>4} {boms:>5} {supps:>5} {score:>7.3f}")
