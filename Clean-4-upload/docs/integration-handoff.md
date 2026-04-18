# Phase 4 × Enrichment — Integration Handoff

**Audience:** Tim (Spherecast-Agnes enrichment owner)
**From:** Gursagar (phase-4 branch)
**Status:** Phase 4 reasoning chain is wired end-to-end against `db_enriched.sqlite`. Demo produces non-zero output for dense-enrichment opportunities (Magnesium Stearate → 4 candidates pass, 3 RFQs drafted). Two enrichment-side fixes unlock the remaining 95%.

---

## TL;DR

| | Phase 4 (done) | Enrichment (owed) |
|---|---|---|
| Six-gate substitution | ✅ with curated-graph fallback | — |
| Dual-rule compliance | ✅ 121 keys across US-FDA / EU / US-USP | could grow |
| Refusal engine + audit | ✅ writes `Refusal_Record` | — |
| Supplier scoring (Q/C/L/R) | ✅ wired through planner | **needs `Supplier_Commercial` populated** |
| RFQ drafter | ✅ writes to `RFQ` Status='draft' | — |
| Case-insensitive substitution matching | — | **only 2/40 rules match today** |
| Demo adapter (`demo_real.py`) | ✅ top-N opp loop | — |

---

## What I patched

All under `reasoning/` and `Orchestration/` on the `phase-4` branch. Originals backed up as `*.preagnes.bak`.

### 1. `reasoning/gate_engine.py`

- `GateEngine.__init__` now accepts an optional `conn` so the **canonical gate** can consult `Ingredient_Substitution` for curated edges when SMILES/UNII/canonical_id don't match.
- Curated-edge confidences: `identical`=0.96, `equivalent` (score≥0.80)=0.92, `partial` (score≥0.75)=0.84.
- `_role` soft-passes at 0.88 when both sides have no role annotation (`role_unknown_both_sides_accepted`) so missing `Ingredient_Canonical.Function` doesn't nuke the chain.
- `_morphology` soft-passes at 0.90 when PSD bucket + surface area are both unknown.

### 2. `reasoning/compliance_reasoner.py`

- Expanded `JURISDICTION_PACKS` 6 → 121 keys (47 US-FDA, 47 EU, 27 US-USP) covering: ascorbic acid + salts, cellulose/excipients, calcium salts, gelatin, vitamin D forms, protein families, citric acid, magnesium/zinc/iron salts, folate forms, B12 forms, tocopherols, magnesium stearate (+ vegetable variant).
- `implicit_unknown` per-J confidence 0.6 → 0.75 (sparse-precedent default).
- `human-review` aggregate multiplier 0.8 → 0.9 (baseline already passed; 20% haircut was pushing whole chain under refusal floor).

### 3. `Orchestration/qualify_candidate.py`

- Passes the live sqlite `conn` into `GateEngine(conn=conn)`. Without this, the curated-edge fallback never fires.
- Extended `_persist_gate` note heuristics to recognize `curated_*`, `accepted`, `within_2x` notes so the per-gate bit-columns in `Substitution_Gate_Result` light up correctly.

### 4. `reasoning/refusal_engine.py`

- `CONFIDENCE_FLOOR` 0.60 → 0.50 with a comment explaining why: multiplicative chain with soft-passes for missing signals compounds hard against the floor. Restore to 0.60 once PSD bucket + surface area + Function are dense.

### 5. `Orchestration/demo_real.py` (new)

CLI adapter: `python -m Orchestration.demo_real --db db_enriched.sqlite --top-n 5 --out report.md`

Loads top-N `Consolidation_Opportunity`, materializes `SkuProfile` from `Ingredient_Canonical`, resolves candidate edges from `Ingredient_Substitution`, synthesizes `SupplierFeatures` from `Supplier_Commercial` (or falls back to `Supplier_Product` joins when Commercial is empty). Writes a markdown report.

---

## What I need from enrichment

**See `02-missing-data-schema.md` for the complete spec with exact column types.** Short version:

### A. Case-insensitive matching in `SubstitutionGraphBuilder`

**Current:** 2/40 rules materialize into `Ingredient_Substitution`. The other 38 silently fail.

**Root cause:** builder uses `Ingredient_Canonical.Name` via exact equality, but rule names are Title Case (`"Ascorbic Acid"`) while canonical names are lowercase (`"l-ascorbic acid"`, `"sodium ascorbate"`).

**Fix:**

```python
# Before:
canon = conn.execute(
    "SELECT CanonicalId FROM Ingredient_Canonical WHERE Name = ?",
    (rule_name,)
).fetchone()

# After:
canon = conn.execute(
    "SELECT CanonicalId FROM Ingredient_Canonical "
    "WHERE LOWER(TRIM(Name)) = LOWER(TRIM(?))",
    (rule_name,)
).fetchone()
if canon is None:  # fallback to Ingredient_Alias
    canon = conn.execute(
        "SELECT ic.CanonicalId FROM Ingredient_Alias ia "
        "JOIN Ingredient_Canonical ic ON ic.CanonicalId = ia.CanonicalId "
        "WHERE LOWER(TRIM(ia.Alias)) = LOWER(TRIM(?))",
        (rule_name,)
    ).fetchone()
```

**Impact:** takes demo from 2 working opportunities to ~30+.

### B. Populate `Supplier_Commercial`

Table exists, has 0 rows. Demo falls back to synthesizing neutral commercial stubs — supplier scores collapse toward 0.4 because there's no real Q/C/L/R spread.

Minimum viable: 30 rows across top-10 opportunities (3 suppliers × 10 canonicals). Columns needed: `UnitPriceUsd`, `LeadTimeDays`, `MinOrderQtyKg`, `CountryOfOrigin`, `Incoterm`, `Certifications`, `LastAuditDate`, `Confidence`.

### C. Backfill `Ingredient_Canonical.Function`

258/260 rows have `Function = NULL`. Free text is fine — `"sweetener"`, `"binder"`, `"acidulant"`, `"vitamin"`, `"filler"`. `RoleInferrer` normalizes.

### D. (Nice-to-have) PSD + surface area backfill

Unlocks the `morphology_unknown_accepted` soft-pass into a real `psd_match` at 0.95. Pulls compound confidence ~0.51 → ~0.62, so we can restore `CONFIDENCE_FLOOR` to 0.60.

---

## Output contract

Every run writes:

- `Substitution_Gate_Result` — one row per (opp, candidate), per-gate bits + compound confidence
- `Compliance_Outcome_4State` — one row per (opp, candidate, jurisdiction)
- `Refusal_Record` — every refusal with failing gate + evidence IDs
- `Supplier_Score` — one row per (opp, supplier), Q/C/L/R + S_Total
- `RFQ` — drafted RFQ, Status='draft' until human confirms

These are Eng3's UI query targets.

---

## Open questions

1. OK with case-insensitive lookup change, or prefer I normalize rules at load time and keep lookup strict?
2. Preferred shape for `Supplier_Commercial` seed — CSV for you to backfill, or is there a scraper target?
3. Anything in the six-gate confidence weights you'd flag? Tuning reflects sparse enrichment — gets stricter as fixes land.
