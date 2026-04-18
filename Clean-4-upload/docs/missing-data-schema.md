# Missing-Data Schema — What Enrichment Owes Phase 4

**Purpose:** every variable Phase 4's reasoning chain reads but cannot find in `db_enriched.sqlite` today. Each row is either a new column/table to add or an existing column to backfill.

**Legend:**
- 🔴 **blocker** — without this, that reasoning path is inert
- 🟡 **degraded** — chain still runs but compound confidence sags
- 🟢 **nice-to-have** — marginal uplift

---

## 1. `Supplier_Commercial` — per (supplier, canonical) commercial facts

🔴 **Blocker for supplier scoring.** Table exists with 0 rows. Demo synthesizes neutral stubs, which collapses every score toward ~0.4.

| Column | Type | Used by | Required? | Example | Notes |
|---|---|---|---|---|---|
| `SupplierCommercialId` | INTEGER PK | — | auto | — | |
| `SupplierId` | INTEGER FK | all | 🔴 | `42` | → `Supplier.SupplierId` |
| `CanonicalIngredientId` | INTEGER FK | all | 🔴 | `263` | → `Ingredient_Canonical.CanonicalId` |
| `UnitPriceUsd` | REAL | `supplier_scorer.C` (cost) | 🔴 | `4.85` | per kg. ±30% ballpark is fine |
| `LeadTimeDays` | INTEGER | `supplier_scorer.L` + `logistics_planner` | 🔴 | `21` | door-to-door median |
| `MinOrderQtyKg` | REAL | RFQ `quantity_band_kg` check | 🟡 | `100` | below this, supplier won't quote |
| `MaxCapacityKgPerMonth` | REAL | `factory_sourcer` capacity match | 🟡 | `5000` | |
| `CountryOfOrigin` | TEXT (ISO-2) | `R` risk + logistics lane | 🔴 | `'US'`, `'DE'`, `'CN'` | |
| `Incoterm` | TEXT | landed-cost calc | 🟡 | `'FOB'`, `'CIF'`, `'DDP'` | defaults to `FOB` |
| `Currency` | TEXT (ISO-4217) | cost normalization | 🟢 | `'USD'` | defaults to USD |
| `Certifications` | TEXT (JSON array) | `Q` quality | 🟡 | `'["ISO22000","Kosher","Halal"]'` | |
| `LastAuditDate` | DATE | `R` risk decay | 🟡 | `'2025-09-14'` | older = higher risk |
| `SourceUrl` | TEXT | evidence | 🟢 | `'https://…'` | for `Evidence_Ledger` |
| `Confidence` | REAL | enrichment trust | 🟡 | `0.85` | 0..1 |

**Minimum viable coverage:** ~30 rows across top 10 consolidation opportunities (3 suppliers × 10 canonicals).

---

## 2. `Ingredient_Canonical` backfills

Table exists with 260 rows, several fields sparse.

| Column | Currently NULL | Used by | Level | What to put |
|---|---|---|---|---|
| `Function` | 258/260 | `gate_engine._role` | 🔴 | Free text — `"sweetener"`, `"binder"`, `"acidulant"`, `"vitamin"`, `"filler"`, `"emulsifier"`, `"preservative"`. `RoleInferrer` normalizes. |
| `PsdBucket` | ~250/260 | `gate_engine._morphology` | 🟡 | One of: `"fine"`, `"medium"`, `"coarse"`, `"granular"`. |
| `SurfaceAreaM2g` | ~250/260 | `gate_engine._morphology` | 🟡 | m²/g value. Enables ±2× fallback when PSD bucket disagrees. |
| `BulkDensityGml` | ~250/260 | `factory_sourcer` process-fit | 🟢 | g/mL. |
| `Grade` | ~50% | `gate_engine._grade` | 🟡 | `"pharma"`, `"food"`, `"feed"`, `"technical"`. |
| `UseClassDefault` | missing | `compliance_reasoner.use_class` fallback | 🟢 | `"food"`, `"supplement"`, `"beverage"`. Lets demo_real avoid hardcoded `--use-class`. |

**Priority:** just the top-30 canonicals by `Consolidation_Opportunity.Score`.

---

## 3. `Ingredient_Substitution_Rule` → `Ingredient_Substitution` materialization

🔴 **Only 2/40 rules materialize.** Case-sensitivity bug in `SubstitutionGraphBuilder`, not missing data.

In `enrichment/substitution_graph.py`, change strict equality to case-insensitive with alias fallback:

