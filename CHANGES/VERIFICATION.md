# consolidated-baseline — Verification Report
Generated: 2026-04-18T23:20Z

## Scope

Per user directive: *"all the code for the base infrastructure (back end, front end)
should be compiled and it exists between the master github and clean 4 branch,
can we consolidate into a new branch, run the full pipeline, debug and test the full
product, we will work on integrating new features after we achieve this baseline
success with everything currently compiled."*

Branch: `consolidated-baseline`, off `master` HEAD with Clean-4 overlays.

## Stack-up

| Layer | Status | Notes |
|---|---|---|
| FastAPI backend | ✅ healthy | `uvicorn` boots clean, `/health` returns ok |
| Lifespan scheduler | ✅ running | `_price_monitor_scheduler` task spawned |
| Lovable SPA | ✅ built + served | `orchestration/ui/dist` at `/`, fallback to `index.html` for unknown paths |
| SQLite enriched DB | ✅ patched | view `v_bom_signature` rewritten for SQLite 3.37 |
| Reasoning scaffold | ✅ overlaid | evidence_ledger, gate_engine, justification, red_team, tools_extra |
| Molport 3-path | ✅ overlaid | API → scraper → fixtures (API key empty is expected) |
| Logistics + Scout | ✅ overlaid | from Clean-4 |

## Pipelines (7/7 green)

All triggered through `POST /pipelines/{name}/run` and observed via `/runs/{run_id}`.

| Pipeline | Status |
|---|---|
| `substitution_discovery` | ✅ completed |
| `new_ingredient_research` | ✅ completed (proposal emitted) |
| `price_audit` | ✅ completed |
| `proactive_consolidation` | ✅ completed — 21 Consolidation_Opportunity rows persisted, top scoring=0.893 (Vitamin C) |
| `regulatory_drift_alert` | ✅ completed |
| `supplier_fallout` | ✅ completed |
| `price_monitor` | ✅ completed (377s) — 20 stale ingredients, 11 suppliers updated via web search, 0 alerts (narrative skipped correctly), see run_id `39952d48-3fa0-42a5-9fa7-766c68db1d01` |

## End-to-end chat-to-proposal flow

Prompt: *"Find consolidation opportunities for magnesium stearate across our suppliers"*

| Step | Result |
|---|---|
| `POST /chat` router classification | `proactive_consolidation`, confidence **1.0** |
| Pipeline duration | 13 s |
| Opportunities surfaced | 2 (Vitamin C @ 0.893, Cellulose @ 0.584) |
| SSE stream events | `pipeline_started`, `node_started×2`, `node_completed×2`, `pipeline_completed`, `stream_closed` — all delivered live |
| Persisted to `/api/data/proposals` | ✅ 21 total rows including the fresh ones |

## Bugs fixed silently (per user posture)

1. **SQLite 3.37 `GROUP_CONCAT(col ORDER BY col)`** in `v_bom_signature` view → patched in-place via `PRAGMA writable_schema=1`.
2. **`Supplier` table INSERT with phantom `Country` column** → `commercial_enricher.py` and `supplier_web_enricher.py` patched to drop the column from the INSERT (country lives on `Supplier_Commercial.Country_Origin`).

## Known caveats (non-blocking)

- `sentence-transformers` and `playwright` browser binaries are not installed in this sandbox — none of the 7 pipelines need them in their happy paths.
- Two modules (`enrichment/run_dedup.py`, `reasoning/substitution_graph.py`) have side-effecting `__main__` logic that runs on import-walk; not triggered by FastAPI boot.
- Three skill-creator scripts under `.claude/skills/skill-creator/scripts/` failed import-walk; they are part of Claude Code's own infra, not Agnes app code.
- `MOLPORT_API_KEY` left empty — scraper / fixtures path is the documented fallback.

## What ships in this branch

- All master commits up to current HEAD.
- Clean-4 overlay: Molport 3-path, logistics, scout, reasoning scaffold (evidence_ledger / gate_engine / justification / red_team / tools_extra), index downloader.
- Lovable SPA built artefacts (`orchestration/ui/dist`) and committed for FastAPI to serve.
- Patched `db_enriched.sqlite` (view fix only — data unchanged; backup at `db_enriched.sqlite.preview-fix.bak`).
- Patched two enrichers (`commercial_enricher.py`, `supplier_web_enricher.py`).
- This `CHANGES/` folder.

## What is NOT in this branch

- No new features beyond consolidation, per user directive.
- No agent-prompt edits, no new pipelines, no new DAG nodes.
