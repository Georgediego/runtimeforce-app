"""
HTTP API Router for Git status, diff, commit, branch, log, push, pull, and remote operations.
"""
import logging
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

import re
import shlex
import os
import httpx
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import require_plan_feature, get_plan_entitlements, require_limit, plan_limit, require_feature, require_project_access, require_ssh_host_access, count_other_git_repos
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


@router.get("/usage")
async def git_usage(
    project_id: Optional[str] = None,
    user_id: str = Depends(require_authenticated_user),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    entitlements: dict = Depends(get_plan_entitlements),
):
    require_feature(entitlements, "git")
    target_project_id = project_id
    if not target_project_id:
        active_project = container.project_repo.get_active_project(user_id)
        target_project_id = str((active_project or {}).get("id") or "")
    require_project_access(user_id, target_project_id, entitlements)
    project = container.project_repo.get_project(target_project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workspace = container.workspace_repo.get_workspace_by_project_id(target_project_id, user_id)
    current_host = str((workspace or {}).get("host") or project.get("ssh_host") or "").strip().lower()
    require_ssh_host_access(user_id, current_host, entitlements)
    current_driver = await workspace_manager.get_driver_for_project(user_id, target_project_id)
    current_has_repo = bool(str(project.get("github_remote_url") or "").strip())
    if not current_has_repo and current_driver:
        current_has_repo = await GitStatusService.is_repo(current_driver)
    used_elsewhere = await count_other_git_repos(
        user_id, workspace_manager, target_project_id, entitlements
    )
    used = used_elsewhere + (1 if current_has_repo else 0)
    maximum = plan_limit(entitlements, "git_repos")
    return {
        "used": used,
        "maximum": maximum,
        "current_project_has_repo": current_has_repo,
        "can_add": maximum > 0 and (current_has_repo or used < maximum),
    }


@router.get("/status")
async def git_status(
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "entries": []}
    entries = await GitStatusService.status(driver)
    return {"is_repo": True, "entries": entries}

@router.post("/init")
async def git_init(
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager),
    entitlements: dict = Depends(get_plan_entitlements),
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")
    active_project = container.project_repo.get_active_project(user_id)
    current_project_id = str(active_project.get("id") or "") if active_project else None
    if not await GitStatusService.is_repo(driver):
        used_repos = await count_other_git_repos(user_id, workspace_manager, current_project_id, entitlements)
        require_limit(entitlements, "git_repos", used_repos, "Git Repositories")
    return await GitCommitService.init_repo(driver)

@router.get("/diff")
async def git_diff(
    path: Optional[str] = None,
    staged: bool = False,
    user_id: str = Depends(require_plan_feature("git")),
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
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
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
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")

    active_proj = project_service.get_active_project(user_id)
    branch = payload.branch or (active_proj.get("git_branch_main") if active_proj else "main")
    remote = payload.remote or "origin"

    token = None
    target_project_id = payload.project_id
    if not target_project_id and active_proj:
        target_project_id = active_proj.get("id")

    if target_project_id:
        proj = project_service.repo.get_project(target_project_id, user_id)
        if proj:
            oauth_token_data = await container.oauth_repo.get_token(target_project_id, "github")
            if oauth_token_data and oauth_token_data.get("access_token"):
                token = oauth_token_data["access_token"]
            else:
                pat_enc = proj.get("github_pat_enc")
                if pat_enc:
                    try:
                        decrypted_pat = AESCryptoService.decrypt(pat_enc)
                        if decrypted_pat:
                            token = decrypted_pat
                    except Exception:
                        pass

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
    driver = await workspace_manager.get_driver(user_id)
    if not driver:
        raise HTTPException(status_code=404, detail="No active workspace")

    active_proj = project_service.get_active_project(user_id)
    branch = payload.branch or (active_proj.get("git_branch_main") if active_proj else "main")
    remote = payload.remote or "origin"

    token = await _get_saas_github_token(request) if not isinstance(driver, WorkspaceSSHDriver) and await _is_github_remote(driver, remote) else None
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
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "commits": []}
    commits = await GitLogService.log(driver, n=n)
    return {"is_repo": True, "commits": commits}

@router.get("/branches")
async def git_branches(
    user_id: str = Depends(require_plan_feature("git")),
    workspace_manager: WorkspaceManagerService = Depends(get_workspace_manager)
):
    driver = await workspace_manager.get_driver(user_id)
    if not driver or not await GitStatusService.is_repo(driver):
        return {"is_repo": False, "branches": []}
    branches = await GitBranchService.branches(driver)
    return {"is_repo": True, "branches": branches}

async def _get_github_token_and_project(project_id: Optional[str], user_id: str, project_service: ProjectService) -> str:
    target_project_id = project_id
    if not target_project_id:
        active_proj = project_service.get_active_project(user_id)
        if active_proj:
            target_project_id = active_proj.get("id")
    
    if not target_project_id:
        raise HTTPException(status_code=404, detail="Project not found")

    proj = project_service.repo.get_project(target_project_id, user_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    oauth_token_data = await container.oauth_repo.get_token(target_project_id, "github")
    if oauth_token_data and oauth_token_data.get("access_token"):
        return oauth_token_data["access_token"]

    pat_enc = proj.get("github_pat_enc")
    if pat_enc:
        try:
            decrypted_pat = AESCryptoService.decrypt(pat_enc)
            if decrypted_pat:
                return decrypted_pat
        except Exception:
            pass

    raise HTTPException(status_code=409, detail={"error": "github_not_connected"})

@router.get("/github/repos")
async def list_github_repos(
    project_id: Optional[str] = None,
    user_id: str = Depends(require_plan_feature("git")),
    project_service: ProjectService = Depends(get_project_service),
    github_api: GitHubApiService = Depends(get_github_api)
):
    try:
        token = await _get_github_token_and_project(project_id, user_id, project_service)
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
    project_id: Optional[str] = None,
    user_id: str = Depends(require_plan_feature("git")),
    project_service: ProjectService = Depends(get_project_service),
    github_api: GitHubApiService = Depends(get_github_api)
):
    try:
        token = await _get_github_token_and_project(project_id, user_id, project_service)
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
