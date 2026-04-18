"""
Pipeline management endpoints:
  POST   /pipelines/run/{name}    — trigger a named pipeline directly
  GET    /pipelines               — list available pipelines
  GET    /runs                    — list recent runs
  GET    /runs/{run_id}           — run status + events
  GET    /runs/{run_id}/stream    — SSE stream of live events
  GET    /proposals               — list runs with proposals
"""
import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestration.api import db as _db
from orchestration.api.dag_executor import execute_pipeline, _topological_layers
from orchestration.api.event_bus import subscribe, unsubscribe
from orchestration.api.pipeline_loader import list_pipelines, load as load_pipeline

router = APIRouter(tags=["pipelines"])


class RunRequest(BaseModel):
    params: dict = {}


# ── Trigger ──────────────────────────────────────────────────────────────────

@router.post("/pipelines/run/{name}")
async def run_pipeline(name: str, req: RunRequest):
    available = list_pipelines()
    if name not in available:
        raise HTTPException(404, f"Pipeline {name!r} not found. Available: {available}")
    run_id = await execute_pipeline(
        pipeline_name=name,
        trigger_source="manual",
        trigger_payload=req.params,
    )
    return {"run_id": run_id, "pipeline": name, "status": "started"}


# ── Listing ───────────────────────────────────────────────────────────────────

@router.get("/pipelines")
def list_available_pipelines():
    return list_pipelines()


@router.get("/pipelines/{name}/graph")
def get_pipeline_graph(name: str):
    available = list_pipelines()
    if name not in available:
        raise HTTPException(404, f"Pipeline {name!r} not found")
    pipeline = load_pipeline(name)
    layers = _topological_layers(pipeline.nodes)
    return {
        "name": pipeline.name,
        "trigger": pipeline.trigger,
        "layers": [[n.id for n in layer] for layer in layers],
        "nodes": [
            {
                "id": n.id,
                "type": "agent" if n.agent_class else "tool",
                "class": n.agent_class or n.tool_class,
                "depends_on": n.depends_on,
                "when": n.when,
            }
            for n in pipeline.nodes
        ],
    }


def _format_run(r: dict) -> dict:
    from datetime import datetime
    started = r.get("started_at")
    ended = r.get("completed_at")
    duration_ms = None
    if started and ended:
        try:
            dt_start = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
            dt_end = datetime.strptime(ended, "%Y-%m-%d %H:%M:%S")
            duration_ms = int((dt_end - dt_start).total_seconds() * 1000)
        except Exception:
            pass
    return {
        "run_id": r["id"],
        "pipeline": r["pipeline_name"],
        "status": r["status"],
        "started_at": started,
        "ended_at": ended,
        "duration_ms": duration_ms,
    }


@router.get("/runs")
def list_runs(limit: int = 50):
    return [_format_run(r) for r in _db.list_runs(limit)]


# ── Run status ────────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}")
def get_run(run_id: str):
    run = _db.get_run_with_events(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    formatted = _format_run(run)
    formatted["events"] = run.get("events", [])
    return formatted


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    run = _db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    async def event_stream() -> AsyncIterator[str]:
        # Replay historical events first
        for ev in _db.get_events(run_id):
            data = json.dumps({
                "event_type": ev["event_type"],
                "node_id": ev["node_id"],
                **json.loads(ev["data"] or "{}"),
                "created_at": ev["created_at"],
            })
            yield f"data: {data}\n\n"

        # If run is already terminal, close stream
        if run["status"] in ("completed", "failed"):
            yield "data: {\"event_type\": \"stream_closed\"}\n\n"
            return

        # Subscribe to live events
        q = subscribe(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event_type") in ("pipeline_completed", "pipeline_failed"):
                        yield "data: {\"event_type\": \"stream_closed\"}\n\n"
                        return
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield ": heartbeat\n\n"
        finally:
            unsubscribe(run_id, q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Proposals ─────────────────────────────────────────────────────────────────

@router.get("/proposals")
def list_proposals(limit: int = 20):
    """Returns completed runs that produced a write-proposal node output."""
    runs = _db.list_runs(limit=200)
    proposals = []
    for r in runs:
        if r["status"] != "completed":
            continue
        events = _db.get_events(r["id"])
        for ev in events:
            if ev["node_id"] == "write-proposal" and ev["event_type"] == "node_completed":
                data = json.loads(ev["data"] or "{}")
                node_out = data.get("node_output", {})
                if node_out.get("proposal_text") or node_out.get("proposals_narrative"):
                    proposals.append({
                        "run_id": r["id"],
                        "pipeline": r["pipeline_name"],
                        "started_at": r["started_at"],
                        "completed_at": r["completed_at"],
                        "ingredient_name": node_out.get("ingredient_name"),
                        "proposal_text": node_out.get("proposal_text") or node_out.get("proposals_narrative"),
                    })
                break
        if len(proposals) >= limit:
            break
    return {"proposals": proposals, "count": len(proposals)}