```python
# Before:
row = conn.execute(
    "SELECT CanonicalId FROM Ingredient_Canonical WHERE Name = ?",
    (rule_name,)
).fetchone()

# After:
row = conn.execute(
    "SELECT CanonicalId FROM Ingredient_Canonical "
    "WHERE LOWER(TRIM(Name)) = LOWER(TRIM(?))",
    (rule_name,)
).fetchone()
if row is None:
    row = conn.execute(
        "SELECT ic.CanonicalId FROM Ingredient_Alias ia "
        "JOIN Ingredient_Canonical ic ON ic.CanonicalId = ia.CanonicalId "
        "WHERE LOWER(TRIM(ia.Alias)) = LOWER(TRIM(?))",
        (rule_name,)
    ).fetchone()
```

Also log unmatched rule names — right now silent fallthrough hides 38 failures.

**Impact:** demo goes from 2 to ~30+ working opportunities.

---

## 4. `Incumbent_Precedent` — jurisdiction × canonical presence facts

🟡 We currently pass `incumbent_precedents={}` into `ComplianceReasoner`, so every jurisdiction falls into `implicit_unknown` (0.75 per-J confidence). Real precedent data raises it to 0.95 for `True` and unlocks the `fork-recommended` outcome.

### Option A — new table

```sql
CREATE TABLE Incumbent_Precedent (
  IncumbentPrecedentId INTEGER PRIMARY KEY,
  CanonicalIngredientId INTEGER NOT NULL,
  Jurisdiction TEXT NOT NULL,       -- 'US-FDA', 'EU', 'US-USP'
  Present INTEGER NOT NULL,         -- 1 = a trusted incumbent uses this canonical in this J
  SourceUrl TEXT,
  AsOfDate DATE,
  FOREIGN KEY (CanonicalIngredientId) REFERENCES Ingredient_Canonical(CanonicalId)
);
```

### Option B — view (lighter)

```sql
CREATE VIEW v_incumbent_precedent AS
SELECT DISTINCT
    sc.CanonicalIngredientId,
    pc.Jurisdiction,
    1 AS Present
  FROM SKU_To_Canonical sc
  JOIN Supplier_Product sp ON sp.SupplierProductId = sc.SupplierProductId
  JOIN Product_Compliance pc ON pc.ProductId = sp.ProductId
 WHERE pc.Status = 'compliant';
```

Happy with either.

---

## 5. `Supplier` risk augmentation

🟢 Current `Supplier` has basics only. `R` (risk) is currently flat 0.3 for everyone. Two fields unlock a real risk score:

| Column | Type | Drives | Default |
|---|---|---|---|
| `GeographicRiskTier` | INTEGER (1–5) | `R` geopolitical risk | `2` |
| `PastIncidentCount` | INTEGER | `R` audit trail | `0` |

5 = sanctions list / adversarial country; 1 = domestic, low-risk. Could also be derived from `CountryOfOrigin` via lookup table.

---

## 6. `Supplier_Facility` — for factory sourcing

🟢 New table, prerequisite for `factory_sourcer` module (phase-4b). Not blocking the demo.

| Column | Type | Notes |
|---|---|---|
| `FacilityId` | INTEGER PK | |
| `SupplierId` | INTEGER FK | |
| `Country` | TEXT (ISO-2) | |
| `City` | TEXT | |
| `ProcessCapabilities` | TEXT (JSON) | `["spray-dry","wet-granulation","fluid-bed"]` |
| `Certifications` | TEXT (JSON) | `["GMP","ISO9001","FSSC22000"]` |
| `CapacityKgPerMonth` | REAL | |
| `LastAuditScore` | REAL | 0..1 |

A supplier can have N facilities. `factory_sourcer` ranks facilities, not suppliers, when the incumbent ingredient needs a specific process.

---

## Priority order

1. 🔴 Case-insensitive fix in `SubstitutionGraphBuilder` — 10 LOC, unlocks 38 rules.
2. 🔴 30 rows of `Supplier_Commercial` — hand-curated is fine.
3. 🔴 `Ingredient_Canonical.Function` on top 30 canonicals.
4. 🟡 `PsdBucket` + `SurfaceAreaM2g`.
5. 🟡 `Incumbent_Precedent` view (Option B).
6. 🟢 Supplier risk fields + `Supplier_Facility`.

Items 1–3 = demo jumps from 2 → 30+ opportunities. Items 4–5 = compound confidence recovers enough to restore `CONFIDENCE_FLOOR` to 0.60.
