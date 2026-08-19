"""
Service for user support tickets and diagnostic automated intake.
"""
import logging
from typing import Dict, Any, List, Optional
from app.core.interfaces.support_ticket_service_interface import ISupportTicketService
from app.repository.support_ticket_db_repository import SupportTicketDBRepository

logger = logging.getLogger("runtimeforce.service.support")

class SupportTicketService(ISupportTicketService):
    def __init__(self, repo: SupportTicketDBRepository):
        self.repo = repo

    def create_ticket(
        self,
        user_id: str,
        subject: str,
        description: str,
        diagnostics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.repo.create_ticket(user_id, subject, description, diagnostics)

    def list_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        return self.repo.list_tickets(user_id)
