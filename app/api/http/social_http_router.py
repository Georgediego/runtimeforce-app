"""
HTTP API Router for Social Module, Project Integrations & SaaS OAuth Proxy.
"""
import logging
import uuid
import urllib.parse
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse

from app.core.security.jwt_auth_service import JWTAuthService
from app.core.security.aes_crypto_service import AESCryptoService
from app.container import get_project_repo
from app.services.social.oauth_smm_service import OAuthSMMService

logger = logging.getLogger("runtimeforce.api.http.social")
router = APIRouter(prefix="/api/v1/social", tags=["social"])

class ConnectOAuthPayload(BaseModel):
    project_id: str
    token: Optional[str] = ""
    username: Optional[str] = ""
    email: Optional[str] = ""

def get_optional_user(request: Request) -> str:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    u = JWTAuthService.extract_user_from_jwt(token)
    return u or "default_user"

# ═══════════════════════════════════════════════════
# GITHUB OAUTH ENDPOINTS
# ═══════════════════════════════════════════════════
@router.get("/github/auth-url")
@router.post("/github/auth-url")
async def get_github_auth_url(request: Request):
    raise HTTPException(status_code=410, detail="Use the RuntimeForce UI PKCE flow to connect GitHub.")
@router.post("/github/connect-oauth")
async def connect_github_oauth(
    payload: ConnectOAuthPayload,
    request: Request,
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    target_pid = payload.project_id
    if target_pid == "default":
        active_proj = project_repo.get_active_project(user_id)
        if active_proj:
            target_pid = active_proj["id"]
    
    raw_token = payload.token or f"github_oauth_{payload.username or payload.email}"
    enc_token = AESCryptoService.encrypt(raw_token)
    project_repo.update_project(target_pid, user_id, github_pat_enc=enc_token)
    return {"status": "success", "connected": True, "project_id": target_pid}

@router.get("/github/callback", response_class=HTMLResponse)
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    smm = OAuthSMMService(project_repo)
    res = await smm.handle_github_callback(code, state)
    if "error" in res:
        return f"<h3>GitHub Auth Failed: {res['error']}</h3><script>setTimeout(() => window.close(), 3000);</script>"
    return """
    <html>
        <body style="background:#0a0a0f;color:#07f77a;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="text-align:center;">
                <h2>✓ GitHub connected successfully!</h2>
                <p>This window will close automatically.</p>
            </div>
            <script>
                if (window.opener) { window.opener.postMessage({ type: "github_connected" }, "*"); }
                setTimeout(() => window.close(), 1000);
            </script>
        </body>
    </html>
    """

@router.post("/github/disconnect")
async def disconnect_github(
    request: Request,
    project_id: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    project_repo.update_project(project_id, user_id, github_pat_enc="")
    return {"status": "disconnected"}

# ═══════════════════════════════════════════════════
# X.COM (TWITTER) OAUTH 2.0 ENDPOINTS
# ═══════════════════════════════════════════════════
@router.get("/x/auth-url")
@router.post("/x/auth-url")
async def get_x_auth_url(request: Request):
    raise HTTPException(status_code=410, detail="Use the RuntimeForce UI PKCE flow to connect X.")
@router.post("/x/connect-oauth")
async def connect_x_oauth(
    payload: ConnectOAuthPayload,
    request: Request,
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    target_pid = payload.project_id
    if target_pid == "default":
        active_proj = project_repo.get_active_project(user_id)
        if active_proj:
            target_pid = active_proj["id"]
    
    raw_token = payload.token or f"x_oauth_{payload.username}"
    enc_token = AESCryptoService.encrypt(raw_token)
    username = payload.username or (payload.email.split("@")[0] if payload.email else "user")
    project_repo.update_project(target_pid, user_id, x_api_key_enc=enc_token, x_username=username)
    return {"status": "success", "connected": True, "username": username, "project_id": target_pid}

@router.get("/x/callback", response_class=HTMLResponse)
async def x_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    smm = OAuthSMMService(project_repo)
    res = await smm.handle_x_callback(code, state)
    if "error" in res:
        return f"<h3>X Authentication Failed: {res['error']}</h3><script>setTimeout(() => window.close(), 3000);</script>"
    return """
    <html>
        <body style="background:#0a0a0f;color:#07f77a;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="text-align:center;">
                <h2>✓ Connected to X.com successfully!</h2>
                <p>This window will close automatically.</p>
            </div>
            <script>
                if (window.opener) { window.opener.postMessage({ type: "x_connected" }, "*"); }
                setTimeout(() => window.close(), 1000);
            </script>
        </body>
    </html>
    """

@router.post("/x/disconnect")
async def disconnect_x(
    request: Request,
    project_id: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    project_repo.update_project(project_id, user_id, x_api_key_enc="", x_refresh_token_enc="", x_username="")
    return {"status": "disconnected"}

# ═══════════════════════════════════════════════════
# REDDIT OAUTH 2.0 ENDPOINTS
# ═══════════════════════════════════════════════════
@router.get("/reddit/auth-url")
@router.post("/reddit/auth-url")
async def get_reddit_auth_url(request: Request):
    raise HTTPException(status_code=410, detail="Use the RuntimeForce UI PKCE flow to connect Reddit.")
@router.post("/reddit/connect-oauth")
async def connect_reddit_oauth(
    payload: ConnectOAuthPayload,
    request: Request,
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    target_pid = payload.project_id
    if target_pid == "default":
        active_proj = project_repo.get_active_project(user_id)
        if active_proj:
            target_pid = active_proj["id"]
    
    raw_token = payload.token or f"reddit_oauth_{payload.username}"
    enc_token = AESCryptoService.encrypt(raw_token)
    username = payload.username or (payload.email.split("@")[0] if payload.email else "user")
    project_repo.update_project(target_pid, user_id, reddit_client_id_enc=enc_token, reddit_username=username)
    return {"status": "success", "connected": True, "username": username, "project_id": target_pid}

@router.get("/reddit/callback", response_class=HTMLResponse)
async def reddit_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    smm = OAuthSMMService(project_repo)
    res = await smm.handle_reddit_callback(code, state)
    if "error" in res:
        return f"<h3>Reddit Authentication Failed: {res['error']}</h3><script>setTimeout(() => window.close(), 3000);</script>"
    return """
    <html>
        <body style="background:#0a0a0f;color:#ff4500;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="text-align:center;">
                <h2>✓ Connected to Reddit successfully!</h2>
                <p>This window will close automatically.</p>
            </div>
            <script>
                if (window.opener) { window.opener.postMessage({ type: "reddit_connected" }, "*"); }
                setTimeout(() => window.close(), 1000);
            </script>
        </body>
    </html>
    """

@router.get("/reddit/subreddits")
async def get_reddit_subreddits(
    request: Request,
    project_id: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    smm = OAuthSMMService(project_repo)
    subs = await smm.get_user_subreddits(project_id, user_id)
    return {"subreddits": subs}

@router.post("/reddit/disconnect")
async def disconnect_reddit(
    request: Request,
    project_id: str = Query(...),
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    project_repo.update_project(project_id, user_id, reddit_client_id_enc="", reddit_client_secret_enc="", reddit_username="", reddit_subreddit="")
    return {"status": "disconnected"}

@router.get("/status/{project_id}")
async def get_social_status(
    request: Request,
    project_id: str,
    project_repo = Depends(get_project_repo)
):
    user_id = get_optional_user(request)
    proj = project_repo.get_project(project_id, user_id)
    if not proj:
        return {
            "x_connected": False, "x_username": "",
            "reddit_connected": False, "reddit_username": "", "reddit_subreddit": "r/buildinpublic",
            "github_connected": False,
        }
    return {
        "x_connected": bool(proj.get("x_api_key_enc")),
        "x_username": proj.get("x_username", ""),
        "reddit_connected": bool(proj.get("reddit_client_id_enc")),
        "reddit_username": proj.get("reddit_username", ""),
        "reddit_subreddit": proj.get("reddit_subreddit", "r/buildinpublic"),
        "github_connected": bool(proj.get("github_pat_enc")),
    }
