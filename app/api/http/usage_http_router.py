"""
HTTP API Router for querying usage statistics and operation cost limits.
"""
import logging
from fastapi import APIRouter, Depends
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_telemetry_repo
from app.repository.telemetry_db_repository import TelemetryDBRepository

logger = logging.getLogger("runtimeforce.api.http.usage")
router = APIRouter(prefix="/api/v1/usage", tags=["usage"])

@router.get("/summary")
async def get_usage_summary(
    hours: int = 24,
    user_id: str = Depends(require_authenticated_user),
    telemetry_repo: TelemetryDBRepository = Depends(get_telemetry_repo)
):
    stats = telemetry_repo.get_telemetry_stats(hours=hours, user_id=user_id)
    return {"user_id": user_id, "stats": stats}
