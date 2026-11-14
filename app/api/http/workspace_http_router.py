"""
HTTP API Router for Workspaces, File Tree Children, File Operations, and Shell Command Execution.
"""
import logging
import uuid
import getpass
import os
import socket
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from app.container import container
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.workspace.workspace_tree_service import WorkspaceTreeService
from app.services.workspace.workspace_file_service import WorkspaceFileService
from app.core.security.entitlements import get_plan_entitlements, require_feature, require_limit, plan_limit
from app.core.security.plan_access import command_requires_git, command_creates_git_repo
from app.services.git.git_status_service import GitStatusService

logger = logging.getLogger("runtimeforce.workspace_http")
router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])

class ExecuteCommandPayload(BaseModel):
    command: str
    cwd: Optional[str] = None
    password: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None


def _get_user_ssh_hosts(user_id: str) -> set[str]:
    hosts = set()
    for project in container.project_repo.list_projects(user_id):
        project_host = str(project.get("ssh_host") or "").strip().lower()
        if project_host:
            hosts.add(project_host)
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        for workspace in container.workspace_repo.get_all_workspaces(user_id=user_id, project_id=project_id):
            host = str(workspace.get("host") or "").strip().lower()
            if host and (str(workspace.get("type") or "").lower() in {"ssh", "remote"} or host not in {"localhost", "127.0.0.1"}):
                hosts.add(host)
    return hosts


def _require_project_ssh_access(user_id: str, project_id: str, entitlements: dict) -> None:
    workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
    project = container.project_repo.get_project(project_id, user_id)
    host = str((workspace or {}).get("host") or (project or {}).get("ssh_host") or "").strip().lower()
    if not host or host in {"localhost", "127.0.0.1"}:
        return
    all_hosts = sorted(_get_user_ssh_hosts(user_id))
    limit = plan_limit(entitlements, "max_ssh_hosts")
    if host not in set(all_hosts[:limit]):
        raise HTTPException(status_code=403, detail={
            "code": "plan_limit_reached",
            "limit": "max_ssh_hosts",
            "used": len(all_hosts),
            "maximum": limit,
            "plan": entitlements.get("plan", "unknown"),
            "message": "This SSH host is outside the host allowance for your current plan.",
        })


async def _count_other_git_repos(user_id: str, current_project_id: str) -> int:
    repo_projects = set()
    for project in container.project_repo.list_projects(user_id):
        project_id = str(project.get("id") or "")
        if not project_id or project_id == current_project_id:
            continue
        if str(project.get("github_remote_url") or "").strip():
            repo_projects.add(project_id)
            continue
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, project_id)
        if driver and await GitStatusService.is_repo(driver):
            repo_projects.add(project_id)
    return len(repo_projects)


def _get_active_project_id(user_id: str) -> str:
    active_proj = container.project_repo.get_active_project(user_id)
    return active_proj.get("id", "") if active_proj else ""

@router.get("")
async def list_workspaces(
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user)
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        if not target_project_id:
            return {"workspaces": []}
        workspaces = container.workspace_repo.get_all_workspaces(user_id=user_id, project_id=target_project_id)
        return {"workspaces": workspaces}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        return {"workspaces": []}

@router.get("/active")
async def get_active_workspace(
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user)
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        if target_project_id:
            ws = container.workspace_repo.get_workspace_by_project_id(target_project_id, user_id)
            return {"active": ws}
        ws = container.workspace_repo.get_active_workspace(user_id)
        return {"active": ws}
    except Exception as e:
        logger.error(f"Error getting active workspace: {e}")
        return {"active": None}

