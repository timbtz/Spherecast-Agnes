"""Phase 4 migration runner.

Applies schema/migration_v12.sql with PRAGMA-guarded re-run safety so
running twice doesn't double-add columns or duplicate tables.

Usage (matches Tim's enrichment runner conventions):
    python -m enrichment.db_migrate_v12 --db ./db_enriched.sqlite

After the SQL applies, also seeds Lane_Cost via map_logistics so the
demo has lane data to score against. Both steps are idempotent.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import List

from .logistics.map_logistics import seed_lane_costs


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "migration_v12.sql"


def _existing_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _existing_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return [r[0] for r in rows]


def _safe_alter(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """ALTER TABLE ... ADD COLUMN, but skip if the column already exists.

    sqlite has no IF NOT EXISTS for columns, so we PRAGMA-check first.
    """
    if column in _existing_columns(conn, table):
        return False
    conn.execute(ddl)
    return True


def apply_migration(db_path: str) -> dict:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"missing schema file: {SCHEMA_PATH}")

    conn = sqlite3.connect(db_path)
    try:
        report = {"altered": [], "tables_created": [], "tables_existing": [], "lanes_seeded": 0}

        # 1. Pre-flight checks: only attempt ALTERs on tables that exist.
        tables = _existing_tables(conn)
        if "Ingredient_Canonical" not in tables:
            raise RuntimeError(
                "Ingredient_Canonical table not found. Run Tim's Phase 1 enrichment first."
            )
        if "Consolidation_Opportunity" not in tables:
            raise RuntimeError(
                "Consolidation_Opportunity table not found. Run Tim's Phase 3 first."
            )

        # 2. Additive ALTERs guarded by PRAGMA.
        alters = [
            ("Ingredient_Canonical", "Form",              "ALTER TABLE Ingredient_Canonical ADD COLUMN Form TEXT"),
            ("Ingredient_Canonical", "Processing",        "ALTER TABLE Ingredient_Canonical ADD COLUMN Processing TEXT"),
            ("Ingredient_Canonical", "PSD_Bucket",        "ALTER TABLE Ingredient_Canonical ADD COLUMN PSD_Bucket TEXT"),
            ("Ingredient_Canonical", "Surface_Area_m2g",  "ALTER TABLE Ingredient_Canonical ADD COLUMN Surface_Area_m2g REAL"),
            ("Ingredient_Canonical", "Bulk_Density_gmL",  "ALTER TABLE Ingredient_Canonical ADD COLUMN Bulk_Density_gmL REAL"),
            ("Consolidation_Opportunity", "IncumbentRole","ALTER TABLE Consolidation_Opportunity ADD COLUMN IncumbentRole TEXT"),
            ("Consolidation_Opportunity", "CandidateRole","ALTER TABLE Consolidation_Opportunity ADD COLUMN CandidateRole TEXT"),
        ]
        for tbl, col, ddl in alters:
            if _safe_alter(conn, tbl, col, ddl):
                report["altered"].append(f"{tbl}.{col}")

        # 3. CREATE TABLE IF NOT EXISTS — pull straight from the SQL file
        #    but only execute the CREATE statements (skip ALTERs we just did).
        sql_text = SCHEMA_PATH.read_text()
        for stmt in _split_statements(sql_text):
            stripped = stmt.strip().upper()
            if not stripped.startswith("CREATE TABLE"):
                continue
            # Detect target table name and skip if exists (CREATE IF NOT EXISTS
            # in the SQL handles this too — this just lets us report it).
            tbl_name = _table_name_from_create(stmt)
            if tbl_name in _existing_tables(conn):
                report["tables_existing"].append(tbl_name)
            else:
                report["tables_created"].append(tbl_name)
            conn.execute(stmt)

        conn.commit()

        # 4. Seed lane costs (idempotent).
        report["lanes_seeded"] = seed_lane_costs(conn)
        return report
    finally:
        conn.close()


def _split_statements(sql: str) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.strip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt and stmt.upper() not in ("BEGIN TRANSACTION;", "COMMIT;"):
                out.append(stmt)
            buf = []
    return out


def _table_name_from_create(stmt: str) -> str:
    # CREATE TABLE IF NOT EXISTS Foo (...)
    head = stmt.strip().split("(", 1)[0]
    parts = head.replace("\n", " ").split()
    return parts[-1].strip()


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Apply Phase 4 schema additions.")
    ap.add_argument("--db", required=True, help="Path to db_enriched.sqlite")
    args = ap.parse_args()
    report = apply_migration(args.db)
    print("[phase-4 migration applied]")
    for k, v in report.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()
