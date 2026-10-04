"""
Service for structured metadata audit event logging.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

from app.core.interfaces.audit_logger_interface import IAuditLogger
from app.repository.audit_local_db_repository import AuditLocalDBRepository
from app.core.events.event_bus import EventBus

logger = logging.getLogger("runtimeforce.service.audit")


class AuditLoggerService(IAuditLogger):
    def __init__(self, repo: AuditLocalDBRepository, event_bus: EventBus):
        self.repo = repo
        self.event_bus = event_bus

    def log_event(
        self, event_type: str, payload: Dict[str, Any], user_id: str = "anonymous"
    ) -> bool:
        success = self.repo.log_event(event_type, payload, user_id)
        if success:
            try:
                asyncio.create_task(
                    self.event_bus.publish(
                        "audit.event_added", event_type=event_type, user_id=user_id
                    )
                )
            except Exception as e:
                logger.error(f"Failed to publish audit event: {e}")
        return success

    def query_logs(
        self, user_id: str, limit: int = 50, event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.repo.query_logs(user_id, limit, event_type)
