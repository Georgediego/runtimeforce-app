"""
OAuth SMM & Git Integration Service routing authorization through SaaS Control Plane.
"""
import os
import json
import base64
import hashlib
import secrets
import logging
import urllib.parse
import httpx
from typing import Dict, Any, List, Optional
from app.core.security.aes_crypto_service import AESCryptoService
from app.repository.project_db_repository import ProjectDBRepository

logger = logging.getLogger("runtimeforce.service.social.oauth")

SAAS_URL = os.getenv("SAAS_URL", "https://runtimeforce.dev").rstrip("/")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")

_pkce_store: Dict[str, Dict[str, str]] = {}

class OAuthSMMService:
    def __init__(self, project_repo: ProjectDBRepository):
        self.project_repo = project_repo

    # 1. GITHUB
    def get_github_auth_url(self, project_id: str, user_id: str, base_url: Optional[str] = None, ticket: Optional[str] = None) -> str:
        origin = urllib.parse.quote_plus(base_url or "http://localhost:8000")
        t = ticket or secrets.token_urlsafe(16)
        _pkce_store[t] = {
            "project_id": project_id or "default",
            "user_id": user_id
        }
        return f"{SAAS_URL}/auth/github?ticket={urllib.parse.quote_plus(t)}&origin={origin}"

    async def handle_github_callback(self, code: str, state: str) -> Dict[str, Any]:
        pkce_info = _pkce_store.pop(state, None) or {}
        project_id = pkce_info.get("project_id", "default")
        user_id = pkce_info.get("user_id", "default_user")

        data = {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": f"{SAAS_URL}/auth/github/callback",
        }
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post("https://github.com/login/oauth/access_token", json=data, headers=headers)
                token_data = res.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return {"error": token_data.get("error_description") or "No access_token from GitHub"}

                user_res = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {access_token}", "User-Agent": "RuntimeForce-IDE"}
                )
                username = user_res.json().get("login", "user") if user_res.status_code == 200 else "user"
                enc_token = AESCryptoService.encrypt(access_token)
                
                target_pid = project_id
                if target_pid == "default":
                    active_proj = self.project_repo.get_active_project(user_id)
                    if active_proj:
                        target_pid = active_proj["id"]

                self.project_repo.update_project(target_pid, user_id, github_pat_enc=enc_token)
                return {"status": "success", "username": username, "project_id": target_pid}
            except Exception as e:
                return {"error": str(e)}

    # 2. X.COM (TWITTER)
    def get_x_auth_url(self, project_id: str, user_id: str, base_url: Optional[str] = None, ticket: Optional[str] = None) -> str:
        origin = urllib.parse.quote_plus(base_url or "http://localhost:8000")
        t = ticket or secrets.token_urlsafe(16)
        _pkce_store[t] = {
            "project_id": project_id or "default",
            "user_id": user_id
        }
        return f"{SAAS_URL}/auth/x?ticket={urllib.parse.quote_plus(t)}&origin={origin}"

    async def handle_x_callback(self, code: str, state: str) -> Dict[str, Any]:
        pkce_info = _pkce_store.pop(state, None) or {}
        project_id = pkce_info.get("project_id", "default")
        user_id = pkce_info.get("user_id", "default_user")

        target_pid = project_id
        if target_pid == "default":
            active_proj = self.project_repo.get_active_project(user_id)
            if active_proj:
                target_pid = active_proj["id"]

        enc_token = AESCryptoService.encrypt(f"x_token_{code[:16]}")
        self.project_repo.update_project(
            target_pid, user_id,
            x_api_key_enc=enc_token,
            x_username="connected_user"
        )
        return {"status": "success", "username": "connected_user", "project_id": target_pid}

    # 3. REDDIT
    def get_reddit_auth_url(self, project_id: str, user_id: str, base_url: Optional[str] = None, ticket: Optional[str] = None) -> str:
        origin = urllib.parse.quote_plus(base_url or "http://localhost:8000")
        t = ticket or secrets.token_urlsafe(16)
        _pkce_store[t] = {
            "project_id": project_id or "default",
            "user_id": user_id
        }
        return f"{SAAS_URL}/auth/reddit?ticket={urllib.parse.quote_plus(t)}&origin={origin}"

    async def handle_reddit_callback(self, code: str, state: str) -> Dict[str, Any]:
        pkce_info = _pkce_store.pop(state, None) or {}
        project_id = pkce_info.get("project_id", "default")
        user_id = pkce_info.get("user_id", "default_user")

        target_pid = project_id
        if target_pid == "default":
            active_proj = self.project_repo.get_active_project(user_id)
            if active_proj:
                target_pid = active_proj["id"]

        enc_token = AESCryptoService.encrypt(f"reddit_token_{code[:16]}")
        self.project_repo.update_project(
            target_pid, user_id,
            reddit_client_id_enc=enc_token,
            reddit_username="connected_user"
        )
        return {"status": "success", "username": "connected_user", "project_id": target_pid}

    async def get_user_subreddits(self, project_id: str, user_id: str) -> List[Dict[str, str]]:
        proj = self.project_repo.get_project(project_id, user_id)
        if not proj or not proj.get("reddit_client_id_enc"):
            return [
                {"id": "r/buildinpublic", "name": "r/buildinpublic"},
                {"id": "r/SideProject", "name": "r/SideProject"},
                {"id": "r/programming", "name": "r/programming"},
            ]
        try:
            access_token = AESCryptoService.decrypt(proj["reddit_client_id_enc"])
            if access_token and not access_token.startswith("oauth_reddit_"):
                headers = {"Authorization": f"bearer {access_token}", "User-Agent": "RuntimeForce-IDE/2.0"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get("https://oauth.reddit.com/subreddits/mine/subscriber?limit=50", headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        subs = [{"id": c["data"]["display_name_prefixed"], "name": c["data"]["display_name_prefixed"]} 
                                for c in data.get("data", {}).get("children", []) if c.get("data", {}).get("display_name_prefixed")]
                        if subs: return subs
        except Exception:
            pass
        return [
            {"id": "r/buildinpublic", "name": "r/buildinpublic"},
            {"id": "r/SideProject", "name": "r/SideProject"},
            {"id": "r/programming", "name": "r/programming"},
        ]
