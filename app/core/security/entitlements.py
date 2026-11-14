"""FastAPI dependency wrappers for centralized plan access policy."""
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from app.container import container, get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.plan_access import (
    feature_enabled, require_feature, plan_limit, require_limit,
    provider_feature, model_allowed_by_plan,
)
from app.services.billing.license_service import LicenseService


def request_token(request: Request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()


async def get_plan_entitlements(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    license_service: LicenseService = Depends(get_license_service),
) -> Dict[str, Any]:
    entitlements = await license_service.get_entitlements(request_token(request))
    if not entitlements.get("valid"):
        raise HTTPException(status_code=403, detail={
            "code": "entitlements_unverified",
            "message": "Account entitlements could not be verified.",
        })
    return entitlements


def user_ssh_hosts(user_id: str) -> set[str]:
    hosts: set[str] = set()
    for project in container.project_repo.list_projects(user_id):
        project_host = str(project.get("ssh_host") or "").strip().lower()
        if project_host and project_host not in {"localhost", "127.0.0.1"}:
            hosts.add(project_host)
        project_id = str(project.get("id") or "")
        if project_id:
            for workspace in container.workspace_repo.get_all_workspaces(user_id=user_id, project_id=project_id):
                host = str(workspace.get("host") or "").strip().lower()
                if host and host not in {"localhost", "127.0.0.1"}:
                    hosts.add(host)
    return hosts


def allowed_ssh_hosts(user_id: str, entitlements: Dict[str, Any]) -> set[str]:
    hosts = user_ssh_hosts(user_id)
    maximum = plan_limit(entitlements, "max_ssh_hosts")
    active = container.project_repo.get_active_project(user_id)
    active_id = str((active or {}).get("id") or "")
    active_workspace = (
        container.workspace_repo.get_workspace_by_project_id(active_id, user_id)
        if active_id else None
    )
    preferred_host = str(
        (active_workspace or {}).get("host") or (active or {}).get("ssh_host") or ""
    ).strip().lower()
    ordered = ([preferred_host] if preferred_host in hosts else []) + sorted(hosts - {preferred_host})
    return set(ordered[:maximum])


def _require_active_ssh_host_allowed(user_id: str, entitlements: Dict[str, Any]) -> None:
    project = container.project_repo.get_active_project(user_id)
    if not project:
        return
    project_id = str(project.get("id") or "")
    workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
    host = str((workspace or {}).get("host") or project.get("ssh_host") or "").strip().lower()
    if not host or host in {"localhost", "127.0.0.1"}:
        return
    hosts = user_ssh_hosts(user_id)
    allowed_hosts = allowed_ssh_hosts(user_id, entitlements)
    if host not in allowed_hosts:
        raise HTTPException(status_code=403, detail={
            "code": "plan_limit_reached",
            "limit": "max_ssh_hosts",
            "used": len(hosts),
            "maximum": plan_limit(entitlements, "max_ssh_hosts"),
            "plan": entitlements.get("plan", "unknown"),
            "message": "The active SSH host is outside the host allowance for your current plan.",
        })


def require_project_access(user_id: str, project_id: str, entitlements: Dict[str, Any]) -> None:
    maximum = plan_limit(entitlements, "max_projects")
    if maximum <= 0:
        require_limit(entitlements, "max_projects", 0, "Active Projects")
    if not project_id:
        raise HTTPException(status_code=403, detail={
            "code": "project_required",
            "limit": "max_projects",
            "maximum": maximum,
            "plan": entitlements.get("plan", "unknown"),
            "message": "Select an allowed project before using workspace features.",
        })
    projects = container.project_repo.list_projects(user_id)
    if len(projects) <= maximum:
        return
    allowed_project_ids = {
        str(project.get("id") or "")
        for project in projects[:maximum]
        if project.get("id")
    }
    if str(project_id) in allowed_project_ids:
        return
    raise HTTPException(status_code=403, detail={
        "code": "plan_limit_reached",
        "limit": "max_projects",
        "used": len(projects),
        "maximum": maximum,
        "plan": entitlements.get("plan", "unknown"),
        "message": "This project is outside the Active Projects allowance for your current plan. Projects within the current plan allowance remain available.",
    })


def require_plan_feature(feature_key: str):
    async def dependency(
        user_id: str = Depends(require_authenticated_user),
        entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
    ) -> str:
        require_feature(entitlements, feature_key)
        if feature_key == "git":
            require_limit(entitlements, "max_projects", 0, "Active Projects")
            require_limit(entitlements, "git_repos", 0, "Git Repositories")
            _require_active_ssh_host_allowed(user_id, entitlements)
        return user_id
    return dependency
