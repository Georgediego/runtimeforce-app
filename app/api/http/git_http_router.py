"""
HTTP API Router for Git status, diff, commit, branch, log, push, pull, and remote operations.
"""
import logging
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel

import re
import shlex
import os
import httpx
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import require_plan_feature
from app.container import get_workspace_manager, get_project_service, get_github_api, container
from fastapi.responses import JSONResponse
from app.services.git.github_api_service import GitHubApiService, GitHubApiError
from app.services.git.github_git_auth import git_auth_env
from app.core.security.aes_crypto_service import AESCryptoService
from app.services.workspace.workspace_manager_service import WorkspaceManagerService
from app.services.workspace.workspace_ssh_driver import WorkspaceSSHDriver
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
    project_id: Optional[str] = None

class PushPullPayload(BaseModel):
    project_id: Optional[str] = None
    remote: Optional[str] = "origin"
    branch: Optional[str] = None

async def _is_github_remote(driver: Any, remote: str) -> bool:
    try:
        result = await driver.execute_command(f"git remote get-url {shlex.quote(remote)}")
        url = (result.get("stdout") or "").strip().lower()
        return bool(re.match(r"^(https?://github\.com/|git@github\.com:|ssh://git@github\.com/)", url))
    except Exception:
        return False


def _resolve_project(project_id: Optional[str], user_id: str, project_service: ProjectService):
    active_project = project_service.get_active_project(user_id)
    target_id = project_id or (active_project.get("id") if active_project else None)
    if not target_id:
        raise HTTPException(status_code=404, detail="No project selected")
    project = project_service.repo.get_project(target_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return target_id, project


async def _get_project_driver(project_id: Optional[str], user_id: str, workspace_manager: WorkspaceManagerService, project_service: ProjectService):
    target_id, project = _resolve_project(project_id, user_id, project_service)
    driver = await workspace_manager.get_driver_for_project(user_id, target_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No workspace connected to this project")
    return driver, target_id, project


def _validate_project_remote_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    allowed = (
        value.startswith("https://github.com/")
        or value.startswith("git@github.com:")
        or value.startswith("ssh://git@github.com/")
    )
    if not allowed or any(char in value for char in (" ", "\\n", "\\r", ";", "|", "&")):
        raise HTTPException(status_code=400, detail="Project GitHub remote must be a valid GitHub clone URL")
    return value


async def _ensure_project_remote(driver: Any, project: dict, remote: str) -> None:
    # The selected GitHub repository is stored per project. Keep origin in
    # that project's own workspace aligned with its project settings.
    if remote != "origin":
        return
    configured_url = _validate_project_remote_url(project.get("github_remote_url") or "")
    if not configured_url:
        return
    if isinstance(driver, WorkspaceSSHDriver) and configured_url.startswith("https://github.com/"):
        # Git runs on the remote host, so use its SSH key rather than a local
        # HTTPS credential that cannot be forwarded into the remote shell.
        configured_url = "git@github.com:" + configured_url.removeprefix("https://github.com/")
    current = await driver.execute_command("git remote get-url origin")
    current_url = (current.get("stdout") or "").strip()
    if current.get("exit_code") == 0:
        if current_url == configured_url:
            return
        command = f"git remote set-url origin {shlex.quote(configured_url)}"
    else:
        command = f"git remote add origin {shlex.quote(configured_url)}"
    result = await driver.execute_command(command)
    if result.get("exit_code") != 0:
        detail = (result.get("stderr") or result.get("stdout") or "Could not configure project GitHub remote").strip()
        raise HTTPException(status_code=400, detail=detail)


async def _current_branch(driver: Any, fallback: str) -> str:
    result = await driver.execute_command("git branch --show-current")
    branch = (result.get("stdout") or "").strip()
    return branch if result.get("exit_code") == 0 and branch else fallback


async def _get_saas_github_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    base_url = os.getenv("SAAS_URL", "https://runtimeforce.dev").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                f"{base_url}/api/v1/social/github/access-token",
                headers={"Authorization": authorization},
            )
        if response.status_code == 200:
            return response.json().get("access_token") or None
    except Exception as exc:
        logger.warning("SaaS GitHub credential bridge unavailable: %s", type(exc).__name__)
    return None


@router.get("/status")
async def git_status(
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    try:
        driver, _, _ = await _get_project_driver(project_id, user_id, workspace_manager, project_service)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"is_repo": False, "entries": [], "workspace_connected": False}
        raise
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "entries": []}
    entries = await GitStatusService.status(driver)
    return {"is_repo": True, "entries": entries}

@router.post("/init")
async def git_init(
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    driver, _, project = await _get_project_driver(project_id, user_id, workspace_manager, project_service)
    result = await GitCommitService.init_repo(driver)
    if result.get("success"):
        await _ensure_project_remote(driver, project, "origin")
    return result

@router.get("/diff")
async def git_diff(
    path: Optional[str] = None,
    staged: bool = False,
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    try:
        driver, _, _ = await _get_project_driver(project_id, user_id, workspace_manager, project_service)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"is_repo": False, "diff": ""}
        raise
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "diff": ""}
    diff_text = await GitDiffService.diff(driver, path=path, staged=staged)
    return {"is_repo": True, "diff": diff_text}

