"""HTTP endpoints for interactive shell command approvals."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.container import container
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.entitlements import get_plan_entitlements, require_feature, require_limit
from app.core.security.plan_access import command_requires_git, command_creates_git_repo

router = APIRouter(prefix="/api/v1/approvals", tags=["command approvals"])

class ApprovalDecisionPayload(BaseModel):
    choice: str

@router.get("/pending")
async def list_pending_approvals(
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements),
):
    require_feature(entitlements, "terminal")
    require_limit(entitlements, "max_projects", 0, "Active Projects")
    return {"pending": await container.command_approval_service.list_pending(user_id)}

@router.post("/{pending_id}/decision")
async def decide_command_approval(
    pending_id: str,
    payload: ApprovalDecisionPayload,
    user_id: str = Depends(require_authenticated_user),
    entitlements: dict = Depends(get_plan_entitlements),
):
    require_feature(entitlements, "terminal")
    require_limit(entitlements, "max_projects", 0, "Active Projects")
    pending_items = await container.command_approval_service.list_pending(user_id)
    pending = next((item for item in pending_items if item.get("pending_id") == pending_id), None)
    if pending and command_requires_git(pending.get("command", "")):
        require_feature(entitlements, "git")
        require_limit(entitlements, "git_repos", 0, "Git Repositories")
        if command_creates_git_repo(pending.get("command", "")):
            current_project_id = str(pending.get("project_id") or "")
            used_repos = {
                str(project.get("id") or "")
                for project in container.project_repo.list_projects(user_id)
                if str(project.get("id") or "") != current_project_id
                and str(project.get("github_remote_url") or "").strip()
            }
            require_limit(entitlements, "git_repos", len(used_repos), "Git Repositories")
    try:
        return await container.command_approval_service.decide(pending_id, user_id, payload.choice)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
