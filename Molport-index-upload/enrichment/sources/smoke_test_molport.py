"""Offline smoke test — exercises cache + fixtures + flatten_suppliers without Playwright.

Run with:
    MOLPORT_FIXTURES_ONLY=1 python -m enrichment.sources.smoke_test_molport
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Stand up a throwaway DB so the cache table exists without requiring the
# full enriched schema to be bootstrapped.
_tmp_dir = tempfile.mkdtemp(prefix="molport_smoke_")
_tmp_db = str(Path(_tmp_dir) / "db_enriched.sqlite")
with sqlite3.connect(_tmp_db) as _c:
    _c.execute(
        """CREATE TABLE IF NOT EXISTS API_Response_Cache (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            Source TEXT NOT NULL,
            Cache_Key TEXT NOT NULL,
            Response TEXT,
            Fetched_At TEXT NOT NULL DEFAULT (datetime('now')),
            TTL_Days INTEGER NOT NULL DEFAULT 30,
            UNIQUE (Source, Cache_Key)
        )"""
    )

os.environ["MOLPORT_FIXTURES_ONLY"] = "1"

# Build a throwaway identity index for testing.
_tmp_index = str(Path(_tmp_dir) / "db_molport_index.sqlite")
with sqlite3.connect(_tmp_index) as _c:
    _c.execute(
        """CREATE TABLE compounds (
            molport_id TEXT PRIMARY KEY,
            smiles TEXT,
            smiles_canonical TEXT
        ) WITHOUT ROWID"""
    )
    _c.executemany(
        "INSERT INTO compounds VALUES (?, ?, ?)",
        [
            ("Molport-000-871-563", "CCCCCCCCCCCCCCCCCC(=O)[O-].[Mg+2]", "CCCCCCCCCCCCCCCCCC(=O)[O-].[Mg+2]"),
            ("Molport-000-871-102", "C([C@@H]1[C@H]([C@@H](C(=O)O1)O)O)O", "OCC1OC(=O)C(O)=C1O"),
            ("Molport-001-782-999", "CCCCCCCCCCCCCCCCCC(=O)O", "CCCCCCCCCCCCCCCCCC(=O)O"),
        ],
    )
    _c.execute("CREATE INDEX idx_smiles ON compounds(smiles)")
    _c.execute("CREATE INDEX idx_smiles_canonical ON compounds(smiles_canonical)")

from enrichment.sources import molport_cache  # noqa: E402
from enrichment.sources.molport import MolportClient  # noqa: E402
from enrichment.sources.molport_fixtures import FIXTURES_BY_CAS  # noqa: E402
from enrichment.sources.molport_index import MolportIndex, product_url  # noqa: E402

FAILURES: list[str] = []


def assert_(cond: bool, msg: str) -> None:
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        FAILURES.append(msg)


def test_cache_roundtrip() -> None:
    print("\n[1] cache round-trip")
    conn = sqlite3.connect(_tmp_db)
    molport_cache.ensure_schema(conn)
    molport_cache.cache_put(conn, "cas", "557-04-0", {"hello": "world"})
    got = molport_cache.cache_get(conn, "cas", "557-04-0")
    assert_(got == {"hello": "world"}, "cache_get returns what cache_put stored")
    stats = molport_cache.cache_stats(conn)
    assert_(stats["total"] >= 1 and stats["fresh"] >= 1, "cache_stats reports >=1 fresh entry")
    conn.close()


def test_fixtures_flatten() -> None:
    print("\n[2] fixtures + flatten_suppliers")
    client = MolportClient(db_path=_tmp_db)
    assert_(client.fixtures_only is True, "client reads MOLPORT_FIXTURES_ONLY env var")

    rows = client.lookup_ingredient({"cas_number": "557-04-0", "name": "magnesium stearate"})
    assert_(len(rows) >= 3, f"magnesium stearate yields at least 3 rows (got {len(rows)})")

    sample = rows[0] if rows else {}
    required_keys = {
        "supplier_name", "price", "currency", "price_qty_kg", "amount_raw",
        "measure", "delivery_days", "purity", "country_shipping",
        "country_origin", "stock_status", "is_minimum_order",
        "price_type", "grade_unverified",
    }
    missing = required_keys - set(sample.keys())
    assert_(
        required_keys.issubset(sample.keys()),
        f"row has all Supplier_Commercial-ready keys (missing: {missing})",
    )
    assert_(sample.get("price_type") == "retail_proxy", "row price_type is retail_proxy")
    assert_(sample.get("grade_unverified") == 1, "row grade_unverified is 1")
    assert_(sample.get("currency") == "USD", f"row currency passed through (got {sample.get('currency')!r})")
    assert_(
        sample.get("stock_status") in {"in_stock", "backorder", "unknown"},
        f"stock_status normalized to known vocab (got {sample.get('stock_status')!r})",
    )


def test_price_qty_kg_normalization() -> None:
    print("\n[3] amount→kg normalization")
    client = MolportClient(db_path=_tmp_db)
    rows = client.lookup_ingredient({"cas_number": "557-04-0"})
    g_row = next((r for r in rows if r["measure"] == "g" and r["amount_raw"] == 500), None)
    kg_row = next((r for r in rows if r["measure"] == "kg" and r["amount_raw"] == 1), None)
    assert_(g_row is not None and abs(g_row["price_qty_kg"] - 0.5) < 1e-9, "500g → 0.5 kg")
    assert_(kg_row is not None and abs(kg_row["price_qty_kg"] - 1.0) < 1e-9, "1kg → 1.0 kg")


def test_is_minimum_order_tagging() -> None:
    print("\n[3b] is_minimum_order tagging per (supplier, catalogue)")
    client = MolportClient(db_path=_tmp_db)
    rows = client.lookup_ingredient({"cas_number": "557-04-0"})

    # Sigma-Aldrich has 3 packings (100g, 500g, 1kg). Smallest is 100g.
    sigma_rows = [r for r in rows if r["supplier_name"] == "Sigma-Aldrich"]
    sigma_moq = [r for r in sigma_rows if r.get("is_minimum_order") == 1]
    assert_(len(sigma_moq) == 1, f"exactly one Sigma row is MOQ (got {len(sigma_moq)})")
    assert_(
        sigma_moq and sigma_moq[0]["amount_raw"] == 100 and sigma_moq[0]["measure"] == "g",
        "Sigma MOQ is the 100g packing (smallest price_qty_kg)",
    )

    # TCI has only one packing (500g) — must be tagged MOQ.
    tci_rows = [r for r in rows if r["supplier_name"] == "TCI Chemicals"]
    assert_(
        len(tci_rows) == 1 and tci_rows[0].get("is_minimum_order") == 1,
        "single-packing supplier's only row is MOQ",
    )


def test_stock_status_normalization() -> None:
    print("\n[3c] stock_status normalization")
    client = MolportClient(db_path=_tmp_db)
    rows = client.lookup_ingredient({"cas_number": "557-04-0"})
    # Sigma's 1kg packing has "Backorder" — scraper/fixture form
    sigma_1kg = next(
        (r for r in rows if r["supplier_name"] == "Sigma-Aldrich"
         and r["measure"] == "kg" and r["amount_raw"] == 1),
        None,
    )
    assert_(
        sigma_1kg is not None and sigma_1kg["stock_status"] == "backorder",
        f"'Backorder' → 'backorder' (got {sigma_1kg and sigma_1kg.get('stock_status')!r})",
    )
    # Sigma's 100g has "In Stock"
    sigma_100g = next(
        (r for r in rows if r["supplier_name"] == "Sigma-Aldrich"
         and r["measure"] == "g" and r["amount_raw"] == 100),
        None,
    )
    assert_(
        sigma_100g is not None and sigma_100g["stock_status"] == "in_stock",
        f"'In Stock' → 'in_stock' (got {sigma_100g and sigma_100g.get('stock_status')!r})",
    )


def test_unknown_cas_returns_empty() -> None:
    print("\n[4] unknown CAS → empty list")
    client = MolportClient(db_path=_tmp_db)
    rows = client.lookup_ingredient({"cas_number": "99999-99-9"})
    assert_(rows == [], "unknown CAS returns empty list (no crash)")


def test_cache_key_is_normalized() -> None:
    print("\n[5] cache key normalization")
    conn = sqlite3.connect(_tmp_db)
    molport_cache.cache_put(conn, "cas", "  557-04-0  ", {"v": 1})
    got = molport_cache.cache_get(conn, "cas", "557-04-0")
    assert_(got == {"v": 1}, "whitespace-padded key resolves to same entry")
    conn.close()


def test_all_fixtures_are_valid_envelopes() -> None:
    print("\n[6] all fixtures have valid envelope shape")
    for cas, env in FIXTURES_BY_CAS.items():
        mol = env.get("Molecule")
        suppliers = (mol or {}).get("Suppliers", [])
        assert_(bool(suppliers), f"fixture {cas} has at least one supplier")
        for s in suppliers:
            cats = s.get("Catalogue", [])
            assert_(bool(cats), f"fixture {cas} supplier {s.get('Supplier Name')} has Catalogue")
            for c in cats:
                assert_(bool(c.get("Packings")), f"fixture {cas} catalogue has Packings")


def test_index_lookup() -> None:
    print("\n[7] identity index lookups")
    idx = MolportIndex(_tmp_index)
    assert_(idx.available(), "index reports available when DB exists")
    stats = idx.stats()
    assert_(stats["rows"] == 3, f"test index has 3 rows (got {stats.get('rows')})")

    mid = idx.lookup_by_smiles("CCCCCCCCCCCCCCCCCC(=O)O")
    assert_(mid == "Molport-001-782-999", "SMILES matches raw column → correct Molport ID")

    mid = idx.lookup_by_smiles("OCC1OC(=O)C(O)=C1O")
    assert_(mid == "Molport-000-871-102", "SMILES matches canonical column → correct Molport ID")

    mid = idx.lookup_by_smiles("nothing-here")
    assert_(mid is None, "unknown SMILES → None")

    idx.close()


def test_index_validate() -> None:
    print("\n[8] index validate() anti-hallucination check")
    idx = MolportIndex(_tmp_index)
    assert_(idx.validate("Molport-001-782-999", None) is True, "known ID, no SMILES → pass")
    assert_(
        idx.validate("Molport-001-782-999", "CCCCCCCCCCCCCCCCCC(=O)O") is True,
        "known ID + matching SMILES → pass",
    )
    assert_(
        idx.validate("Molport-001-782-999", "WRONG") is False,
        "known ID + wrong SMILES → reject",
    )
    assert_(
        idx.validate("Molport-999-999-999", "anything") is False,
        "unknown ID → reject (hallucination guard)",
    )
    idx.close()


def test_index_missing_graceful_degradation() -> None:
    print("\n[9] missing index degrades gracefully")
    idx = MolportIndex("/nonexistent/db_molport_index.sqlite")
    assert_(idx.available() is False, "missing DB → available()=False")
    assert_(idx.lookup_by_smiles("anything") is None, "lookup returns None when DB missing")
    assert_(idx.validate("Molport-X-Y-Z", None) is False, "validate returns False when DB missing")


def test_product_url_builder() -> None:
    print("\n[10] product_url builder")
    url = product_url("Molport-000-871-563")
    assert_(
        url == "https://www.molport.com/shop/compound/Molport-000-871-563",
        f"product_url returns canonical path (got {url!r})",
    )


if __name__ == "__main__":
    test_cache_roundtrip()
    test_fixtures_flatten()
    test_price_qty_kg_normalization()
    test_is_minimum_order_tagging()
    test_stock_status_normalization()
    test_unknown_cas_returns_empty()
    test_cache_key_is_normalized()
    test_all_fixtures_are_valid_envelopes()
    test_index_lookup()
    test_index_validate()
    test_index_missing_graceful_degradation()
    test_product_url_builder()

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll smoke tests passed.")
