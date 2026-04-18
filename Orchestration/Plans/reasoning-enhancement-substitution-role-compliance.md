# Feature: Agnes Reasoning Enhancement — Substitution Graph, Role Classification & 4-State Compliance

The following plan should be complete, but validate documentation and codebase patterns before implementing. Pay special attention to naming of existing utils, types, and models. Import from the right files.

## Feature Description

Four targeted, high-value upgrades that improve Agnes's reasoning quality without requiring missing API data (Molport, FDC) or new infrastructure. All changes are additive and backward-compatible with the existing DAG executor and pipeline YAMLs. Together they go from coarse binary reasoning to nuanced, 4-state, jurisdiction-aware compliance decisions — and from 30 substitution edges to potentially 40+.

## User Story

As an Agnes pipeline operator  
I want substitution discovery and compliance gating to use richer, more precise reasoning  
So that pipeline outputs produce graded recommendations (recommend / fork / human-review / refuse) instead of binary pass/fail, and so ingredient roles and substitution options are correctly identified even for near-miss name variants

## Problem Statement

1. **SubstitutionGraphBuilder** uses exact-match lookup (COLLATE NOCASE) to resolve rule names to canonical IDs. 18/40 rules fail to materialize because rule names like "Zinc Oxide", "Ergocalciferol", "Methylcobalamin" don't exactly match any canonical entry name — even after the `scripts/fix_substitution_rules.py` alias pass.
2. **`Ingredient_Canonical.Function`** is NULL for all 250 rows. The local-dev `GateEngine._role()` soft-passes with 0.88 confidence when role is unknown, degrading compound confidence and preventing partial-substitute detection.
3. **`ComplianceGateTool`** is binary (pass/fail based on `Confidence >= 0.6`). It cannot detect "fork-recommended" (OK in US, banned in JP), does not read jurisdiction packs, and has no typed refusal reasons.
4. **No hard confidence floor** — LLM agents can generate proposals even when gate + compliance compound confidence is below any meaningful threshold.

## Solution Statement

- **Phase A**: Augment `_canonical_id()` in `reasoning/substitution_graph.py` with a `rapidfuzz` fuzzy fallback (threshold 85) so rule names that don't exactly match still resolve. Re-run to materialize additional edges.
- **Phase B**: Create `enrichment/enrichers/role_classifier.py` (mirrors `grade_classifier.py`) using ROLE_RULES from `local-dev/reasoning/role_inferrer.py` to populate `Ingredient_Canonical.Function` for all 250 rows.
- **Phase C**: Lift `ComplianceReasoner`, `RefusalEngine`, and `RoleInferrer` from `local-dev/reasoning/` into `reasoning/` as first-class project modules.
- **Phase D**: Create `orchestration/tools/compliance_reasoner_tool.py` — a DAG-compatible wrapper that runs the 4-state ComplianceReasoner + hard confidence floor check. Register it. Update `supplier_fallout.yaml` and `substitution_discovery.yaml` to use it.

## Feature Metadata

**Feature Type**: Enhancement  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `reasoning/`, `enrichment/enrichers/`, `orchestration/tools/`, `orchestration/api/agent_registry.py`, pipeline YAMLs  
**Dependencies**: `rapidfuzz` (already in requirements.txt), `sqlite3` (stdlib)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `reasoning/substitution_graph.py` (lines 29-86) — The `SubstitutionGraphBuilder` to enhance; `_canonical_id()` at line 82 is the exact method to fix
- `local-dev/reasoning/role_inferrer.py` (entire file, 222 lines) — **PRIMARY SOURCE**: `ROLE_RULES` dict and `MULTI_ROLE_MOLECULES` dict are the heuristic tables to copy into the role classifier. `covers_roles()` function is the partial-substitute detection logic.
- `local-dev/reasoning/compliance_reasoner.py` (entire file, ~582 lines) — **PRIMARY SOURCE**: `JURISDICTION_PACKS` (US-FDA, EU, CA, JP, US-USP), `ComplianceReasoner`, `ComplianceInput`, `_JurisdictionVerdict`, 4-state outcome logic
- `local-dev/reasoning/refusal_engine.py` (entire file, 144 lines) — **PRIMARY SOURCE**: `RefusalEngine`, `RefusalContext`, `CONFIDENCE_FLOOR = 0.50`
- `local-dev/reasoning/base.py` (entire file, 87 lines) — **PRIMARY SOURCE**: `ToolResult`, `Tool` ABC, `compound_confidence()` — the contract for all reasoning tools
- `local-dev/reasoning/gate_engine.py` (lines 86-125) — `_canonical()` method shows how curated-substitution fallback works for context only; NOT lifting full GateEngine in this plan
- `local-dev/Orchestration/qualify_candidate.py` (entire file, 223 lines) — Shows how all modules chain together; reference for how ComplianceInput is constructed from DB data
- `enrichment/enrichers/grade_classifier.py` (entire file, 99 lines) — **PATTERN TO MIRROR** for role_classifier.py: class structure, `__main__` runner, per-row UPDATE pattern
- `orchestration/tools/compliance_gate.py` (entire file, 84 lines) — **FILE TO DEPRECATE-IN-PLACE**: the old binary gate; understand its AgnesContext.get() pattern before replacing
- `orchestration/tools/substitution_walker.py` (entire file, 61 lines) — Reference for how tools read from enriched_db_path and return dicts; note it already uses `LOWER(Name) = LOWER(?)` 
- `orchestration/api/agent_registry.py` (entire file, 40 lines) — Add new tool entry here; lazy-import pattern is `"module.path:function_name"`
- `orchestration/api/agnes_context.py` (entire file, 29 lines) — `AgnesContext.get(node_id, default)` is how tools read upstream node outputs
- `orchestration/api/dag_executor.py` (lines 55-76) — Shows how tool functions are called: `fn = get_tool(node.tool_class); output = await run_in_executor(None, fn, ctx)` — tool functions must be synchronous and take `ctx: AgnesContext` only
- `orchestration/pipelines/supplier_fallout.yaml` — Pipeline to update: replace `ComplianceGateTool` with `ComplianceReasonerTool`; update condition guard
- `orchestration/pipelines/substitution_discovery.yaml` — Pipeline to update: add `ComplianceReasonerTool` node after `find-substitutes`
- `orchestration/api/conditions.py` (entire file) — Add `compliance_reasoner_feasible` condition to guard downstream nodes

