"""
HTTP API Router for Project Management with Tier Limits Enforcement.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import require_plan_feature
from app.container import get_project_service, get_license_service, container
from app.services.project.project_service import ProjectService
from app.services.billing.license_service import LicenseService

logger = logging.getLogger("runtimeforce.api.http.project")

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _unique_ssh_hosts(user_id: str, projects, exclude_project_id: Optional[str] = None):
    hosts = set()
    for project in projects:
        project_id = project.get("id")
        if project_id != exclude_project_id:
            host = str(project.get("ssh_host") or "").strip().lower()
            if host:
                hosts.add((host, int(project.get("ssh_port") or 22)))
        if project_id:
            for workspace in container.workspace_repo.get_all_workspaces(user_id, project_id):
                if str(workspace.get("type") or "").lower() != "ssh":
                    continue
                workspace_host = str(workspace.get("host") or "").strip().lower()
                if workspace_host:
                    hosts.add((workspace_host, int(workspace.get("port") or 22)))
    return hosts


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
    service: ProjectService = Depends(get_project_service),
    license_service: LicenseService = Depends(get_license_service),
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
    entitlements = await license_service.get_entitlements(token)
    if not entitlements.get("valid"):
        raise HTTPException(403, detail="Account entitlements could not be verified")
    limits = entitlements.get("limits") or {}
    features = entitlements.get("features") or {}
    existing_projects = service.list_projects(user_id)

    if payload.ssh_host and payload.ssh_host.strip():
        max_ssh_hosts = max(0, int(limits.get("max_ssh_hosts", 0) or 0))
        current_ssh_hosts = _unique_ssh_hosts(user_id, existing_projects)
        ssh_key = (payload.ssh_host.strip().lower(), int(payload.ssh_port or 22))
        if ssh_key not in current_ssh_hosts and len(current_ssh_hosts) >= max_ssh_hosts:
            raise HTTPException(403, detail="SSH host limit reached for this plan")

    if payload.github_remote_url and payload.github_remote_url.strip():
        if features.get("git") is not True:
            raise HTTPException(403, detail="Git integration is not enabled for this plan")
        max_git_repos = max(0, int(limits.get("git_repos", 0) or 0))
        current_git_repos = sum(1 for project in existing_projects if (project.get("github_remote_url") or "").strip())
        if current_git_repos >= max_git_repos:
            raise HTTPException(403, detail="Git repository limit reached for this plan")

    # Project access is derived from the authoritative project limit.
    # Do not require a duplicate features.projects flag: cached entitlements
    # may omit it while a dynamic plan still grants project slots.
    max_projects = limits.get("max_projects", 0)
    try:
        max_projects = max(0, int(max_projects))
    except (TypeError, ValueError):
        max_projects = 0
    if max_projects <= 0:
        raise HTTPException(403, detail="Project creation is not enabled for this plan")
    res = service.create_project(user_id, payload.dict(), plan=entitlements.get("plan", "free"), max_projects=max_projects)
    if "error" in res:
        status_code = 403 if res.get("status") == "limit_reached" else 500
        raise HTTPException(status_code, detail=res["error"])
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
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
    license_service: LicenseService = Depends(get_license_service),
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
    entitlements = await license_service.get_entitlements(token)
    if not entitlements.get("valid"):
        raise HTTPException(403, detail="Account entitlements could not be verified")

    current = service.get_project_details(project_id, user_id)
    if not current:
        raise HTTPException(404, "Project not found")
    features = entitlements.get("features") or {}
    limits = entitlements.get("limits") or {}
    projects = service.list_projects(user_id)
    new_ssh_host = (payload.ssh_host or "").strip()
    old_ssh_host = (current.get("ssh_host") or "").strip()
    if new_ssh_host and new_ssh_host != old_ssh_host:
        if "ssh" in features and features.get("ssh") is not True:
            raise HTTPException(403, detail="SSH workspaces are not enabled for this plan")
        max_ssh_hosts = max(0, int(limits.get("max_ssh_hosts", 0) or 0))
        other_ssh_hosts = _unique_ssh_hosts(user_id, projects, exclude_project_id=project_id)
        ssh_key = (new_ssh_host.lower(), int(payload.ssh_port or 22))
        if ssh_key not in other_ssh_hosts and len(other_ssh_hosts) >= max_ssh_hosts:
            raise HTTPException(403, detail="SSH host limit reached for this plan")

    new_remote = (payload.github_remote_url or "").strip()
    old_remote = (current.get("github_remote_url") or "").strip()
    if new_remote and new_remote != old_remote:
        if features.get("git") is not True:
            raise HTTPException(403, detail="Git integration is not enabled for this plan")
        max_git_repos = max(0, int(limits.get("git_repos", 0) or 0))
        other_git_repos = sum(
            1 for project in projects
            if project.get("id") != project_id and (project.get("github_remote_url") or "").strip()
        )
        if other_git_repos >= max_git_repos:
            raise HTTPException(403, detail="Git repository limit reached for this plan")

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
    user_id: str = Depends(require_plan_feature("git")),
    service: ProjectService = Depends(get_project_service)
):
    res = service.bump_version(project_id, user_id, payload.changelog, payload.bump_type, payload.commit_hash)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res
