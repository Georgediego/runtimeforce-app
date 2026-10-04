"""
HTTP API Router for Telemetry statistics and Model Scores.
"""
from fastapi import APIRouter, Depends
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_telemetry_repo
from app.repository.telemetry_db_repository import TelemetryDBRepository

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

@router.get("/scores")
async def get_scores(
    user_id: str = Depends(require_authenticated_user),
    repo: TelemetryDBRepository = Depends(get_telemetry_repo)
):
    return {"scores": repo.get_model_scores(user_id)}

@router.get("/stats")
async def get_stats(
    hours: int = 24,
    user_id: str = Depends(require_authenticated_user),
    repo: TelemetryDBRepository = Depends(get_telemetry_repo)
):
    return {"stats": repo.get_telemetry_stats(hours, user_id)}
