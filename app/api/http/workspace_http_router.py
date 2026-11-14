"""
HTTP API Router for Workspaces, File Tree Children, File Operations, and Shell Command Execution.
"""
import logging
import uuid
import getpass
import os
import socket
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from typing import Optional
from pydantic import BaseModel
from app.container import container
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import require_plan_feature
from app.services.workspace.workspace_tree_service import WorkspaceTreeService
from app.services.workspace.workspace_file_service import WorkspaceFileService

logger = logging.getLogger("runtimeforce.workspace_http")
router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])

class ExecuteCommandPayload(BaseModel):
    command: str
    cwd: Optional[str] = None
    password: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None

def _get_active_project_id(user_id: str) -> str:
    active_proj = container.project_repo.get_active_project(user_id)
    return active_proj.get("id", "") if active_proj else ""

async def _verified_entitlements(request: Request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    token = token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
    entitlements = await container.license_service.get_entitlements(token)
    if not entitlements.get("valid"):
        raise HTTPException(status_code=403, detail="Account entitlements could not be verified")
    return entitlements


async def _ensure_ssh_workspace_allowed(user_id: str, project_id: str, request: Request):
    workspace = container.workspace_repo.get_workspace_by_project_id(project_id, user_id)
    is_ssh = bool(workspace and str(workspace.get("type") or "").lower() == "ssh")
    if not workspace:
        project = container.project_repo.get_project(project_id, user_id)
        is_ssh = bool(project and (project.get("ssh_host") or "").strip())
    if not is_ssh:
        return
    entitlements = await _verified_entitlements(request)
    features = entitlements.get("features") or {}
    limits = entitlements.get("limits") or {}
    max_ssh_hosts = max(0, int(limits.get("max_ssh_hosts", 0) or 0))
    if max_ssh_hosts <= 0:
        raise HTTPException(status_code=403, detail="SSH host access is disabled by the SSH Hosts limit for this plan")
    if len(_count_unique_ssh_hosts(user_id)) > max_ssh_hosts:
        raise HTTPException(status_code=403, detail="Configured SSH hosts exceed this plan's limit. Remove an SSH host before connecting.")


def _count_unique_ssh_hosts(user_id: str):
    hosts = set()
    for project in container.project_repo.list_projects(user_id):
        project_id = project.get("id")
        legacy_host = str(project.get("ssh_host") or "").strip().lower()
        if legacy_host:
            hosts.add((legacy_host, int(project.get("ssh_port") or 22)))
        if not project_id:
            continue
        for workspace in container.workspace_repo.get_all_workspaces(user_id, project_id):
            if str(workspace.get("type") or "").lower() != "ssh":
                continue
            host = str(workspace.get("host") or "").strip().lower()
            if host:
                hosts.add((host, int(workspace.get("port") or 22)))
    return hosts


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
    request: Request,
    project_id: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("editor"))
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        await _ensure_ssh_workspace_allowed(user_id, target_project_id, request)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tree/children")
async def get_workspace_tree_children(
    request: Request,
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("editor"))
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        await _ensure_ssh_workspace_allowed(user_id, target_project_id, request)
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
    except HTTPException:
        raise
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
    request: Request,
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("editor"))
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        await _ensure_ssh_workspace_allowed(user_id, target_project_id, request)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        content = await WorkspaceFileService.read_file(driver, path)
        return {"path": path, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file")
async def save_workspace_file(
    payload: dict,
    request: Request,
    user_id: str = Depends(require_plan_feature("editor"))
):
    try:
        path = payload.get("path")
        content = payload.get("content", "")
        project_id = payload.get("project_id") or _get_active_project_id(user_id)
        await _ensure_ssh_workspace_allowed(user_id, project_id, request)
        if not path:
            raise HTTPException(status_code=400, detail="File path is required")
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        await WorkspaceFileService.write_file(driver, path, content)
        return {"status": "success", "path": path}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error writing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_command(
    payload: ExecuteCommandPayload,
    request: Request,
    user_id: str = Depends(require_plan_feature("terminal"))
):
    try:
        target_project_id = payload.project_id or _get_active_project_id(user_id)
        await _ensure_ssh_workspace_allowed(user_id, target_project_id, request)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
        with container.command_approval_service.context(session_id=payload.session_id or "", project_id=target_project_id):
            res = await driver.execute_command(payload.command, cwd=payload.cwd, password=payload.password)
        return res
    except HTTPException:
        raise
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
    request: Request,
    user_id: str = Depends(require_authenticated_user)
):
    try:
        ws_id = payload.get("id") or str(uuid.uuid4())
        target_project_id = payload.get("project_id") or _get_active_project_id(user_id)
        payload["project_id"] = target_project_id

        if str(payload.get("type") or "").lower() == "ssh":
            entitlements = await _verified_entitlements(request)
            features = entitlements.get("features") or {}
            if max(0, int((entitlements.get("limits") or {}).get("max_ssh_hosts", 0) or 0)) <= 0:
                raise HTTPException(status_code=403, detail="SSH host access is disabled by the SSH Hosts limit for this plan")
            current_hosts = _count_unique_ssh_hosts(user_id)
            host_key = (str(payload.get("host") or "").strip().lower(), int(payload.get("port") or 22))
            if host_key[0] and host_key not in current_hosts:
                max_ssh_hosts = max(0, int((entitlements.get("limits") or {}).get("max_ssh_hosts", 0) or 0))
                if len(current_hosts) >= max_ssh_hosts:
                    raise HTTPException(status_code=403, detail="SSH host limit reached for this plan")

        success = container.workspace_repo.create_workspace(ws_id, user_id, **payload)
        return {"status": "created" if success else "failed", "workspace_id": ws_id}
    except HTTPException:
        raise
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
