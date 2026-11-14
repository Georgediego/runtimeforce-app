"""
HTTP API Router for Project Management with Tier Limits Enforcement.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_project_service, get_license_service
from app.services.project.project_service import ProjectService
from app.services.billing.license_service import LicenseService
from app.core.security.entitlements import get_plan_entitlements, require_feature, require_limit, plan_limit

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

def _known_ssh_hosts(service: ProjectService, user_id: str, projects: list) -> set[str]:
    hosts = {
        str(project.get("ssh_host") or "").strip().lower()
        for project in projects
        if str(project.get("ssh_host") or "").strip()
    }
    workspace_repo = getattr(service, "workspace_repo", None)
    if workspace_repo:
        for project in projects:
            project_id = str(project.get("id") or "")
            if not project_id:
                continue
            for workspace in workspace_repo.get_all_workspaces(user_id=user_id, project_id=project_id):
                host = str(workspace.get("host") or "").strip().lower()
                if host and (str(workspace.get("type") or "").lower() in {"ssh", "remote"} or host not in {"localhost", "127.0.0.1"}):
                    hosts.add(host)
    return hosts


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
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    max_projects = plan_limit(entitlements, "max_projects")
    existing_projects = service.list_projects(user_id)
    if len(existing_projects) >= max_projects:
        require_limit(entitlements, "max_projects", len(existing_projects), "Active Projects")

    github_remote = (payload.github_remote_url or "").strip()
    if github_remote:
        require_feature(entitlements, "git")
        known_repos = {
            str(project.get("github_remote_url") or "").strip().rstrip("/").lower()
            for project in existing_projects
            if str(project.get("github_remote_url") or "").strip()
        }
        if github_remote.rstrip("/").lower() not in known_repos:
            require_limit(entitlements, "git_repos", len(known_repos), "Git Repositories")

    ssh_host = (payload.ssh_host or "").strip().lower()
    if ssh_host:
        known_hosts = _known_ssh_hosts(service, user_id, existing_projects)
        if ssh_host not in known_hosts:
            require_limit(entitlements, "max_ssh_hosts", len(known_hosts), "SSH Hosts")
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
    service: ProjectService = Depends(get_project_service),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    project = service.get_project_details(project_id, user_id)
    if not project:
        raise HTTPException(404, "Project not found")
    workspace = project.get("workspace") or {}
    host = str(workspace.get("host") or project.get("ssh_host") or "").strip().lower()
    if host and host not in {"localhost", "127.0.0.1"}:
        allowed_hosts = set(sorted(_known_ssh_hosts(service, user_id, service.list_projects(user_id)))[:plan_limit(entitlements, "max_ssh_hosts")])
        if host not in allowed_hosts:
            require_limit(entitlements, "max_ssh_hosts", len(_known_ssh_hosts(service, user_id, service.list_projects(user_id))), "SSH Hosts")
    service.activate_project(project_id, user_id)
    return {"status": "success", "active_id": project_id}

@router.put("/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectPayload,
    user_id: str = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
    entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
):
    current = service.get_project_details(project_id, user_id)
    if not current:
        raise HTTPException(404, "Project not found")
    new_remote = (payload.github_remote_url or "").strip()
    old_remote = str(current.get("github_remote_url") or "").strip()
    if new_remote and new_remote.rstrip("/").lower() != old_remote.rstrip("/").lower():
        require_feature(entitlements, "git")
        projects = service.list_projects(user_id)
        known_repos = {
            str(project.get("github_remote_url") or "").strip().rstrip("/").lower()
            for project in projects
            if str(project.get("github_remote_url") or "").strip()
        }
        if new_remote.rstrip("/").lower() not in known_repos:
            require_limit(entitlements, "git_repos", len(known_repos), "Git Repositories")
    new_ssh_host = (payload.ssh_host or "").strip().lower()
    old_ssh_host = str(current.get("ssh_host") or "").strip().lower()
    if new_ssh_host and new_ssh_host != old_ssh_host:
        projects = service.list_projects(user_id)
        known_hosts = _known_ssh_hosts(service, user_id, projects)
        if new_ssh_host not in known_hosts:
            require_limit(entitlements, "max_ssh_hosts", len(known_hosts), "SSH Hosts")
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
