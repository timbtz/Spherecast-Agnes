"""
POST /data-update — trigger proactive consolidation pipeline when new external data arrives.
Called by enrichment scripts after updating Supplier_Commercial or BOM_Component_Quantity.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from orchestration.api.dag_executor import execute_pipeline

router = APIRouter(prefix="/data-update", tags=["data_update"])


class DataUpdateEvent(BaseModel):
    source: str          # supplier_commercial|bom|compliance|price_refresh
    changed_ids: list[int] = []   # changed canonical ingredient IDs (optional)
    top_n: int = 10
    notes: str = ""


@router.post("")
async def data_update(event: DataUpdateEvent):
    run_id = await execute_pipeline(
        pipeline_name="proactive_consolidation",
        trigger_source="data_update",
        trigger_payload={
            "source": event.source,
            "changed_ids": event.changed_ids,
            "top_n": event.top_n,
            "notes": event.notes,
        },
    )
    return {
        "run_id": run_id,
        "pipeline": "proactive_consolidation",
        "trigger": event.source,
        "status": "started",
    }
