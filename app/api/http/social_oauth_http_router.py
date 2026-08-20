"""
Social OAuth HTTP Router - X.com (Twitter) and Reddit authentication flows.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional
import logging

from app.container import get_container
from app.services.social.x_oauth_service import XOAuthService
from app.services.social.reddit_oauth_service import RedditOAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth-social"])


def get_x_oauth():
    container = get_container()
    return container.x_oauth_service


def get_reddit_oauth():
    container = get_container()
    return container.reddit_oauth_service


# ===== X.com (Twitter) OAuth =====

@router.post("/x/authorize")
async def x_authorize(
    request: Request,
    project_id: Optional[str] = Query(None, description="Project ID to associate"),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Generate X.com OAuth authorization URL."""
    try:
        base_url = str(request.base_url).rstrip('/')
        auth_url = service.get_authorization_url(project_id or "default", base_url)
        return {"authorization_url": auth_url, "provider": "x"}
    except Exception as e:
        logger.error(f"X.com OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {str(e)}")


@router.get("/x/callback")
async def x_callback(
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: Optional[str] = Query(None, description="State parameter"),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Handle X.com OAuth callback and exchange code for token."""
    try:
        base_url = str(request.base_url).rstrip('/')
        token_data = service.handle_callback(code, state, base_url)
        
        if not token_data or 'access_token' not in token_data:
            raise HTTPException(status_code=400, detail="Failed to obtain access token")
        
        return {
            "success": True,
            "access_token": token_data.get('access_token'),
            "token_type": token_data.get('token_type', 'bearer'),
            "username": token_data.get('username'),
            "expires_at": token_data.get('expires_at')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"X.com OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Callback failed: {str(e)}")


@router.get("/x/status")
async def x_status(
    project_id: str = Query(..., description="Project ID"),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Check X.com OAuth connection status."""
    try:
        status = service.get_connection_status(project_id)
        return status
    except Exception as e:
        logger.error(f"X.com OAuth status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/x/disconnect")
async def x_disconnect(
    project_id: str = Query(..., description="Project ID"),
    service: XOAuthService = Depends(get_x_oauth)
):
    """Disconnect X.com OAuth."""
    try:
        service.disconnect(project_id)
        return {"success": True, "message": "X.com OAuth disconnected"}
    except Exception as e:
        logger.error(f"X.com OAuth disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Reddit OAuth =====

@router.post("/reddit/authorize")
async def reddit_authorize(
    request: Request,
    project_id: Optional[str] = Query(None, description="Project ID to associate"),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Generate Reddit OAuth authorization URL."""
    try:
        base_url = str(request.base_url).rstrip('/')
        auth_url = service.get_authorization_url(project_id or "default", base_url)
        return {"authorization_url": auth_url, "provider": "reddit"}
    except Exception as e:
        logger.error(f"Reddit OAuth authorize error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {str(e)}")


@router.get("/reddit/callback")
async def reddit_callback(
    request: Request,
    code: str = Query(..., description="Authorization code"),
    state: Optional[str] = Query(None, description="State parameter"),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Handle Reddit OAuth callback and exchange code for token."""
    try:
        base_url = str(request.base_url).rstrip('/')
        token_data = service.handle_callback(code, state, base_url)
        
        if not token_data or 'access_token' not in token_data:
            raise HTTPException(status_code=400, detail="Failed to obtain access token")
        
        return {
            "success": True,
            "access_token": token_data.get('access_token'),
            "token_type": token_data.get('token_type', 'bearer'),
            "username": token_data.get('username'),
            "expires_at": token_data.get('expires_at')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reddit OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Callback failed: {str(e)}")


@router.get("/reddit/status")
async def reddit_status(
    project_id: str = Query(..., description="Project ID"),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Check Reddit OAuth connection status."""
    try:
        status = service.get_connection_status(project_id)
        return status
    except Exception as e:
        logger.error(f"Reddit OAuth status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reddit/disconnect")
async def reddit_disconnect(
    project_id: str = Query(..., description="Project ID"),
    service: RedditOAuthService = Depends(get_reddit_oauth)
):
    """Disconnect Reddit OAuth."""
    try:
        service.disconnect(project_id)
        return {"success": True, "message": "Reddit OAuth disconnected"}
    except Exception as e:
        logger.error(f"Reddit OAuth disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
