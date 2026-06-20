"""Compute landed cost for a (supplier_country, plant_country) pair.

Called from supplier scoring to produce the L (logistics) and partly the
C (cost) features. Uses Lane_Cost rows seeded by map_logistics.py.

If no direct lane is found, we fall back to a 2-leg route through a hub
country (US or DE) and add a 1.15x penalty for the extra handling.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple


HUB_FALLBACKS = ["US", "DE"]
INDIRECT_PENALTY = 1.15


@dataclass
class LandedCost:
    cost_usd_per_kg: float
    lead_time_days: float
    mode: str
    via: Optional[str] = None
    confidence: float = 0.7  # default for direct lookup


def _direct(
    conn: sqlite3.Connection, origin: str, dest: str, preferred_mode: Optional[str] = None
) -> Optional[LandedCost]:
    if preferred_mode:
        row = conn.execute(
            """
            SELECT Mode, LeadTimeDays, CostUSDPerKg FROM Lane_Cost
            WHERE OriginCountry = ? AND DestCountry = ? AND Mode = ?
            ORDER BY LastUpdated DESC LIMIT 1
            """,
            (origin, dest, preferred_mode),
        ).fetchone()
        if row:
            return LandedCost(
                cost_usd_per_kg=row[2], lead_time_days=row[1], mode=row[0], confidence=0.85
            )

    # Pick cheapest direct lane regardless of mode.
    row = conn.execute(
        """
        SELECT Mode, LeadTimeDays, CostUSDPerKg FROM Lane_Cost
        WHERE OriginCountry = ? AND DestCountry = ?
        ORDER BY CostUSDPerKg ASC LIMIT 1
        """,
        (origin, dest),
    ).fetchone()
    if row:
        return LandedCost(
            cost_usd_per_kg=row[2], lead_time_days=row[1], mode=row[0], confidence=0.75
        )
    return None


def _via_hub(conn: sqlite3.Connection, origin: str, dest: str) -> Optional[LandedCost]:
    for hub in HUB_FALLBACKS:
        if hub in (origin, dest):
            continue
        leg1 = _direct(conn, origin, hub)
        leg2 = _direct(conn, hub, dest)
        if leg1 and leg2:
            return LandedCost(
                cost_usd_per_kg=(leg1.cost_usd_per_kg + leg2.cost_usd_per_kg) * INDIRECT_PENALTY,
                lead_time_days=leg1.lead_time_days + leg2.lead_time_days,
                mode=f"{leg1.mode}+{leg2.mode}",
                via=hub,
                confidence=0.55,
            )
    return None


def compute_landed_cost(
    conn: sqlite3.Connection,
    origin_country: str,
    dest_country: str,
    preferred_mode: Optional[str] = None,
) -> Optional[LandedCost]:
    if not origin_country or not dest_country:
        return None
    if origin_country == dest_country:
        # Domestic — use whatever truck/rail rate exists.
        return _direct(conn, origin_country, dest_country, preferred_mode or "truck")
    direct = _direct(conn, origin_country, dest_country, preferred_mode)
    if direct:
        return direct
    return _via_hub(conn, origin_country, dest_country)


def compute_for_many(
    conn: sqlite3.Connection,
    origin_dest_pairs: List[Tuple[str, str]],
    preferred_mode: Optional[str] = None,
) -> List[Optional[LandedCost]]:
    return [compute_landed_cost(conn, o, d, preferred_mode) for o, d in origin_dest_pairs]
