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

