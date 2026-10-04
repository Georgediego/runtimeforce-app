"""
HTTP API Router for Git status, diff, commit, branch, log, push, pull, and remote operations.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_workspace_manager, get_project_service
from app.services.workspace.workspace_manager_service import WorkspaceManagerService
from app.services.project.project_service import ProjectService
from app.services.git.git_status_service import GitStatusService
from app.services.git.git_diff_service import GitDiffService
from app.services.git.git_commit_service import GitCommitService
from app.services.git.git_branch_service import GitBranchService
from app.services.git.git_log_service import GitLogService

logger = logging.getLogger("runtimeforce.api.http.git")
router = APIRouter(prefix="/api/v1/git", tags=["git"])

class CommitPayload(BaseModel):
    message: str
    paths: Optional[List[str]] = None

class PushPullPayload(BaseModel):
    project_id: Optional[str] = None
    remote: Optional[str] = "origin"
    branch: Optional[str] = None

@router.get("/status")
async def git_status(
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "entries": []}
    entries = await GitStatusService.status(driver)
    return {"is_repo": True, "entries": entries}

@router.post("/init")
async def git_init(
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")
    return await GitCommitService.init_repo(driver)

@router.get("/diff")
async def git_diff(
    path: Optional[str] = None,
    staged: bool = False,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "diff": ""}
    diff_text = await GitDiffService.diff(driver, path=path, staged=staged)
    return {"is_repo": True, "diff": diff_text}

@router.post("/commit")
async def git_commit(
    payload: CommitPayload,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        raise HTTPException(status_code=400, detail="Not a git repository")
    return await GitCommitService.commit(driver, message=payload.message, paths=payload.paths)

@router.post("/push")
async def git_push(
    payload: PushPullPayload,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")

    active_proj = project_service.get_active_project(user_id)
    branch = payload.branch or (active_proj.get("git_branch_main") if active_proj else "main")
    remote = payload.remote or "origin"

    res = await driver.execute_command(f"git push {remote} {branch}")
    return {
        "success": res.get("exit_code") == 0,
        "stdout": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
        "branch": branch,
        "remote": remote
    }

@router.post("/pull")
async def git_pull(
    payload: PushPullPayload,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")

    active_proj = project_service.get_active_project(user_id)
    branch = payload.branch or (active_proj.get("git_branch_main") if active_proj else "main")
    remote = payload.remote or "origin"

    res = await driver.execute_command(f"git pull {remote} {branch}")
    return {
        "success": res.get("exit_code") == 0,
        "stdout": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
        "branch": branch,
        "remote": remote
    }

@router.get("/log")
async def git_log(
    n: int = 10,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "commits": []}
    commits = await GitLogService.log(driver, n=n)
    return {"is_repo": True, "commits": commits}

@router.get("/branches")
async def git_branches(
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "branches": []}
    branches = await GitBranchService.branches(driver)
    return {"is_repo": True, "branches": branches}
