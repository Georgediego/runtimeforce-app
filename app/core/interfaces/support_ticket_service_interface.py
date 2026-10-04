"""
Abstract interface for support ticket processing and diagnostic intake.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class ISupportTicketService(ABC):

    @abstractmethod
    def create_ticket(
        self,
        user_id: str,
        subject: str,
        description: str,
        diagnostics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create new support ticket with optional metadata."""
        pass

    @abstractmethod
    def list_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        """List all support tickets submitted by user_id."""
        pass
