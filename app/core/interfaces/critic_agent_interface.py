from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ICriticAgentService(ABC):
    @abstractmethod
    async def validate_result(
        self,
        specialist_result: Dict[str, Any],
        task_context: Dict[str, Any],
        user_id: str,
        project_id: str,
        user_plan: str,
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validates specialist execution result via cheapest ENABLED model.
        Checks graph test nodes and LLM assertion.
        """
        pass