### New Files to Create

- `reasoning/base.py` — Lifted from local-dev; `ToolResult`, `Tool` ABC, `compound_confidence()`
- `reasoning/role_inferrer.py` — Lifted from local-dev; `ROLE_RULES`, `MULTI_ROLE_MOLECULES`, `RoleInferrer`, `covers_roles()`
- `reasoning/compliance_reasoner.py` — Lifted from local-dev; `JURISDICTION_PACKS`, `ComplianceReasoner`, `ComplianceInput`
- `reasoning/refusal_engine.py` — Lifted from local-dev; `RefusalEngine`, `RefusalContext`, `CONFIDENCE_FLOOR`
- `enrichment/enrichers/role_classifier.py` — New heuristic classifier; writes to `Ingredient_Canonical.Function`
- `orchestration/tools/compliance_reasoner_tool.py` — DAG-compatible wrapper for ComplianceReasoner + RefusalEngine

### Files to Modify

- `reasoning/substitution_graph.py` — `_canonical_id()`: add rapidfuzz fuzzy fallback after exact match fails
- `orchestration/api/agent_registry.py` — Add `ComplianceReasonerTool` entry
- `orchestration/api/conditions.py` — Add `compliance_reasoner_feasible()` condition
- `orchestration/pipelines/supplier_fallout.yaml` — Replace `ComplianceGateTool` → `ComplianceReasonerTool`
- `orchestration/pipelines/substitution_discovery.yaml` — Add `ComplianceReasonerTool` node

### Patterns to Follow

**Tool function signature** (dag_executor calls these synchronously in thread pool):
```python
def run(ctx: AgnesContext) -> dict:
    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row
    ...
    conn.close()
    return {"key": value, ...}
```

**Reading upstream node output** (from `orchestration/tools/compliance_gate.py:17`):
```python
alternatives = ctx.get("find-alternatives", {}).get("alternatives", [])
canonical_id = ctx.get("find-alternatives", {}).get("canonical_id")
```

**Heuristic classifier pattern** (from `enrichment/enrichers/grade_classifier.py:66-98`):
```python
class RoleClassifier:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT Id, Name, SMILES FROM Ingredient_Canonical").fetchall()
        conn.close()
        for canonical_id, name, smiles in rows:
            role, _ = classify_role(name)
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE Ingredient_Canonical SET Function = ? WHERE Id = ?", (role, canonical_id))
            conn.commit()
            conn.close()
```

**Agent registry entry** (from `orchestration/api/agent_registry.py:11-18`):
```python
_TOOL_REGISTRY: dict[str, str] = {
    ...
    "ComplianceReasonerTool": "orchestration.tools.compliance_reasoner_tool:run",
}
```

**Condition guard pattern** (from `orchestration/api/conditions.py`):
```python
def compliance_reasoner_feasible(ctx: AgnesContext) -> bool:
    result = ctx.get("gate-compliance", {})
    return bool(result.get("qualified")) and result.get("above_floor", False)
```

**Fuzzy matching pattern** (rapidfuzz already in requirements.txt):
```python
from rapidfuzz import process, fuzz
match = process.extractOne(name.lower(), candidates_lower, scorer=fuzz.ratio, score_cutoff=85)
```

**Naming conventions**: snake_case files, snake_case functions, PascalCase classes, SCREAMING_SNAKE for constants

---

## IMPLEMENTATION PLAN

### Phase A: SubstitutionGraph Fuzzy Enhancement

Augment `_canonical_id()` to try rapidfuzz after exact match fails. This is a single method change — 10-15 lines. Re-run the builder to materialize new edges.

**Key design**: Fuzzy threshold of 85 catches "Zinc Oxide" → "zinc oxide" (if present in canonical), "Ergocalciferol" → "ergocalciferol", etc. Does NOT catch cases where the ingredient genuinely doesn't exist in the canonical table (Fish Oil, Krill Oil). Log misses at DEBUG level for future work.

