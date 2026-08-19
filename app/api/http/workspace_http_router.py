"""
HTTP API Router for Workspaces, File Tree Children, File Operations, and Shell Command Execution.
"""
import logging
import uuid
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from app.container import container
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.workspace.workspace_tree_service import WorkspaceTreeService
from app.services.workspace.workspace_file_service import WorkspaceFileService

logger = logging.getLogger("runtimeforce.workspace_http")
router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])

class ExecuteCommandPayload(BaseModel):
    command: str
    cwd: Optional[str] = None
    password: Optional[str] = None
    project_id: Optional[str] = None

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
    user_id: str = Depends(require_authenticated_user)
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            return {"tree": None}
        target_path = path or getattr(driver, "root", "~")
        tree = await WorkspaceTreeService.get_tree(driver, target_path)
        return {"tree": tree}
    except Exception as e:
        logger.error(f"Error getting workspace tree: {e}")
        return {"tree": None}

@router.get("/tree/children")
async def get_workspace_tree_children(
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user)
):
    try:
        target_project_id = project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            return {"path": path, "children": []}
        res = await WorkspaceTreeService.get_tree_children(driver, path)
        return res
    except Exception as e:
        logger.error(f"Error getting tree children for path {path}: {e}")
        return {"path": path, "children": []}

@router.get("/file")
async def read_workspace_file(
    path: str = Query(...),
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_authenticated_user)
):
    try:
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
    user_id: str = Depends(require_authenticated_user)
):
    try:
        path = payload.get("path")
        content = payload.get("content", "")
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
    user_id: str = Depends(require_authenticated_user)
):
    try:
        target_project_id = payload.project_id or _get_active_project_id(user_id)
        driver = await container.workspace_manager_service.get_driver_for_project(user_id, target_project_id)
        if not driver:
            raise HTTPException(status_code=404, detail="No workspace connected for this project")
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
    user_id: str = Depends(require_authenticated_user)
):
    try:
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
