# Enriched DB upload — READ THIS FIRST

Single-file drop folder. Upload the `.sqlite` to the repo; do NOT upload this README.

## What's here

```
enriched-db-upload/
├── READ-THIS-FIRST.md      ← do NOT upload
└── db_enriched.sqlite      ← upload to repo root on Clean-4 branch
```

Size: 22 MB. WAL already checkpointed + VACUUMed into this single file, so no
`-wal` or `-shm` sidecar to worry about.

## Where it goes

- Repo: `timbtz/Spherecast-Agnes`
- Branch: `Clean-4` (then it rides the existing Clean-4 → master PR)
- Path: repo root — overwrite the existing `db_enriched.sqlite`

## Commit recipe

```bash
cd ~/path/to/Spherecast-Agnes
git checkout Clean-4
cp ~/Documents/enriched-db-upload/db_enriched.sqlite ./db_enriched.sqlite
git add db_enriched.sqlite
git commit -m "db: refresh db_enriched.sqlite — Clean-4 Molport enrichment + full reasoning run"
git push origin Clean-4
```

## What's in the DB

Full enrichment pipeline ran end-to-end. Snapshot:

| Table | Rows | Meaning |
|---|---|---|
| `Ingredient_Canonical` | 260 | Phase-1 canonical ingredients |
| `SKU_To_Canonical` | 854 | Phase-1 SKU→canonical mappings |
| `BOM_Component_Quantity` | 515 | Phase-2 per-BOM quantities |
| `Supplier_Commercial` | 6 | **Phase-3 — Molport commercial leg, Clean-4 delivered** |
| `Supplier` | 45 | 5 added by Molport enrichment |
| `Product_Compliance` | 126 | Phase-3 compliance facts |
| `Consolidation_Opportunity` | 129 | Phase-4 ranked opportunities (top: Vitamin C 0.893) |
| `Ingredient_Substitution` | 4 | Phase-4 curated substitution edges |
| `Substitution_Gate_Result` | 241 | Gate engine decisions |
| `Compliance_Outcome_4State` | 548 | Dual-rule compliance outcomes |
| `Supplier_Score` | 67 | 5-axis weighted supplier scores |
| `Refusal_Record` | 186 | Structured refusals across 6 reason codes |
| `RFQ` | 57 | Draft RFQs with full JSON specs |
| `API_Response_Cache` | 1,653 | PubChem / DSLD / Molport responses |
| `Enrichment_Run_Log` | 1,298 | Audit trail |

## Caveats

- This DB has live reasoning-run state baked in (RFQs, refusals, scores).
  That's a feature for the demo — teammates get a DB that proves the pipeline
  runs end-to-end. If a teammate wants a clean slate to re-run, truncate
  `Substitution_Gate_Result / Compliance_Outcome_4State / Supplier_Score /
  Refusal_Record / RFQ` before running, or re-run
  `python -m enrichment.db_bootstrap --force` to start from scratch.
- `Evidence_Ledger` is present (schema) but has 0 rows — no producer wired
  yet. This is the Tier-S3 "citation ledger" feature from `winning-features.md`.
- `Drafted_RFQ` table exists in the schema but is 0 rows; the active RFQ
  persistence path writes to the `RFQ` table (see `Orchestration/rfq.py`).

## If it's too big for a plain git commit

22 MB is within GitHub's 100 MB hard limit and only slightly above the
50 MB soft warning, so plain `git add` is fine. If you'd rather keep the
repo trim:

```bash
# Option B — publish as a Release asset (same pattern as db_molport_index.sqlite)
gh release create demo-db-v1 db_enriched.sqlite \
    --title "Demo-ready enriched DB (Apr 18)" \
    --notes "22MB. 129 opportunities, 57 RFQs, 6 Molport supplier rows, 186 refusals."
```

## Sanity check after upload

On a fresh clone:

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('db_enriched.sqlite')
print('RFQs:', c.execute('SELECT COUNT(*) FROM RFQ').fetchone()[0])
print('Opportunities:', c.execute('SELECT COUNT(*) FROM Consolidation_Opportunity').fetchone()[0])
print('Supplier_Commercial:', c.execute('SELECT COUNT(*) FROM Supplier_Commercial').fetchone()[0])
"
# Expected: 57, 129, 6
```
