"""Parse a downloaded Molport Full Database file (SDF or CSV) into Supplier_Commercial rows.

Usage
-----
    # After downloading from molport.com → Downloads → Full Database
    PYTHONPATH=. python3 -m enrichment.sources.molport_db_parser \
        --file /path/to/MolportFullDatabase.sdf \
        --db db_enriched.sqlite

Supported formats
-----------------
* SDF  — Molport's primary download format; properties are in SD tags
* CSV  — alternate flat format (header row required)

What Molport Full Database SDF tags look like
----------------------------------------------
> <MOLPORTID>
MOLPORT:001-456-789

> <CAS>
50-81-7

> <SMILES>
OC[C@H](O1)[C@@H](O)[C@H](O)[C@@H]2[C@@H]1c3c(O)c(CO)c(O)c3C2=O

> <SUPPLIER>
Some Chemical Co

> <CATALOG_ID>
SCC-12345

> <PRICE>
25.00

> <AMOUNT>
1

> <MEASURE>
g

> <CURRENCY>
USD

> <DELIVERYDAYS>
5

The parser collects all records sharing a CAS number (multiple pack sizes from
multiple suppliers) and writes them as Supplier_Commercial rows with
Price_Source='molport_db', Price_Type='retail_proxy', Confidence=0.70.

Only CAS numbers already in Ingredient_Canonical are imported (inner join on CAS).
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.molport_db_parser")

_LB_TO_KG = 2.20462
_FX_TO_USD = {
    "USD": 1.0, "EUR": 1.07, "GBP": 1.27, "INR": 0.012,
    "CNY": 0.14, "RMB": 0.14, "JPY": 0.0067,
    "AUD": 0.66, "CAD": 0.74, "CHF": 1.13,
}


# ---------------------------------------------------------------------------
# SDF parsing
# ---------------------------------------------------------------------------

def _parse_sdf(path: Path):
    """Yield dicts of SDF tag→value for each record in the file."""
    record: dict[str, str] = {}
    current_tag: str | None = None
    lines: list[str] = []

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line == "$$$$":
                # End of record — flush
                if current_tag and lines:
                    record[current_tag] = "\n".join(lines).strip()
                if record:
                    yield record
                record = {}
                current_tag = None
                lines = []
            elif line.startswith("> <") and line.endswith(">"):
                # New tag — flush previous
                if current_tag and lines:
                    record[current_tag] = "\n".join(lines).strip()
                current_tag = line[3:-1].upper()
                lines = []
            elif current_tag is not None:
                lines.append(line)
    # Last record (file may lack trailing $$$$)
    if current_tag and lines:
        record[current_tag] = "\n".join(lines).strip()
    if record:
        yield record


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _parse_csv(path: Path):
    """Yield dicts from a Molport CSV export. Header row normalised to UPPER."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k.upper().strip(): v for k, v in row.items()}


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

_CAS_TAG_CANDIDATES = ("CAS", "CAS_NUMBER", "CAS NUMBER", "CASNUMBER", "CASRN")
_PRICE_TAG_CANDIDATES = ("PRICE", "BESTPRICE", "BEST_PRICE", "PRICE_USD")
_AMOUNT_TAG_CANDIDATES = ("AMOUNT", "PACK_SIZE", "PACKSIZE", "QTY", "QUANTITY")
_MEASURE_TAG_CANDIDATES = ("MEASURE", "UNIT", "UNITS", "PACK_UNIT")
_SUPPLIER_TAG_CANDIDATES = ("SUPPLIER", "SUPPLIER_NAME", "SUPPLIERNAME", "VENDOR")
_CATALOG_TAG_CANDIDATES = ("CATALOG_ID", "CATALOGID", "CATALOGUE_ID", "CATID")
_DELIVERY_TAG_CANDIDATES = ("DELIVERYDAYS", "DELIVERY_DAYS", "LEAD_TIME", "LEADTIME")
_CURRENCY_TAG_CANDIDATES = ("CURRENCY", "CURR")
_MOLPORTID_TAG_CANDIDATES = ("MOLPORTID", "MOLPORT_ID", "MOLPORT ID")


def _pick(record: dict, candidates: tuple) -> str | None:
    for k in candidates:
        v = record.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _normalize_price(price_str: str | None, currency: str | None,
                     amount: str | None, measure: str | None) -> float | None:
    """Convert to USD/kg. Returns None if unparseable or nonsensical."""
    if not price_str:
        return None
    nums = re.findall(r"\d+(?:[.,]\d+)?", price_str)
    if not nums:
        return None
    val = float(nums[0].replace(",", ""))

    # Currency conversion
    fx = 1.0
    if currency:
        fx = _FX_TO_USD.get(currency.upper().strip(), 1.0)

    # Amount + measure → per-kg
    per_kg = None
    if amount and measure:
        try:
            amt = float(re.findall(r"\d+(?:[.,]\d+)?", amount)[0].replace(",", ""))
        except (IndexError, ValueError):
            amt = None
        if amt:
            m = measure.strip().lower()
            if m in ("kg", "kilogram", "kilograms"):
                per_kg = (val * fx) / amt
            elif m in ("g", "gram", "grams"):
                per_kg = (val * fx) / (amt / 1000)
            elif m in ("mg", "milligram", "milligrams"):
                per_kg = (val * fx) / (amt / 1_000_000)
            elif m in ("lb", "lbs", "pound", "pounds"):
                per_kg = (val * fx) / (amt / _LB_TO_KG)

    if per_kg is None:
        # Fall back: assume the price is $/g and convert
        per_kg = val * fx * 1000

    if per_kg > 100_000 or per_kg < 0.01:
        return None
    return round(per_kg, 4)