### Phase B: Role Classifier — Populate Function Column

`Ingredient_Canonical.Function` is defined in schema (line 17 of `enriched_schema.sql`) as `TEXT -- "excipient:lubricant" | "nutrient:mineral" etc.` but all 250 rows are NULL. This field is what the local-dev `GateEngine._role()` uses.

**Key design**: Mirror `grade_classifier.py` exactly. Use ROLE_RULES from local-dev's `role_inferrer.py` as the primary keyword table. For multi-role molecules, write the primary role (e.g., `magnesium stearate` → `lubricant`). Write `"unknown"` for genuinely unclassifiable entries (not NULL), so role gate can distinguish "no data" from "not yet classified".

### Phase C: Lift Reasoning Modules

Copy `base.py`, `compliance_reasoner.py`, `refusal_engine.py`, `role_inferrer.py` from `local-dev/reasoning/` into `reasoning/`. Fix imports (`from .base import ...` → `from reasoning.base import ...` for non-relative use, or keep relative for the reasoning package). Add `reasoning/__init__.py` if it doesn't expose these.

**Key design**: Copy, don't symlink. local-dev is a development sandbox, not a Python package. Remove the `local-dev/Orchestration/` import paths; adjust to match project's `PYTHONPATH=.` convention. Do NOT modify the logic — the local-dev versions have been battle-tested.

### Phase D: ComplianceReasonerTool — DAG Integration

Create `orchestration/tools/compliance_reasoner_tool.py`. This tool:
1. Reads `canonical_id` from context (from `find-alternatives` or `find-substitutes` node)
2. Fetches ingredient name + Grade_Flag from `Ingredient_Canonical`
3. Maps Grade_Flag → use_class (`supplement` → `"supplement"`, `food` → `"food"`, `excipient` → `"supplement"` as fallback)
4. Builds `incumbent_precedents` from `Product_Compliance` (which jurisdictions have 'confirmed'/'claimed'/'implied' records for products using this ingredient)
5. Runs `ComplianceReasoner` across `["US-FDA", "EU", "CA", "JP"]`
6. Checks compound confidence against `CONFIDENCE_FLOOR = 0.50`
7. Returns structured dict including `outcome`, `per_jurisdiction`, `compound_confidence`, `above_floor`, `qualified` (list of per-jurisdiction-passing candidates)

Register in `agent_registry.py`. Add `compliance_reasoner_feasible` condition. Update `supplier_fallout.yaml` to use `ComplianceReasonerTool` instead of `ComplianceGateTool` (old tool stays as-is, just not used in this pipeline). Update `substitution_discovery.yaml` to insert a `gate-compliance` node after `find-substitutes`.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task top-to-bottom. Each task is atomic. Validate before moving to next.

---

### TASK A1 — UPDATE `reasoning/substitution_graph.py`

- **IMPLEMENT**: Replace `_canonical_id()` (lines 82-86) with a two-stage lookup:
  1. Exact match: `SELECT Id FROM Ingredient_Canonical WHERE LOWER(TRIM(Name)) = LOWER(TRIM(?))` (improved from bare COLLATE NOCASE to also strip whitespace)
  2. If None: load all canonical names into memory and run `rapidfuzz.process.extractOne(name.lower(), names_lower_map.keys(), scorer=fuzz.ratio, score_cutoff=85)`; return the matched canonical ID if found; log the fuzzy match at DEBUG level
- **PATTERN**: `substitution_walker.py:20` uses `LOWER(Name) = LOWER(?)` — same style
- **IMPORTS**: Add `from rapidfuzz import process, fuzz` at top of file
- **GOTCHA**: Load all canonical names once per `_apply_curated_rules` call, not once per rule — pass the names dict into `_canonical_id()` as an optional arg to avoid N+1 queries. Signature: `_canonical_id(self, conn, name, names_cache=None)`
- **GOTCHA**: Fuzzy match must be on lowercase normalized names to avoid false positives on "Zinc" matching "Zinc Gluconate"
- **VALIDATE**: `python3 -c "from reasoning.substitution_graph import SubstitutionGraphBuilder; print('import ok')"`

### TASK A2 — RE-RUN SubstitutionGraphBuilder

- **IMPLEMENT**: After the code change, re-run to materialize new edges
- **VALIDATE**: 
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
import logging; logging.basicConfig(level=logging.INFO)
from reasoning.substitution_graph import SubstitutionGraphBuilder
SubstitutionGraphBuilder().run()
"
```
Then verify edge count increased:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
print('Edges:', conn.execute('SELECT COUNT(*) FROM Ingredient_Substitution').fetchone()[0])
"
```
Expected: count increases above 30

---

### TASK B1 — CREATE `enrichment/enrichers/role_classifier.py`

- **IMPLEMENT**: Create file mirroring `grade_classifier.py` exactly in structure. Key elements:
  ```python
  """Heuristic role/function classifier — no API required.
  Populates Ingredient_Canonical.Function for all rows.
  Values: lubricant | mineral-fortificant | vitamin-fortificant | antioxidant |
          sweetener | high-intensity-sweetener | acidulant | preservative |
          emulsifier | thickener | stabilizer | colorant | functional-stimulant |
          functional-amino | functional-performance | protein-source | unknown
  """
  ```
