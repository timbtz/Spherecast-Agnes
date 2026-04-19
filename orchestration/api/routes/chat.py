"""
POST /chat — receive a natural-language message, classify it with RouterAgent,
launch the matching pipeline (plus any secondary pipelines for compound
requests), return all run_ids immediately.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from orchestration.agents.router_agent import classify
from orchestration.api.dag_executor import execute_pipeline

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"


class SecondaryRun(BaseModel):
    run_id: str
    pipeline: str
    params: dict


class ChatResponse(BaseModel):
    run_id: str | None
    pipeline: str | None
    params: dict
    confidence: float
    reasoning: str
    status: str   # "started" | "no_match"
    # Compound-request fan-out. Empty list when the request was single-intent
    # or rejected. The primary run is always (run_id, pipeline, params); the
    # additional intents land here so the UI can poll all of them.
    secondary_runs: list[SecondaryRun] = []


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    classification = await classify(req.message)
    pipeline = classification.get("pipeline")
    params = classification.get("params") or {}
    confidence = classification.get("confidence", 0.0)
    reasoning = classification.get("reasoning", "")
    secondary_intents = classification.get("secondary_intents") or []

    if not pipeline:
        return ChatResponse(
            run_id=None,
            pipeline=None,
            params=params,
            confidence=confidence,
            reasoning=reasoning,
            status="no_match",
        )

    # Primary run
    params["_user_message"] = req.message
    params["_user_id"] = req.user_id
    run_id = await execute_pipeline(
        pipeline_name=pipeline,
        trigger_source="chat",
        trigger_payload=params,
    )

    # Fan-out for any secondary intents the router identified. Each runs
    # independently — we don't wait for completion here, the caller polls
    # /runs/{id} as usual. We tolerate malformed entries to avoid one bad
    # secondary intent from blowing up the whole compound request.
    secondary_runs: list[SecondaryRun] = []
    for intent in secondary_intents:
        if not isinstance(intent, dict):
            continue
        sec_pipeline = intent.get("pipeline")
        sec_params = intent.get("params") or {}
        if not sec_pipeline or not isinstance(sec_params, dict):
            continue
        # Same pipeline twice is almost always a router hallucination — skip.
        if sec_pipeline == pipeline:
            continue
        sec_params["_user_message"] = req.message
        sec_params["_user_id"] = req.user_id
        try:
            sec_run_id = await execute_pipeline(
                pipeline_name=sec_pipeline,
                trigger_source="chat",
                trigger_payload=sec_params,
            )
            secondary_runs.append(
                SecondaryRun(run_id=sec_run_id, pipeline=sec_pipeline, params=sec_params)
            )
        except Exception:
            # Bad pipeline name from router — log via FastAPI's normal error
            # path but don't fail the whole request.
            continue

    return ChatResponse(
        run_id=run_id,
        pipeline=pipeline,
        params=params,
        confidence=confidence,
        reasoning=reasoning,
        status="started",
        secondary_runs=secondary_runs,
    )
