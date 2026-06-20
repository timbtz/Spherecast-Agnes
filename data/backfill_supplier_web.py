"""Batch supplier web enrichment: populate Supplier_Commercial from Google Search."""
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.backfill_supplier_web")


async def _run():
    import os
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not set — cannot run web enrichment")
        return
    from enrichment.enrichers.supplier_web_enricher import SupplierWebEnricher
    enricher = SupplierWebEnricher(ENRICHED_DB)
    result = await enricher.run_batch()
    print(f"Done: {result['processed']} ingredients processed, {result['total_suppliers_written']} suppliers written")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
