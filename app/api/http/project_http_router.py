"""
HTTP API Router for Project Management with Tier Limits Enforcement.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user, JWTAuthService
from app.container import get_project_service
from app.services.project.project_service import ProjectService

logger = logging.getLogger("runtimeforce.api.http.project")
router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

class ProjectPayload(BaseModel):
    name: str
    workspace_path: Optional[str] = ""
    ssh_host: Optional[str] = ""
    ssh_port: Optional[int] = 22
    ssh_username: Optional[str] = ""
    project_context: Optional[str] = ""
    rules_of_engagement: Optional[str] = ""
    github_remote_url: Optional[str] = ""
    github_pat_enc: Optional[str] = ""
    x_api_key_enc: Optional[str] = ""
    reddit_client_id_enc: Optional[str] = ""
    reddit_client_secret_enc: Optional[str] = ""
    git_mode: Optional[str] = "manual"
    git_branch_main: Optional[str] = "main"
    git_branch_dev: Optional[str] = "dev"
    version_scheme: Optional[str] = "semver"
    prerelease_tag: Optional[str] = ""
    current_version: Optional[str] = "v1.0.0"

class BumpVersionPayload(BaseModel):
    changelog: str
    bump_type: Optional[str] = "patch"
    commit_hash: Optional[str] = None

@router.get("")
async def list_projects(
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    return {"projects": service.list_projects(user_id)}

@router.post("")
async def create_project(
    payload: ProjectPayload,
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    plan = JWTAuthService.extract_plan_from_jwt(token)
    res = service.create_project(user_id, payload.dict(), plan=plan)
    if "error" in res and res.get("status") == "limit_reached":
        raise HTTPException(403, detail=res["error"])
    return res

@router.get("/{project_id}")
async def get_project(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    proj = service.get_project_details(project_id, user_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj

@router.post("/{project_id}/activate")
async def activate_project(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    service.activate_project(project_id, user_id)
    return {"status": "success", "active_id": project_id}

@router.put("/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectPayload,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    updated = service.update_project(project_id, user_id, payload.dict())
    if not updated:
        raise HTTPException(404, "Project not found or no changes made")
    return {"status": "success", "id": project_id}

@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    deleted = service.delete_project(project_id, user_id)
    if not deleted:
        raise HTTPException(404, "Project not found")
    return {"status": "success", "id": project_id}

@router.post("/{project_id}/bump-version")
async def bump_version(
    project_id: str,
    payload: BumpVersionPayload,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service)
):
    res = service.bump_version(project_id, user_id, payload.changelog, payload.bump_type, payload.commit_hash)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res
