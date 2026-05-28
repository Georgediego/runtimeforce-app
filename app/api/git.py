"""
Git API router.
Endpoints:
  GET  /api/v1/git/status
  GET  /api/v1/git/diff
  GET  /api/v1/git/log
  GET  /api/v1/git/branches
  POST /api/v1/git/commit
  POST /api/v1/git/revert
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from app.core.workspace import workspace_manager

router = APIRouter(prefix="/api/v1/git", tags=["git"])


@router.get("/status")
async def git_status():
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            return {"is_repo": False, "entries": []}
        entries = await workspace_manager.git.status()
        return {"is_repo": True, "entries": entries}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/diff")
async def git_diff(path: Optional[str] = None, staged: bool = False):
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            return {"is_repo": False, "diff": ""}
        diff_text = await workspace_manager.git.diff(path=path, staged=staged)
        return {"is_repo": True, "diff": diff_text, "path": path}
    except Exception as e:
        raise HTTPException(500, str(e))


class CommitPayload(BaseModel):
    message: str
    paths: Optional[List[str]] = None


@router.post("/commit")
async def git_commit(payload: CommitPayload):
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            raise HTTPException(400, "Not a git repository")
        result = await workspace_manager.git.commit(payload.message, paths=payload.paths)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/log")
async def git_log(n: int = 10):
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            return {"is_repo": False, "commits": []}
        commits = await workspace_manager.git.log(n=n)
        return {"is_repo": True, "commits": commits}
    except Exception as e:
        raise HTTPException(500, str(e))


class RevertPayload(BaseModel):
    path: str


@router.post("/revert")
async def git_revert(payload: RevertPayload):
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            raise HTTPException(400, "Not a git repository")
        result = await workspace_manager.git.revert_file(payload.path)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/branches")
async def git_branches():
    try:
        is_repo = await workspace_manager.git.is_repo()
        if not is_repo:
            return {"is_repo": False, "branches": []}
        branches = await workspace_manager.git.branches()
        return {"is_repo": True, "branches": branches}
    except Exception as e:
        raise HTTPException(500, str(e))
