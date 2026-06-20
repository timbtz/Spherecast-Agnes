"""
POST /chat — classify user message with RouterAgent, launch matching pipeline(s).
Supports compound intents: primary run + secondary_runs for multi-task workflows.
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
    status: str          # "started" | "no_match"
    secondary_runs: list[SecondaryRun] = []


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    classification = await classify(req.message)
    pipeline = classification.get("pipeline")
    params = classification.get("params", {})
    confidence = classification.get("confidence", 0.0)
    reasoning = classification.get("reasoning", "")
    secondary_intents = classification.get("secondary_intents", [])

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

    # Fan out secondary intents — tolerate individual failures
    secondary_runs: list[SecondaryRun] = []
    for intent in secondary_intents:
        try:
            sec_params = dict(intent.get("params", {}))
            sec_params["_user_message"] = req.message
            sec_params["_user_id"] = req.user_id
            sec_run_id = await execute_pipeline(
                pipeline_name=intent["pipeline"],
                trigger_source="chat",
                trigger_payload=sec_params,
            )
            secondary_runs.append(
                SecondaryRun(run_id=sec_run_id, pipeline=intent["pipeline"], params=sec_params)
            )
        except Exception:
            pass  # Secondary failures don't break primary response

    return ChatResponse(
        run_id=run_id,
        pipeline=pipeline,
        params=params,
        confidence=confidence,
        reasoning=reasoning,
        status="started",
        secondary_runs=secondary_runs,
    )
