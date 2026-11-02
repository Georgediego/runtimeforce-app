"""
HTTP API Router for Social Module, Project Integrations & SaaS OAuth Proxy.
"""
import logging
import uuid
import urllib.parse
import os
import httpx
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse

from app.core.security.jwt_auth_service import JWTAuthService
from app.core.security.aes_crypto_service import AESCryptoService
from app.container import get_project_repo, container
from app.core.security.entitlements import require_plan_feature
from app.services.social.oauth_smm_service import OAuthSMMService

logger = logging.getLogger("runtimeforce.api.http.social")
router = APIRouter(prefix="/api/v1/social", tags=["social"])

class ConnectOAuthPayload(BaseModel):
    project_id: str
    token: Optional[str] = ""
    username: Optional[str] = ""
    email: Optional[str] = ""


class SocialDraftPayload(BaseModel):
    project_id: str
    changelog_entry: str
    platform: str = "x.com"


class SocialDraftPublishPayload(BaseModel):
    project_id: str
    content: str

def get_optional_user(request: Request) -> str:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    u = JWTAuthService.extract_user_from_jwt(token)
    return u or "default_user"

# ═══════════════════════════════════════════════════
# GITHUB OAUTH ENDPOINTS
# ═══════════════════════════════════════════════════
@router.get("/github/auth-url")
@router.post("/github/auth-url")
async def get_github_auth_url(
    request: Request,
    project_id: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
    project_repo = Depends(get_project_repo)
):
    try:
        user_id = get_optional_user(request)
        pid = (project_id or "").strip() or "default"
        smm = OAuthSMMService(project_repo)
        base_url = str(request.base_url).rstrip("/")
        url = smm.get_github_auth_url(pid, user_id, base_url=base_url, ticket=ticket)
        return {"auth_url": url}
    except Exception as e:
        logger.error(f"Failed to get GitHub auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
async def get_x_auth_url(
    request: Request,
    project_id: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
    project_repo = Depends(get_project_repo)
):
    try:
        user_id = get_optional_user(request)
        pid = (project_id or "").strip() or "default"
        smm = OAuthSMMService(project_repo)
        base_url = str(request.base_url).rstrip("/")
        url = smm.get_x_auth_url(pid, user_id, base_url=base_url, ticket=ticket)
        return {"auth_url": url}
    except Exception as e:
        logger.error(f"Failed to get X auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
async def get_reddit_auth_url(
    request: Request,
    project_id: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
    project_repo = Depends(get_project_repo)
):
    try:
        user_id = get_optional_user(request)
        pid = (project_id or "").strip() or "default"
        smm = OAuthSMMService(project_repo)
        base_url = str(request.base_url).rstrip("/")
        url = smm.get_reddit_auth_url(pid, user_id, base_url=base_url, ticket=ticket)
        return {"auth_url": url}
    except Exception as e:
        logger.error(f"Failed to get Reddit auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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


@router.post("/draft")
async def generate_social_draft(
    payload: SocialDraftPayload,
    user_id: str = Depends(require_plan_feature("social_vip")),
):
    changelog = (payload.changelog_entry or "").strip()
    if not changelog:
        raise HTTPException(status_code=422, detail="A changelog entry is required")
    if payload.platform != "x.com":
        raise HTTPException(status_code=400, detail="Only X.com drafts are supported right now")

    project = container.project_service.get_project_details(payload.project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory_context = ""
    try:
        context = await container.context_builder_service.build_optimal_context(
            user_prompt=f"Create an accurate public release post from these changes: {changelog}",
            session_id=f"social-draft-{uuid.uuid4().hex}",
            user_id=user_id,
            project_id=payload.project_id,
            max_context_tokens=2500,
        )
        memory_context = context.get("compiled_memory_context", "")
    except Exception as exc:
        logger.info("Social draft memory context unavailable: %s", type(exc).__name__)

    provider_keys = container.provider_keys_repo.get_all_provider_keys(user_id) or {}
    selected_map = container.provider_keys_repo.get_all_selected_models(user_id) or {}
    enabled_models = [model for models in selected_map.values() if isinstance(models, list) for model in models]
    try:
        candidates = container.llm_router.build_route(
            strategy="auto", model_lock=None, plan="free",
            provider_keys=provider_keys, scores={},
            user_prompt=changelog, enabled_models=enabled_models or None,
            required_capability="chat_completion",
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"No configured text model is available: {exc}") from exc

    prompt = (
        "Write one high-quality X.com launch/update post, maximum 280 characters. "
        "Start with a strong developer pain-point hook. Use concrete changes only; "
        "do not invent metrics, features, users, or claims. Use short readable lines and "
        "at most two bullets. No generic 'we updated' announcement. Return only the post text.\n\n"
        f"Project: {project.get('name') or 'Current project'}\n"
        f"Project context: {project.get('project_context') or ''}\n"
        f"Relevant local memory: {memory_context}\n"
        f"Verified changes from Git history/changelog:\n{changelog}"
    )
    last_error = "The selected model returned no content."
    for model_id in candidates[:3]:
        provider = model_id.split("/", 1)[0] if "/" in model_id else "unknown"
        output = []
        try:
            async for chunk in container.llm_orchestrator.stream_completion(
                messages=[
                    {"role": "system", "content": "You are a concise technical product marketer. Be accurate and specific."},
                    {"role": "user", "content": prompt},
                ],
                model_id=model_id,
                provider=provider,
                temperature=0.35,
                user_id=user_id,
                max_tokens=220,
            ):
                if chunk.get("status") == "streaming":
                    output.append(chunk.get("content", ""))
                elif chunk.get("status") == "error":
                    last_error = chunk.get("error", last_error)
            content = "".join(output).strip().strip('"')
            if content:
                draft_id = f"draft-{uuid.uuid4().hex[:12]}"
                container.social_feed_repo.save_draft(
                    draft_id, payload.project_id, user_id, changelog, content, "x.com"
                )
                return {"draft_id": draft_id, "project_id": payload.project_id, "content": content, "platform": "x.com", "model": model_id}
        except Exception as exc:
            last_error = str(exc)
    raise HTTPException(status_code=502, detail=f"Draft generation failed: {last_error}")


@router.get("/drafts/{project_id}")
async def list_social_drafts(
    project_id: str,
    user_id: str = Depends(require_plan_feature("social_vip")),
):
    return {"drafts": container.social_feed_repo.get_drafts(project_id, user_id)}


@router.post("/drafts/{draft_id}/publish")
async def publish_social_draft(
    draft_id: str,
    payload: SocialDraftPublishPayload,
    request: Request,
    user_id: str = Depends(require_plan_feature("social_vip")),
):
    draft = next((item for item in container.social_feed_repo.get_drafts(payload.project_id, user_id) if item.get("id") == draft_id), None)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    content = (payload.content or "").strip()
    if not content or len(content) > 280:
        raise HTTPException(status_code=422, detail="X.com post must contain 1-280 characters")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="RuntimeForce account session required")
    saas_url = os.getenv("SAAS_URL", "https://runtimeforce.dev").rstrip("/")
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(
            f"{saas_url}/api/v1/social/post",
            headers={"Authorization": auth, "Content-Type": "application/json"},
            json={"platform": "x", "content": content},
        )
    if response.status_code not in (200, 201):
        try:
            detail = response.json().get("detail", "X.com publish failed")
        except Exception:
            detail = "X.com publish failed"
        raise HTTPException(status_code=response.status_code, detail=detail)
    result = response.json()
    container.social_feed_repo.update_draft_status(draft_id, user_id, "published")
    return result
