# Agnes — Phase 4 Real-Data Demo

Ran the full six-gate / dual-rule / supplier-score / RFQ chain against Tim's enriched dataset. Evaluated the top 4 consolidation opportunities.

## Summary table

| Opp | Incumbent | Candidates | Recommend+Review | Refused | Top supplier | Score | RFQs |
|----:|:----------|-----------:|-----------------:|--------:|:-------------|------:|-----:|
| 259 | Calcium citrate | 4 | 0 | 4 | — | — | 0 |
| 263 | MAGNESIUM STEARATE | 4 | 0 | 4 | — | — | 0 |
| 307 | CALCIUM CARBONATE | 8 | 0 | 8 | — | — | 0 |
| 306 | Vegetable Magnesium Stearate | 4 | 0 | 4 | — | — | 0 |

## Opportunity #259 — Calcium citrate

- consolidation_score: `0.630` · companies: 17 · BOMs: 23 · current suppliers: 4
- candidates evaluated: 4
- decision breakdown: {'refuse_gate_fail': 4}

## Opportunity #259 — Calcium citrate

- use_class: `supplement`

- jurisdictions: US-FDA, EU

- candidates evaluated: 4

- recommend / human-review: 0

- refused: 4

- top-supplier score: 0.000

- drafted RFQs: 0



### Per-candidate justifications

### Calcium citrate → CALCIUM CARBONATE
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Calcium citrate → CALCIUM CARBONATE
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Calcium citrate → CALCIUM CARBONATE
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Calcium citrate → CALCIUM CARBONATE
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

## Opportunity #263 — MAGNESIUM STEARATE

- consolidation_score: `0.427` · companies: 11 · BOMs: 22 · current suppliers: 2
- candidates evaluated: 4
- decision breakdown: {'refuse_low_confidence': 4}

## Opportunity #263 — MAGNESIUM STEARATE

- use_class: `supplement`

- jurisdictions: US-FDA, EU

- candidates evaluated: 4

- recommend / human-review: 0

- refused: 4

- top-supplier score: 0.000

- drafted RFQs: 0



### Per-candidate justifications

### MAGNESIUM STEARATE → Vegetable Magnesium Stearate
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### MAGNESIUM STEARATE → Vegetable Magnesium Stearate
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### MAGNESIUM STEARATE → Vegetable Magnesium Stearate
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### MAGNESIUM STEARATE → Vegetable Magnesium Stearate
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

## Opportunity #307 — CALCIUM CARBONATE

- consolidation_score: `0.310` · companies: 8 · BOMs: 14 · current suppliers: 2
- candidates evaluated: 8
- decision breakdown: {'refuse_gate_fail': 8}

## Opportunity #307 — CALCIUM CARBONATE

- use_class: `supplement`

- jurisdictions: US-FDA, EU

- candidates evaluated: 8

- recommend / human-review: 0

- refused: 8

- top-supplier score: 0.000

- drafted RFQs: 0



### Per-candidate justifications

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### CALCIUM CARBONATE → Calcium citrate
**Decision:** `refuse_gate_fail`  •  **Confidence:** 16%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_partial:0.76` (84%)
- ✗ Functional role: `role_missing_one_side` (35%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)
- **First gate failure:** `role`

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_gate_fail at compound confidence 16%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

## Opportunity #306 — Vegetable Magnesium Stearate

- consolidation_score: `0.170` · companies: 4 · BOMs: 6 · current suppliers: 2
- candidates evaluated: 4
- decision breakdown: {'refuse_low_confidence': 4}

## Opportunity #306 — Vegetable Magnesium Stearate

- use_class: `supplement`

- jurisdictions: US-FDA, EU

- candidates evaluated: 4

- recommend / human-review: 0

- refused: 4

- top-supplier score: 0.000

- drafted RFQs: 0



### Per-candidate justifications

### Vegetable Magnesium Stearate → MAGNESIUM STEARATE
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Vegetable Magnesium Stearate → MAGNESIUM STEARATE
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Vegetable Magnesium Stearate → MAGNESIUM STEARATE
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.

### Vegetable Magnesium Stearate → MAGNESIUM STEARATE
**Decision:** `refuse_low_confidence`  •  **Confidence:** 45%
**Jurisdictions evaluated:** US-FDA, EU

**Substitution gates**
- ✓ Canonical identity: `curated_identical:0.98` (96%)
- ✓ Functional role: `role_unknown_both_sides_accepted` (88%)
- ✓ Physical form: `form_ok:powder/powder` (96%)
- ✓ Grade tier: `grade_ok:food>=food` (97%)
- ✓ Morphology / PSD: `morphology_unknown_accepted` (90%)
- ✓ Regulatory approval: `reg_approved:US-FDA` (97%)

**Compliance**
- Outcome: `human-review`
- Reason: `baseline_ok;implicit_ambiguous`
  - US-FDA: baseline_ok=True, implicit_ok=no, conf=82%
  - EU: baseline_ok=True, implicit_ok=no, conf=82%

**Why we refused**
- refuse_low_confidence at compound confidence 45%.
- Every refusal is logged to `Refusal_Record` with full evidence trail.
