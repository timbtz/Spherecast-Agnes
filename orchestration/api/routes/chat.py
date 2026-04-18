"""
POST /chat — receive a natural-language message, classify it with RouterAgent,
launch the matching pipeline, return run_id immediately.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestration.agents.router_agent import classify
from orchestration.api.dag_executor import execute_pipeline

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    run_id: str | None
    pipeline: str | None
    params: dict
    confidence: float
    reasoning: str
    status: str   # "started" | "no_match"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    classification = await classify(req.message)
    pipeline = classification.get("pipeline")
    params = classification.get("params", {})
    confidence = classification.get("confidence", 0.0)
    reasoning = classification.get("reasoning", "")

    if not pipeline:
        return ChatResponse(
            run_id=None,
            pipeline=None,
            params=params,
            confidence=confidence,
            reasoning=reasoning,
            status="no_match",
        )

    params["_user_message"] = req.message
    params["_user_id"] = req.user_id

    run_id = await execute_pipeline(
        pipeline_name=pipeline,
        trigger_source="chat",
        trigger_payload=params,
    )

    return ChatResponse(
        run_id=run_id,
        pipeline=pipeline,
        params=params,
        confidence=confidence,
        reasoning=reasoning,
        status="started",
    )
