import os
import aiohttp
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.interfaces.x_oauth_service_interface import IXOAuthService
from app.repository.oauth_db_repository import OAuthDBRepository

class XOAuthService(IXOAuthService):
    """X.com (Twitter) OAuth 2.0 implementation for project-based authentication."""

    def __init__(self, oauth_repository: OAuthDBRepository):
        self.oauth_repository = oauth_repository
        self.client_id = os.getenv("X_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("X_OAUTH_CLIENT_SECRET")
        self.redirect_uri = os.getenv("X_OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/x/callback")

    def get_authorization_url(self, project_id: str) -> str:
        """Generate X.com OAuth 2.0 authorization URL with PKCE."""
        import secrets
        
        # Generate code verifier and challenge (PKCE)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()
        
        # Store verifier temporarily (in production, use Redis/cache)
        state = secrets.token_urlsafe(32)
        
        return (
            f"https://twitter.com/i/oauth2/authorize"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope=tweet.read%20tweet.write%20users.read"
            f"&state={project_id}:{state}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

    async def exchange_code_for_token(self, code: str, project_id: str) -> Dict[str, Any]:
        """Exchange OAuth code for access/refresh tokens."""
        # Note: In production, retrieve code_verifier from cache using state
        code_verifier = "placeholder_verifier"  # TODO: Retrieve from secure storage
        
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(login=self.client_id, password=self.client_secret)
            
            async with session.post(
                "https://api.twitter.com/2/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
                    raise Exception(f"X.com token exchange failed: {response.status} - {error_text}")
                
                data = await response.json()
                
                if "access_token" not in data:
                    raise Exception("No access token in X.com response")
                
                # Save tokens to repository
                token_data = {
                    "access_token": data["access_token"],
                    "token_type": data.get("token_type", "bearer"),
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": data.get("expires_in"),  # 2 hours typically
                    "expires_at": None,  # Will be calculated
                    "scope": data.get("scope", ""),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                # Calculate expiration time
                if data.get("expires_in"):
                    from datetime import timedelta
                    expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])
                    token_data["expires_at"] = expires_at.isoformat()
                
                success = await self.oauth_repository.save_token(project_id, "x", token_data)
                if not success:
                    raise Exception("Failed to save X.com token")
                
                return token_data

    async def refresh_token(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Refresh expired access token using refresh token."""
        token_data = await self.oauth_repository.get_token(project_id, "x")
        if not token_data or not token_data.get("refresh_token"):
            return None
        
        refresh_token = token_data["refresh_token"]
        
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(login=self.client_id, password=self.client_secret)
            
            async with session.post(
                "https://api.twitter.com/2/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
                    "expires_in": data.get("expires_in"),
                    "expires_at": None,
                    "scope": data.get("scope", ""),
                    "created_at": datetime.utcnow().isoformat()
                }
                
                if data.get("expires_in"):
                    from datetime import timedelta
                    expires_at = datetime.utcnow() + timedelta(seconds=data["expires_in"])
                    new_token_data["expires_at"] = expires_at.isoformat()
                
                success = await self.oauth_repository.save_token(project_id, "x", new_token_data)
                if not success:
                    return None
                
                return new_token_data

    async def revoke_token(self, project_id: str) -> bool:
        """Revoke X.com access token."""
        token_data = await self.oauth_repository.get_token(project_id, "x")
        if not token_data:
            return False
        
        access_token = token_data.get("access_token")
        
        # Revoke token via X API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.twitter.com/2/oauth2/revoke",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"token": access_token}
            ) as response:
                pass  # Ignore response, delete locally anyway
        
        return await self.oauth_repository.delete_token(project_id, "x")

    async def get_user_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get X.com user information using stored token."""
        token_data = await self.oauth_repository.get_token(project_id, "x")
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
                "https://api.twitter.com/2/users/me",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                },
                params={"user.fields": "id,name,username,profile_image_url"}
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return data.get("data")

    async def post_tweet(self, project_id: str, text: str, media_ids: Optional[list] = None) -> Dict[str, Any]:
        """Post a tweet using stored credentials."""
        token_data = await self.oauth_repository.get_token(project_id, "x")
        if not token_data:
            raise Exception("X.com not connected")
        
        access_token = token_data.get("access_token")
        
        # Refresh if expired
        if token_data.get("expires_at"):
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if expires_at < datetime.utcnow():
                token_data = await self.refresh_token(project_id)
                if not token_data:
                    raise Exception("X.com token expired and refresh failed")
                access_token = token_data.get("access_token")
        
        payload = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.twitter.com/2/tweets",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json=payload
            ) as response:
                if response.status != 201 and response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Failed to post tweet: {response.status} - {error_text}")
                
                return await response.json()


# Import hashlib at module level
import hashlib
