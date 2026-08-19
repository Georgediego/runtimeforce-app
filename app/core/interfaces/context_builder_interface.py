"""
Abstract interface for the Context Builder Pipeline and Token Budget Allocation.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IContextBuilder(ABC):

    @abstractmethod
    async def build_optimal_context(
        self,
        user_prompt: str,
        session_id: str,
        user_id: str,
        project_id: str,
        max_token_budget: int = 128000
    ) -> Dict[str, Any]:
        """Execute Context Pipeline and return budget-capped, graph-backed prompt context."""
        pass

    @abstractmethod
    def calculate_token_budget(
        self,
        total_budget: int = 128000
    ) -> Dict[str, int]:
        """Calculate token allocations across system, files, git, memory, and reserve."""
        pass
