from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class IRedditOAuthService(ABC):
    """Interface for Reddit OAuth 2.0 authentication flow."""

    @abstractmethod
    def get_authorization_url(self, project_id: str) -> str:
        """Generate Reddit OAuth 2.0 authorization URL."""
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
        """Revoke Reddit access token (note: Reddit doesn't support token revocation)."""
        pass

    @abstractmethod
    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get Reddit user information using stored token."""
        pass

    @abstractmethod
    async def post_submission(self, project_id: str, subreddit: str, title: str, text: str = None, url: str = None) -> Dict[str, Any]:
        """Post a submission (link or text) to Reddit."""
        pass
