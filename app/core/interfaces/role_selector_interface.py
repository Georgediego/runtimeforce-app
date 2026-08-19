from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IRoleSelectorService(ABC):
    @abstractmethod
    async def select_model_for_role(
        self,
        role: str,
        required_capabilities: List[str],
        mode: str,
        user_plan: str,
        user_id: str,
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Dynamically selects best matching model for a role.
        Only considers models present in enabled_models list.
        If enabled_models is None, all discovered models are eligible.
        If enabled_models is [], no models are eligible (user unchecked all).
        """
        pass

    @abstractmethod
    async def select_cheapest_model(
        self,
        required_capabilities: List[str],
        user_plan: str,
        user_id: str,
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Selects cheapest available model matching capabilities.
        Respects enabled_models strict filter.
        """
        pass

    @abstractmethod
    async def select_most_powerful_model(
        self,
        required_capabilities: List[str],
        user_plan: str,
        user_id: str,
        enabled_models: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Selects most powerful available model matching capabilities.
        Respects enabled_models strict filter.
        """
        pass
