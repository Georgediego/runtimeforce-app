"""
OAuth HTTP Router for GitHub, X.com (Twitter), and Reddit authentication flows.
Provides endpoints for initiating OAuth, handling callbacks, and managing connections.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional, Dict, Any
import logging

from app.container import get_container
from app.services.git.github_oauth_service import GitHubOAuthService
from app.services.social.x_oauth_service import XOAuthService
from app.services.social.reddit_oauth_service import RedditOAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])


def get_github_oauth():
    container = get_container()
    return container.github_oauth_service


def get_x_oauth():
    container = get_container()
    return container.x_oauth_service


def get_reddit_oauth():
    container = get_container()
    return container.reddit_oauth_service


@router.get("/github/authorize")
async def github_authorize(
    project_id: str = Query(..., description="Project ID to associate with OAuth token"),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Generate GitHub OAuth authorization URL."""
    try:
        auth_url = service.get_authorization_url(project_id)
        return {"authorization_url": auth_url, "provider": "github"}
    except Exception as e:
        logger.error(f"GitHub OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Handle GitHub OAuth callback and exchange code for token."""
    try:
        # Extract project_id from state parameter (format: project_id:state_token)
        parts = state.split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        project_id = parts[0]
        
        # Exchange code for token
        token_data = await service.exchange_code_for_token(code, project_id)
        
        # Get user info
        user_info = await service.get_user_info(project_id)
        
        return {
            "success": True,
            "provider": "github",
            "project_id": project_id,
            "user": user_info,
            "token_expires": token_data.get("expires_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GitHub OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"GitHub authentication failed: {str(e)}")


@router.get("/github/status")
async def github_status(
    project_id: str = Query(...),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Check GitHub connection status for a project."""
    try:
        is_connected = await service.oauth_repository.is_connected(project_id, "github")
        user_info = None
        
        if is_connected:
            user_info = await service.get_user_info(project_id)
        
        return {
            "connected": is_connected,
            "provider": "github",
            "project_id": project_id,
            "user": user_info
        }
    except Exception as e:
        logger.error(f"GitHub status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/github/revoke")
async def github_revoke(
    project_id: str = Query(...),
    service: GitHubOAuthService = Depends(get_github_oauth)
):
    """Revoke GitHub OAuth token."""
    try:
        success = await service.revoke_token(project_id)
        return {"success": success, "provider": "github", "project_id": project_id}
    except Exception as e:
        logger.error(f"GitHub revoke error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# X.com (Twitter) OAuth endpoints


@router.get("/x/authorize")
async def x_authorize(
    project_id: str = Query(...),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Generate X.com OAuth authorization URL."""
    try:
        auth_url = service.get_authorization_url(project_id)
        return {"authorization_url": auth_url, "provider": "x"}
    except Exception as e:
        logger.error(f"X.com OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/x/callback")
async def x_callback(
    code: str = Query(...),
    state: str = Query(...),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Handle X.com OAuth callback."""
    try:
        parts = state.split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        project_id = parts[0]
        token_data = await service.exchange_code_for_token(code, project_id)
        user_info = await service.get_user_info(project_id)
        
        return {
            "success": True,
            "provider": "x",
            "project_id": project_id,
            "user": user_info,
            "token_expires": token_data.get("expires_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"X.com OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"X.com authentication failed: {str(e)}")


@router.get("/x/status")
async def x_status(
    project_id: str = Query(...),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Check X.com connection status."""
    try:
        is_connected = await service.oauth_repository.is_connected(project_id, "x")
        user_info = None
        
        if is_connected:
            user_info = await service.get_user_info(project_id)
        
        return {
            "connected": is_connected,
            "provider": "x",
            "project_id": project_id,
            "user": user_info
        }
    except Exception as e:
        logger.error(f"X.com status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/x/revoke")
async def x_revoke(
    project_id: str = Query(...),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Revoke X.com OAuth token."""
    try:
        success = await service.revoke_token(project_id)
        return {"success": success, "provider": "x", "project_id": project_id}
    except Exception as e:
        logger.error(f"X.com revoke error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Reddit OAuth endpoints


@router.get("/reddit/authorize")
async def reddit_authorize(
    project_id: str = Query(...),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Generate Reddit OAuth authorization URL."""
    try:
        auth_url = service.get_authorization_url(project_id)
        return {"authorization_url": auth_url, "provider": "reddit"}
    except Exception as e:
        logger.error(f"Reddit OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reddit/callback")
async def reddit_callback(
    code: str = Query(...),
    state: str = Query(...),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Handle Reddit OAuth callback."""
    try:
        parts = state.split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        project_id = parts[0]
        token_data = await service.exchange_code_for_token(code, project_id)
        user_info = await service.get_user_info(project_id)
        
        return {
            "success": True,
            "provider": "reddit",
            "project_id": project_id,
            "user": user_info,
            "token_expires": token_data.get("expires_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reddit OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Reddit authentication failed: {str(e)}")


@router.get("/reddit/status")
async def reddit_status(
    project_id: str = Query(...),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Check Reddit connection status."""
    try:
        is_connected = await service.oauth_repository.is_connected(project_id, "reddit")
        user_info = None
        
        if is_connected:
            user_info = await service.get_user_info(project_id)
        
        return {
            "connected": is_connected,
            "provider": "reddit",
            "project_id": project_id,
            "user": user_info
        }
    except Exception as e:
        logger.error(f"Reddit status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reddit/revoke")
async def reddit_revoke(
    project_id: str = Query(...),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Revoke Reddit OAuth token."""
    try:
        success = await service.revoke_token(project_id)
        return {"success": success, "provider": "reddit", "project_id": project_id}
    except Exception as e:
        logger.error(f"Reddit revoke error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
