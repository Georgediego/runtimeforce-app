from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class IXOAuthService(ABC):
    """Interface for X.com (Twitter) OAuth 2.0 authentication flow."""

    @abstractmethod
    def get_authorization_url(self, project_id: str) -> str:
        """Generate X.com OAuth 2.0 authorization URL."""
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str, project_id: str) -> Dict[str, Any]:
        """Exchange OAuth code for access/refresh tokens."""
        pass

    @abstractmethod
    async def refresh_token(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Refresh expired access token using refresh token."""
        pass

    @abstractmethod
    async def revoke_token(self, project_id: str) -> bool:
        """Revoke X.com access token."""
        pass

    @abstractmethod
    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get X.com user information using stored token."""
        pass

    @abstractmethod
    async def post_tweet(self, project_id: str, text: str, media_ids: Optional[list] = None) -> Dict[str, Any]:
        """Post a tweet using stored credentials."""
        pass
