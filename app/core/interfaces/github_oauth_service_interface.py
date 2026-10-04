from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class IGitHubOAuthService(ABC):
    """Interface for GitHub OAuth authentication flow."""

    @abstractmethod
    def get_authorization_url(self, project_id: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str, project_id: str) -> Dict[str, Any]:
        """Exchange OAuth code for access token."""
        pass

    @abstractmethod
    async def refresh_token(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Refresh expired access token."""
        pass

    @abstractmethod
    async def revoke_token(self, project_id: str) -> bool:
        """Revoke GitHub access token."""
        pass

    @abstractmethod
    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get GitHub user information using stored token."""
        pass
