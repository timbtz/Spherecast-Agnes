# Consolidated-baseline changelog — 2026-04-18T22:55:49Z

## 1. Overlay Clean-4 Molport 3-path into enrichment/sources/

Master had API-only molport.py. Overlaying Clean-4 drops in fixtures, scraper, cache, and identity index.


**Files overlaid from Clean-4 → consolidated-baseline:**
- `enrichment/sources/molport.py` (replaces master's API-only version with 3-path dispatch)
- `enrichment/sources/molport_cache.py` (new)
- `enrichment/sources/molport_fixtures.py` (new — demo fallback for 4 anchor CASes)
- `enrichment/sources/molport_index.py` (new — identity lookup via 1.65 GB Release asset)
- `enrichment/sources/molport_index_build.py` (new — builder for the index)
- `enrichment/sources/molport_scraper.py` (new — Playwright)
- `enrichment/sources/smoke_test_molport.py` (new)
- `enrichment/logistics/` (new — lane cost calc)
- `enrichment/scout/` (new — supplier discovery)
- `scripts/download_index.py` (new — Release-asset download helper)
- `reasoning/evidence_ledger.py` (new — Tier S3 citation ledger hookup)
- `reasoning/gate_engine.py` (new — six-gate substitution check)
- `reasoning/justification.py` (new — per-decision markdown trace)
- `reasoning/red_team.py` (new — adversarial checker)
- `reasoning/tools_extra.py` (new)

## 2. Patched SQLite view for 3.37 compatibility

`db_enriched.sqlite` view `v_bom_signature` used `GROUP_CONCAT(col ORDER BY col)`
which requires SQLite ≥ 3.44. Sandbox runs 3.37.2. Removed the ORDER BY via
`writable_schema=1` patch. Data unchanged. Backup at `db_enriched.sqlite.preview-fix.bak`.

## 3. Kept master's db_enriched.sqlite (not Clean-4's)

Master's DB is 23.9 MB vs Clean-4's 22.5 MB. Master has:
- Claim_Citation (208 rows) — citation ledger
- Refusal_Log (4 rows) — demo refusal traps
- FDA_Inactive_Ingredient (9067 rows) + FDA_IID_Change_Log (187 rows)

These are from the newer `feat: connection MVP` commit on master. The Clean-4
reasoning-run artifacts (57 RFQs, 186 Refusal_Record, etc.) will be regenerated
when the pipeline runs against this DB with the Molport 3-path wired in.


## 4. Dependency install + import check

Installed core deps (fastapi, uvicorn, pydantic, anthropic, google-genai, google-adk,
yaml, httpx, rapidfuzz, pubchempy, bs4, lxml, pdfplumber, python-dotenv, pyyaml).
Skipped sentence-transformers + playwright browser binaries (heavy; not needed for
FastAPI boot or YAML pipelines).

Import-check: 87 app modules imported clean, 3 broken (all in
`.claude/skills/skill-creator/scripts/` which is Claude Code's own infra, not ours).

Side effects observed on import (candidates for refactor, not blocking):
- `enrichment/run_dedup.py` runs UNII dedup at import
- `reasoning/substitution_graph.py` seeds edges at import
These are only triggered by the greedy import-walker; they're no-ops at runtime.

## 5. Patched Supplier-table INSERT in two enrichers

`Supplier` table schema is `(Id, Name)` — country lives on `Supplier_Commercial.Country_Origin`.
Both enrichers were trying to insert `Country` into `Supplier`, which raised
`OperationalError: table Supplier has no column named Country` on every web-search hit.

Files patched:
- `enrichment/enrichers/commercial_enricher.py` (lines ~77–80) — dropped the second column from the INSERT
- `enrichment/enrichers/supplier_web_enricher.py` (line ~75–76) — same fix

After the patch, `price_monitor` ran cleanly: 11 suppliers updated via web search, 0 alerts
(no thresholds breached), narrative correctly skipped.

## 6. Built and wired Lovable SPA into FastAPI root

Vite build of `orchestration/ui/`:
- 1773 modules transformed in ~2.1s
- Output: `orchestration/ui/dist/{index.html, assets/index-*.css (71 kB), assets/index-*.js (1.27 MB)}`
- Title: "Agnes — Spherecast Procurement Intelligence"

FastAPI mounts at `/` (already wired in `main.py:80–86`); SPA fallback returns
`index.html` for any unrecognised path so client-side React Router works.
Verified `GET /`, `GET /ingredients`, `GET /proposals/xyz/detail` all return 200 with
the SPA shell.

## 7. End-to-end verification — all 7 pipelines

Boot:
- `uvicorn orchestration.api.main:app --host 127.0.0.1 --port 8000` — comes up clean,
  background `_price_monitor_scheduler` task starts on lifespan-startup.
- `/health` → `{"status":"ok"}`.

Pipeline runs (all triggered via `POST /pipelines/{name}/run` and watched via
`GET /runs/{run_id}` + `GET /runs/{run_id}/stream`):

| Pipeline | Run ID prefix | Outcome |
|---|---|---|
| `substitution_discovery` | (parallel batch) | completed |
| `new_ingredient_research` | (parallel batch) | completed (proposal emitted) |
| `price_audit` | (parallel batch) | completed |
| `proactive_consolidation` | (parallel batch) | completed (21 Consolidation_Opportunity rows persisted) |
| `regulatory_drift_alert` | (parallel batch) | completed |
| `supplier_fallout` | (parallel batch) | completed |
| `price_monitor` | `39952d48…` | completed in 377s — 20 stale ingredients scanned, 11 suppliers updated, 0 alerts (skipped narrative correctly) |

End-to-end chat-to-proposal flow (E2E demo):
- Prompt: *"Find consolidation opportunities for magnesium stearate across our suppliers"*
- `POST /chat` → router classified as `proactive_consolidation` with **confidence 1.0**
- Pipeline ran in 13s, produced 2 executive-ready proposals:
  - **Vitamin C** — 33 companies, 60 BOMs, recommended supplier *Prinova USA* (consolidation score 0.893)
  - **Cellulose** — 21 companies, 36 BOMs, recommended supplier *Colorcon* (score 0.584)
- SSE stream replays all events (`pipeline_started → node_started/completed pairs → pipeline_completed → stream_closed`).

## 8. Frontend ↔ backend integration confirmed

- `GET /api/data/proposals` returns 21 persisted Consolidation_Opportunity rows.
- `GET /api/data/products`, `/api/data/ingredients`, `/api/data/fda-limits/{id}` all respond.
- SPA loads from `/`, hot-reloads from Vite dev not needed (built artifacts served by FastAPI StaticFiles).

## 9. What was NOT changed

- No changes to: orchestration agents, DAG executor, YAML pipeline definitions, ADK tools, scoring routes.
- No new features beyond consolidation of master + Clean-4 — per the user's directive
  ("we will work on integrating new features after we achieve this baseline success").
- `MOLPORT_API_KEY` left empty in `.env` — the 3-path Molport client falls back to
  scraper / fixtures, which is expected behaviour for this baseline.

## 10. Data-quality hardening of the price_monitor ingestion chain (2026-04-19)

**Problem found during system test:** `price_monitor` reported `suppliers_updated=0`
on a fresh run. Initial hypothesis was "correct dedup — prior run enriched everything";
live trace against Calcium citrate proved otherwise: the LLM returned 14 valid
suppliers, but the parser dropped all 14 silently.

**Three compounding root causes:**

1. **Field-name mismatch (silent data loss).** The LLM was returning keys like
   `price_range`, `moq`, `contact_website` — the parser was only looking for
   `price_range_usd_per_kg`, `moq_range_kg`, `website`. Every `s.get(...)` returned
   `None`; `_parse_price(None)` returned `None`; and the row was dropped without
   any warning.
2. **No currency or unit normalisation.** Prices like `"250.0 INR/Kilograms"` or
   `"$12-14 per lb"` were written verbatim as USD/kg — off by 83× and 2.2×
   respectively. Pyridoxine-HCl ended up with a $22 → $1,370/kg spread in the DB.
3. **No outlier QC.** Even correctly parsed prices were accepted without comparing
   against the existing baseline for the same ingredient, so one bad row could
   blow up a supplier's reputation score downstream.

**Fixes shipped:**

- `orchestration/agents/search_sub_agent.py` — system prompt hardened: explicit
  field-name list, currency/unit normalisation requirements, one-shot example.
  Enforces "convert to USD/kg before writing."
- `enrichment/enrichers/supplier_web_enricher.py`:
  - Field-name alias tuples (`_PRICE_KEYS`, `_MOQ_KEYS`, `_URL_KEYS`, `_CERT_KEYS`).
  - `_first(dict, keys)` defensive lookup helper.
  - `_FX_TO_USD` table (USD, EUR, GBP, INR, CNY, JPY, AUD, CAD, CHF, SGD + symbols).
  - Unit conversion (`$/lb` × 2.20462 = `$/kg`, `$/g` × 1000 = `$/kg`).
  - `_parse_price` now applies `price × currency × unit_factor`, sanity-bounded
    to $0.01–$100,000/kg.
  - `_parse_moq` converts `lb` → `kg` on write.
  - `_normalize_certs` coerces string/list certifications to `list[str]`
    (fixes the "GMP, ISO 9001, Halal" → `["G", "M", "P"]` regression).
  - `_normalize_country` strips parentheticals.
  - `_existing_prices_for_ingredient` + `_is_outlier` — rejects prices
    > 10× or < 0.1× the existing median for the same ingredient.
  - `_write_commercial` now returns `bool` (True = written, False = QC-rejected).
  - `enrich_ingredient` logs WARN if an ingredient yields 0 usable rows.
- `orchestration/agents/price_fetch_agent.py`:
  - Uses the new `_first` / `_PRICE_KEYS` / `_URL_KEYS` defensive lookups.
  - Adds `found_ingredients`, `failed_ingredients`, `stale_total` to node output.
  - WARN logs when an ingredient search yields 0 usable rows with the specific
    reason (`search_error` / `parse_empty` / `no_usable_rows`).

**Verification (2026-04-19, live trace):**

Live search against Calcium citrate (canonical_id=1) via the hardened chain:

```
Parsed 11 rows from model output
Row 0: price_raw='$55.80-90.00 USD/kg' → price_usd=72.9 (midpoint, normalised)
Row 1: price_raw=None → skipped (price) but supplier kept for MOQ + URL capture
Row 2: price_raw=None → same

==> 8 Supplier_Commercial rows written for 'Calcium citrate'
==> DB has rows spanning USA ($40.4/kg, $20.12/kg), India ($4.43/kg),
    Germany (Jungbunzlauer), with MOQs 0.45 kg → 100 kg.
```

Before: 14 of 14 rows dropped. After: 8 of 11 rows written, with normalised
USD/kg prices, provenance (`google_search`), and outlier QC active.

Node output for `price_monitor`'s `fetch-prices` now carries a structured
reconciliation breakdown (`stale_total`, `found_ingredients`, `failed_ingredients`)
so the pipeline is self-diagnosing rather than silently zero-result.

## 11. Provenance hardening: staleness, countries, dedup, corroboration (2026-04-19)

**Problem found during an audit of the price_monitor results:** three questions
had no clean answer against the prior baseline — (1) how is "stale" being counted
and is it uniform across ingredient classes, (2) how vetted is LLM-populated
data like country of origin, and (3) where do new suppliers actually come from
and how do we catch hallucinated ones. The existing schema had no column to
record a row's evidentiary tier, no blocklist for non-supplier domains, no
normaliser for country strings, and no cross-run accounting for the same
supplier showing up under spelling variations.

**Changes shipped across five commits** (`ef3673b` → `8ee2ace`):

### 11.1. Schema migration (`ef3673b`)
`enrichment/db_migrate_provenance.py` — idempotent. Adds to
`Supplier_Commercial`: `Provenance_Confidence`, `Evidence_Snippet`,
`URL_Archetype`, `URL_Health`, `Corroboration_Score`. Adds to
`Ingredient_Canonical`: `Category`, `Usage_Tier`. Creates `URL_Blocklist`
(seeded with 28 non-supplier domains: wikipedia, reddit, linkedin,
vertexaisearch.cloud.google.com grounding redirects, etc.) and
`Supplier_Master` (queue for trade-register verification).

Backfilled against current DB: `Usage_Tier` populated for all 250 canonicals
(top 50 by BOM appearance = tier 1, next 50 = tier 2, rest = tier 3);
`Category` populated for 165 of 250 from the existing `Function` column.

### 11.2. Per-category staleness TTL (`81d83ae`)
`orchestration/tools/price_staleness_checker.py` rewritten. Replaces the
single 7-day window with a category-keyed dict — `commodity_excipient=14`,
`mineral/protein=10`, `botanical=7`, `vitamin/api=5`, default=7 — plus ±12h
jitter so a batch refresh doesn't create a thundering-herd on the next run.
Adds a `_classify_timestamp` guard that flags forward-dated or >2-year-old
`Last_Updated` values as `timestamp_invalid` rather than treating them as
fresh. Splits the result into `never_refreshed` / `stale` /
`refresh_failed_recently` buckets. Sorts by `Usage_Tier` first so tier-1
ingredients drain the queue before tier-3 when the batch is capped.

### 11.3. Provenance gates on write (`0200994`)
`enrichment/enrichers/country_iso.py` — hand-curated ISO-3166 allow-list
(~60 countries) with alias resolution (USA / US / U.S. / United States all
collapse to `"USA"`). Unknown inputs return `None`; caller WARN-logs and
persists `NULL` rather than the garbage string.

`enrichment/enrichers/supplier_web_enricher.py` gained:
  - `_load_blocklist` / `_hostname_blocked` with parent-domain walk
    (e.g. `news.reddit.com` matches `reddit.com`), rejecting the entire row
    before a Supplier_Commercial insert.
  - `_EVIDENCE_KEYS` alias tuple + 200-char capture into `Evidence_Snippet`
    on every write — the audit trail for each row, paired with its
    `Source_URL`.

`orchestration/agents/search_sub_agent.py` — schema extended with
`evidence_snippet: string (<=200 chars)` and example updated. The model is
now asked for the substring it used to derive the claim, not just the
claim itself.

### 11.4. Dedup + archetype + corroboration (`afbbf60`)
`supplier_web_enricher.py` continued:
  - `_CORP_SUFFIX_RE` + `_normalize_supplier_name` strip Inc / Ltd / LLC /
    GmbH / AG / SA / Pvt / Pty / etc., plus punctuation, before comparison.
  - `_fuzzy_match_supplier` uses `rapidfuzz.process.extractOne` with
    `token_set_ratio` and a 90-point cutoff. `_upsert_supplier` now does
    exact → fuzzy → insert, so `"PureBulk, Inc."` and `"Purebulk Inc"`
    collapse to one SupplierId.
  - `_ARCHETYPE_HOSTS` — hostname → archetype table covering ~45 domains:
    directory_listing (indiamart, alibaba, tradeindia, exportersindia),
    distributor (bulksupplements, purebulk, univarsolutions, bulkfoods),
    lab_reagent (sigmaaldrich, fishersci, thermofisher), and
    manufacturer_direct (jungbunzlauer, chem-impex, rpicorp, DSM, BASF,
    Cargill, ADM, Roquette, Ingredion). Parent-domain walk handles subdomains.
  - `_classify_provenance` — decision tree producing `vendor_verified >
    website_explicit > directory_listing > model_inferred > unknown`.
    `manufacturer_direct` archetype lifts to `website_explicit`; everything
    else with a resolved country caps at `directory_listing`.

`enrichment/backfill_provenance.py` — four-pass migration script. Archetype,
provenance, and corroboration passes are offline and idempotent;
`url_health` pass is async (httpx, 10 concurrent, 2s timeout) and gated
behind `--check-urls`.

Ran against current DB: 169 rows re-classified, 138 suppliers scored.
Corroboration formula: `max(0, distinct_hosts + distinct_dates - 2)`.

### 11.5. Two-pass verification + trade-register stub (`8ee2ace`)
`enrichment/verify_suppliers.py` — two independent passes:

  - `homepage_verify` (network, opt-in via `--pass homepage`): picks top-N
    suppliers by corroboration, fetches each one's dominant host's homepage
    (4s timeout, 8 concurrent), and checks whether the normalised supplier
    name appears in the first 4KB of body text. On match, lifts
    `Provenance_Confidence` on every row of that supplier from
    `website_explicit` / `directory_listing` → `vendor_verified`.
  - `trade_register_stub` (offline): for suppliers with
    `Corroboration_Score >= 3`, upserts a `Supplier_Master` row with
    `Vetted=0`, `Vetted_Source='pending_manual_review'`. A real batch
    job would consume this queue via OpenCorporates / D&B / GLEIF.

Ran `trade_register` pass — 2 suppliers enqueued (Chem-Impex, Sinofi
Ingredients, both score=3). Re-run is clean (2 refreshed, 0 new).

### 11.6. Final verification state (2026-04-19)

Schema: all 7 new columns present, `URL_Blocklist` 28 entries,
`Supplier_Master` 2 queued.

`Usage_Tier`: 50 / 50 / 150 across 250 canonicals.
`Category`: 65 commodity_excipient, 36 mineral, 35 botanical, 19 vitamin,
10 protein, 85 unknown (ingredients with empty/novel `Function` strings).

`URL_Archetype` post-backfill (169 google_search rows):
`directory_listing=58 / distributor=35 / manufacturer_direct=8 /
lab_reagent=4 / unknown=64`.

`Provenance_Confidence` (169 google_search rows):
`directory_listing=140 / model_inferred=21 / website_explicit=8 /
vendor_verified=0`. vendor_verified stays at 0 until the homepage pass runs
against a live network, which is intentionally not triggered in the default
pipeline.

Top-5 corroboration: Sinofi Ingredients (3), Chem-Impex (3),
BulkSupplements.com (2), Univar Solutions (2), TALSEN CHEM (1).

Unit-style checks: `country_iso` 17/17, `_classify_archetype` 12/12,
`_classify_provenance` 7/7, `_fuzzy_match_supplier` 10/10,
`_name_matches_page` 8/8.

**What's still soft:**
  - 64 rows at `URL_Archetype=unknown` — long tail of one-off legit domains
    (dudadiesel, marinehydrocolloids, solvo-chem, etc.). Not worth per-host
    mapping; they correctly fall through to `Provenance_Confidence ∈
    {directory_listing, model_inferred}` which reflects the weaker evidence.
  - `vendor_verified` requires the opt-in `homepage_verify` pass (network).
    The existing 5 `vertexaisearch.cloud.google.com` rows are now blocklisted
    so fresh enrichments won't re-introduce them; the stale rows remain
    until the next `supplier_web_enrich` run overwrites or the URL_Blocklist
    gate is applied retroactively.
  - DUNS / LEI resolution is stubbed. The `Supplier_Master` queue is real
    and idempotent, but no external API is called until keys are wired in.
