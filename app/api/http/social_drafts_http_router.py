"""Authenticated local social-draft workflows. OAuth credentials remain on RuntimeForce SaaS."""
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.container import container
from app.core.security.entitlements import require_plan_feature

logger = logging.getLogger("runtimeforce.api.http.social_drafts")
router = APIRouter(prefix="/api/v1/social", tags=["social"])

SAAS_SOCIAL_POST_URL = "https://runtimeforce.dev/api/v1/social/post"


class SocialDraftPayload(BaseModel):
    project_id: str
    changelog_entry: str
    platform: str = "x.com"


class SocialDraftPublishPayload(BaseModel):
    project_id: str
    content: str
    media_ids: list[str] = Field(default_factory=list)


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
    enabled_models = [
        model for models in selected_map.values() if isinstance(models, list)
        for model in models
    ]
    try:
        candidates = container.llm_router.build_route(
            strategy="auto", model_lock=None, plan="free",
            provider_keys=provider_keys, scores={},
            user_prompt=changelog, enabled_models=enabled_models or None,
            required_capability="chat_completion",
        )
        model_catalog = container.llm_registry.get_available_models(required_capability="chat_completion")
        free_model_ids = {
            model.id for model in model_catalog
            if getattr(model, "tier", "") == "free" or ":free" in model.id.lower()
        }
        candidates.sort(key=lambda model_id: 0 if model_id in free_model_ids else 1)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"No configured text model is available: {exc}") from exc

    prompt = (
        "Write one high-quality X.com launch/update post, maximum 280 characters. "
        "The first sentence must be a sharp developer pain-point hook; the next line must show how this change helps. "
        "Use concrete changes only; do not invent metrics, features, users, or claims. Use short readable paragraphs "
        "and up to two compact bullets where they fit. No generic 'we updated' announcement. Return only the post text.\n\n"
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
            if content and len(content) > 280:
                last_error = "Generated post exceeded X.com's 280-character limit."
                continue
            if content:
                draft_id = f"draft-{uuid.uuid4().hex[:12]}"
                container.social_feed_repo.save_draft(
                    draft_id, payload.project_id, user_id, changelog, content, "x.com"
                )
                return {
                    "draft_id": draft_id, "project_id": payload.project_id,
                    "content": content, "platform": "x.com", "model": model_id,
                }
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
    draft = next(
        (item for item in container.social_feed_repo.get_drafts(payload.project_id, user_id)
         if item.get("id") == draft_id),
        None,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    content = (payload.content or "").strip()
    if not content or len(content) > 280:
        raise HTTPException(status_code=422, detail="X.com post must contain 1-280 characters")
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="RuntimeForce account session required")

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
        response = await client.post(
            SAAS_SOCIAL_POST_URL,
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            json={"platform": "x", "content": content, "media_ids": payload.media_ids},
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
