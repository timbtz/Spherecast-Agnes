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
    from enrichment.enrichers.supplier_web_enricher import (
        _parse_suppliers, SupplierWebEnricher,
        _first, _PRICE_KEYS, _URL_KEYS,
    )

    enricher = SupplierWebEnricher(ctx.enriched_db_path)
    alerts_created = []
    suppliers_updated = 0
    found_ingredients = 0
    failed_ingredients = []

    for item in stale:
        canonical_id = item["canonical_id"]
        name = item["name"]
        logger.info(f"Fetching fresh prices for {name} (canonical_id={canonical_id})")

        try:
            raw = await search(name, query_hint="bulk supplier B2B price per kg 2025")
        except Exception as e:
            logger.warning(f"Search failed for {name}: {e}")
            failed_ingredients.append({"ingredient": name, "reason": "search_error"})
            continue

        parsed_suppliers = _parse_suppliers(raw, name)
        if not parsed_suppliers:
            logger.warning(f"  {name}: parser returned 0 suppliers")
            failed_ingredients.append({"ingredient": name, "reason": "parse_empty"})
            continue

        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row

        written_for_ingredient = 0
        for s in parsed_suppliers:
            sname = (s.get("supplier_name") or "").strip()[:200]
            if not sname or sname == "research_result":
                continue
            # Defensive field-name lookup — the model sometimes returns
            # `price_range` or `price` instead of `price_range_usd_per_kg`.
            price_raw = _first(s, _PRICE_KEYS)
            new_price = _parse_price(price_raw)
            if new_price is None:
                continue

            supplier_id = enricher._upsert_supplier(conn, sname, s.get("country"))

            existing = conn.execute(
                """SELECT Price_USD_Per_KG FROM Supplier_Commercial
                   WHERE SupplierId = ? AND CanonicalIngredientId = ?""",
                (supplier_id, canonical_id)
            ).fetchone()

            old_price = existing["Price_USD_Per_KG"] if existing else None

            url = _first(s, _URL_KEYS)
            if not enricher._write_commercial(conn, supplier_id, canonical_id, s, url):
                # QC-rejected — skip alert generation too
                continue
            suppliers_updated += 1
            written_for_ingredient += 1

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

        if written_for_ingredient > 0:
            found_ingredients += 1
            logger.info(f"  {name}: {written_for_ingredient} supplier rows written")
        else:
            logger.warning(
                f"  {name}: found {len(parsed_suppliers)} suppliers in search, "
                f"but 0 usable after parse/QC (field-name mismatch, price unparseable, "
                f"or all outliers)"
            )
            failed_ingredients.append({"ingredient": name, "reason": "no_usable_rows"})

    return {
        "alerts_created": alerts_created,
        "suppliers_updated": suppliers_updated,
        "count": len(alerts_created),
        "found_ingredients": found_ingredients,
        "failed_ingredients": failed_ingredients,
        "stale_total": len(stale),
    }
