import os
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.interfaces.github_oauth_service_interface import IGitHubOAuthService
from app.repository.oauth_db_repository import OAuthDBRepository

class GitHubOAuthService(IGitHubOAuthService):
    """GitHub OAuth implementation for project-based authentication."""

    def __init__(self, oauth_repository: OAuthDBRepository):
        self.oauth_repository = oauth_repository
        self.client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/github/callback")

    def get_authorization_url(self, project_id: str) -> str:
        """Generate GitHub OAuth authorization URL with state parameter."""
        import secrets
        state = secrets.token_urlsafe(32)
        # Store state temporarily to verify callback (could use Redis or in-memory cache)
        # For now, we'll pass it via query param and verify in callback
        scope = "repo user:email workflow"
        return (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope}"
            f"&state={project_id}:{state}"
        )

    async def exchange_code_for_token(self, code: str, project_id: str) -> Dict[str, Any]:
        """Exchange OAuth code for access token."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri
                }
            ) as response:
                if response.status != 200:
                    raise Exception(f"GitHub token exchange failed: {response.status}")
                
                data = await response.json()
                
                if "access_token" not in data:
                    raise Exception("No access token in GitHub response")
                
                # Save token to repository
                token_data = {
                    "access_token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "scope": data.get("scope", ""),
                    "expires_at": None,  # GitHub tokens don't expire by default
                    "refresh_token": data.get("refresh_token"),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                success = await self.oauth_repository.save_token(project_id, "github", token_data)
                if not success:
                    raise Exception("Failed to save GitHub token")
                
                return token_data

    async def refresh_token(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Refresh expired access token (GitHub tokens don't expire, but method kept for interface)."""
        # GitHub personal access tokens don't expire, so no refresh needed
        # But we can re-validate the token
        return await self.get_user_info(project_id)

    async def revoke_token(self, project_id: str) -> bool:
        """Revoke GitHub access token."""
        token_data = await self.oauth_repository.get_token(project_id, "github")
        if not token_data:
            return False
        
        access_token = token_data.get("access_token")
        
        # Revoke token via GitHub API
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                "https://api.github.com/applications/{client_id}/grant",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"Basic {self.client_id}:{self.client_secret}"
                },
                json={"access_token": access_token}
            ) as response:
                # Even if revoke fails, delete from local storage
                pass
        
        return await self.oauth_repository.delete_token(project_id, "github")

    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get GitHub user information using stored token."""
        token_data = await self.oauth_repository.get_token(project_id, "github")
        if not token_data:
            return None
        
        access_token = token_data.get("access_token")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"token {access_token}"
                }
            ) as response:
                if response.status != 200:
                    return None
                
                return await response.json()
