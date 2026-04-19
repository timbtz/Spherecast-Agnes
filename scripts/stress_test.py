"""End-to-end stress test harness for Agnes.

Runs a battery of offline checks across five phases:
  A. DB + schema integrity
  B. Parser + classifier unit checks
  C. Migration + backfill idempotence
  D. Adversarial inputs
  E. Cross-layer sanity (staleness checker, blocklist gate, outlier QC)

Network-dependent phases (live enrichment, FastAPI probing) live in their
own runners — this script is intentionally offline and reproducible.

Each check is a (name, thunk) that returns either None (pass), a string
(fail with reason), or raises (fail with traceback). Output goes to stdout
in a machine-readable single-line-per-check format so the report generator
can parse it.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
import traceback
from pathlib import Path

# Silence all noisy loggers during the stress test.
logging.basicConfig(level=logging.CRITICAL)

ROOT = Path(__file__).parent.parent
DB = ROOT / "db_enriched.sqlite"

# --- Fixture data for checks -------------------------------------------------

_MALFORMED_JSON_CASES = [
    # (name, raw_output, expected_min_rows)
    ("markdown fences", "```json\n[{\"supplier_name\":\"X\"}]\n```", 1),
    ("leading prose", "Here are the results:\n[{\"supplier_name\":\"X\"}]", 1),
    ("trailing prose", "[{\"supplier_name\":\"X\"}]\nHope this helps.", 1),
    ("empty string", "", 0),
    ("pure prose no json", "The model refused to answer.", 1),  # falls through to research_result
    ("truncated array", "[{\"supplier_name\":\"X\"}", 1),  # falls through to research_result
    ("unicode supplier", '[{"supplier_name":"Müllér GmbH 株式会社"}]', 1),
    ("array with single item", '[{"supplier_name":"ACME Inc."}]', 1),
]

_COUNTRY_CASES = [
    ("USA", "USA"), ("US", "USA"), ("U.S.", "USA"),
    ("United States", "USA"), ("UNITED STATES", "USA"),
    ("UK", "UK"), ("GB", "UK"), ("Great Britain", "UK"),
    ("India", "India"), ("IND", "India"),
    ("China", "China"), ("PRC", "China"),
    ("USA, Germany", "USA"),  # first-separator-split
    ("USA (inferred)", "USA"),  # parenthetical strip
    ("Germany/France", "Germany"),
    ("Not A Country", None),
    ("Atlantis", None),
    ("", None),
    (None, None),
]

_ARCHETYPE_CASES = [
    ("https://www.alibaba.com/showroom/x.html", "directory_listing"),
    ("https://tradeindia.com/prod-x", "directory_listing"),
    ("https://exportersindia.com/foo", "directory_listing"),
    ("https://purebulk.com/product/x", "distributor"),
    ("https://www.univarsolutions.com/a", "distributor"),
    ("https://www.jungbunzlauer.com/products/x", "manufacturer_direct"),
    ("https://chem-impex.com/p/x", "manufacturer_direct"),
    ("https://rpicorp.com/catalog/x", "manufacturer_direct"),
    ("https://sigmaaldrich.com/catalog/x", "lab_reagent"),
    ("https://www.thermofisher.com/order/x", "lab_reagent"),
    ("https://obscure-unlisted.example.com/x", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
]

_PROVENANCE_CASES = [
    # (url, country_ok, evidence, archetype, expected)
    (None, False, None, "unknown", "unknown"),
    (None, True, None, "unknown", "model_inferred"),
    ("https://x.com", False, None, "manufacturer_direct", "website_explicit"),
    ("https://x.com", True, None, "directory_listing", "directory_listing"),
    ("https://x.com", True, None, "distributor", "directory_listing"),
    ("https://x.com", True, None, "lab_reagent", "directory_listing"),
    ("https://x.com", False, None, "unknown", "model_inferred"),
    ("https://x.com", True, None, "unknown", "directory_listing"),
]

_FUZZY_CASES = [
    # (candidate, existing_list, expected_match_name_or_None)
    ("PureBulk, Inc.", [(1, "Purebulk Inc")], "Purebulk Inc"),
    ("purebulk inc", [(1, "PureBulk, Inc.")], "PureBulk, Inc."),
    ("SIGMA ALDRICH", [(2, "Sigma-Aldrich")], "Sigma-Aldrich"),
    ("Sigma Aldrich Corp.", [(2, "Sigma-Aldrich")], "Sigma-Aldrich"),
    ("Acme Chemicals Limited", [(3, "Acme Chemicals Ltd.")], "Acme Chemicals Ltd."),
    ("BulkSupplements.com", [(4, "BulkSupplements.com")], "BulkSupplements.com"),
    ("PureBulk", [(5, "Purely Nutrition")], None),  # should NOT match
    ("Fisher Scientific", [(6, "Thermo Fisher Scientific")], None),  # different company
    ("Unknown Co", [], None),
    ("ACME", [(7, "BETA")], None),
]

_PRICE_CASES = [
    # (input, expected_usd_per_kg_approx, tolerance_pct)
    ("$22-28 USD/kg", 25.0, 0.01),
    ("$12-14 per lb", 28.0, 0.05),                  # ~12.99*2.2046
    ("250.0 INR/Kilograms", 3.0, 0.1),              # 250*0.012
    ("€18/kg", 19.26, 0.01),                        # 18*1.07
    ("8.50-10 CNY per gram", 1295.0, 0.1),          # 9.25*0.14*1000
    ("Request Quote", None, 0),
    ("", None, 0),
    (None, None, 0),
    ("$100000000/kg", None, 0),                     # clamped → reject
]

_MOQ_CASES = [
    ("25 kg", 25.0),
    ("1-5 kg", 1.0),
    ("50 lb", 22.68),  # 50 / 2.20462
    ("100kg", 100.0),
    ("", None),
    (None, None),
]

_NAME_MATCH_CASES = [
    ("PureBulk, Inc.", "<title>PureBulk - bulk supplements</title>", True),
    ("Sinofi Ingredients", "<h1>Sinofi Ingredients Inc</h1>", True),
    ("Univar Solutions", "footer: univar solutions inc.", True),
    ("Random Chem Co Ltd", "contact us", False),
    ("PureBulk Inc", "Purely Natural Foods", False),
    ("", "anything", False),
]


def _near(a, b, tol):
    if a is None or b is None:
        return a == b
    if tol == 0:
        return a == b
    return abs(a - b) / b <= tol


# --- Check runners -----------------------------------------------------------

def _run_checks(checks: list[tuple[str, callable]]) -> list[dict]:
    results = []
    for name, thunk in checks:
        t0 = time.monotonic()
        try:
            rv = thunk()
            dur_ms = int((time.monotonic() - t0) * 1000)
            if rv is None or rv is True:
                results.append({"name": name, "ok": True, "dur_ms": dur_ms})
            else:
                results.append({"name": name, "ok": False, "reason": str(rv), "dur_ms": dur_ms})
        except Exception as e:
            dur_ms = int((time.monotonic() - t0) * 1000)
            tb = traceback.format_exc().splitlines()[-3:]
            results.append({
                "name": name, "ok": False,
                "reason": f"EXC: {e} | {' | '.join(tb)}",
                "dur_ms": dur_ms
            })
    return results


# --- Phase A: DB + schema integrity -----------------------------------------

def phase_a() -> list[dict]:
    def fk_check():
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA foreign_keys=ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.close()
        if violations:
            return f"{len(violations)} FK violations: {violations[:3]}"
        return None

    def integrity_check():
        conn = sqlite3.connect(str(DB))
        rv = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        return None if rv == "ok" else f"integrity: {rv}"

    def provenance_cols():
        conn = sqlite3.connect(str(DB))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(Supplier_Commercial)").fetchall()}
        conn.close()
        missing = [c for c in (
            "Provenance_Confidence", "Evidence_Snippet", "URL_Archetype",
            "URL_Health", "Corroboration_Score"
        ) if c not in cols]
        return f"missing: {missing}" if missing else None

    def tier_cols():
        conn = sqlite3.connect(str(DB))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(Ingredient_Canonical)").fetchall()}
        conn.close()
        missing = [c for c in ("Category", "Usage_Tier") if c not in cols]
        return f"missing: {missing}" if missing else None

    def blocklist_populated():
        conn = sqlite3.connect(str(DB))
        n = conn.execute("SELECT COUNT(*) FROM URL_Blocklist").fetchone()[0]
        conn.close()
        return None if n >= 20 else f"blocklist only {n} entries"

    def supplier_master_exists():
        conn = sqlite3.connect(str(DB))
        try:
            conn.execute("SELECT 1 FROM Supplier_Master LIMIT 1")
            return None
        except sqlite3.OperationalError as e:
            return str(e)
        finally:
            conn.close()

    def tier_distribution():
        conn = sqlite3.connect(str(DB))
        rows = conn.execute(
            "SELECT Usage_Tier, COUNT(*) FROM Ingredient_Canonical GROUP BY Usage_Tier"
        ).fetchall()
        conn.close()
        d = dict(rows)
        if d.get(1, 0) != 50 or d.get(2, 0) != 50:
            return f"tier sizes wrong: {d}"
        return None

    def category_coverage():
        conn = sqlite3.connect(str(DB))
        total = conn.execute("SELECT COUNT(*) FROM Ingredient_Canonical").fetchone()[0]
        known = conn.execute(
            "SELECT COUNT(*) FROM Ingredient_Canonical WHERE Category != 'unknown'"
        ).fetchone()[0]
        conn.close()
        if known < total * 0.5:
            return f"category coverage too low: {known}/{total}"
        return None

    return _run_checks([
        ("A1 foreign key check", fk_check),
        ("A2 sqlite integrity_check", integrity_check),
        ("A3 Supplier_Commercial provenance columns", provenance_cols),
        ("A4 Ingredient_Canonical tier columns", tier_cols),
        ("A5 URL_Blocklist populated", blocklist_populated),
        ("A6 Supplier_Master table exists", supplier_master_exists),
        ("A7 Usage_Tier distribution (50/50/rest)", tier_distribution),
        ("A8 Category coverage >= 50%", category_coverage),
    ])


# --- Phase B: unit checks ---------------------------------------------------

def phase_b() -> list[dict]:
    from enrichment.enrichers.country_iso import normalize_country
    from enrichment.enrichers.supplier_web_enricher import (
        _classify_archetype, _classify_provenance, _fuzzy_match_supplier,
        _parse_price, _parse_moq, _normalize_certs, _parse_suppliers,
        _hostname, _hostname_blocked,
    )
    from enrichment.verify_suppliers import _name_matches_page

    def country_suite():
        fails = []
        for raw, expected in _COUNTRY_CASES:
            got = normalize_country(raw)
            if got != expected:
                fails.append(f"  {raw!r}: got {got!r} want {expected!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def archetype_suite():
        fails = []
        for url, expected in _ARCHETYPE_CASES:
            got = _classify_archetype(url)
            if got != expected:
                fails.append(f"  {url!r}: got {got!r} want {expected!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def provenance_suite():
        fails = []
        for url, country_ok, evidence, archetype, expected in _PROVENANCE_CASES:
            got = _classify_provenance(url, country_ok, evidence, archetype)
            if got != expected:
                fails.append(f"  {url!r},{country_ok},{archetype}: got {got!r} want {expected!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def fuzzy_suite():
        fails = []
        for cand, existing, expected in _FUZZY_CASES:
            m = _fuzzy_match_supplier(cand, existing, threshold=90)
            got = m[1] if m else None
            if got != expected:
                fails.append(f"  {cand!r} vs {existing}: got {got!r} want {expected!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def price_suite():
        fails = []
        for raw, expected, tol in _PRICE_CASES:
            got = _parse_price(raw)
            if not _near(got, expected, tol):
                fails.append(f"  {raw!r}: got {got} want ~{expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    def moq_suite():
        fails = []
        for raw, expected in _MOQ_CASES:
            got = _parse_moq(raw)
            if not _near(got, expected, 0.01):
                fails.append(f"  {raw!r}: got {got} want ~{expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    def certs_suite():
        cases = [
            (None, []),
            ("", []),
            ("GMP, ISO 9001, Halal", ["GMP", "ISO 9001", "Halal"]),
            (["USP", "NSF"], ["USP", "NSF"]),
            ("USP; NSF", ["USP", "NSF"]),
        ]
        fails = []
        for raw, expected in cases:
            got = _normalize_certs(raw)
            if got != expected:
                fails.append(f"  {raw!r}: got {got} want {expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    def parse_suppliers_suite():
        fails = []
        for name, raw, expected_min in _MALFORMED_JSON_CASES:
            rows = _parse_suppliers(raw, "test_ingredient")
            if len(rows) < expected_min:
                fails.append(f"  {name}: got {len(rows)} rows, expected >= {expected_min}")
        return ("\n" + "\n".join(fails)) if fails else None

    def name_match_suite():
        fails = []
        for supplier, body, expected in _NAME_MATCH_CASES:
            got = _name_matches_page(supplier, body)
            if got != expected:
                fails.append(f"  {supplier!r} vs {body[:30]!r}: got {got} want {expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    def hostname_suite():
        cases = [
            ("https://www.alibaba.com/x", "www.alibaba.com"),
            ("http://SUB.MADE-IN-CHINA.COM/x", "sub.made-in-china.com"),
            ("not a url", None),
            ("", None),
            (None, None),
        ]
        fails = []
        for url, expected in cases:
            got = _hostname(url)
            if got != expected:
                fails.append(f"  {url!r}: got {got!r} want {expected!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def blocklist_suite():
        bl = {"reddit.com", "vertexaisearch.cloud.google.com", "wikipedia.org"}
        cases = [
            ("https://reddit.com/r/x", True),
            ("https://news.reddit.com/z", True),       # subdomain → parent match
            ("https://www.reddit.com/x", True),
            ("https://vertexaisearch.cloud.google.com/redirect/xyz", True),
            ("https://legitimate-supplier.com/x", False),
            ("", False),
            (None, False),
        ]
        fails = []
        for url, expected in cases:
            got = _hostname_blocked(url, bl)
            if got != expected:
                fails.append(f"  {url!r}: got {got} want {expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    return _run_checks([
        ("B1 country normalizer", country_suite),
        ("B2 url archetype classifier", archetype_suite),
        ("B3 provenance classifier", provenance_suite),
        ("B4 fuzzy supplier match", fuzzy_suite),
        ("B5 price parser (currency+unit)", price_suite),
        ("B6 moq parser", moq_suite),
        ("B7 certs normalizer", certs_suite),
        ("B8 parse_suppliers (malformed)", parse_suppliers_suite),
        ("B9 name match (homepage)", name_match_suite),
        ("B10 hostname extract", hostname_suite),
        ("B11 blocklist parent-domain walk", blocklist_suite),
    ])


# --- Phase C: migration + backfill idempotence ------------------------------

def phase_c() -> list[dict]:
    from enrichment.db_migrate_provenance import migrate
    from enrichment.backfill_provenance import (
        backfill_archetype, backfill_provenance, backfill_corroboration,
    )

    def migrate_reentrant():
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA foreign_keys=ON")
        stats = migrate(conn)
        conn.close()
        if stats["columns_added"] != 0:
            return f"re-run added {stats['columns_added']} columns (should be 0)"
        return None

    def backfill_archetype_stable():
        conn = sqlite3.connect(str(DB))
        before = conn.execute(
            "SELECT URL_Archetype, COUNT(*) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY URL_Archetype"
        ).fetchall()
        backfill_archetype(conn)
        after = conn.execute(
            "SELECT URL_Archetype, COUNT(*) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY URL_Archetype"
        ).fetchall()
        conn.close()
        if dict(before) != dict(after):
            return f"distribution drifted: {dict(before)} vs {dict(after)}"
        return None

    def backfill_provenance_stable():
        conn = sqlite3.connect(str(DB))
        before = conn.execute(
            "SELECT Provenance_Confidence, COUNT(*) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY Provenance_Confidence"
        ).fetchall()
        backfill_provenance(conn)
        after = conn.execute(
            "SELECT Provenance_Confidence, COUNT(*) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY Provenance_Confidence"
        ).fetchall()
        conn.close()
        if dict(before) != dict(after):
            return f"distribution drifted: {dict(before)} vs {dict(after)}"
        return None

    def backfill_corroboration_stable():
        conn = sqlite3.connect(str(DB))
        before = conn.execute(
            "SELECT SupplierId, MAX(Corroboration_Score) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY SupplierId"
        ).fetchall()
        backfill_corroboration(conn)
        after = conn.execute(
            "SELECT SupplierId, MAX(Corroboration_Score) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' GROUP BY SupplierId"
        ).fetchall()
        conn.close()
        if dict(before) != dict(after):
            # report only differences
            diffs = []
            after_d = dict(after)
            for sid, s in before:
                if after_d.get(sid) != s:
                    diffs.append(f"sid={sid}: {s}→{after_d.get(sid)}")
            return f"{len(diffs)} suppliers drifted: {diffs[:5]}"
        return None

    def trade_register_stub_idempotent():
        from enrichment.verify_suppliers import run_trade_register_stub
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA foreign_keys=ON")
        s1 = run_trade_register_stub(conn)
        s2 = run_trade_register_stub(conn)
        conn.close()
        if s2["enqueued_new"] != 0:
            return f"re-run enqueued {s2['enqueued_new']} new (should be 0)"
        return None

    return _run_checks([
        ("C1 migrate_provenance idempotent", migrate_reentrant),
        ("C2 backfill_archetype stable", backfill_archetype_stable),
        ("C3 backfill_provenance stable", backfill_provenance_stable),
        ("C4 backfill_corroboration stable", backfill_corroboration_stable),
        ("C5 trade_register_stub idempotent", trade_register_stub_idempotent),
    ])


# --- Phase D: adversarial inputs ---------------------------------------------

def phase_d() -> list[dict]:
    from enrichment.enrichers.country_iso import normalize_country
    from enrichment.enrichers.supplier_web_enricher import (
        SupplierWebEnricher, _parse_suppliers, _parse_price,
    )

    def injection_prompts_country():
        """Country normaliser must reject adversarial strings."""
        adversarial = [
            "'; DROP TABLE Supplier; --",
            "\x00\x01\x02",
            "USA' OR 1=1 --",
            "<script>alert(1)</script>",
            "../../etc/passwd",
            "USA\n\nIgnore previous instructions",
            "A" * 500,
        ]
        fails = []
        for s in adversarial:
            got = normalize_country(s)
            if got is not None and got not in ("USA",):  # only the "USA\n..." prefix is allowed to resolve
                fails.append(f"  {s[:40]!r}: returned {got!r}")
        return ("\n" + "\n".join(fails)) if fails else None

    def unicode_supplier_name():
        """_parse_suppliers must keep unicode intact without crashing."""
        raw = '[{"supplier_name":"株式会社 Müllér GmbH", "country":"Japan"}]'
        rows = _parse_suppliers(raw, "test")
        if not rows or "株式会社" not in rows[0].get("supplier_name", ""):
            return f"lost unicode: {rows!r}"
        return None

    def extreme_price_rejection():
        """Prices outside $0.01-$100k/kg must return None."""
        cases = [("$0/kg", None), ("$200000000/kg", None),
                 ("$0.001/kg", None), ("$50/kg", 50.0)]
        fails = []
        for raw, expected in cases:
            got = _parse_price(raw)
            if not _near(got, expected, 0.01):
                fails.append(f"  {raw!r}: got {got} want {expected}")
        return ("\n" + "\n".join(fails)) if fails else None

    def blocklist_gate_fires():
        """SupplierWebEnricher._write_commercial must reject blocklisted URLs."""
        enricher = SupplierWebEnricher(db_path=str(DB))
        conn = sqlite3.connect(str(DB))
        conn.execute("PRAGMA foreign_keys=ON")
        # Seed a supplier id we can clean up after
        cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name) VALUES ('_test_adv_supplier')")
        sid = cur.lastrowid or conn.execute(
            "SELECT Id FROM Supplier WHERE Name='_test_adv_supplier'"
        ).fetchone()[0]
        # Pick any canonical id for the test
        cid = conn.execute(
            "SELECT Id FROM Ingredient_Canonical LIMIT 1"
        ).fetchone()[0]
        parsed = {"supplier_name": "_test_adv_supplier",
                  "price_range_usd_per_kg": "$50/kg",
                  "country": "USA",
                  "website": "https://reddit.com/r/xyz"}
        result = enricher._write_commercial(conn, sid, cid, parsed, parsed["website"])
        # Clean up
        conn.execute("DELETE FROM Supplier_Commercial WHERE SupplierId = ?", (sid,))
        conn.execute("DELETE FROM Supplier WHERE Id = ?", (sid,))
        conn.commit()
        conn.close()
        return None if result is False else "blocklist gate failed to reject reddit.com"

    def outlier_qc_fires():
        """Write-path must reject a price that's 100× baseline."""
        enricher = SupplierWebEnricher(db_path=str(DB))
        conn = sqlite3.connect(str(DB))
        # find an ingredient with existing baseline >= 2
        cid = conn.execute("""
            SELECT CanonicalIngredientId FROM Supplier_Commercial
            WHERE Price_USD_Per_KG IS NOT NULL
            GROUP BY CanonicalIngredientId
            HAVING COUNT(*) >= 2
            LIMIT 1
        """).fetchone()
        if not cid:
            return "no ingredient with >=2 baseline prices to test outlier QC"
        cid = cid[0]
        baseline = enricher._existing_prices_for_ingredient(conn, cid)
        median_ish = sorted(baseline)[len(baseline) // 2]
        bad_price = median_ish * 200  # 200× → outlier
        is_out = enricher._is_outlier(bad_price, baseline)
        conn.close()
        return None if is_out else f"outlier QC didn't catch {bad_price} vs baseline median {median_ish}"

    def malformed_json_resilience():
        """Worst-case inputs — _parse_suppliers must never raise."""
        nastys = [
            "{malformed", "[]", "null", "{\"a\": [infinity]}",
            "[{\"supplier_name\": null}]",
            "\"just a string\"",
            "\n\n\n",
        ]
        for s in nastys:
            try:
                _parse_suppliers(s, "x")
            except Exception as e:
                return f"  {s[:40]!r} raised {e}"
        return None

    def sql_injection_filter():
        """/api/data/ingredients grade filter must parameterise."""
        # Simulate the raw SQL used in data.py — read the file and check
        src = (ROOT / "orchestration/api/routes/data.py").read_text()
        if "f\"" in src and "WHERE" in src and "{grade}" in src:
            return "found f-string WHERE {grade} — SQL injection risk"
        return None

    return _run_checks([
        ("D1 injection strings in country", injection_prompts_country),
        ("D2 unicode supplier name preserved", unicode_supplier_name),
        ("D3 extreme price rejection", extreme_price_rejection),
        ("D4 blocklist gate fires (reddit.com)", blocklist_gate_fires),
        ("D5 outlier QC fires (200× baseline)", outlier_qc_fires),
        ("D6 _parse_suppliers resilience", malformed_json_resilience),
        ("D7 data.py f-string SQL injection scan", sql_injection_filter),
    ])


# --- Phase E: cross-layer sanity --------------------------------------------

def phase_e() -> list[dict]:
    from orchestration.tools.price_staleness_checker import run as stale_run
    from orchestration.api.agnes_context import AgnesContext

    def _mk_ctx():
        return AgnesContext(
            run_id="stress",
            pipeline_name="stress",
            trigger_source="stress_test",
            trigger_payload={},
            enriched_db_path=Path(str(DB)),
        )

    def staleness_returns_structured():
        out = stale_run(_mk_ctx())
        expected_keys = {"stale_ingredients", "count", "never_refreshed_total",
                         "stale_total", "total_candidates"}
        missing = expected_keys - set(out.keys())
        if missing:
            return f"missing keys: {missing}"
        return None

    def staleness_tier_ordering():
        out = stale_run(_mk_ctx())
        tiers = [x["usage_tier"] for x in out["stale_ingredients"]]
        # Must be monotonically non-decreasing (tier 1 before tier 3)
        for i in range(1, len(tiers)):
            if tiers[i] < tiers[i - 1]:
                return f"tier out of order at idx {i}: {tiers}"
        return None

    def supplier_master_queue_visible():
        conn = sqlite3.connect(str(DB))
        rows = conn.execute(
            """SELECT COUNT(*) FROM Supplier_Master WHERE Vetted = 0
               AND Vetted_Source = 'pending_manual_review'"""
        ).fetchone()[0]
        conn.close()
        if rows == 0:
            return "no pending_manual_review rows (trade-register queue empty)"
        return None

    def every_google_row_has_archetype():
        """Post-backfill invariant: no NULL URL_Archetype on google_search rows."""
        conn = sqlite3.connect(str(DB))
        n = conn.execute(
            "SELECT COUNT(*) FROM Supplier_Commercial "
            "WHERE Price_Source='google_search' AND URL_Archetype IS NULL"
        ).fetchone()[0]
        conn.close()
        if n > 0:
            return f"{n} google_search rows have NULL URL_Archetype"
        return None

    def provenance_never_unknown_when_url_present():
        """If Source_URL and Country_Origin are both set, Provenance_Confidence
        should not be 'unknown'. (It should at least resolve to directory_listing
        via the archetype=unknown + country_ok branch.)"""
        conn = sqlite3.connect(str(DB))
        n = conn.execute("""
            SELECT COUNT(*) FROM Supplier_Commercial
            WHERE Price_Source='google_search'
              AND Source_URL IS NOT NULL AND Source_URL != ''
              AND Country_Origin IS NOT NULL AND Country_Origin != ''
              AND Provenance_Confidence = 'unknown'
        """).fetchone()[0]
        conn.close()
        if n > 0:
            return f"{n} rows have url+country but Provenance_Confidence='unknown'"
        return None

    return _run_checks([
        ("E1 staleness returns structured output", staleness_returns_structured),
        ("E2 staleness tier ordering (tier1 first)", staleness_tier_ordering),
        ("E3 Supplier_Master queue visible", supplier_master_queue_visible),
        ("E4 every google_search row has archetype", every_google_row_has_archetype),
        ("E5 provenance != unknown when url+country", provenance_never_unknown_when_url_present),
    ])


# --- Driver ------------------------------------------------------------------

def _summarize(all_results: dict[str, list[dict]]) -> dict:
    total = sum(len(v) for v in all_results.values())
    passed = sum(1 for v in all_results.values() for r in v if r["ok"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pct": round(passed * 100 / total, 1) if total else 0,
    }


def main() -> int:
    phases = [
        ("A. DB + schema integrity", phase_a),
        ("B. Parser + classifier unit checks", phase_b),
        ("C. Migration + backfill idempotence", phase_c),
        ("D. Adversarial inputs", phase_d),
        ("E. Cross-layer sanity", phase_e),
    ]
    all_results: dict[str, list[dict]] = {}
    t_start = time.monotonic()
    for title, fn in phases:
        print(f"\n=== {title} ===")
        results = fn()
        all_results[title] = results
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            line = f"  [{mark}] ({r['dur_ms']:4d}ms) {r['name']}"
            if not r["ok"]:
                line += f"\n    → {r.get('reason', 'unknown')}"
            print(line)
    dur = time.monotonic() - t_start
    summary = _summarize(all_results)
    print(f"\n=== SUMMARY ===")
    print(f"  {summary['passed']}/{summary['total']} passed ({summary['pct']}%) in {dur:.1f}s")

    # Emit a JSON blob for the report generator
    out_path = ROOT / "tmp" / "stress_test_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w") as f:
        json.dump({
            "summary": summary,
            "duration_s": round(dur, 2),
            "phases": all_results,
        }, f, indent=2)
    print(f"  results → {out_path}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
