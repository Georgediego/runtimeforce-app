from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IRoleRouterService(ABC):
    @abstractmethod
    async def classify_and_route(
        self,
        user_prompt: str,
        project_id: str,
        user_id: str,
        user_plan: str,
        mode: str = "AUTO",
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Classifies user prompt complexity and routes to appropriate role.
        Passes enabled_models to downstream selector for strict filtering.
        """
        pass
