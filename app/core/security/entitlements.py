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
from app.services.git.git_status_service import GitStatusService


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


def require_ssh_host_access(user_id: str, host: str, entitlements: Dict[str, Any]) -> None:
    normalized_host = str(host or "").strip().lower()
    if not normalized_host or normalized_host in {"localhost", "127.0.0.1"}:
        return
    known_hosts = user_ssh_hosts(user_id)
    allowed_hosts = allowed_ssh_hosts(user_id, entitlements)
    if normalized_host in known_hosts:
        if normalized_host in allowed_hosts:
            return
        raise HTTPException(status_code=403, detail={
            "code": "plan_limit_reached",
            "limit": "max_ssh_hosts",
            "used": len(known_hosts),
            "maximum": plan_limit(entitlements, "max_ssh_hosts"),
            "plan": entitlements.get("plan", "unknown"),
            "message": "This SSH host is outside the host allowance for your current plan.",
        })
    require_limit(entitlements, "max_ssh_hosts", len(known_hosts), "SSH Hosts")


async def user_git_repo_ids(
    user_id: str,
    workspace_manager: Any,
    entitlements: Dict[str, Any],
) -> list[str]:
    projects = container.project_repo.list_projects(user_id)
    # Stable ordering prevents switching the active project from changing which
    # repositories are entitled after a downgrade.
    projects = sorted(
        enumerate(projects),
        key=lambda item: (str(item[1].get("created_at") or ""), str(item[1].get("id") or ""), item[0]),
    )
    allowed_hosts = allowed_ssh_hosts(user_id, entitlements)
    repo_ids: list[str] = []
    for _, project in projects:
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        if str(project.get("github_remote_url") or "").strip():
            repo_ids.append(project_id)
            continue
        workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
        host = str((workspace or {}).get("host") or project.get("ssh_host") or "").strip().lower()
        if host and host not in {"localhost", "127.0.0.1"} and host not in allowed_hosts:
            continue
        driver = await workspace_manager.get_driver_for_project(user_id, project_id)
        if driver and await GitStatusService.is_repo(driver):
            repo_ids.append(project_id)
    return repo_ids


async def git_repo_quota_state(
    user_id: str,
    project_id: str,
    workspace_manager: Any,
    entitlements: Dict[str, Any],
) -> Dict[str, Any]:
    maximum = plan_limit(entitlements, "git_repos")
    repo_ids = await user_git_repo_ids(user_id, workspace_manager, entitlements)
    current_has_repo = project_id in repo_ids
    current_allowed = current_has_repo and project_id in set(repo_ids[:maximum])
    can_create = not current_has_repo and maximum > 0 and len(repo_ids) < maximum
    return {
        "used": len(repo_ids),
        "maximum": maximum,
        "current_project_has_repo": current_has_repo,
        "current_project_allowed": current_allowed if current_has_repo else True,
        "can_use_git": bool(current_allowed or can_create),
        "allowed_project_ids": repo_ids[:maximum],
    }


async def count_other_git_repos(
    user_id: str,
    workspace_manager: Any,
    current_project_id: str | None,
    entitlements: Dict[str, Any],
) -> int:
    repo_ids = await user_git_repo_ids(user_id, workspace_manager, entitlements)
    return sum(1 for project_id in repo_ids if project_id != current_project_id)


async def require_git_repo_access(
    user_id: str,
    project_id: str,
    workspace_manager: Any,
    entitlements: Dict[str, Any],
) -> None:
    maximum = plan_limit(entitlements, "git_repos")
    if maximum <= 0:
        require_limit(entitlements, "git_repos", 0, "Git Repositories")
    state = await git_repo_quota_state(user_id, project_id, workspace_manager, entitlements)
    if state["current_project_has_repo"] and not state["current_project_allowed"]:
        raise HTTPException(status_code=403, detail={
            "code": "plan_limit_reached",
            "limit": "git_repos",
            "used": state["used"],
            "maximum": maximum,
            "plan": entitlements.get("plan", "unknown"),
            "message": "This repository is outside the Git Repos allowance for your current plan.",
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
    ordered_projects = sorted(
        enumerate(projects),
        key=lambda item: (str(item[1].get("created_at") or ""), str(item[1].get("id") or ""), item[0]),
    )
    allowed_project_ids = {
        str(project.get("id") or "")
        for _, project in ordered_projects[:maximum]
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
            active_project = container.project_repo.get_active_project(user_id)
            active_project_id = str((active_project or {}).get("id") or "")
            if active_project_id:
                await require_git_repo_access(
                    user_id, active_project_id, container.workspace_manager_service, entitlements
                )
        return user_id
    return dependency
