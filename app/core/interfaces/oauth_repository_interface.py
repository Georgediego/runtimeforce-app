from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime

class IOAuthRepository(ABC):
    """Interface for storing and retrieving OAuth tokens securely."""

    @abstractmethod
    async def save_token(self, project_id: str, provider: str, token_data: Dict[str, Any]) -> bool:
        """Save or update OAuth token data for a project."""
        pass

    @abstractmethod
    async def get_token(self, project_id: str, provider: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth token data for a project."""
        pass

    @abstractmethod
    async def delete_token(self, project_id: str, provider: str) -> bool:
        """Revoke and delete OAuth token data."""
        pass

    @abstractmethod
    async def is_connected(self, project_id: str, provider: str) -> bool:
        """Check if a provider is connected."""
        pass
