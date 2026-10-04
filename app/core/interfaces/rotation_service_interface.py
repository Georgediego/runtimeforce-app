from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IRotationService(ABC):
    @abstractmethod
    def is_model_available(self, model_id: str) -> bool:
        pass

    @abstractmethod
    def is_provider_available(self, provider: str) -> bool:
        pass

    @abstractmethod
    def is_provider_degraded(self, provider: str) -> bool:
        pass

    @abstractmethod
    def mark_model_failed(self, model_id: str, provider: str, error: str) -> None:
        pass

    @abstractmethod
    def mark_provider_permanent_failure(self, provider: str) -> None:
        pass

    @abstractmethod
    def mark_provider_cooldown(self, provider: str, duration: float) -> None:
        pass

    @abstractmethod
    def get_available_models(self, all_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass
