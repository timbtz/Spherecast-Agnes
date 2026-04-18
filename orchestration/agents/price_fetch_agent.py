"""Async DAG agent: fetch fresh prices for stale ingredients, detect changes, write alerts."""
import logging
import re
import sqlite3
from dotenv import load_dotenv
load_dotenv()

from orchestration.api.agnes_context import AgnesContext

logger = logging.getLogger("agnes.price_fetch_agent")
_ALERT_THRESHOLD = 0.15  # 15% change triggers an alert


def _parse_price(s: str | None) -> float | None:
    if not s:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(s))
    if not nums:
        return None
    return round(sum(float(n) for n in nums[:2]) / min(len(nums), 2), 4)


def _severity(change_pct: float) -> str:
    abs_pct = abs(change_pct)
    if abs_pct >= 30:
        return "critical"
    if abs_pct >= 15:
        return "warning"
    return "info"


async def run(ctx: AgnesContext) -> dict:
    stale = ctx.get("find-stale", {}).get("stale_ingredients", [])
    if not stale:
        return {"alerts_created": [], "suppliers_updated": 0, "count": 0}

    import os
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"alerts_created": [], "suppliers_updated": 0, "count": 0, "skipped": "GOOGLE_API_KEY not set"}

    from orchestration.agents.search_sub_agent import search
    from enrichment.enrichers.supplier_web_enricher import _parse_suppliers, SupplierWebEnricher

    enricher = SupplierWebEnricher(ctx.enriched_db_path)
    alerts_created = []
    suppliers_updated = 0

    for item in stale:
        canonical_id = item["canonical_id"]
        name = item["name"]
        logger.info(f"Fetching fresh prices for {name} (canonical_id={canonical_id})")

        try:
            raw = await search(name, query_hint="bulk supplier B2B price per kg 2025")
        except Exception as e:
            logger.warning(f"Search failed for {name}: {e}")
            continue

        parsed_suppliers = _parse_suppliers(raw, name)
        if not parsed_suppliers:
            continue

        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row

        for s in parsed_suppliers:
            sname = (s.get("supplier_name") or "").strip()[:200]
            if not sname or sname == "research_result":
                continue
            new_price = _parse_price(s.get("price_range_usd_per_kg"))
            if new_price is None:
                continue

            supplier_id = enricher._upsert_supplier(conn, sname, s.get("country"))

            existing = conn.execute(
                """SELECT Price_USD_Per_KG FROM Supplier_Commercial
                   WHERE SupplierId = ? AND CanonicalIngredientId = ?""",
                (supplier_id, canonical_id)
            ).fetchone()

            old_price = existing["Price_USD_Per_KG"] if existing else None

            enricher._write_commercial(conn, supplier_id, canonical_id, s, s.get("website"))
            suppliers_updated += 1

            if old_price and old_price > 0:
                change_pct = (new_price - old_price) / old_price
                if abs(change_pct) >= _ALERT_THRESHOLD:
                    direction = "down" if change_pct < 0 else "up"
                    severity = _severity(change_pct)
                    conn.execute(
                        """INSERT INTO Price_Change_Alert
                           (CanonicalIngredientId, SupplierId, Ingredient_Name, Supplier_Name,
                            Previous_Price_USD, New_Price_USD, Change_Pct, Direction,
                            Severity, Run_Id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (canonical_id, supplier_id, name, sname,
                         old_price, new_price, round(change_pct * 100, 2),
                         direction, severity, ctx.run_id)
                    )
                    alerts_created.append({
                        "ingredient": name, "supplier": sname,
                        "old_price": old_price, "new_price": new_price,
                        "change_pct": round(change_pct * 100, 2),
                        "direction": direction, "severity": severity,
                    })
                    logger.info(f"  ALERT: {name} @ {sname}: ${old_price}→${new_price} ({change_pct:+.1%})")

        conn.commit()
        conn.close()

    return {
        "alerts_created": alerts_created,
        "suppliers_updated": suppliers_updated,
        "count": len(alerts_created),
    }
