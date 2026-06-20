"""Scoring configuration and supplier ranking endpoints."""
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/scoring", tags=["scoring"])
_DB = Path(__file__).parent.parent.parent.parent / "db_enriched.sqlite"


class WeightsPayload(BaseModel):
    price: Annotated[float, Field(ge=1.0, le=5.0)]
    lead_time: Annotated[float, Field(ge=1.0, le=5.0)]
    quality: Annotated[float, Field(ge=1.0, le=5.0)]


@router.get("/weights")
def get_weights():
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT Key, Value FROM Scoring_Config").fetchall()
    conn.close()
    cfg = {r["Key"]: r["Value"] for r in rows}
    return {
        "price": cfg.get("weight_price", 3.0),
        "lead_time": cfg.get("weight_lead_time", 3.0),
        "quality": cfg.get("weight_quality", 3.0),
    }


@router.post("/weights")
def save_weights(payload: WeightsPayload):
    conn = sqlite3.connect(str(_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    for key, val in [
        ("weight_price", payload.price),
        ("weight_lead_time", payload.lead_time),
        ("weight_quality", payload.quality),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, val)
        )
    conn.commit()
    conn.close()
    return {"status": "saved", "price": payload.price, "lead_time": payload.lead_time, "quality": payload.quality}


@router.get("/suppliers/{ingredient_id}")
def scored_suppliers(ingredient_id: int):
    from reasoning.supplier_scorer import SupplierScorer
    scorer = SupplierScorer(_DB)
    results = scorer.score_suppliers(ingredient_id)
    if not results and not _ingredient_exists(ingredient_id):
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return {
        "ingredient_id": ingredient_id,
        "weights": scorer.get_weights(),
        "suppliers": results,
        "count": len(results),
    }


def _ingredient_exists(ingredient_id: int) -> bool:
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    row = conn.execute("SELECT Id FROM Ingredient_Canonical WHERE Id = ?", (ingredient_id,)).fetchone()
    conn.close()
    return row is not None
