# Run Instructions — Phase 4 Demo

## One-time setup

From the repo root (`Spherecast-Agnes`) on the `phase-4` branch:

```bash
# 1. Drop patches into place (back up originals first)
for f in gate_engine.py compliance_reasoner.py refusal_engine.py; do
  cp reasoning/$f reasoning/$f.preagnes.bak
  cp tim-package/patches/$f reasoning/$f
done
cp Orchestration/qualify_candidate.py Orchestration/qualify_candidate.py.preagnes.bak
cp tim-package/patches/qualify_candidate.py Orchestration/qualify_candidate.py
cp tim-package/Orchestration/demo_real.py Orchestration/demo_real.py

# 2. Run v12 migration (adds Refusal_Record, Supplier_Score, RFQ tables, etc.)
python -m enrichment.db_migrate_v12

# 3. Materialize substitution graph from the curated rule table
python -m enrichment.substitution_graph
```

## Known schema-view fix (SQLite < 3.44)

If you see `sqlite3.OperationalError: malformed database schema (v_bom_signature) - near 'ORDER': syntax error`, your SQLite is older than 3.44 and doesn't support `GROUP_CONCAT(... ORDER BY ...)` inside a view:

```bash
python - <<'PY'
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
c.executescript("""
PRAGMA writable_schema = ON;
DELETE FROM sqlite_master WHERE name='v_bom_signature';
PRAGMA writable_schema = OFF;
""")
c.commit()
PY
```

## Run the demo

```bash
python -m Orchestration.demo_real \
    --db db_enriched.sqlite \
    --top-n 5 \
    --use-class supplement \
    --jurisdictions US-FDA EU \
    --out /tmp/agnes_demo.md
```

Then open `/tmp/agnes_demo.md` for the full report.

## What you should see

With current enrichment depth:

```
[demo_real] evaluating opportunity 259 — Calcium citrate
[demo_real] evaluating opportunity 263 — MAGNESIUM STEARATE
[demo_real] evaluating opportunity 307 — CALCIUM CARBONATE
[demo_real] evaluating opportunity 306 — Vegetable Magnesium Stearate
[demo_real] wrote /tmp/agnes_demo.md
```

Summary row for Magnesium Stearate:
```
| 263 | MAGNESIUM STEARATE | 4 | 4 | 0 | Ashland | 0.402 | 3 |
```
→ 4 candidates pass gate+compliance, top supplier Ashland scored 0.402, 3 RFQs drafted.

See `example-output.md` for a frozen reference report.

## Tables to inspect after a run

```sql
-- every (opp, candidate) gate outcome
SELECT OpportunityId, CandidateSkuId, OverallPass, FailedGate, CompoundConfidence
  FROM Substitution_Gate_Result
 ORDER BY GateRunId DESC LIMIT 20;

-- every (opp, candidate, jurisdiction) compliance verdict
SELECT * FROM Compliance_Outcome_4State ORDER BY ComplianceRunId DESC LIMIT 20;

-- auditable refusal trail
SELECT * FROM Refusal_Record ORDER BY RefusalId DESC LIMIT 20;

-- supplier scoring output
SELECT * FROM Supplier_Score ORDER BY ScoreId DESC LIMIT 10;

-- drafted RFQs (Status='draft' until a human clicks Send)
SELECT * FROM RFQ WHERE Status='draft' ORDER BY RfqId DESC LIMIT 10;
```

## Resetting between runs

The demo is idempotent per-schema but append-only per-run:

```sql
DELETE FROM Refusal_Record;
DELETE FROM Substitution_Gate_Result;
DELETE FROM Compliance_Outcome_4State;
DELETE FROM Supplier_Score;
DELETE FROM RFQ;
```

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--db` | `db_enriched.sqlite` | SQLite path |
| `--top-n` | `5` | Number of top-scoring opportunities to evaluate |
| `--use-class` | `supplement` | Must match `compliance_reasoner.JURISDICTION_PACKS[j][x].allowed_use_classes` — accepts `food`, `beverage`, `dietary-supplement` |
| `--jurisdictions` | `US-FDA EU` | Space-separated; also accepts `US-USP` |
| `--out` | `report.md` | Output markdown path |
