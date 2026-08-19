"""
HTTP API Router for Studio Plan Social Build-in-Public module and Feedback Loop.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_social_service
from app.services.social.social_post_generator_service import SocialPostGeneratorService

logger = logging.getLogger("runtimeforce.api.http.social")
router = APIRouter(prefix="/api/v1/social", tags=["social"])

class DraftPostPayload(BaseModel):
    project_id: str
    changelog_entry: str
    platform: Optional[str] = "x.com"

@router.post("/draft")
async def generate_draft(
    payload: DraftPostPayload,
    user_id: str = Depends(require_authenticated_user),
    social_service: SocialPostGeneratorService = Depends(get_social_service)
):
    return await social_service.generate_post_draft(payload.project_id, payload.changelog_entry, payload.platform)

@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    user_id: str = Depends(require_authenticated_user),
    social_service: SocialPostGeneratorService = Depends(get_social_service)
):
    success = await social_service.approve_and_publish(draft_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Draft not found or approval failed")
    return {"status": "published", "draft_id": draft_id}

@router.get("/feedback/{project_id}")
async def get_feedback(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    social_service: SocialPostGeneratorService = Depends(get_social_service)
):
    items = await social_service.fetch_incoming_feedback(project_id)
    return {"project_id": project_id, "feedback": items}
