"""Sync tool: find canonical ingredients with stale or missing web-sourced prices.

Hardening (2026-04-19):

  1. Per-category staleness TTL. Commodity excipients (cellulose, magnesium
     stearate) are stable week-to-week; vitamins and APIs move faster.
     Category → TTL days, with 'unknown' falling through to the default.

  2. Sanity-clamp of Last_Updated on read. If MAX(Last_Updated) parses to
     > today (forward-dated, clock skew) or > _MAX_REASONABLE_AGE_DAYS in the
     past, we flag it as 'timestamp_invalid' and refresh it. That eliminates
     the "-400 days" class of artifact from test backfills or bad writes.

  3. Split of no_web_data into:
        - never_refreshed         : canonical has zero google_search rows ever
        - refresh_failed_recently : had rows but all of them are NULL_timestamp
                                    or timestamp_invalid

  4. Priority ordering by Usage_Tier (1/2/3). Tier-1 canonicals are drained
     first regardless of age within the batch cap. Tier-3 can starve when the
     queue is long — that's intentional.

  5. Small jitter on the per-ingredient TTL (±12h) so ingredients refreshed in
     the same batch don't all expire in the same second and create a
     thundering-herd request on the next run.
"""
import random
import sqlite3
from datetime import datetime, timedelta
from orchestration.api.agnes_context import AgnesContext


# Per-category TTL in days. Falls back to _DEFAULT_TTL_DAYS for unknown/missing
# Category. Tune these based on observed price-volatility per category.
_CATEGORY_TTL_DAYS = {
    "commodity_excipient": 14,   # cellulose, mag stearate — stable
    "mineral":             10,
    "protein":             10,
    "botanical":            7,
    "vitamin":              5,   # B-vitamins / D3 move on harvest + processing cycles
    "api":                  5,   # high-purity APIs move with supply shocks
}
_DEFAULT_TTL_DAYS = 7

# Any Last_Updated more than this many days in the past is treated as invalid
# (likely a test backfill with a fixed fake date). Forward-dated timestamps
# are always invalid regardless of magnitude.
_MAX_REASONABLE_AGE_DAYS = 365 * 2

_MAX_RESULTS = 20


def _classify_timestamp(last_updated: str | None, now: datetime) -> tuple[int | None, str | None]:
    """Return (days_ago, validity_flag). flag is None if valid, else a reason."""
    if not last_updated:
        return None, "null_timestamp"
    try:
        dt = datetime.fromisoformat(last_updated)
    except Exception:
        return None, "unparseable_timestamp"
    delta_seconds = (now - dt).total_seconds()
    if delta_seconds < 0:
        return None, "forward_dated"
    days = int(delta_seconds // 86400)
    if days > _MAX_REASONABLE_AGE_DAYS:
        return None, "too_old"
    return days, None


def run(ctx: AgnesContext) -> dict:
    ingredient_name = ctx.trigger_payload.get("ingredient_name", "")
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.utcnow()

    # --- 1. never_refreshed: canonicals with zero google_search rows ever ---
    q_never = """
        SELECT ic.Id, ic.Name, ic.Category, ic.Usage_Tier,
               NULL as last_updated, 'never_refreshed' as reason
        FROM Ingredient_Canonical ic
        WHERE ic.UNII_Code IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM Supplier_Commercial sc
            WHERE sc.CanonicalIngredientId = ic.Id
              AND sc.Price_Source = 'google_search'
        )
    """
    params_never: list = []
    if ingredient_name:
        q_never += " AND LOWER(ic.Name) = LOWER(?)"
        params_never = [ingredient_name]

    never_rows = conn.execute(q_never, params_never).fetchall()

    # --- 2. candidate "maybe stale" rows — fetch latest-per-canonical and
    # classify per-category in Python. WHERE on UNII + Price_Source keeps this
    # cheap (< 1k rows typically).
    q_maybe = """
        SELECT ic.Id, ic.Name, ic.Category, ic.Usage_Tier,
               MAX(sc.Last_Updated) as last_updated
        FROM Ingredient_Canonical ic
        JOIN Supplier_Commercial sc ON sc.CanonicalIngredientId = ic.Id
        WHERE sc.Price_Source = 'google_search'
          AND ic.UNII_Code IS NOT NULL
    """
    params_maybe: list = []
    if ingredient_name:
        q_maybe += " AND LOWER(ic.Name) = LOWER(?)"
        params_maybe = [ingredient_name]
    q_maybe += " GROUP BY ic.Id"
    maybe_rows = conn.execute(q_maybe, params_maybe).fetchall()
    conn.close()

    stale: list[dict] = []
    for r in maybe_rows:
        days_ago, bad_flag = _classify_timestamp(r["last_updated"], now)
        category = r["Category"] or "unknown"
        tier = r["Usage_Tier"] or 3

        if bad_flag:
            # Any kind of invalid timestamp is treated like a failed refresh.
            stale.append({
                "canonical_id": r["Id"],
                "name": r["Name"],
                "category": category,
                "usage_tier": tier,
                "reason": f"refresh_failed_recently:{bad_flag}",
                "days_since_update": None,
            })
            continue

        # Valid timestamp — compare against per-category TTL ± 12h jitter.
        ttl = _CATEGORY_TTL_DAYS.get(category, _DEFAULT_TTL_DAYS)
        effective_ttl_with_jitter = ttl + random.uniform(-0.5, 0.5)
        if days_ago >= effective_ttl_with_jitter:
            stale.append({
                "canonical_id": r["Id"],
                "name": r["Name"],
                "category": category,
                "usage_tier": tier,
                "reason": "stale",
                "days_since_update": days_ago,
            })

    # Build never_refreshed entries.
    never_refreshed = [
        {
            "canonical_id": r["Id"],
            "name": r["Name"],
            "category": r["Category"] or "unknown",
            "usage_tier": r["Usage_Tier"] or 3,
            "reason": "never_refreshed",
            "days_since_update": None,
        }
        for r in never_rows
    ]

    # --- 3. merge + dedupe + order by tier then age ---
    combined = never_refreshed + stale
    seen: set[int] = set()
    deduped: list[dict] = []
    for item in combined:
        if item["canonical_id"] in seen:
            continue
        seen.add(item["canonical_id"])
        deduped.append(item)

    # Tier 1 first (lowest int = highest priority), then oldest-first within tier.
    # Rows with no days_since_update (never_refreshed, invalid timestamps) sort
    # second within tier — we still want the aged ones to jump the queue.
    def _sort_key(x):
        age = x["days_since_update"]
        age_key = -age if age is not None else 10**6  # positive = sorts later
        return (x["usage_tier"], age_key)

    deduped.sort(key=_sort_key)
    return {
        "stale_ingredients":     deduped[:_MAX_RESULTS],
        "count":                 min(len(deduped), _MAX_RESULTS),
        "never_refreshed_total": len(never_refreshed),
        "stale_total":           len(stale),
        "total_candidates":      len(deduped),
    }
