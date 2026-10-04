import os
import aiohttp
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.interfaces.reddit_oauth_service_interface import IRedditOAuthService
from app.repository.oauth_db_repository import OAuthDBRepository

class RedditOAuthService(IRedditOAuthService):
    """Reddit OAuth 2.0 implementation for project-based authentication."""

    def __init__(self, oauth_repository: OAuthDBRepository):
        self.oauth_repository = oauth_repository
        self.client_id = os.getenv("REDDIT_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("REDDIT_OAUTH_CLIENT_SECRET")
        self.redirect_uri = os.getenv("REDDIT_OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/reddit/callback")
        self.user_agent = os.getenv("REDDIT_USER_AGENT", "RuntimeForce/1.0 by /u/yourusername")

    def get_authorization_url(self, project_id: str) -> str:
        """Generate Reddit OAuth 2.0 authorization URL with PKCE."""
        import secrets
        
        # Generate code verifier and challenge (PKCE)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()
        
        state = secrets.token_urlsafe(32)
        
        return (
            f"https://www.reddit.com/api/v1/authorize"
            f"?client_id={self.client_id}"
            f"&response_type=code"
            f"&state={project_id}:{state}"
            f"&redirect_uri={self.redirect_uri}"
            f"&duration=permanent"
            f"&scope=submit%20read%20identity"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

    async def exchange_code_for_token(self, code: str, project_id: str) -> Dict[str, Any]:
        """Exchange OAuth code for access/refresh tokens."""
        code_verifier = "placeholder_verifier"  # TODO: Retrieve from secure storage
        
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(login=self.client_id, password=self.client_secret)
            
            async with session.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.user_agent
                },
                auth=auth,
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": code_verifier
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Reddit token exchange failed: {response.status} - {error_text}")
                
                data = await response.json()
                
                if "access_token" not in data:
                    raise Exception("No access token in Reddit response")
                
                # Save tokens to repository
                token_data = {
                    "access_token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in", 3600),  # 1 hour default
                    "expires_at": None,
                    "scope": data.get("scope", ""),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                # Calculate expiration time
                from datetime import timedelta
                expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
                token_data["expires_at"] = expires_at.isoformat()
                
                success = await self.oauth_repository.save_token(project_id, "reddit", token_data)
                if not success:
                    raise Exception("Failed to save Reddit token")
                
                return token_data

    async def refresh_token(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Refresh expired access token using refresh token."""
        token_data = await self.oauth_repository.get_token(project_id, "reddit")
        if not token_data or not token_data.get("refresh_token"):
            return None
        
        refresh_token = token_data["refresh_token"]
        
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(login=self.client_id, password=self.client_secret)
            
            async with session.post(
                "https://www.reddit.com/api/v1/access_token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.user_agent
                },
                auth=auth,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                }
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                
                # Update stored tokens
                new_token_data = {
                    "access_token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "refresh_token": data.get("refresh_token", refresh_token),
                    "expires_in": data.get("expires_in", 3600),
                    "expires_at": None,
                    "scope": data.get("scope", ""),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                from datetime import timedelta
                expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
                new_token_data["expires_at"] = expires_at.isoformat()
                
                success = await self.oauth_repository.save_token(project_id, "reddit", new_token_data)
                if not success:
                    return None
                
                return new_token_data

    async def revoke_token(self, project_id: str) -> bool:
        """Revoke Reddit access token (Reddit doesn't support revocation, just delete locally)."""
        # Reddit API doesn't support token revocation
        # We can only delete from local storage
        return await self.oauth_repository.delete_token(project_id, "reddit")

    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get Reddit user information using stored token."""
        token_data = await self.oauth_repository.get_token(project_id, "reddit")
        if not token_data:
            return None
        
        access_token = token_data.get("access_token")
        
        # Check if token is expired and refresh if needed
        if token_data.get("expires_at"):
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if expires_at < datetime.utcnow():
                token_data = await self.refresh_token(project_id)
                if not token_data:
                    return None
                access_token = token_data.get("access_token")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://oauth.reddit.com/api/v1/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": self.user_agent,
                    "Accept": "application/json"
                }
            ) as response:
                if response.status != 200:
                    return None
                
                return await response.json()

    async def post_submission(self, project_id: str, subreddit: str, title: str, text: str = None, url: str = None) -> Dict[str, Any]:
        """Post a submission (link or text) to Reddit."""
        token_data = await self.oauth_repository.get_token(project_id, "reddit")
        if not token_data:
            raise Exception("Reddit not connected")
        
        access_token = token_data.get("access_token")
        
        # Refresh if expired
        if token_data.get("expires_at"):
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if expires_at < datetime.utcnow():
                token_data = await self.refresh_token(project_id)
                if not token_data:
                    raise Exception("Reddit token expired and refresh failed")
                access_token = token_data.get("access_token")
        
        # Prepare form data
        form_data = aiohttp.FormData()
        form_data.add_field("api_type", "json")
        form_data.add_field("title", title)
        form_data.add_field("sr", subreddit)
        
        if url:
            form_data.add_field("url", url)
            form_data.add_field("kind", "link")
        elif text:
            form_data.add_field("text", text)
            form_data.add_field("kind", "self")
        else:
            raise Exception("Either text or url must be provided")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://oauth.reddit.com/api/submit",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": self.user_agent,
                    "Accept": "application/json"
                },
                data=form_data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Failed to post to Reddit: {response.status} - {error_text}")
                
                result = await response.json()
                
                # Extract post ID from response
                if "json" in result and "data" in result["json"]:
                    post_data = result["json"]["data"]
                    return {
                        "id": post_data.get("id"),
                        "url": post_data.get("url"),
                        "name": post_data.get("name")
                    }
                
                raise Exception("Unexpected Reddit response format")


# Import hashlib at module level
import hashlib
