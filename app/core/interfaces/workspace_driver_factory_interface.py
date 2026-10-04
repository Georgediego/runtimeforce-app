from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.core.interfaces.workspace_driver_interface import IWorkspaceDriver

class IWorkspaceDriverFactory(ABC):
    @abstractmethod
    def create_driver(self, ws: Dict[str, Any], user_id: str) -> Optional[IWorkspaceDriver]:
        """Instantiate workspace execution driver by configuration and user_id."""
        pass
