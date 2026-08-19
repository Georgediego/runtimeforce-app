from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IArchitectAgentService(ABC):
    @abstractmethod
    async def consult(
        self,
        user_prompt: str,
        project_id: str,
        user_id: str,
        user_plan: str,
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Provides architectural guidance using the most powerful ENABLED model.
        Never calls models not present in enabled_models.
        """
        pass
