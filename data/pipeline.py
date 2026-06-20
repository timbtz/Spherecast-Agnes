"""Agnes enrichment pipeline — orchestrates phases 1–4."""
import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("agnes.pipeline")

ENRICHED_DB = ROOT / "db_enriched.sqlite"


def _ensure_bootstrapped() -> None:
    if not ENRICHED_DB.exists():
        logger.info("db_enriched.sqlite not found — running bootstrap first")
        from enrichment.db_bootstrap import bootstrap
        bootstrap()


def run_phase_1() -> None:
    logger.info("═══ Phase 1: Ingredient Identity & Cross-Referencing ═══")
    from enrichment.normalizers.ingredient_normalizer import IngredientNormalizer
    IngredientNormalizer().run()
    _print_cluster_report()


def run_phase_2() -> None:
    logger.info("═══ Phase 2: BOM Quantity Enrichment ═══")
    from enrichment.enrichers.quantity_enricher import QuantityEnricher
    QuantityEnricher().run()


def run_phase_3() -> None:
    logger.info("═══ Phase 3: Commercial & Compliance Enrichment ═══")
    from enrichment.enrichers.commercial_enricher import CommercialEnricher
    from enrichment.enrichers.compliance_enricher import ComplianceEnricher
    CommercialEnricher().run()
    ComplianceEnricher().run()


def run_phase_4() -> None:
    logger.info("═══ Phase 4: Reasoning & Proposal Generation ═══")
    from reasoning.substitution_graph import SubstitutionGraphBuilder
    from reasoning.consolidation_scorer import ConsolidationScorer
    from reasoning.proposal_generator import ProposalGenerator
    SubstitutionGraphBuilder().run()
    ConsolidationScorer().run()
    ProposalGenerator().run()


def _print_cluster_report() -> None:
    """Print top-20 ingredient clusters by company count after Phase 1."""
    import sqlite3
    conn = sqlite3.connect(ENRICHED_DB)
    rows = conn.execute("""
        SELECT
            ic.Name,
            ic.CAS_Number,
            COUNT(DISTINCT p.CompanyId)  AS company_count,
            COUNT(DISTINCT bc.BOMId)     AS bom_count,
            COUNT(DISTINCT sp.SupplierId) AS supplier_count
        FROM Ingredient_Canonical ic
        JOIN SKU_To_Canonical stc ON stc.CanonicalId = ic.Id
        JOIN Product p            ON p.Id = stc.ProductId
        LEFT JOIN BOM_Component bc ON bc.ConsumedProductId = p.Id
        LEFT JOIN Supplier_Product sp ON sp.ProductId = p.Id
        GROUP BY ic.Id
        ORDER BY company_count DESC, bom_count DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    if not rows:
        logger.info("No clusters yet — Phase 1 may not have run.")
        return

    logger.info("\n── Top Consolidation Candidates ──────────────────────────────")
    logger.info(f"{'Ingredient':<40} {'CAS':<14} {'Companies':>9} {'BOMs':>5} {'Suppliers':>9}")
    logger.info("─" * 82)
    for name, cas, companies, boms, suppliers in rows:
        logger.info(f"{name:<40} {(cas or 'N/A'):<14} {companies:>9} {boms:>5} {suppliers:>9}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agnes enrichment pipeline")
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3, 4],
        help="Run a single phase (omit to run all phases)"
    )
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="Force re-bootstrap of db_enriched.sqlite before running"
    )
    args = parser.parse_args()

    if args.bootstrap:
        from enrichment.db_bootstrap import bootstrap
        bootstrap(force=True)

    _ensure_bootstrapped()

    phases = {1: run_phase_1, 2: run_phase_2, 3: run_phase_3, 4: run_phase_4}

    if args.phase:
        phases[args.phase]()
    else:
        for phase_fn in phases.values():
            phase_fn()

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