@router.get("/tree")
async def get_workspace_tree(
    project_id: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        require_feature(entitlements, "editor")
        _require_project_ssh_access(user_id, target_project_id, entitlements)
        target_project_id = project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            logger.error(f"No workspace driver found for project {target_project_id}")
            return {"tree": None}
        target_path = path or getattr(driver, "root", "/")
        logger.info(f"Getting tree for path: {target_path}, driver type: {type(driver).__name__}")
        tree = await WorkspaceTreeService.get_tree(driver, target_path)
        logger.info(f"Tree retrieved successfully: {len(tree) if tree else 0} entries")
        return {"tree": tree}
    except FileNotFoundError as e:
        logger.error(f"Workspace path not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.error(f"Workspace permission denied: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting workspace tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tree/children")
async def get_workspace_tree_children(
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        require_feature(entitlements, "editor")
        _require_project_ssh_access(user_id, target_project_id, entitlements)
        target_project_id = project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            logger.error(f"No workspace driver found for project {target_project_id}")
            return {"path": path, "children": []}
        logger.info(f"Getting tree children for path: {path}, driver type: {type(driver).__name__}")
        res = await WorkspaceTreeService.get_tree_children(driver, path)
        logger.info(f"Tree children retrieved successfully: {len(res.get('children', []))} entries")
        return res
    except FileNotFoundError as e:
        logger.error(f"Workspace path not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.error(f"Workspace permission denied: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting tree children for path {path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/environment")
async def get_local_environment(user_id: str = Depends(require_authenticated_user)):
    """Return the OS identity of the machine running this local IDE process."""
    try:
        username = getpass.getuser()
    except Exception:
        username = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    return {
        "username": username,
        "hostname": socket.gethostname() or "localhost",
        "home": os.path.expanduser("~"),
        "cwd": os.getcwd(),
    }


@router.get("/file")
async def read_workspace_file(
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        require_feature(entitlements, "editor")
        _require_project_ssh_access(user_id, target_project_id, entitlements)
        target_project_id = project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        content = await WorkspaceFileService.read_file(driver, path)
        return {"path": path, "content": content}
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file")
async def save_workspace_file(
    payload: dict,
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        require_feature(entitlements, "editor")
        path = payload.get("path")
        content = payload.get("content", "")
        _require_project_ssh_access(user_id, project_id, entitlements)
        project_id = payload.get("project_id") or _get_active_project_id(user_id)
        if not path:
            raise HTTPException(status_code=400, detail="File path is required")
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        await WorkspaceFileService.write_file(driver, path, content)
        return {"status": "success", "path": path}
    except Exception as e:
        logger.error(f"Error writing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_command(
    payload: ExecuteCommandPayload,
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        require_feature(entitlements, "terminal")
        _require_project_ssh_access(user_id, target_project_id, entitlements)
        target_project_id = payload.project_id or _get_active_project_id(user_id)
        if command_requires_git(payload.command):
            require_feature(entitlements, "git")
            if command_creates_git_repo(payload.command):
                used_repos = await _count_other_git_repos(user_id, target_project_id)
                require_limit(entitlements, "git_repos", used_repos, "Git Repositories")
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        with container.command_approval_service.context(session_id=payload.session_id or "", project_id=target_project_id):
            res = await driver.execute_command(payload.command, cwd=payload.cwd, password=payload.password)
        return res
    except Exception as e:
        logger.error(f"Error executing command '{payload.command}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{workspace_id}/activate")
async def activate_workspace_by_path_id(
    workspace_id: str,
    user_id: str = Depends(require_authenticated_user)
):
    try:
        container.workspace_repo.set_active_workspace(workspace_id, user_id)
        return {"status": "activated", "workspace_id": workspace_id}
    except Exception as e:
        logger.error(f"Error activating workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/activate")
async def activate_workspace_payload(
    payload: dict,
    user_id: str = Depends(require_authenticated_user)
):
    try:
        ws_id = payload.get("workspace_id") or payload.get("id")
        if ws_id:
            container.workspace_repo.set_active_workspace(ws_id, user_id)
        return {"status": "activated", "workspace_id": ws_id}
    except Exception as e:
        logger.error(f"Error activating workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_workspace(
    payload: dict,
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements)
):
    try:
        host_value = str(payload.get("host") or payload.get("ssh_host") or "").strip().lower()
        is_ssh_workspace = bool(host_value) and (
            str(payload.get("type") or "").lower() in {"ssh", "remote"}
            or host_value not in {"localhost", "127.0.0.1"}
        )
        if is_ssh_workspace:
            known_hosts = _get_user_ssh_hosts(user_id)
            if host_value not in known_hosts:
                require_limit(entitlements, "max_ssh_hosts", len(known_hosts), "SSH Hosts")
        ws_id = payload.get("id") or str(uuid.uuid4())
        target_project_id = payload.get("project_id") or _get_active_project_id(user_id)
        payload["project_id"] = target_project_id
        
        success = container.workspace_repo.create_workspace(ws_id, user_id, **payload)
        return {"status": "created" if success else "failed", "workspace_id": ws_id}
    except Exception as e:
        logger.error(f"Error creating workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    user_id: str = Depends(require_authenticated_user)
):
    try:
        container.workspace_repo.delete_workspace(workspace_id, user_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Error deleting workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))