- **PATTERN**: Mirror `grade_classifier.py:66-98` exactly — same class structure, same `__main__` runner, same per-row UPDATE pattern
- **SOURCE for ROLE_RULES**: Copy `ROLE_RULES` dict and `MULTI_ROLE_MOLECULES` dict verbatim from `local-dev/reasoning/role_inferrer.py` (lines 23-99). For multi-role molecules, write the primary role from ROLE_RULES as the Function value.
- **IMPLEMENT `classify_role(name: str) -> tuple[str, float]`**: 
  1. Normalize: `n = name.strip().lower()`
  2. Check ROLE_RULES exact lookup: return (role, 0.9) if found
  3. Check keyword fragments from MULTI_ROLE_MOLECULES keys
  4. Additional keyword passes (supplement pattern from grade_classifier for vitamins/minerals)
  5. Return ("unknown", 0.0) as final fallback — NOT None
- **GOTCHA**: `Ingredient_Canonical.Function` schema comment says `"excipient:lubricant" | "nutrient:mineral"` format. Do NOT use compound format — write simple single-role strings ("lubricant", "mineral-fortificant") for now. The `GateEngine._role()` normalizes to lowercase and compares directly.
- **VALIDATE**: 
```bash
python3 -m enrichment.enrichers.role_classifier
python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
print('Function NULL:', conn.execute(\"SELECT COUNT(*) FROM Ingredient_Canonical WHERE Function IS NULL\").fetchone()[0])
print('Function populated:', conn.execute(\"SELECT COUNT(*) FROM Ingredient_Canonical WHERE Function IS NOT NULL AND Function != 'unknown'\").fetchone()[0])
for row in conn.execute(\"SELECT Function, COUNT(*) FROM Ingredient_Canonical GROUP BY Function ORDER BY COUNT(*) DESC\").fetchall():
    print(' ', row)
"
```
Expected: Function NULL = 0, most rows have a non-unknown role

---

### TASK C1 — CREATE `reasoning/base.py`

- **IMPLEMENT**: Copy `local-dev/reasoning/base.py` verbatim (87 lines). Adjust the module docstring only — replace local-dev references with project references. No logic changes.
- **IMPORTS**: File is self-contained — only stdlib imports (abc, time, dataclasses, typing)
- **VALIDATE**: `python3 -c "from reasoning.base import ToolResult, Tool, compound_confidence; print('ok')"`

### TASK C2 — CREATE `reasoning/role_inferrer.py`

- **IMPLEMENT**: Copy `local-dev/reasoning/role_inferrer.py` verbatim (222 lines). Change only the import line: `from .base import Tool, ToolResult` → `from reasoning.base import Tool, ToolResult`
- **GOTCHA**: The `_self_test()` function at line 167 assumes `python -m reasoning.role_inferrer` style execution — keep it but verify the import path works from project root
- **VALIDATE**: `python3 -c "from reasoning.role_inferrer import RoleInferrer, covers_roles, ROLE_RULES; r = RoleInferrer(); print(r('magnesium stearate'))"`

### TASK C3 — CREATE `reasoning/compliance_reasoner.py`

- **IMPLEMENT**: Copy `local-dev/reasoning/compliance_reasoner.py` verbatim (~582 lines). Change only: `from .base import Tool, ToolResult, compound_confidence` → `from reasoning.base import Tool, ToolResult, compound_confidence`
- **GOTCHA**: `JURISDICTION_PACKS` has all 4 jurisdictions (US-FDA, EU, CA, JP) + US-USP with ~47 rules each — do NOT trim it; the full pack is needed for the compliance tool to return meaningful results for our top ingredients
- **VALIDATE**: 
```bash
python3 -c "
from reasoning.compliance_reasoner import ComplianceReasoner, ComplianceInput, JURISDICTION_PACKS
cr = ComplianceReasoner()
inp = ComplianceInput('ascorbic acid', 'supplement', ['US-FDA', 'EU'], {'US-FDA': True, 'EU': True})
result = cr(inp)
print(result.result['outcome'])  # expect 'pass-global'
inp2 = ComplianceInput('cyclamate', 'supplement', ['US-FDA'], {})
result2 = cr(inp2)
print(result2.result['outcome'])  # expect 'refuse'
"
```

### TASK C4 — CREATE `reasoning/refusal_engine.py`

- **IMPLEMENT**: Copy `local-dev/reasoning/refusal_engine.py` verbatim (144 lines). Change only: `from .base import Tool, ToolResult` → `from reasoning.base import Tool, ToolResult`. Remove the `_persist()` method's DB write logic — the DAG orchestration tool will handle persistence if needed; replace with a no-op that returns `None`. Keep `CONFIDENCE_FLOOR = 0.50` and all decision logic intact.
- **RATIONALE for removing _persist**: The DAG runs tools in a thread pool with shared context; DB writes from within the lifted module create transaction conflicts. The DAG's node_outputs already provide audit capability. If persistence is needed later, add it back in the wrapper tool (Phase D).
- **VALIDATE**: 
```bash
python3 -c "
from reasoning.refusal_engine import RefusalEngine, RefusalContext, CONFIDENCE_FLOOR
print('floor:', CONFIDENCE_FLOOR)
re = RefusalEngine()
ctx = RefusalContext(0, None, {'passed': True}, 0.9, {'outcome': 'pass-global'}, 0.9, [])
result = re(ctx)
print(result.result['decision'])  # expect 'recommend'
"
```

