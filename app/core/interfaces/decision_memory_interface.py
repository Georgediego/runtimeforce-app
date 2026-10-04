"""
Abstract interface for Long-Term Architectural and Technical Decision Memory.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IDecisionMemory(ABC):

    @abstractmethod
    def record_decision(
        self,
        project_id: str,
        user_id: str,
        topic: str,
        decision: str,
        rationale: str
    ) -> Dict[str, Any]:
        """Record architectural or technical decision to prevent repeated debates."""
        pass

    @abstractmethod
    def get_decisions(
        self,
        project_id: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant project decisions."""
        pass
