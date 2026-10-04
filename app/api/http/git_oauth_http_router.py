"""
Git OAuth HTTP Router - GitHub OAuth authentication flow.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
import logging

from app.container import get_container
from app.services.git.github_oauth_service import GitHubOAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth/github", tags=["oauth-github"])


def get_github_oauth():
    container = get_container()
    return container.github_oauth_service


@router.post("/authorize")
async def github_authorize(
    request: Request,
    project_id: Optional[str] = Query(None, description="Project ID to associate"),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Generate GitHub OAuth authorization URL."""
    try:
        base_url = str(request.base_url).rstrip('/')
        auth_url = service.get_authorization_url(project_id or "default", base_url)
        return {"authorization_url": auth_url, "provider": "github"}
    except Exception as e:
        logger.error(f"GitHub OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {str(e)}")


@router.get("/callback")
async def github_callback(
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: Optional[str] = Query(None, description="State parameter"),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Handle GitHub OAuth callback and exchange code for token."""
    try:
        base_url = str(request.base_url).rstrip('/')
        token_data = service.handle_callback(code, state, base_url)
        
        if not token_data or 'access_token' not in token_data:
            raise HTTPException(status_code=400, detail="Failed to obtain access token")
        
        return {
            "success": True,
            "access_token": token_data.get('access_token'),
            "token_type": token_data.get('token_type', 'bearer'),
            "scope": token_data.get('scope', ''),
            "username": token_data.get('username'),
            "expires_at": token_data.get('expires_at')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GitHub OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Callback failed: {str(e)}")


@router.get("/status")
async def github_status(
    project_id: str = Query(..., description="Project ID"),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Check GitHub OAuth connection status for a project."""
    try:
        status = service.get_connection_status(project_id)
        return status
    except Exception as e:
        logger.error(f"GitHub OAuth status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/disconnect")
async def github_disconnect(
    project_id: str = Query(..., description="Project ID"),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Disconnect GitHub OAuth from a project."""
    try:
        service.disconnect(project_id)
        return {"success": True, "message": "GitHub OAuth disconnected"}
    except Exception as e:
        logger.error(f"GitHub OAuth disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
