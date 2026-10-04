"""
Abstract interface for local and relayed audit event logging.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IAuditLogger(ABC):

    @abstractmethod
    def log_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        user_id: str = "anonymous"
    ) -> bool:
        """Record structured metadata audit log entry."""
        pass

    @abstractmethod
    def query_logs(
        self,
        user_id: str,
        limit: int = 50,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve filtered audit logs for user_id."""
        pass