@router.post("/commit")
async def git_commit(
    payload: CommitPayload,
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    driver, _, _ = await _get_project_driver(payload.project_id, user_id, workspace_manager, project_service)
    if not driver or not await GitStatusService.is_repo(driver):
        raise HTTPException(status_code=400, detail="Not a git repository")
    return await GitCommitService.commit(driver, message=payload.message, paths=payload.paths)

@router.post("/push")
async def git_push(
    payload: PushPullPayload,
    request: Request,
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service)
):
    driver, target_project_id, active_proj = await _get_project_driver(payload.project_id, user_id, workspace_manager, project_service)
    remote = payload.remote or "origin"
    await _ensure_project_remote(driver, active_proj, remote)
    branch_fallback = active_proj.get("git_branch_main") or "main"
    branch = payload.branch or await _current_branch(driver, branch_fallback)

    token = None
    pat_enc = active_proj.get("github_pat_enc")
    if pat_enc:
        try:
            token = AESCryptoService.decrypt(pat_enc)
        except Exception:
            token = None

    if not token and not isinstance(driver, WorkspaceSSHDriver) and await _is_github_remote(driver, remote):
        token = await _get_saas_github_token(request)

    if token and isinstance(driver, WorkspaceSSHDriver):
        raise HTTPException(status_code=400, detail="Token authentication is not supported for SSH workspaces yet")

    if not re.match(r"^[A-Za-z0-9._/-]{1,200}$", remote) or not re.match(r"^[A-Za-z0-9._/-]{1,200}$", branch):
        raise HTTPException(status_code=400, detail="Invalid remote or branch name")

    safe_remote = shlex.quote(remote)
    safe_branch = shlex.quote(branch)
    cmd = f"git push {safe_remote} {safe_branch}"

    if token:
        res = await driver.execute_command(cmd, env=git_auth_env(token))
    else:
        res = await driver.execute_command(cmd)

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
    request: Request,
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service)
):
    driver, target_project_id, active_proj = await _get_project_driver(payload.project_id, user_id, workspace_manager, project_service)
    remote = payload.remote or "origin"
    await _ensure_project_remote(driver, active_proj, remote)
    branch_fallback = active_proj.get("git_branch_main") or "main"
    branch = payload.branch or await _current_branch(driver, branch_fallback)

    token = None
    pat_enc = active_proj.get("github_pat_enc")
    if pat_enc:
        try:
            token = AESCryptoService.decrypt(pat_enc)
        except Exception:
            token = None
    if not token and not isinstance(driver, WorkspaceSSHDriver) and await _is_github_remote(driver, remote):
        token = await _get_saas_github_token(request)
    if token and isinstance(driver, WorkspaceSSHDriver):
        raise HTTPException(status_code=400, detail="Token authentication is not supported for SSH workspaces yet")
    pull_command = f"git pull {shlex.quote(remote)} {shlex.quote(branch)}"
    res = await driver.execute_command(pull_command, env=git_auth_env(token)) if token else await driver.execute_command(pull_command)
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
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    try:
        driver, _, _ = await _get_project_driver(project_id, user_id, workspace_manager, project_service)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"is_repo": False, "commits": []}
        raise
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "commits": []}
    commits = await GitLogService.log(driver, n=n)
    return {"is_repo": True, "commits": commits}

@router.get("/branches")
async def git_branches(
    project_id: Optional[str] = Query(None),
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    project_service: ProjectService = Depends(get_project_service),
):
    try:
        driver, _, _ = await _get_project_driver(project_id, user_id, workspace_manager, project_service)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"is_repo": False, "branches": []}
        raise
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "branches": []}
    branches = await GitBranchService.branches(driver)
    return {"is_repo": True, "branches": branches}

async def _get_github_token_and_project(
    project_id: Optional[str],
    user_id: str,
    project_service: ProjectService,
    request: Request,
) -> str:
    target_project_id, project = _resolve_project(project_id, user_id, project_service)

    pat_enc = project.get("github_pat_enc")
    if pat_enc:
        try:
            decrypted_pat = AESCryptoService.decrypt(pat_enc)
            if decrypted_pat:
                return decrypted_pat
        except Exception:
            logger.warning("Could not decrypt project GitHub token for project %s", target_project_id)

    token = await _get_saas_github_token(request)
    if token:
        return token

    raise HTTPException(status_code=409, detail={"error": "github_not_connected"})

@router.get("/github/repos")
async def list_github_repos(
    request: Request,
    project_id: Optional[str] = None,
    user_id: str = Depends(require_plan_feature("git")),
    project_service: ProjectService = Depends(get_project_service),
    github_api: GitHubApiService = Depends(get_github_api)
):
    try:
        token = await _get_github_token_and_project(project_id, user_id, project_service, request)
        repos = await github_api.list_repos(token)
        return {"repos": repos}
    except GitHubApiError as e:
        status_map = {
            "github_token_invalid": 401,
            "github_rate_limited": 429,
            "github_not_found": 404,
            "invalid_repo_name": 400,
            "github_unavailable": 502
        }
        status_code = status_map.get(e.code, 500)
        return JSONResponse(status_code=status_code, content={"error": e.code})
    except HTTPException as he:
        if he.status_code == 409:
            return JSONResponse(status_code=409, content={"error": "github_not_connected"})
        raise he

@router.get("/github/repos/{owner}/{repo}/branches")
async def list_github_branches(
    owner: str,
    repo: str,
    request: Request,
    project_id: Optional[str] = None,
    user_id: str = Depends(require_plan_feature("git")),
    project_service: ProjectService = Depends(get_project_service),
    github_api: GitHubApiService = Depends(get_github_api)
):
    try:
        token = await _get_github_token_and_project(project_id, user_id, project_service, request)
        result = await github_api.list_branches(token, owner, repo)
        return result
    except GitHubApiError as e:
        status_map = {
            "github_token_invalid": 401,
            "github_rate_limited": 429,
            "github_not_found": 404,
            "invalid_repo_name": 400,
            "github_unavailable": 502
        }
        status_code = status_map.get(e.code, 500)
        return JSONResponse(status_code=status_code, content={"error": e.code})
    except HTTPException as he:
        if he.status_code == 409:
            return JSONResponse(status_code=409, content={"error": "github_not_connected"})
        raise he