---

### TASK D1 — CREATE `orchestration/tools/compliance_reasoner_tool.py`

- **IMPLEMENT**: New DAG tool. Full logic:

```python
"""
4-state compliance reasoner tool for Agnes DAG.
Reads canonical_id from upstream node output (find-alternatives OR find-substitutes).
Builds ComplianceInput from DB, runs ComplianceReasoner, applies CONFIDENCE_FLOOR.
Returns structured dict for downstream nodes and condition guards.
"""
import sqlite3
from orchestration.api.agnes_context import AgnesContext
from reasoning.compliance_reasoner import ComplianceReasoner, ComplianceInput, JURISDICTION_PACKS
from reasoning.refusal_engine import RefusalEngine, RefusalContext, CONFIDENCE_FLOOR

_DEFAULT_JURISDICTIONS = ["US-FDA", "EU", "CA", "JP"]

_GRADE_TO_USE_CLASS = {
    "supplement": "supplement",
    "food": "food",
    "excipient": "supplement",   # excipients are used in supplement products
    "sweetener": "food",
    "flavor": "food",
    "unknown": "supplement",     # pessimistic default
}


def run(ctx: AgnesContext) -> dict:
    # 1. Resolve canonical_id from upstream nodes
    canonical_id = (
        ctx.get("find-alternatives", {}).get("canonical_id")
        or ctx.get("find-substitutes", {}).get("canonical_id")
    )
    if not canonical_id:
        return {"qualified": [], "outcome": "no_canonical_id", "above_floor": False}

    conn = sqlite3.connect(str(ctx.enriched_db_path))
    conn.row_factory = sqlite3.Row

    # 2. Fetch ingredient metadata
    ic_row = conn.execute(
        "SELECT Name, Grade_Flag, Function FROM Ingredient_Canonical WHERE Id = ?",
        (canonical_id,),
    ).fetchone()
    if not ic_row:
        conn.close()
        return {"qualified": [], "outcome": "canonical_not_found", "above_floor": False}

    ingredient_name = ic_row["Name"]
    grade_flag = (ic_row["Grade_Flag"] or "unknown").lower()
    use_class = _GRADE_TO_USE_CLASS.get(grade_flag, "supplement")

    # 3. Build incumbent_precedents: which jurisdictions have compliance evidence
    #    for products using this ingredient?
    compliance_rows = conn.execute(
        """
        SELECT DISTINCT pc.Certification
        FROM Product_Compliance pc
        JOIN SKU_To_Canonical stc ON stc.ProductId = pc.ProductId
        WHERE stc.CanonicalId = ?
          AND pc.Status IN ('confirmed', 'claimed', 'implied')
        """,
        (canonical_id,),
    ).fetchall()
    conn.close()

    # Infer incumbent_precedents from cert coverage
    # NSF/USP certs are primarily US, EU/EFSA not in our cert data → mark as unknown
    has_certs = len(compliance_rows) > 0
    incumbent_precedents = {
        "US-FDA": has_certs,    # certs present → incumbent passes US-FDA
        "EU": None,             # unknown — insufficient EU-specific cert data
        "CA": None,             # unknown
        "JP": None,             # unknown
    }

    # 4. Run compliance reasoner
    cr = ComplianceReasoner()
    inp = ComplianceInput(
        candidate_name=ingredient_name,
        use_class=use_class,
        jurisdictions=_DEFAULT_JURISDICTIONS,
        incumbent_precedents=incumbent_precedents,
    )
    comp_result = cr(inp)

    # 5. Check confidence floor
    comp_confidence = comp_result.confidence or 0.0
    above_floor = comp_confidence >= CONFIDENCE_FLOOR
    outcome = (comp_result.result or {}).get("outcome", "unknown")

    # 6. Determine qualified flag (for condition guards)
    # "refuse" means not viable; others are viable with caveats
    viable = outcome != "refuse" and above_floor

    return {
        "outcome": outcome,
        "compound_confidence": comp_confidence,
        "above_floor": above_floor,
        "qualified": viable,
        "ingredient_name": ingredient_name,
        "use_class": use_class,
        "per_jurisdiction": (comp_result.result or {}).get("per_jurisdiction", []),
        "reason": (comp_result.result or {}).get("reason", ""),
        "refusal": comp_result.refusal,
        "canonical_id": canonical_id,
    }
```

- **PATTERN**: `compliance_gate.py:15-83` — AgnesContext usage, conn open/close pattern
- **GOTCHA**: The function signature must be `def run(ctx: AgnesContext) -> dict` — no other parameters; the DAG executor calls `fn(ctx)` only
- **GOTCHA**: `conn.row_factory = sqlite3.Row` must be set before any `fetchone()` so column access by name works
- **VALIDATE**: `python3 -c "from orchestration.tools.compliance_reasoner_tool import run; print('import ok')"`

