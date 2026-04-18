# REF-YAML-PIPELINE-SCHEMA — YAML Pipeline Definition System

**Version:** 1.0  
**Date:** 2026-04-15  
**Scope:** PRD 6 Phase 2 — Declarative Pipelines  
**Depends on:** `api/pipeline_def.py`, `api/dag_executor.py`, `api/main.py`  
**Status:** Authoritative — Implementation-ready

> **Pre-reading required:** Read `api/pipeline_def.py` (dataclasses + 7 pipelines) and `api/dag_executor.py` (`build_topological_layers`, `execute_node`, `execute_pipeline`) before implementing. This guide assumes familiarity with both files.

---

## Table of Contents

1. [Overview and Design Goals](#1-overview-and-design-goals)
2. [YAML Schema Specification](#2-yaml-schema-specification)
3. [Named Condition Registry](#3-named-condition-registry)
4. [Pydantic v2 Validation Schema](#4-pydantic-v2-validation-schema)
5. [Pipeline Loader — `api/pipeline_loader.py`](#5-pipeline-loader--apipipeline_loaderpy)
6. [Startup Registration — `api/main.py` modification](#6-startup-registration--apimainpy-modification)
7. [Complete YAML Examples — All 7 Existing Pipelines](#7-complete-yaml-examples--all-7-existing-pipelines)
8. [Bonus: `knowledge_scan.yaml`](#8-bonus-knowledge_scanyaml)
9. [Validation Error Messages](#9-validation-error-messages)
10. [Testing the Loader](#10-testing-the-loader)
11. [Security Notes — PyYAML `safe_load`](#11-security-notes--pyyaml-safe_load)
12. [Implementation Checklist](#12-implementation-checklist)

---

## 1. Overview and Design Goals

### Problem

All 7 pipelines are currently defined as Python dataclasses in `api/pipeline_def.py`. Adding a new pipeline requires editing Python, redeploying, and knowing the internal dataclass API. This blocks non-Python developers from extending the system.

### Solution

A YAML pipeline definition layer that:
1. Maps directly to the existing `PipelineNode` and `ApprovalNode` dataclasses — no executor changes required.
2. Is loaded at startup from a `pipelines/` directory, registered into the existing `PIPELINE_REGISTRY`.
3. Validates at load time (not at runtime) via Pydantic v2 — fails fast with clear error messages.
4. Coexists safely with Python-defined pipelines. Python pipelines win on name conflict.

### What does NOT change

- `api/dag_executor.py` — no modifications. The loader produces `Pipeline` objects the executor already understands.
- `api/pipeline_def.py` — Python pipelines remain and retain priority.
- The `_get_agent()` resolver in `dag_executor.py` — agent class names in YAML must match names already known to this function.

### Directory convention

```
pipelines/
  inbound_responder.yaml
  cold_outreach.yaml
  knowledge_curation.yaml
  OpportunityScanPipeline.yaml
  SellerUpdatePipeline.yaml
  AutodreamPipeline.yaml
  new_lead_onboarding.yaml
  knowledge_scan.yaml          # bonus — new PRD 6 pipeline
```

Filename stem is advisory only. The authoritative pipeline name is the `name:` field inside the file. The loader uses `name:` as the registry key.

---

## 2. YAML Schema Specification

### Top-level structure

```yaml
# pipelines/{name}.yaml

name: string          # REQUIRED — kebab-case or PascalCase, unique, used as registry key
description: string   # OPTIONAL — human-readable; ignored by executor

nodes:
  - id: string                # REQUIRED — kebab-case, unique within this pipeline
    agent_class: string       # REQUIRED for agent nodes — must match a key in _AGENT_REGISTRY
    type: string              # OPTIONAL — set to "approval" to create ApprovalNode instead
    depends_on: [string]      # OPTIONAL — list of node ids this node waits for; default []
    when: string              # OPTIONAL — named condition from CONDITION_REGISTRY; default: no condition
    capture_response: bool    # OPTIONAL — only valid when type: approval; default true
```

### Field-by-field reference

| Field | Level | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `name` | top | string | YES | — | Registry key. Kebab-case recommended but PascalCase accepted for existing pipelines. |
| `description` | top | string | NO | null | Documentation only; not passed to executor. |
| `nodes` | top | list | YES | — | Must have at least one node. |
| `id` | node | string | YES | — | Unique within the pipeline. Kebab-case enforced by validator. Used as `node.id` in `PipelineNode`. |
| `agent_class` | node | string | YES* | — | *Required unless `type: approval`. Must match a key in `_AGENT_REGISTRY` (see §3). |
| `type` | node | string | NO | null | Only valid value is `"approval"`. Creates `ApprovalNode` instead of `PipelineNode`. |
| `depends_on` | node | list[string] | NO | `[]` | Each string must be the `id` of another node in this pipeline. Self-references are invalid. |
| `when` | node | string | NO | null | Must be a key in `CONDITION_REGISTRY` (see §3). Resolved to callable at load time. |
| `capture_response` | node | bool | NO | `true` | Only meaningful when `type: approval`; silently ignored on agent nodes. |

### Mutual exclusivity rules

1. If `type: approval` is set, `agent_class` must be absent (or null).
2. If `agent_class` is set, `type` must be absent (or null).
3. A node must have exactly one of: `agent_class` or `type: approval`.

### `name:` field vs. filename

The `name:` field inside the YAML is the registry key used by `PIPELINE_REGISTRY` and `execute_pipeline()`. The filename is used only for discovery. Mismatches produce a warning in the loader log but are not errors.

Recommendation: keep them consistent. `cold_outreach.yaml` → `name: cold_outreach`.

### Existing pipelines with PascalCase names

Three existing pipelines use PascalCase names (`OpportunityScanPipeline`, `SellerUpdatePipeline`, `AutodreamPipeline`). The YAML `name:` field must match these exactly for the Python pipelines to override them correctly via the coexistence rule. Do not rename them in YAML.

---

## 3. Named Condition Registry

### Python addition to `api/pipeline_def.py`

Add this block after the existing `when:` helper functions and before `INBOUND_PIPELINE`:

```python
# ---------------------------------------------------------------------------
# Named condition registry — resolves YAML `when:` strings to callables
# ---------------------------------------------------------------------------

from typing import Callable

CONDITION_REGISTRY: dict[str, Callable[[dict], bool]] = {
    "requires_approval":   _requires_approval,
    "check_strategy_memo": _check_strategy_memo,
    "autodream_enabled":   _autodream_enabled,
    "score_above_threshold": _score_above_threshold,
    "always":              lambda ctx: True,
    "never":               lambda ctx: False,
}
```

### Condition reference table

| YAML `when:` name | Python callable | Returns True when... | Context fields read |
|---|---|---|---|
| `requires_approval` | `_requires_approval(ctx)` | `AUTO_SEND_ENABLED=false` OR profile.md has `require_approval: true` OR profile unreadable | `ctx["lead_path"]`, env `AUTO_SEND_ENABLED`, env `WIKI_ROOT` |
| `check_strategy_memo` | `_check_strategy_memo(ctx)` | strategy-memo.md does NOT say `recommended_action: wait` (default true = run the node) | `ctx["lead_path"]`, env `WIKI_ROOT` |
| `autodream_enabled` | `_autodream_enabled(ctx)` | env `AUTODREAM_ENABLED` is not `"false"` (default: true) | env `AUTODREAM_ENABLED` |
| `score_above_threshold` | `_score_above_threshold(ctx)` | `ctx["opportunity_score"]` >= `AUTODREAM_SCORE_THRESHOLD` (default 60) | `ctx["opportunity_score"]`, env `AUTODREAM_SCORE_THRESHOLD` |
| `always` | `lambda ctx: True` | Always — unconditional execution | none |
| `never` | `lambda ctx: False` | Never — node always skipped; useful during development | none |

### When-condition semantics

A condition returning `False` causes the node to be **skipped** (writes a `node_skipped` event with `reason: when_condition_false`). The pipeline continues to the next layer — it does not abort. This is identical behavior to the existing Python-defined `when=` callables.

A condition returning `True` means the node proceeds normally.

A missing `when:` field (null) means no condition check — the node always runs.

### Agent class registry

The `_AGENT_REGISTRY` is not a named dict in the current code; it is encoded as the `if/elif` chain in `dag_executor.py:_get_agent()`. The known valid `agent_class` values as of this writing are:

```
WikiReadinessAgent
StrategyAgent
ResponseAgent
SenderAgent
KnowledgeCurationAgent
ColdOutreachAgent
OpportunityAgent
AutodreamAgent
LeadDiscoveryAgent
LeadClassificationAgent
ResearchAgent
```

The loader must validate `agent_class` values against this set. If a new agent is added to `_get_agent()`, it must also be added to the validation set in `api/pipeline_loader.py`.

**Maintenance note:** The canonical source of truth for valid agent class names is the `_get_agent()` function in `api/dag_executor.py`. Keep `_AGENT_CLASS_REGISTRY` in the loader in sync with that function.

---

## 4. Pydantic v2 Validation Schema

### Module: `api/pipeline_loader.py` (validation models section)

```python
import re
from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Pydantic v2 models for YAML validation
# ---------------------------------------------------------------------------

_KEBAB_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


class YamlNodeDef(BaseModel):
    id: str
    agent_class: str | None = None
    type: str | None = None        # "approval" or None
    depends_on: list[str] = []
    when: str | None = None
    capture_response: bool = True

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(
                f"Node id {v!r} must be kebab-case (lowercase letters, digits, hyphens only). "
                f"Example: 'wiki-readiness', 'strategy', 'draft-approval'."
            )
        return v

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v != "approval":
            raise ValueError(
                f"Node type {v!r} is not valid. Only 'approval' is supported. "
                f"To define an agent node, omit 'type' and set 'agent_class' instead."
            )
        return v

    @model_validator(mode='after')
    def validate_node_type_exclusivity(self) -> 'YamlNodeDef':
        is_approval = self.type == "approval"
        has_agent = bool(self.agent_class)
        if is_approval and has_agent:
            raise ValueError(
                f"Node {self.id!r}: cannot set both 'type: approval' and 'agent_class'. "
                f"Approval nodes do not run an agent."
            )
        if not is_approval and not has_agent:
            raise ValueError(
                f"Node {self.id!r}: must have either 'agent_class' (for agent nodes) "
                f"or 'type: approval' (for approval gates). Got neither."
            )
        return self


class YamlPipelineDef(BaseModel):
    name: str
    description: str | None = None
    nodes: list[YamlNodeDef]

    @field_validator('nodes')
    @classmethod
    def validate_non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Pipeline must have at least one node.")
        return v

    @model_validator(mode='after')
    def validate_pipeline_structure(self) -> 'YamlPipelineDef':
        # 1. Unique node ids
        ids = [n.id for n in self.nodes]
        seen = set()
        for nid in ids:
            if nid in seen:
                raise ValueError(
                    f"Pipeline {self.name!r}: duplicate node id {nid!r}. "
                    f"All node ids must be unique within a pipeline."
                )
            seen.add(nid)

        # 2. No self-references in depends_on
        for node in self.nodes:
            for dep in node.depends_on:
                if dep == node.id:
                    raise ValueError(
                        f"Pipeline {self.name!r}: node {node.id!r} lists itself in "
                        f"'depends_on'. Self-references are not allowed."
                    )

        # 3. No dangling depends_on references
        id_set = set(ids)
        for node in self.nodes:
            for dep in node.depends_on:
                if dep not in id_set:
                    raise ValueError(
                        f"Pipeline {self.name!r}: node {node.id!r} depends_on {dep!r}, "
                        f"but no node with that id exists in this pipeline. "
                        f"Known node ids: {sorted(id_set)}"
                    )

        return self
```

### Why Pydantic v2 `model_validate()` instead of v1 `parse_obj()`

Pydantic v2 (shipped with FastAPI ≥ 0.100) uses `Model.model_validate(dict)` not `Model.parse_obj(dict)`. Both `field_validator` and `model_validator` are v2 API. The `mode='after'` parameter on `model_validator` means the validator runs after all individual fields have been validated and coerced — this is required here because we need to access `self.id`, `self.type`, and `self.agent_class` simultaneously.

---

## 5. Pipeline Loader — `api/pipeline_loader.py`

### Complete implementation

```python
"""
YAML pipeline loader for HappyRobot.

Discovers, parses, validates, and converts all *.yaml files in a pipelines/ directory
into Pipeline dataclass objects compatible with dag_executor.py.

Usage (called from api/main.py lifespan):
    from api.pipeline_loader import load_yaml_pipelines
    yaml_pipelines = load_yaml_pipelines(Path(__file__).parent.parent / "pipelines")
    PIPELINE_REGISTRY.update(yaml_pipelines)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from api.pipeline_def import (
    ApprovalNode,
    CONDITION_REGISTRY,
    Pipeline,
    PipelineNode,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent class registry — must stay in sync with dag_executor.py:_get_agent()
# ---------------------------------------------------------------------------

_AGENT_CLASS_REGISTRY: frozenset[str] = frozenset({
    "WikiReadinessAgent",
    "StrategyAgent",
    "ResponseAgent",
    "SenderAgent",
    "KnowledgeCurationAgent",
    "ColdOutreachAgent",
    "OpportunityAgent",
    "AutodreamAgent",
    "LeadDiscoveryAgent",
    "LeadClassificationAgent",
    "ResearchAgent",
    "WikiLintAgent",           # PRD 6 Phase 2
})

# ---------------------------------------------------------------------------
# Pydantic v2 validation models
# ---------------------------------------------------------------------------

_KEBAB_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


class YamlNodeDef(BaseModel):
    id: str
    agent_class: str | None = None
    type: str | None = None
    depends_on: list[str] = []
    when: str | None = None
    capture_response: bool = True

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(
                f"Node id {v!r} must be kebab-case. "
                f"Example: 'wiki-readiness', 'draft-approval'."
            )
        return v

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None and v != "approval":
            raise ValueError(
                f"Node type {v!r} is invalid. Only 'approval' is supported."
            )
        return v

    @model_validator(mode='after')
    def validate_node_type_exclusivity(self) -> 'YamlNodeDef':
        is_approval = self.type == "approval"
        has_agent = bool(self.agent_class)
        if is_approval and has_agent:
            raise ValueError(
                f"Node {self.id!r}: cannot set both 'type: approval' and 'agent_class'."
            )
        if not is_approval and not has_agent:
            raise ValueError(
                f"Node {self.id!r}: must have either 'agent_class' or 'type: approval'."
            )
        return self


class YamlPipelineDef(BaseModel):
    name: str
    description: str | None = None
    nodes: list[YamlNodeDef]

    @field_validator('nodes')
    @classmethod
    def validate_non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Pipeline must have at least one node.")
        return v

    @model_validator(mode='after')
    def validate_pipeline_structure(self) -> 'YamlPipelineDef':
        ids = [n.id for n in self.nodes]
        seen: set[str] = set()
        for nid in ids:
            if nid in seen:
                raise ValueError(f"Duplicate node id {nid!r}.")
            seen.add(nid)
        for node in self.nodes:
            if node.id in node.depends_on:
                raise ValueError(
                    f"Node {node.id!r} lists itself in 'depends_on'."
                )
            for dep in node.depends_on:
                if dep not in seen:
                    raise ValueError(
                        f"Node {node.id!r} depends_on {dep!r} which does not exist. "
                        f"Known ids: {sorted(seen)}"
                    )
        return self


# ---------------------------------------------------------------------------
# Semantic validation (beyond Pydantic structure)
# ---------------------------------------------------------------------------

def _validate_agent_classes(pipeline_name: str, defn: YamlPipelineDef) -> None:
    """Raise ValueError if any agent_class is not in _AGENT_CLASS_REGISTRY."""
    for node in defn.nodes:
        if node.agent_class and node.agent_class not in _AGENT_CLASS_REGISTRY:
            raise ValueError(
                f"YAML pipeline {pipeline_name!r}: node {node.id!r} references "
                f"unknown agent_class {node.agent_class!r}. "
                f"Known agents: {sorted(_AGENT_CLASS_REGISTRY)}"
            )


def _validate_conditions(pipeline_name: str, defn: YamlPipelineDef) -> None:
    """Raise ValueError if any when: name is not in CONDITION_REGISTRY."""
    for node in defn.nodes:
        if node.when and node.when not in CONDITION_REGISTRY:
            raise ValueError(
                f"YAML pipeline {pipeline_name!r}: node {node.id!r} references "
                f"unknown when condition {node.when!r}. "
                f"Known conditions: {sorted(CONDITION_REGISTRY.keys())}"
            )


# ---------------------------------------------------------------------------
# Conversion: YamlPipelineDef → Pipeline dataclass
# ---------------------------------------------------------------------------

def yaml_to_pipeline(defn: YamlPipelineDef) -> Pipeline:
    """Convert a validated YamlPipelineDef to a Pipeline dataclass for the executor.

    Resolves when: string names to callables via CONDITION_REGISTRY.
    Creates PipelineNode or ApprovalNode per node definition.
    """
    nodes: list[PipelineNode | ApprovalNode] = []

    for n in defn.nodes:
        when_callable: Callable[[dict], bool] | None = None
        if n.when:
            when_callable = CONDITION_REGISTRY[n.when]  # already validated

        if n.type == "approval":
            nodes.append(ApprovalNode(
                id=n.id,
                depends_on=n.depends_on,
                capture_response=n.capture_response,
                when=when_callable,
            ))
        else:
            nodes.append(PipelineNode(
                id=n.id,
                agent_class=n.agent_class,  # type: ignore[arg-type]  # validated non-null
                depends_on=n.depends_on,
                when=when_callable,
            ))

    return Pipeline(name=defn.name, nodes=nodes)


# ---------------------------------------------------------------------------
# File discovery and loading
# ---------------------------------------------------------------------------

def load_yaml_pipelines(pipelines_dir: Path) -> dict[str, Pipeline]:
    """Discover, parse, validate, and convert all *.yaml files in pipelines_dir.

    Raises ValueError on the first invalid pipeline (fail-fast at startup).
    Returns dict of {pipeline_name: Pipeline} ready to merge into PIPELINE_REGISTRY.

    Cycle detection is performed by calling build_topological_layers() from
    dag_executor.py before registration — the same algorithm the executor uses at
    runtime, run proactively at load time.
    """
    from api.dag_executor import build_topological_layers

    pipelines_dir = Path(pipelines_dir)
    if not pipelines_dir.is_dir():
        log.warning(f"[pipeline_loader] pipelines directory not found: {pipelines_dir}")
        return {}

    result: dict[str, Pipeline] = {}
    yaml_files = sorted(pipelines_dir.glob("*.yaml"))

    if not yaml_files:
        log.info(f"[pipeline_loader] no *.yaml files found in {pipelines_dir}")
        return {}

    for yaml_path in yaml_files:
        pipeline_name = yaml_path.stem  # advisory — actual name comes from YAML

        # 1. Parse — use safe_load (never full_load; see §11)
        try:
            with yaml_path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"YAML pipeline file {yaml_path.name!r}: YAML parse error: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ValueError(
                f"YAML pipeline file {yaml_path.name!r}: expected a YAML mapping at "
                f"top level, got {type(raw).__name__}."
            )

        # 2. Pydantic v2 schema validation
        try:
            defn = YamlPipelineDef.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(
                f"YAML pipeline {yaml_path.name!r}: schema validation failed:\n"
                + "\n".join(f"  - {e['loc']}: {e['msg']}" for e in exc.errors())
            ) from exc

        pipeline_name = defn.name  # use authoritative name from YAML

        # 3. Semantic validation: agent classes and condition names
        _validate_agent_classes(pipeline_name, defn)
        _validate_conditions(pipeline_name, defn)

        # 4. Convert to Pipeline dataclass
        pipeline = yaml_to_pipeline(defn)

        # 5. Cycle detection — call executor's Kahn algorithm proactively
        try:
            build_topological_layers(pipeline.nodes)
        except ValueError:
            raise ValueError(
                f"YAML pipeline {pipeline_name!r}: cycle detected in depends_on graph. "
                f"Check your node dependencies."
            )

        result[pipeline_name] = pipeline
        log.info(
            f"[pipeline_loader] registered YAML pipeline {pipeline_name!r} "
            f"({len(pipeline.nodes)} nodes) from {yaml_path.name}"
        )

    log.info(f"[pipeline_loader] loaded {len(result)} YAML pipeline(s): {sorted(result.keys())}")
    return result
```

### Key design decisions

**`safe_load` not `full_load`:** PyYAML `safe_load` deserializes only basic Python types (str, int, float, bool, list, dict, None). It refuses to construct arbitrary Python objects from YAML tags like `!!python/object`. `full_load` and `load()` with no Loader argument permit object construction, which is a remote code execution vector if the YAML source is ever untrusted. Pipeline YAML files are developer-authored, but defense-in-depth still applies — always use `safe_load`. See §11.

**Fail-fast at startup:** `load_yaml_pipelines` raises `ValueError` on the first invalid pipeline rather than skipping it silently. A skipped invalid pipeline is a worse failure mode than a refused startup — you deploy thinking a pipeline is registered, then it fails silently at runtime. Strict startup validation is the right tradeoff.

**Cycle detection at load time:** `build_topological_layers()` is called on each loaded pipeline before registration. This catches cycle errors at startup rather than on the first execution of that pipeline, when a user is waiting for results.

**Python pipelines win:** `PIPELINE_REGISTRY.update(yaml_pipelines)` is called before Python pipelines are registered (Python pipelines register at module import time in `pipeline_def.py`). So Python-defined pipelines overwrite any YAML pipeline with the same name. This is the intentional coexistence rule from PRD 6 §6.3.

---

## 6. Startup Registration — `api/main.py` modification

### Where to insert

In `api/main.py`, inside the `lifespan` async context manager, add the YAML loader block **after** `init_schema(db)` and `fail_orphaned_runs(db)` but **before** the background task creation block. This ordering ensures:
1. DB schema is initialized before anything else runs.
2. Orphaned runs are healed before new pipelines are registered.
3. YAML pipelines are registered before background tasks that might trigger pipeline execution.

### Modified lifespan function

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Existing: Open DB ---
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.commit()
    await init_schema(db)

    # --- Existing: Heal stale runs ---
    from .dag_executor import fail_orphaned_runs
    await fail_orphaned_runs(db)

    app.state.db = db

    # --- NEW: Load YAML pipelines ---
    from api.pipeline_loader import load_yaml_pipelines
    from api.pipeline_def import PIPELINE_REGISTRY
    yaml_dir = Path(__file__).parent.parent / "pipelines"
    if yaml_dir.exists():
        try:
            yaml_pipelines = load_yaml_pipelines(yaml_dir)
            # YAML pipelines are registered first.
            # Python pipelines (already in PIPELINE_REGISTRY from module import)
            # take precedence — they win on name conflict because they were registered
            # at import time before this lifespan block runs.
            PIPELINE_REGISTRY.update(yaml_pipelines)
            log.info(
                f"[startup] {len(yaml_pipelines)} YAML pipeline(s) registered. "
                f"Total registry size: {len(PIPELINE_REGISTRY)}"
            )
        except ValueError as exc:
            # Abort startup on invalid pipeline — do not let the app start in a broken state
            log.error(f"[startup] YAML pipeline load failed: {exc}")
            raise
    else:
        log.info(f"[startup] no pipelines/ directory at {yaml_dir}, skipping YAML load")

    # --- Existing: Register Gmail watch ---
    try:
        from tools.channel_tools import register_gmail_watch
        import asyncio as _asyncio
        await _asyncio.to_thread(register_gmail_watch)
        log.info("[startup] Gmail watch registered")
    except Exception as e:
        log.warning(f"[startup] Gmail watch registration skipped: {e}")

    # --- Existing: Start background tasks ---
    tasks = [
        asyncio.create_task(compile_worker()),
        asyncio.create_task(pipeline_scheduler(db)),
        asyncio.create_task(scheduled_send_loop(db)),
    ]
    app.state.background_tasks = tasks
    log.info("[startup] DB opened, 3 background tasks started")

    yield

    # --- Existing: Shutdown ---
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await db.close()
    log.info("[shutdown] DB closed, background tasks cancelled")
```

### Coexistence rule in detail

`PIPELINE_REGISTRY` is a module-level `dict` defined in `api/pipeline_def.py`. It is populated at module import time (when `pipeline_def.py` is first imported). By the time `lifespan` runs, `PIPELINE_REGISTRY` already contains all 7 Python-defined pipelines.

`PIPELINE_REGISTRY.update(yaml_pipelines)` would overwrite a Python pipeline if a YAML file has the same `name:`. To invert this (Python wins), call `update` in the right order:

```python
# YAML pipelines loaded first into a temporary dict
yaml_pipelines = load_yaml_pipelines(yaml_dir)
# Only register YAML pipelines that are NOT already in the registry
for name, pipeline in yaml_pipelines.items():
    if name not in PIPELINE_REGISTRY:
        PIPELINE_REGISTRY[name] = pipeline
    else:
        log.info(f"[startup] YAML pipeline {name!r} shadowed by Python pipeline — skipping YAML version")
```

This is the safer implementation — it makes the coexistence rule explicit in code rather than relying on dict ordering.

---

## 7. Complete YAML Examples — All 7 Existing Pipelines

These are direct migrations of the Python pipelines in `api/pipeline_def.py`. Inline comments explain non-obvious field choices.

### `pipelines/inbound_responder.yaml`

```yaml
name: inbound_responder
description: >
  Main inbound processing pipeline. Triggered when a known lead sends a message.
  Runs: wiki readiness → strategy → response draft → optional human approval → send.

nodes:
  - id: wiki-readiness
    agent_class: WikiReadinessAgent

  - id: strategy
    agent_class: StrategyAgent
    depends_on: [wiki-readiness]

  - id: response
    agent_class: ResponseAgent
    depends_on: [strategy]
    when: check_strategy_memo    # skip if strategy-memo says recommended_action: wait

  - id: draft-approval
    type: approval
    depends_on: [response]
    capture_response: true
    when: requires_approval      # skip if AUTO_SEND_ENABLED=true and profile says require_approval: false

  - id: sender
    agent_class: SenderAgent
    depends_on: [draft-approval]
```

### `pipelines/cold_outreach.yaml`

```yaml
name: cold_outreach
description: >
  Cold outreach pipeline. Single node — runs ColdOutreachAgent to compose
  and send a first-touch message to a prospect.

nodes:
  - id: cold-outreach
    agent_class: ColdOutreachAgent
```

### `pipelines/knowledge_curation.yaml`

```yaml
name: knowledge_curation
description: >
  Knowledge curation pipeline. Single node — runs KnowledgeCurationAgent
  to update wiki/index.md and append to wiki/log.md.

nodes:
  - id: knowledge-curation
    agent_class: KnowledgeCurationAgent
```

### `pipelines/OpportunityScanPipeline.yaml`

```yaml
# NOTE: name must match the Python registry key exactly — PascalCase preserved
name: OpportunityScanPipeline
description: >
  Opportunity scan pipeline. Triggered by market signal, seller update, or schedule.
  Runs OpportunityAgent to score leads and write opportunity records.

nodes:
  - id: opportunity-agent
    agent_class: OpportunityAgent
    # Python pipeline uses id "opportunity_agent" (underscore) — using kebab-case here
    # because YAML schema requires kebab-case ids. The executor does not care about id
    # format beyond uniqueness; the id is used for event logging only.
    when: autodream_enabled      # reuse as a proxy for trigger_source check
```

> **Migration note for `OpportunityScanPipeline` and `SellerUpdatePipeline`:** The original Python nodes use inline lambdas that check `ctx.get("trigger_source")`. These are not representable as named conditions in the current `CONDITION_REGISTRY`. Two options:
> 1. Add new named conditions `trigger_source_scan` and `trigger_source_seller` to `CONDITION_REGISTRY`.
> 2. Keep these two pipelines as Python-only in `pipeline_def.py` (Python wins on conflict — YAML version is skipped).
>
> Option 2 is recommended for the initial migration. The YAML files below show the closest available approximation for documentation purposes.

### `pipelines/SellerUpdatePipeline.yaml`

```yaml
name: SellerUpdatePipeline
description: >
  Seller update pipeline. Triggered when seller knowledge (products, team, projects)
  is updated. Runs OpportunityAgent to re-score affected leads.

nodes:
  - id: opportunity-agent
    agent_class: OpportunityAgent
    # Original: when=lambda ctx: ctx.get("trigger_source") == "seller_update"
    # No named condition for this in CONDITION_REGISTRY — keep as Python pipeline.
    # This YAML is documentation-only; the Python definition takes precedence.
```

### `pipelines/AutodreamPipeline.yaml`

```yaml
name: AutodreamPipeline
description: >
  Autodream pipeline. Full proactive outreach pipeline:
  opportunity scoring → autodream proposal generation → response draft → send
  (conditional on price guardrails).

nodes:
  - id: opportunity-agent
    agent_class: OpportunityAgent
    # Original: when=lambda ctx: ctx.get("trigger_source") in ("signal", "seller_update", "scheduled")
    # Closest named condition: autodream_enabled (checks kill switch, not trigger_source)
    # Keep Python pipeline for precise trigger_source filtering.

  - id: autodream-agent
    agent_class: AutodreamAgent
    depends_on: [opportunity-agent]
    # Original: when=lambda ctx: _autodream_enabled(ctx) and _score_above_threshold(ctx)
    # CONDITION_REGISTRY does not support compound AND conditions.
    # Option: add "autodream_ready" condition to CONDITION_REGISTRY that combines both.
    when: score_above_threshold  # approximation — autodream_enabled check is omitted

  - id: response-agent
    agent_class: ResponseAgent
    depends_on: [autodream-agent]

  - id: sender-agent
    agent_class: SenderAgent
    depends_on: [response-agent]
    # Original: when=lambda ctx: ctx.get("price_within_guardrails", False)
    # No named condition for guardrail check — add "price_within_guardrails" to CONDITION_REGISTRY.
```

> **Compound condition gap:** The `AutodreamPipeline.autodream_agent` node uses `_autodream_enabled(ctx) and _score_above_threshold(ctx)`. Named conditions are single callables — they cannot express boolean combinations. To support compound conditions in YAML, add composed conditions to `CONDITION_REGISTRY`:
>
> ```python
> "autodream_ready": lambda ctx: _autodream_enabled(ctx) and _score_above_threshold(ctx),
> "price_within_guardrails": lambda ctx: ctx.get("price_within_guardrails", False),
> ```
>
> Without this, the AutodreamPipeline cannot be fully migrated to YAML with identical behavior. Add these two entries to `CONDITION_REGISTRY` in `pipeline_def.py` as part of the Phase 2 implementation.

### `pipelines/new_lead_onboarding.yaml`

```yaml
name: new_lead_onboarding
description: >
  New lead onboarding pipeline. Triggered when an inbound message arrives from
  an unknown lead. Enriches the lead via wiki discovery and web research before
  classifying and responding. Always requires human approval before sending.

nodes:
  - id: lead-discovery
    agent_class: LeadDiscoveryAgent
    # Search existing wiki for any prior context on this person/company

  - id: web-research
    agent_class: ResearchAgent
    depends_on: [lead-discovery]
    # Web research: google_search + LinkedIn profile via search

  - id: lead-classification
    agent_class: LeadClassificationAgent
    depends_on: [web-research]
    # Synthesize findings → write profile.md; place in correct wiki folder

  - id: strategy
    agent_class: StrategyAgent
    depends_on: [lead-classification]
    # Strategy memo — if needs_clarification=true, will note to ask for context

  - id: response
    agent_class: ResponseAgent
    depends_on: [strategy]
    when: check_strategy_memo    # skip if strategy-memo says recommended_action: wait

  - id: draft-approval
    type: approval
    depends_on: [response]
    capture_response: true
    when: always                 # always require approval for brand-new unknown leads

  - id: sender
    agent_class: SenderAgent
    depends_on: [draft-approval]
```

---

## 8. Bonus: `knowledge_scan.yaml`

New pipeline from PRD 6 §7 Phase 2. Runs wiki lint on a schedule.

```yaml
name: knowledge_scan
description: >
  Knowledge scan pipeline. Runs wiki lint (structural check, then optional LLM check)
  and writes the report to wiki/analytics/lint-report.md.
  Triggered by the nightly wiki lint background task or POST /wiki/lint.

nodes:
  - id: wiki-lint-structural
    agent_class: WikiLintAgent
    # WikiLintAgent is a thin wrapper that calls scripts/lint.py --structural-only
    # Add WikiLintAgent to _get_agent() in dag_executor.py

  - id: wiki-lint-llm
    agent_class: WikiLintAgent
    depends_on: [wiki-lint-structural]
    when: never                  # disabled by default; change to "always" to enable LLM checks
    # Set when: always to enable LLM contradiction detection (requires GEMINI API quota)
```

> **Note:** `WikiLintAgent` does not exist yet. It must be added as a thin agent in `agents/wiki_lint_agent.py` and registered in `dag_executor.py:_get_agent()` before this pipeline can execute. Also add `"WikiLintAgent"` to `_AGENT_CLASS_REGISTRY` in `pipeline_loader.py`.

---

## 9. Validation Error Messages

The loader must produce these exact error messages for debuggable startup output. All messages are prefixed with the pipeline name and node id to pinpoint the source immediately.

### Unknown agent class

**Trigger:** `agent_class: XyzAgent` where `XyzAgent` is not in `_AGENT_CLASS_REGISTRY`.

**Message:**
```
YAML pipeline 'foo': node 'bar' references unknown agent_class 'XyzAgent'.
Known agents: ['AutodreamAgent', 'ColdOutreachAgent', 'KnowledgeCurationAgent', ...]
```

**Code location:** `_validate_agent_classes()` in `pipeline_loader.py`.

### Unknown condition name

**Trigger:** `when: xyz_condition` where `xyz_condition` is not in `CONDITION_REGISTRY`.

**Message:**
```
YAML pipeline 'foo': node 'bar' references unknown when condition 'xyz_condition'.
Known conditions: ['always', 'autodream_enabled', 'check_strategy_memo', ...]
```

**Code location:** `_validate_conditions()` in `pipeline_loader.py`.

### Cycle detected

**Trigger:** `depends_on` graph has a circular dependency (e.g., A depends on B and B depends on A).

**Message:**
```
YAML pipeline 'foo': cycle detected in depends_on graph.
Check your node dependencies.
```

**Code location:** `load_yaml_pipelines()` after calling `build_topological_layers()`. The original `ValueError` from `build_topological_layers` reads `"[DAGExecutor] Cycle detected ..."` — catch it and re-raise with the pipeline-scoped message.

### Missing agent_class on non-approval node

**Trigger:** Node has neither `agent_class` nor `type: approval`.

**Message:**
```
YAML pipeline 'foo': node 'bar' must have either agent_class or type: approval
```

**Code location:** `YamlNodeDef.validate_node_type_exclusivity()` model validator.

### Both agent_class and type: approval set

**Trigger:** Node has both `agent_class` and `type: approval`.

**Message:**
```
YAML pipeline 'foo': node 'bar' cannot set both 'type: approval' and 'agent_class'. Approval nodes do not run an agent.
```

### Dangling depends_on reference

**Trigger:** `depends_on: [nonexistent-node]` where `nonexistent-node` is not an id in this pipeline.

**Message:**
```
YAML pipeline 'foo': node 'bar' depends_on 'nonexistent-node' which does not exist.
Known ids: ['lead-discovery', 'strategy', ...]
```

### YAML parse error

**Trigger:** Malformed YAML (invalid indentation, unclosed quotes, etc.).

**Message:**
```
YAML pipeline file 'foo.yaml': YAML parse error: <yaml.YAMLError details>
```

---

## 10. Testing the Loader

### Test file location

`tests/test_pipeline_loader.py`

### Complete test suite

```python
"""Tests for api/pipeline_loader.py"""

import pytest
from pathlib import Path
from api.pipeline_loader import load_yaml_pipelines, yaml_to_pipeline, YamlPipelineDef
from api.pipeline_def import Pipeline, PipelineNode, ApprovalNode


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------

def test_yaml_loader_single_node(tmp_path):
    """A valid single-node pipeline loads and registers correctly."""
    f = tmp_path / "cold_outreach.yaml"
    f.write_text("name: cold_outreach\nnodes:\n  - id: cold-outreach\n    agent_class: ColdOutreachAgent\n")
    result = load_yaml_pipelines(tmp_path)
    assert "cold_outreach" in result
    assert len(result["cold_outreach"].nodes) == 1
    assert isinstance(result["cold_outreach"].nodes[0], PipelineNode)
    assert result["cold_outreach"].nodes[0].agent_class == "ColdOutreachAgent"


def test_yaml_loader_approval_node(tmp_path):
    """An approval node is converted to ApprovalNode dataclass."""
    f = tmp_path / "pipeline.yaml"
    f.write_text("""
name: test_pipeline
nodes:
  - id: response
    agent_class: ResponseAgent
  - id: approval
    type: approval
    depends_on: [response]
    capture_response: true
    when: always
""")
    result = load_yaml_pipelines(tmp_path)
    approval_node = result["test_pipeline"].nodes[1]
    assert isinstance(approval_node, ApprovalNode)
    assert approval_node.capture_response is True
    assert approval_node.when is not None
    assert approval_node.when({}) is True  # "always" condition


def test_yaml_loader_when_condition_resolved(tmp_path):
    """Named when: condition is resolved to a callable."""
    f = tmp_path / "pipeline.yaml"
    f.write_text("""
name: test_with_condition
nodes:
  - id: response
    agent_class: ResponseAgent
    when: check_strategy_memo
""")
    result = load_yaml_pipelines(tmp_path)
    node = result["test_with_condition"].nodes[0]
    assert callable(node.when)


def test_yaml_loader_missing_dir(tmp_path):
    """Missing directory returns empty dict, does not raise."""
    result = load_yaml_pipelines(tmp_path / "nonexistent")
    assert result == {}


def test_yaml_loader_empty_dir(tmp_path):
    """Empty directory returns empty dict."""
    result = load_yaml_pipelines(tmp_path)
    assert result == {}


def test_yaml_loader_multi_pipeline(tmp_path):
    """Multiple yaml files in a directory are all loaded."""
    (tmp_path / "a.yaml").write_text("name: pipeline_a\nnodes:\n  - id: node-a\n    agent_class: ResponseAgent\n")
    (tmp_path / "b.yaml").write_text("name: pipeline_b\nnodes:\n  - id: node-b\n    agent_class: SenderAgent\n")
    result = load_yaml_pipelines(tmp_path)
    assert "pipeline_a" in result
    assert "pipeline_b" in result


def test_yaml_loader_depends_on_order(tmp_path):
    """Nodes are converted in order; depends_on is preserved."""
    f = tmp_path / "pipeline.yaml"
    f.write_text("""
name: ordered
nodes:
  - id: first
    agent_class: WikiReadinessAgent
  - id: second
    agent_class: StrategyAgent
    depends_on: [first]
""")
    result = load_yaml_pipelines(tmp_path)
    second = result["ordered"].nodes[1]
    assert second.depends_on == ["first"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_yaml_loader_unknown_agent(tmp_path):
    """Unknown agent_class raises ValueError with descriptive message."""
    f = tmp_path / "bad.yaml"
    f.write_text("name: bad\nnodes:\n  - id: node\n    agent_class: GhostAgent\n")
    with pytest.raises(ValueError, match="unknown agent_class 'GhostAgent'"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_unknown_condition(tmp_path):
    """Unknown when: condition raises ValueError with descriptive message."""
    f = tmp_path / "bad.yaml"
    f.write_text("name: bad\nnodes:\n  - id: node\n    agent_class: ResponseAgent\n    when: mystery_condition\n")
    with pytest.raises(ValueError, match="unknown when condition 'mystery_condition'"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_cycle_detected(tmp_path):
    """Cyclic depends_on raises ValueError mentioning cycle."""
    f = tmp_path / "cyclic.yaml"
    f.write_text("""
name: cyclic
nodes:
  - id: node-a
    agent_class: ResponseAgent
    depends_on: [node-b]
  - id: node-b
    agent_class: SenderAgent
    depends_on: [node-a]
""")
    with pytest.raises(ValueError, match="cycle detected"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_missing_agent_class(tmp_path):
    """Node with no agent_class and no type: approval raises ValueError."""
    f = tmp_path / "bad.yaml"
    f.write_text("name: bad\nnodes:\n  - id: broken-node\n")
    with pytest.raises(ValueError, match="must have either agent_class or type: approval"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_both_approval_and_agent(tmp_path):
    """Node with both type: approval and agent_class raises ValueError."""
    f = tmp_path / "bad.yaml"
    f.write_text("""
name: bad
nodes:
  - id: conflicted
    type: approval
    agent_class: ResponseAgent
""")
    with pytest.raises(ValueError, match="cannot set both"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_duplicate_node_ids(tmp_path):
    """Duplicate node ids within a pipeline raises ValueError."""
    f = tmp_path / "bad.yaml"
    f.write_text("""
name: bad
nodes:
  - id: same-id
    agent_class: ResponseAgent
  - id: same-id
    agent_class: SenderAgent
""")
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_dangling_depends_on(tmp_path):
    """depends_on referencing a nonexistent node id raises ValueError."""
    f = tmp_path / "bad.yaml"
    f.write_text("""
name: bad
nodes:
  - id: node-a
    agent_class: ResponseAgent
    depends_on: [nonexistent]
""")
    with pytest.raises(ValueError, match="nonexistent"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_malformed_yaml(tmp_path):
    """Malformed YAML raises ValueError with parse error."""
    f = tmp_path / "broken.yaml"
    f.write_text("name: broken\nnodes:\n  - id: [unclosed\n")
    with pytest.raises(ValueError, match="YAML parse error"):
        load_yaml_pipelines(tmp_path)


def test_yaml_loader_non_kebab_node_id(tmp_path):
    """Node id with underscores or spaces fails kebab-case validation."""
    f = tmp_path / "bad.yaml"
    f.write_text("name: bad\nnodes:\n  - id: bad_id\n    agent_class: ResponseAgent\n")
    with pytest.raises(ValueError, match="kebab-case"):
        load_yaml_pipelines(tmp_path)
```

### Running tests

```bash
cd "/home/developer/Projects/TUM.ai Makeathon"
python -m pytest tests/test_pipeline_loader.py -v
```

---

## 11. Security Notes — PyYAML `safe_load`

### Always use `safe_load`

```python
# CORRECT — deserializes only basic Python types
data = yaml.safe_load(fh)

# DANGEROUS — allows arbitrary Python object construction
data = yaml.load(fh, Loader=yaml.FullLoader)   # FullLoader
data = yaml.load(fh, Loader=yaml.Loader)        # UnsafeLoader
data = yaml.load(fh)                            # deprecated; unsafe in PyYAML < 5.1
```

### Why it matters

PyYAML's full loaders support YAML tags like `!!python/object/apply:os.system` which can execute arbitrary shell commands during parsing. `safe_load` uses the `SafeLoader` which recognizes only: str, int, float, bool, null, list, dict, datetime. Any YAML tag that would construct a Python object raises a `yaml.constructor.ConstructorError` instead of executing it.

### What `safe_load` does not protect against

- **Billion laughs / YAML bomb**: Deeply nested alias expansion. PyYAML does not have a built-in depth limit. For pipeline YAML files authored by trusted developers, this is not a practical risk, but be aware if YAML input ever comes from untrusted external sources.
- **Malicious file paths**: A YAML file containing `agent_class: "../../../etc/passwd"` will be caught by the `_AGENT_CLASS_REGISTRY` check. But the path itself is never executed — `safe_load` only deserializes the string.

### Pydantic v2 `model_validate()` vs `parse_obj()`

```python
# Pydantic v2 (correct — FastAPI ≥ 0.100 ships Pydantic v2)
defn = YamlPipelineDef.model_validate(raw_dict)

# Pydantic v1 (incorrect for this codebase)
defn = YamlPipelineDef.parse_obj(raw_dict)  # v1 API — will raise AttributeError in v2
```

Pydantic v2 added significant performance improvements (Rust-compiled core) and stricter validation semantics. `model_validate()` is the v2 equivalent of v1's `parse_obj()`. Do not mix v1 and v2 API calls.

---

## 12. Implementation Checklist

Use this checklist when implementing the YAML pipeline system in PRD 6 Phase 2:

### `api/pipeline_def.py` changes
- [ ] Add `CONDITION_REGISTRY` dict after the existing `when:` helper functions
- [ ] Add compound conditions `autodream_ready` and `price_within_guardrails` to `CONDITION_REGISTRY`
- [ ] Verify all existing `when=lambda ctx: ...` usages have a named equivalent

### `api/pipeline_loader.py` — new file
- [ ] Create file with `YamlNodeDef`, `YamlPipelineDef` Pydantic models
- [ ] Implement `_validate_agent_classes()`
- [ ] Implement `_validate_conditions()`
- [ ] Implement `yaml_to_pipeline()`
- [ ] Implement `load_yaml_pipelines()` with `safe_load`, Pydantic validation, cycle detection

### `api/main.py` changes
- [ ] Add YAML loader block in `lifespan()` after `fail_orphaned_runs()` and before background tasks
- [ ] Use `if name not in PIPELINE_REGISTRY` guard to let Python pipelines win on conflict
- [ ] Abort startup (`raise`) on `ValueError` from loader

### `pipelines/` directory — new directory
- [ ] Create `pipelines/` at project root (sibling of `api/`, `agents/`, `static/`)
- [ ] Create `inbound_responder.yaml`
- [ ] Create `cold_outreach.yaml`
- [ ] Create `knowledge_curation.yaml`
- [ ] Create `OpportunityScanPipeline.yaml` (note: keep Python version for trigger_source logic)
- [ ] Create `SellerUpdatePipeline.yaml` (note: keep Python version for trigger_source logic)
- [ ] Create `AutodreamPipeline.yaml` (note: requires `autodream_ready` compound condition)
- [ ] Create `new_lead_onboarding.yaml`
- [ ] Create `knowledge_scan.yaml` (requires `WikiLintAgent` to be implemented first)

### `api/dag_executor.py` changes (if adding WikiLintAgent)
- [ ] Add `WikiLintAgent` branch to `_get_agent()` resolver

### `tests/test_pipeline_loader.py` — new file
- [ ] Create test file with all test cases from §10

### Verification
- [ ] `python -m pytest tests/test_pipeline_loader.py -v` — all tests pass
- [ ] Start server; confirm startup log shows `N YAML pipeline(s) registered`
- [ ] Confirm `PIPELINE_REGISTRY` has correct entries via `/pipeline/list` or log output
- [ ] Run one YAML-defined pipeline end-to-end and confirm identical behavior to Python version

---

*Reference guide complete. This document is self-contained for any implementer who has read `api/pipeline_def.py` and `api/dag_executor.py`.*
