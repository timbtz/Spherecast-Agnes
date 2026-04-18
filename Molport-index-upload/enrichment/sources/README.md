# `enrichment/sources/` — Molport scraper (Clean-4)

This directory replaces master's `enrichment/sources/` with an API-key-optional
version. Everything the Phase-3 `commercial_enricher` depends on still works;
two new code paths are added for the hackathon demo.

## Files

| File | Purpose | New / Changed |
|---|---|---|
| `__init__.py` | Package marker | new |
| `molport.py` | `MolportClient` with three-path dispatch (API / scraper / fixtures) | **replaces** master's version |
| `molport_scraper.py` | Playwright-driven scraper of molport.com public UI | new |
| `molport_cache.py` | Thin wrapper over existing `API_Response_Cache` table | new |
| `molport_fixtures.py` | Hand-curated envelopes for 4 anchor demo CASes (with verified Molport IDs) | new |
| `molport_index.py` | Read-only wrapper over the 6M-compound identity index (anti-hallucination + direct-URL skip) | new |
| `molport_index_build.py` | One-time CLI that builds `db_molport_index.sqlite` from Molport's public SMILES dump | new |
| `smoke_test_molport.py` | Offline test suite — cache + fixtures + flatten + index (40 assertions) | new |

No schema change required — `API_Response_Cache` already exists in
`schema/enriched_schema.sql` with `Source='molport'` documented.

## Molport identity index (anti-hallucination layer)

The scraper is paired with a 6M-row SQLite index (`db_molport_index.sqlite`,
~1.65 GB) that maps every Molport compound's SMILES → Molport ID. It acts as
a pre-flight and post-flight check around the scraper:

1. **Pre-flight**: SMILES-not-in-index → refuse to scrape (compound doesn't
   exist on Molport, don't waste a page load).
2. **Direct-URL skip**: known Molport ID → navigate directly to
   `https://www.molport.com/shop/compound/<id>` instead of driving the
   search page.
3. **Post-flight**: after scraping, verify the page's Molport ID matches
   what we asked for — rejects any selector drift that would leak fake data.

The index file is too large for the repo (GitHub's 100 MB/file limit).
Two ways to get it:

**Option A — download the pre-built release asset (fast):**

```bash
python scripts/download_index.py
# → writes db_molport_index.sqlite into the repo root (atomic)
```

Override the URL with `--url` or the `MOLPORT_INDEX_URL` env var, and
optionally pass `--sha256 <hex>` to verify the download.

**Option B — rebuild from Molport's public SMILES dump (~3 min, ~6 GB download):**

```bash
# 1. Download the SMILES dump from https://www.molport.com/shop/download-database
#    (the "All Stock Compounds" set — 12 .txt.gz files, ~1.6 GB compressed)
# 2. Run the builder:
python -m enrichment.sources.molport_index_build \
    --src "/path/to/All Stock Compounds/SMILES" \
    --out db_molport_index.sqlite
```

If the index is missing, `MolportIndex` degrades gracefully — all methods
return `None` / `False` and the scraper falls back to search-page parsing
plus the fixture table (still works for the anchor demo CASes).

## Environment flags

| Variable | Effect |
|---|---|
| `MOLPORT_API_KEY` | If set, use REST v3 API (original behavior). |
| `MOLPORT_SCRAPER_ENABLED=1` | If set **and** no API key, use Playwright scraper. Falls back to fixtures when a demo CAS yields no scrape results. |
| `MOLPORT_FIXTURES_ONLY=1` | Short-circuit everything — use fixture table only. Good for 10-minutes-before-demo. |

If none are set, `MolportClient.lookup_ingredient()` returns `[]` and
`commercial_enricher` logs a warning (same as master's behavior).

## Running the scraper

```bash
pip install -r requirements.txt
playwright install chromium

# One-off CLI (writes JSON to stdout)
export MOLPORT_SCRAPER_ENABLED=1
python -m enrichment.sources.molport_scraper --cas 557-04-0

# Full pipeline (Phase 3 will call the scraper when enrichment reaches commercial)
export MOLPORT_SCRAPER_ENABLED=1
python enrichment/pipeline.py --phase 3
```

## Running the offline tests

No browser, no network — exercises cache + fixtures + flatten logic only.

```bash
MOLPORT_FIXTURES_ONLY=1 python -m enrichment.sources.smoke_test_molport
```

All 40 assertions pass in the last validated run (cache + fixtures + flatten
+ index lookup + validate + graceful-degradation + URL builder).

## Known rough edges

1. **Scraper selectors are placeholders.** The live Molport product page is
   heavily JS-rendered and we have not completed a live reconnaissance run.
   The first real scrape will likely require refining `_SELECTORS` in
   `molport_scraper.py`. The logger emits
   `"Product page scraped but no suppliers parsed — selectors likely need refinement"`
   when this happens.
2. **Login-gated pricing.** Some Molport suppliers hide prices behind a login.
   The scraper does not authenticate. Rows that come back with `null` price
   are preserved and tagged `price_type='retail_proxy', grade_unverified=1`
   so the decision layer treats them correctly.
3. **Rate limiting.** Default 2s between navigations. Do not crank this down
   for a full-catalog run — scope to the demo compound list.
4. **ToS.** Automated scraping of molport.com is tolerated for low-volume,
   attributable use. Do not enable the scraper against the full 876-SKU
   catalog in production. For production, wait on the API key.

## Migration from master

Drop-in replacement. Master's `enrichment/sources/molport.py` exported the
same class and method signatures:

```python
from enrichment.sources.molport import MolportClient
client = MolportClient(db_path="db_enriched.sqlite")
rows = client.lookup_ingredient({"cas_number": "557-04-0", "name": "magnesium stearate", "smiles": "..."})
```

The only behavioral change is that `lookup_ingredient` now has three alternative
paths governed by the env flags above; if no flag is set, behavior is identical
to master.