### TASK D2 — UPDATE `orchestration/api/agent_registry.py`

- **ADD**: One entry to `_TOOL_REGISTRY`:
  ```python
  "ComplianceReasonerTool": "orchestration.tools.compliance_reasoner_tool:run",
  ```
- **VALIDATE**: `python3 -c "from orchestration.api.agent_registry import get_tool; fn = get_tool('ComplianceReasonerTool'); print('registry ok', fn)"`

### TASK D3 — UPDATE `orchestration/api/conditions.py`

- **ADD**: New condition function:
  ```python
  def compliance_reasoner_feasible(ctx) -> bool:
      """True when ComplianceReasonerTool returned a viable (non-refused, above-floor) result."""
      result = ctx.get("gate-compliance", {})
      return bool(result.get("qualified")) and bool(result.get("above_floor"))
  ```
- **ADD**: Register in the `_CONDITIONS` dispatch dict at the bottom of the file (or wherever the existing conditions are registered — check the file's dispatch pattern)
- **VALIDATE**: `python3 -c "from orchestration.api.conditions import evaluate; print('conditions ok')"`

### TASK D4 — UPDATE `orchestration/pipelines/supplier_fallout.yaml`

- **UPDATE**: Replace the `gate-qualify` node from `ComplianceGateTool` to `ComplianceReasonerTool`. Rename node id from `gate-qualify` to `gate-compliance` (clearer naming). Update downstream `depends_on` references. Update condition guard from `compliance_feasible` to `compliance_reasoner_feasible`.

New YAML:
```yaml
name: supplier_fallout
trigger: chat
# US-01: A supplier can no longer deliver. Find ranked alternatives, gate on compliance,
# assess BOM impact, draft RFQs, and produce a reactive narrative.
nodes:
  - id: find-alternatives
    tool_class: SupplierAlternativesTool
    depends_on: []

  - id: gate-compliance
    tool_class: ComplianceReasonerTool
    depends_on: [find-alternatives]
    when: has_alternatives

  - id: bom-impact
    tool_class: BomImpactTool
    depends_on: [find-alternatives]

  - id: format-rfqs
    tool_class: RfqFormatterTool
    depends_on: [gate-compliance, bom-impact]
    when: compliance_reasoner_feasible

  - id: write-proposal
    agent_class: ReactiveAgent
    depends_on: [format-rfqs, bom-impact]
```

- **GOTCHA**: The `RfqFormatterTool` reads from `gate-qualify` node output — check `rfq_formatter.py` and update the node_id reference if it's hardcoded
- **VALIDATE**: `python3 -c "from orchestration.api.pipeline_loader import load; p = load('supplier_fallout'); print('nodes:', [n.id for n in p.nodes])"`

### TASK D5 — UPDATE `orchestration/pipelines/substitution_discovery.yaml`

- **ADD**: Insert `gate-compliance` node after `find-substitutes`, before `find-alternatives`:
```yaml
name: substitution_discovery
trigger: chat
nodes:
  - id: find-substitutes
    tool_class: SubstitutionWalkerTool
    depends_on: []

  - id: gate-compliance
    tool_class: ComplianceReasonerTool
    depends_on: [find-substitutes]
    when: has_substitutes

  - id: find-alternatives
    tool_class: SupplierAlternativesTool
    depends_on: [find-substitutes]
    when: has_substitutes

  - id: bom-impact
    tool_class: BomImpactTool
    depends_on: [find-substitutes]

  - id: benchmark-prices
    tool_class: PriceBenchmarkTool
    depends_on: [find-substitutes]
    when: has_substitutes

  - id: write-proposal
    agent_class: ProposalWriter
    depends_on: [gate-compliance, find-alternatives, bom-impact, benchmark-prices]
    when: has_substitutes
```

- **VALIDATE**: `python3 -c "from orchestration.api.pipeline_loader import load; p = load('substitution_discovery'); print('nodes:', [n.id for n in p.nodes])"`

### TASK D6 — CHECK `orchestration/tools/rfq_formatter.py`

- **READ**: Open `rfq_formatter.py` and check if it references `"gate-qualify"` as a node ID anywhere (likely it reads from `gate-qualify` or `compliance_gate` output)
- **UPDATE**: If it hardcodes `"gate-qualify"`, change to `"gate-compliance"`
- **VALIDATE**: `python3 -c "from orchestration.tools.rfq_formatter import run; print('import ok')"`

---

## TESTING STRATEGY

### Unit Tests

No test framework is currently configured in the project (no `tests/` directory, no pytest config). Write quick self-tests as `if __name__ == "__main__"` blocks following the pattern in `local-dev/reasoning/role_inferrer.py:167-220`.

Key test scenarios for each module:

**ComplianceReasoner** (test via Task C3 validate command):
- `ascorbic acid` + US-FDA/EU → `pass-global`
- `cyclamate` + US-FDA → `refuse`
- `calcium stearate` + JP → check if fork-recommended when JP has different scope
- Unknown ingredient → `human-review` (baseline_missing_rule)

**RoleClassifier**:
- `magnesium stearate` → `lubricant`
- `vitamin c` → `antioxidant` or `vitamin-fortificant`
- `sucralose` → `high-intensity-sweetener`
- Unknown ingredient → `unknown`

**ComplianceReasonerTool** (integration test after server start):
```bash
curl -s -X POST http://localhost:8000/pipelines/run/supplier_fallout \
  -H "Content-Type: application/json" \
  -d '{"ingredient_name": "Vitamin C"}' | python3 -m json.tool
```

### Integration Tests

After all tasks complete, trigger the full pipeline to verify no regressions:
```bash
# Start server
PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000 &
sleep 3

# Test substitution_discovery pipeline
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find substitutes for Vitamin C"}' | python3 -m json.tool

# Check run status
curl -s http://localhost:8000/runs | python3 -m json.tool
```

### Edge Cases

- `canonical_id` is None (upstream node returned empty) → tool returns `{"qualified": [], "outcome": "no_canonical_id", "above_floor": False}` without crashing
- Ingredient name not in any JURISDICTION_PACK → `outcome: "human-review"` (pessimistic default, baseline_missing_rule)
- `incumbent_precedents` all None (no compliance rows for ingredient) → `outcome: "human-review"` (implicit_ambiguous)
- `compound_confidence < 0.50` with passing gates → `above_floor: False`, `qualified: False`

---

## VALIDATION COMMANDS

### Level 1: Import checks (run after each Phase)
```bash
PYTHONPATH=. python3 -c "from reasoning.base import ToolResult, compound_confidence; print('base ok')"
PYTHONPATH=. python3 -c "from reasoning.role_inferrer import RoleInferrer, covers_roles; print('role_inferrer ok')"
PYTHONPATH=. python3 -c "from reasoning.compliance_reasoner import ComplianceReasoner; print('compliance_reasoner ok')"
PYTHONPATH=. python3 -c "from reasoning.refusal_engine import RefusalEngine, CONFIDENCE_FLOOR; print('refusal_engine ok, floor=', CONFIDENCE_FLOOR)"
PYTHONPATH=. python3 -c "from enrichment.enrichers.role_classifier import RoleClassifier; print('role_classifier ok')"
PYTHONPATH=. python3 -c "from orchestration.tools.compliance_reasoner_tool import run; print('tool ok')"
```

### Level 2: Functional checks
```bash
# SubstitutionGraphBuilder
PYTHONPATH=. python3 -c "
from reasoning.substitution_graph import SubstitutionGraphBuilder
import sqlite3
before = sqlite3.connect('db_enriched.sqlite').execute('SELECT COUNT(*) FROM Ingredient_Substitution').fetchone()[0]
print('Edges before re-run:', before)
"

# Role classifier results
PYTHONPATH=. python3 -c "
import sqlite3
conn = sqlite3.connect('db_enriched.sqlite')
total = conn.execute('SELECT COUNT(*) FROM Ingredient_Canonical').fetchone()[0]
populated = conn.execute(\"SELECT COUNT(*) FROM Ingredient_Canonical WHERE Function IS NOT NULL\").fetchone()[0]
print(f'Function populated: {populated}/{total}')
for row in conn.execute(\"SELECT Function, COUNT(*) c FROM Ingredient_Canonical GROUP BY Function ORDER BY c DESC\").fetchall():
    print(f'  {row[0]}: {row[1]}')
"

# Compliance reasoner - Vitamin C should pass-global
PYTHONPATH=. python3 -c "
from reasoning.compliance_reasoner import ComplianceReasoner, ComplianceInput
cr = ComplianceReasoner()
inp = ComplianceInput('ascorbic acid', 'supplement', ['US-FDA', 'EU', 'CA', 'JP'], {'US-FDA': True, 'EU': True, 'CA': True, 'JP': True})
r = cr(inp)
print('Vitamin C outcome:', r.result['outcome'])
assert r.result['outcome'] == 'pass-global', f'Expected pass-global, got {r.result[\"outcome\"]}'
print('PASS')
"

# Registry and pipeline loading
PYTHONPATH=. python3 -c "
from orchestration.api.agent_registry import get_tool
fn = get_tool('ComplianceReasonerTool')
print('Tool registered:', fn)
from orchestration.api.pipeline_loader import load
p = load('supplier_fallout')
ids = [n.id for n in p.nodes]
assert 'gate-compliance' in ids, f'gate-compliance not in pipeline: {ids}'
print('Pipeline nodes:', ids)
print('PASS')
"
```

### Level 3: Live pipeline test
```bash
# Start server (ensure PYTHONPATH=. and ANTHROPIC_API_KEY is set)
PYTHONPATH=. uvicorn orchestration.api.main:app --port 8000 &
sleep 3

# Health check
curl -s http://localhost:8000/health

# Trigger supplier_fallout pipeline
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Supplier for Vitamin C went out of business, find alternatives"}' | python3 -m json.tool

# Check last run
curl -s 'http://localhost:8000/runs?limit=1' | python3 -m json.tool
```

### Level 4: Regression check — verify existing pipelines still load
```bash
PYTHONPATH=. python3 -c "
from orchestration.api.pipeline_loader import load
for name in ['supplier_fallout', 'substitution_discovery', 'proactive_consolidation', 'new_ingredient_research', 'price_audit']:
    p = load(name)
    print(f'{name}: {len(p.nodes)} nodes OK')
"
```

---

## ACCEPTANCE CRITERIA

- [ ] `Ingredient_Substitution` edge count exceeds 30 after SubstitutionGraphBuilder re-run
- [ ] `Ingredient_Canonical.Function` has 0 NULL rows (all rows have a value, "unknown" is acceptable)
- [ ] `reasoning/base.py`, `reasoning/compliance_reasoner.py`, `reasoning/refusal_engine.py`, `reasoning/role_inferrer.py` all importable from project root with `PYTHONPATH=.`
- [ ] `ComplianceReasoner()` returns `outcome="pass-global"` for `ascorbic acid` in US-FDA/EU/CA/JP
- [ ] `ComplianceReasoner()` returns `outcome="refuse"` for `cyclamate` in any jurisdiction
- [ ] `ComplianceReasonerTool` registered in `agent_registry.py` and importable
- [ ] `supplier_fallout` and `substitution_discovery` pipelines load without error
- [ ] `gate-compliance` node present in both pipeline YAML definitions
- [ ] `compliance_reasoner_feasible` condition registered and evaluable
- [ ] All 5 pipelines still load without regression
- [ ] Live API `/chat` POST triggers a pipeline run and the run completes or fails gracefully (not with ImportError)

---

## COMPLETION CHECKLIST

- [ ] Task A1: `_canonical_id()` updated with fuzzy fallback
- [ ] Task A2: SubstitutionGraphBuilder re-run, edge count verified
- [ ] Task B1: `role_classifier.py` created and run; Function column populated
- [ ] Task C1: `reasoning/base.py` created
- [ ] Task C2: `reasoning/role_inferrer.py` created
- [ ] Task C3: `reasoning/compliance_reasoner.py` created with all 4 JURISDICTION_PACKS
- [ ] Task C4: `reasoning/refusal_engine.py` created (without DB writes)
- [ ] Task D1: `compliance_reasoner_tool.py` created
- [ ] Task D2: `agent_registry.py` updated
- [ ] Task D3: `conditions.py` updated with new condition
- [ ] Task D4: `supplier_fallout.yaml` updated
- [ ] Task D5: `substitution_discovery.yaml` updated
- [ ] Task D6: `rfq_formatter.py` checked and updated if needed
- [ ] All Level 1–4 validation commands pass

---

## NOTES

### Why not lift the full GateEngine?

The GateEngine's form gate (Gate 3) and morphology gate (Gate 5) both rely on data columns (`form`, `psd_bucket`, `surface_area_m2g`, `bulk_density_gml`) that don't exist in the current `Ingredient_Canonical` schema and have no data. Running them would always produce `GateOutcome(False, 0.4, "form_missing")` and `GateOutcome(True, 0.90, "morphology_unknown_accepted")`, adding latency with ~0 signal. The ComplianceReasonerTool provides the highest signal gain per line of new code.

### Why keep `ComplianceGateTool`?

It's not removed — only removed from the two pipelines updated here. `price_audit.yaml`, `proactive_consolidation.yaml`, and `new_ingredient_research.yaml` are not modified. Old tool stays importable and registered. No regressions.

### Supplier_Commercial still empty

The `ComplianceReasonerTool` doesn't read `Supplier_Commercial` at all — it reads only `Ingredient_Canonical`, `SKU_To_Canonical`, and `Product_Compliance`. These are all well-populated. So this feature is completely unblocked by the Molport API gap.

### CONFIDENCE_FLOOR value

`CONFIDENCE_FLOOR = 0.50` in `refusal_engine.py`. The comment in local-dev explains: "0.50, not 0.60 — we multiply 6 gate factors × 2 compliance factors, and the 'unknown but accepted' gates pass around 0.88-0.90. 0.60 was too tight when morphology / role-inference enrichment hasn't populated yet." After role backfill (Task B1), the role gate will be more confident — the floor can be raised to 0.60 in a future iteration.

### `incumbent_precedents` simplification

The full local-dev design derives `incumbent_precedents` per jurisdiction from actual supplier approval data. With `Supplier_Commercial` empty, we approximate: if `Product_Compliance` rows exist for this ingredient's products, we mark `US-FDA: True` (all our compliance rows use US-centric certifications). EU/CA/JP are `None` (unknown). This causes many candidates to return `human-review` rather than `pass-global`, which is the honest outcome given our data sparsity. Once commercial data is populated, `incumbent_precedents` should be built from per-supplier approval records.

### Local-dev file locations for reference

All source files being lifted:
- `local-dev/reasoning/base.py` — 87 lines
- `local-dev/reasoning/role_inferrer.py` — 222 lines  
- `local-dev/reasoning/compliance_reasoner.py` — ~582 lines
- `local-dev/reasoning/refusal_engine.py` — 144 lines
- `local-dev/Orchestration/qualify_candidate.py` — 223 lines (reference only, not lifted)
- `local-dev/Orchestration/sims/` — anchor_case.py, magnesium_stearate_case.py (reference test scenarios)
