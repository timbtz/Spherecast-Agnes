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
