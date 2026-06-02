"""
Telemetry & Smart Scoring API.
"""
from fastapi import APIRouter
from app.memory.store import store

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.get("/scores")
async def get_scores():
    return {"scores": store.get_model_scores()}


@router.get("/stats")
async def get_stats(hours: int = 24):
    return {"stats": store.get_telemetry_stats(hours)}


@router.post("/recalculate")
async def recalculate_scores(window_hours: int = 168):
    results = store.recalculate_model_scores(window_hours)
    return {
        "status": "success",
        "models_updated": len(results),
        "scores": results
    }
