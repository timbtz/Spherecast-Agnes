"""Seed lane map.

Populates Lane_Cost with a small hand-curated set of (origin, dest,
mode) lanes drawn from public freight rate references. Real rates will
later come from Freightos / Xeneta adapters; the schema is compatible.

We keep this deliberately coarse (country-level, not port-level). The
hackathon doesn't need port-level accuracy to demonstrate the reasoning;
it needs *explainable* landed cost that moves when Tim's data moves.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List


@dataclass
class LaneSeed:
    origin: str
    dest: str
    mode: str          # 'ocean' | 'air' | 'truck' | 'rail'
    lead_time_days: float
    cost_usd_per_kg: float


# Indicative numbers — order-of-magnitude only, updated from public sources
# in spring 2026. Replaced by Freightos/Xeneta when wired up.
SEED_LANES: List[LaneSeed] = [
    # Asia → US
    LaneSeed("CN", "US", "ocean", 30.0, 0.65),
    LaneSeed("CN", "US", "air",   4.0, 5.20),
    LaneSeed("IN", "US", "ocean", 35.0, 0.72),
    LaneSeed("IN", "US", "air",   5.0, 5.80),
    LaneSeed("MY", "US", "ocean", 32.0, 0.70),
    # Asia → EU
    LaneSeed("CN", "DE", "ocean", 33.0, 0.80),
    LaneSeed("CN", "DE", "air",   4.5, 5.60),
    LaneSeed("IN", "DE", "ocean", 28.0, 0.75),
    # Within EU
    LaneSeed("DE", "DE", "truck",  1.0, 0.12),
    LaneSeed("DE", "FR", "truck",  2.0, 0.18),
    LaneSeed("DE", "IT", "truck",  3.0, 0.22),
    # Within US
    LaneSeed("US", "US", "truck",  2.5, 0.14),
    LaneSeed("US", "US", "rail",   5.0, 0.09),
    # Americas
    LaneSeed("MX", "US", "truck",  3.0, 0.20),
    LaneSeed("BR", "US", "ocean", 18.0, 0.55),
    # Transatlantic
    LaneSeed("US", "DE", "ocean", 14.0, 0.60),
    LaneSeed("US", "DE", "air",   2.0, 4.80),
]


def ensure_lane_cost_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Lane_Cost (
            Id            INTEGER PRIMARY KEY AUTOINCREMENT,
            OriginCountry TEXT NOT NULL,
            DestCountry   TEXT NOT NULL,
            Mode          TEXT NOT NULL,
            LeadTimeDays  REAL NOT NULL,
            CostUSDPerKg  REAL NOT NULL,
            LastUpdated   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def seed_lane_costs(conn: sqlite3.Connection) -> int:
    """Idempotent — skips lanes that already exist for (origin, dest, mode)."""
    conn.execute("BEGIN")
    inserted = 0
    for lane in SEED_LANES:
        exists = conn.execute(
            """
            SELECT 1 FROM Lane_Cost
            WHERE OriginCountry = ? AND DestCountry = ? AND Mode = ?
            LIMIT 1
            """,
            (lane.origin, lane.dest, lane.mode),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO Lane_Cost
              (OriginCountry, DestCountry, Mode, LeadTimeDays, CostUSDPerKg)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lane.origin, lane.dest, lane.mode, lane.lead_time_days, lane.cost_usd_per_kg),
        )
        inserted += 1
    conn.commit()
    return inserted


if __name__ == "__main__":
    from pathlib import Path
    db_path = Path(__file__).parent.parent.parent / "db_enriched.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_lane_cost_table(conn)
    n = seed_lane_costs(conn)
    conn.close()
    print(f"Lane_Cost seeded: {n} new rows inserted")
