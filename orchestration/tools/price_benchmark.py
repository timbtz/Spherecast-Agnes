"""
Deterministic tool: compute price statistics for a canonical ingredient and flag
suppliers whose price deviates > threshold% from the median.
"""
import sqlite3
import statistics

from orchestration.api.agnes_context import AgnesContext

_DEVIATION_THRESHOLD = 0.20  # 20% from median


def run(ctx: AgnesContext) -> dict:
    canonical_id = (
        ctx.get("find-alternatives", {}).get("canonical_id")
        or ctx.trigger_payload.get("canonical_id")
    )
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "")

    if not canonical_id and ingredient_name:
        conn = sqlite3.connect(str(ctx.enriched_db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT Id FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
            (ingredient_name,),
        ).fetchone()
        conn.close()
        canonical_id = row["Id"] if row else None

    if not canonical_id:
        return {"outliers": [], "stats": {}, "error": "no canonical_id resolved"}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT
            sc.SupplierId,
            s.Name              AS supplier_name,
            sc.Price_USD_Per_KG AS price,
            sc.MOQ_KG,
            sc.Confidence,
            sc.Price_Type,
            sc.Country_Origin
        FROM Supplier_Commercial sc
        JOIN Supplier s ON s.Id = sc.SupplierId
        WHERE sc.CanonicalIngredientId = ?
        AND sc.Price_USD_Per_KG IS NOT NULL
        AND sc.Confidence >= 0.5
        ORDER BY sc.Price_USD_Per_KG
        """,
        (canonical_id,),
    ).fetchall()

    conn.close()

    if not rows:
        return {"outliers": [], "stats": {}, "prices": []}

    prices = [r["price"] for r in rows]
    median = statistics.median(prices)
    stdev = statistics.stdev(prices) if len(prices) > 1 else 0

    outliers = []
    annotated = []
    for r in rows:
        deviation = (r["price"] - median) / median if median else 0
        entry = {**dict(r), "deviation_from_median": round(deviation, 3), "median": round(median, 4)}
        annotated.append(entry)
        if abs(deviation) > _DEVIATION_THRESHOLD:
            outliers.append(entry)

    return {
        "outliers": outliers,
        "annotated_prices": annotated,
        "stats": {
            "median": round(median, 4),
            "min": round(min(prices), 4),
            "max": round(max(prices), 4),
            "stdev": round(stdev, 4),
            "count": len(prices),
        },
        "canonical_id": canonical_id,
        "ingredient_name": ingredient_name,
    }
