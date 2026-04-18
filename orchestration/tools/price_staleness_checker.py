"""Sync tool: find canonical ingredients with stale or missing web-sourced prices."""
import sqlite3
from datetime import datetime, timedelta
from orchestration.api.agnes_context import AgnesContext

_STALE_DAYS = 7
_MAX_RESULTS = 20


def run(ctx: AgnesContext) -> dict:
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "")
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    q_missing = """
        SELECT ic.Id, ic.Name, NULL as last_updated, 'no_web_data' as reason
        FROM Ingredient_Canonical ic
        WHERE ic.UNII_Code IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM Supplier_Commercial sc
            WHERE sc.CanonicalIngredientId = ic.Id AND sc.Price_Source = 'google_search'
        )
    """
    stale_cutoff = (datetime.utcnow() - timedelta(days=_STALE_DAYS)).strftime("%Y-%m-%d")
    q_stale = """
        SELECT ic.Id, ic.Name, MAX(sc.Last_Updated) as last_updated, 'stale' as reason
        FROM Ingredient_Canonical ic
        JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
        WHERE sc.Price_Source = 'google_search'
        GROUP BY ic.Id
        HAVING MAX(sc.Last_Updated) < ?
    """
    params_stale = [stale_cutoff]

    if ingredient_name:
        q_missing += " AND LOWER(ic.Name) = LOWER(?)"
        q_stale = q_stale.replace("HAVING", f"AND LOWER(ic.Name) = LOWER(?) HAVING")
        params_stale = [ingredient_name, stale_cutoff]

    missing = conn.execute(q_missing, [ingredient_name] if ingredient_name else []).fetchall()
    stale = conn.execute(q_stale, params_stale).fetchall()
    conn.close()

    results = []
    seen: set[int] = set()
    for r in list(missing) + list(stale):
        if r["Id"] in seen:
            continue
        seen.add(r["Id"])
        last_updated = r["last_updated"]
        days_ago = None
        if last_updated:
            try:
                days_ago = (datetime.utcnow() - datetime.fromisoformat(last_updated)).days
            except Exception:
                pass
        results.append({
            "canonical_id": r["Id"],
            "name": r["Name"],
            "reason": r["reason"],
            "days_since_update": days_ago,
        })
        if len(results) >= _MAX_RESULTS:
            break

    return {"stale_ingredients": results, "count": len(results)}
