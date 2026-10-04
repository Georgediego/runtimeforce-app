"""
Abstract interface for generic database and storage persistence repositories.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IStorageRepository(ABC):

    @abstractmethod
    def get_by_id(self, entity_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve entity record by ID and isolated user_id."""
        pass

    @abstractmethod
    def list_all(self, user_id: str) -> List[Dict[str, Any]]:
        """List all entity records belonging to user_id."""
        pass

    @abstractmethod
    def delete(self, entity_id: str, user_id: str) -> bool:
        """Delete record by ID and isolated user_id."""
        pass
