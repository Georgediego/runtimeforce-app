"""
HTTP API Router for querying local audit log entries.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_audit_service
from app.services.audit.audit_logger_service import AuditLoggerService

logger = logging.getLogger("runtimeforce.api.http.audit")
router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

@router.get("/logs")
async def query_audit_logs(
    limit: int = 50,
    event_type: Optional[str] = None,
    user_id: str = Depends(require_authenticated_user),
    audit_service: AuditLoggerService = Depends(get_audit_service)
):
    logs = audit_service.query_logs(user_id=user_id, limit=limit, event_type=event_type)
    return {"user_id": user_id, "count": len(logs), "logs": logs}