def _normalize_price_qty_kg(amount: str | None, measure: str | None) -> float | None:
    """Pack size in kg."""
    if not amount or not measure:
        return None
    try:
        amt = float(re.findall(r"\d+(?:[.,]\d+)?", amount)[0].replace(",", ""))
    except (IndexError, ValueError):
        return None
    m = measure.strip().lower()
    if m in ("kg", "kilogram", "kilograms"):
        return amt
    if m in ("g", "gram", "grams"):
        return amt / 1000
    if m in ("mg", "milligram", "milligrams"):
        return amt / 1_000_000
    if m in ("lb", "lbs", "pound", "pounds"):
        return amt / _LB_TO_KG
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_cas_map(conn: sqlite3.Connection) -> dict[str, int]:
    """CAS → canonical_id for all canonicals with a CAS number."""
    rows = conn.execute(
        "SELECT CAS_Number, Id FROM Ingredient_Canonical WHERE CAS_Number IS NOT NULL"
    ).fetchall()
    return {r[0].strip(): r[1] for r in rows if r[0]}


def _upsert_supplier(conn: sqlite3.Connection, name: str, cache: dict[str, int]) -> int:
    if name in cache:
        return cache[name]
    cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name) VALUES (?)", (name,))
    if cur.lastrowid:
        sid = cur.lastrowid
    else:
        sid = conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (name,)).fetchone()[0]
    cache[name] = sid
    return sid


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def import_file(file_path: Path, db_path: Path = ENRICHED_DB, dry_run: bool = False) -> dict:
    suffix = file_path.suffix.lower()
    if suffix in (".sdf", ".sd"):
        records = _parse_sdf(file_path)
    elif suffix in (".csv", ".tsv", ".txt"):
        records = _parse_csv(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Expected .sdf or .csv")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    cas_map = _load_cas_map(conn)
    logger.info(f"Loaded {len(cas_map)} canonical CAS numbers to match against")

    supplier_cache: dict[str, int] = {}
    stats = {"scanned": 0, "cas_matched": 0, "written": 0, "skipped_price": 0}

    batch: list[tuple] = []

    for record in records:
        stats["scanned"] += 1
        if stats["scanned"] % 100_000 == 0:
            logger.info(f"  Scanned {stats['scanned']:,} records, {stats['cas_matched']} CAS matches so far")

        cas = _pick(record, _CAS_TAG_CANDIDATES)
        if not cas or cas not in cas_map:
            continue

        stats["cas_matched"] += 1
        canonical_id = cas_map[cas]

        supplier_name = _pick(record, _SUPPLIER_TAG_CANDIDATES) or "Molport (unknown supplier)"
        catalog_id = _pick(record, _CATALOG_TAG_CANDIDATES)
        molport_id = _pick(record, _MOLPORTID_TAG_CANDIDATES)
        price_str = _pick(record, _PRICE_TAG_CANDIDATES)
        amount = _pick(record, _AMOUNT_TAG_CANDIDATES)
        measure = _pick(record, _MEASURE_TAG_CANDIDATES)
        currency = _pick(record, _CURRENCY_TAG_CANDIDATES) or "USD"
        delivery_raw = _pick(record, _DELIVERY_TAG_CANDIDATES)

        price_usd_kg = _normalize_price(price_str, currency, amount, measure)
        if price_usd_kg is None:
            stats["skipped_price"] += 1

        price_qty_kg = _normalize_price_qty_kg(amount, measure)
        delivery_days: int | None = None
        if delivery_raw:
            nums = re.findall(r"\d+", delivery_raw)
            delivery_days = int(nums[0]) if nums else None

        if not dry_run:
            sid = _upsert_supplier(conn, supplier_name, supplier_cache)
            conn.execute(
                """INSERT OR REPLACE INTO Supplier_Commercial
                   (SupplierId, CanonicalIngredientId,
                    Price_USD_Per_KG, Price_Qty_KG,
                    Lead_Time_Days,
                    Price_Type, Price_Source, Confidence,
                    Grade_Unverified, Molport_Catalog_Id, Last_Updated)
                   VALUES (?, ?, ?, ?, ?, 'retail_proxy', 'molport_db', 0.70, 1, ?, datetime('now'))""",
                (sid, canonical_id, price_usd_kg, price_qty_kg, delivery_days, catalog_id or molport_id)
            )
            stats["written"] += 1

            # Commit in batches of 500 to avoid long lock times
            if stats["written"] % 500 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import Molport Full Database file into Supplier_Commercial"
    )
    parser.add_argument("--file", required=True, help="Path to Molport SDF or CSV file")
    parser.add_argument("--db", default=str(ENRICHED_DB), help="Path to SQLite DB")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}")
        raise SystemExit(1)

    print(f"Importing {file_path.name} → {args.db}")
    print(f"Mode: {'DRY RUN (no writes)' if args.dry_run else 'LIVE'}")
    t0 = time.time()

    stats = import_file(file_path, Path(args.db), dry_run=args.dry_run)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Scanned:      {stats['scanned']:>10,} records")
    print(f"  CAS matched:  {stats['cas_matched']:>10,} records")
    print(f"  Written:      {stats['written']:>10,} rows to Supplier_Commercial")
    print(f"  No price:     {stats['skipped_price']:>10,} (written with NULL price)")
