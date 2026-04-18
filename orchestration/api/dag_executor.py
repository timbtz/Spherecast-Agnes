"""
DAG executor for Agnes pipelines.

Execution model:
  1. Build dependency graph from pipeline nodes.
  2. Topological sort → layers of nodes that can run in parallel.
  3. For each layer: asyncio.gather() all nodes, write events, collect outputs.
  4. Terminal node outputs are merged into AgnesContext.node_outputs.
"""
import asyncio
import time
import traceback
from pathlib import Path
from typing import Optional

from orchestration.api import db as _db
from orchestration.api.agnes_context import AgnesContext
from orchestration.api.agent_registry import get_agent, get_tool
from orchestration.api.conditions import evaluate
from orchestration.api.pipeline_def import Pipeline, PipelineNode
from orchestration.api.pipeline_loader import load as load_pipeline


_DB_PATH = Path(__file__).parent.parent.parent / "orchestration.db"


def _topological_layers(nodes: list[PipelineNode]) -> list[list[PipelineNode]]:
    """Kahn's algorithm — returns node layers (each layer runs in parallel)."""
    in_degree = {n.id: len(n.depends_on) for n in nodes}
    dependents: dict[str, list[str]] = {n.id: [] for n in nodes}
    by_id = {n.id: n for n in nodes}

    for n in nodes:
        for dep in n.depends_on:
            dependents[dep].append(n.id)

    ready = [n for n in nodes if in_degree[n.id] == 0]
    layers: list[list[PipelineNode]] = []

    while ready:
        layers.append(ready)
        next_ready = []
        for node in ready:
            for child_id in dependents[node.id]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    next_ready.append(by_id[child_id])
        ready = next_ready

    if sum(len(l) for l in layers) != len(nodes):
        raise ValueError("Cycle detected in pipeline DAG")
    return layers


async def _run_node(node: PipelineNode, ctx: AgnesContext) -> tuple[str, Optional[dict], Optional[str]]:
    """Returns (node_id, output_dict | None, error | None)."""
    start = time.monotonic()
    try:
        await _db.write_event(ctx.run_id, "node_started", node.id, {}, ctx.orchestration_db_path)
        if node.when and not evaluate(node.when, ctx):
            return node.id, None, None  # skipped

        if node.tool_class:
            fn = get_tool(node.tool_class)
            output = await asyncio.get_event_loop().run_in_executor(None, fn, ctx)
        elif node.agent_class:
            fn = get_agent(node.agent_class)
            output = await fn(ctx)
        else:
            raise ValueError(f"Node {node.id!r} has neither agent_class nor tool_class")

        elapsed = int((time.monotonic() - start) * 1000)
        return node.id, {**(output or {}), "_elapsed_ms": elapsed}, None
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return node.id, None, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


async def execute_pipeline(
    pipeline_name: str,
    trigger_source: str,
    trigger_payload: dict,
    db_path: Path = _DB_PATH,
) -> str:
    """Start a pipeline run. Returns run_id immediately; execution is background."""
    run_id = _db.create_run(pipeline_name, trigger_source, trigger_payload, db_path)
    asyncio.create_task(_execute(pipeline_name, run_id, trigger_source, trigger_payload, db_path))
    return run_id


async def _execute(
    pipeline_name: str,
    run_id: str,
    trigger_source: str,
    trigger_payload: dict,
    db_path: Path,
) -> None:
    ctx = AgnesContext(
        run_id=run_id,
        pipeline_name=pipeline_name,
        trigger_source=trigger_source,
        trigger_payload=trigger_payload,
        orchestration_db_path=db_path,
    )
    try:
        pipeline: Pipeline = load_pipeline(pipeline_name)
        await _db.write_event(run_id, "pipeline_started", data={"pipeline": pipeline_name}, db_path=db_path)

        layers = _topological_layers(pipeline.nodes)

        for layer in layers:
            results = await asyncio.gather(*[_run_node(n, ctx) for n in layer])

            for node_id, output, error in results:
                if error:
                    await _db.write_event(run_id, "node_failed", node_id, {"error": error}, db_path)
                    _db.update_run_status(run_id, "failed", error=f"Node {node_id} failed: {error[:200]}", db_path=db_path)
                    return
                elif output is None:
                    await _db.write_event(run_id, "node_skipped", node_id, {}, db_path)
                else:
                    ctx.node_outputs[node_id] = output
                    await _db.write_event(run_id, "node_completed", node_id, {"node_output": output}, db_path)

        await _db.write_event(run_id, "pipeline_completed", data={"pipeline": pipeline_name}, db_path=db_path)
        _db.update_run_status(run_id, "completed", db_path=db_path)

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        await _db.write_event(run_id, "pipeline_failed", data={"error": err}, db_path=db_path)
        _db.update_run_status(run_id, "failed", error=err, db_path=db_path)
