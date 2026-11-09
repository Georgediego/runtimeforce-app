"""HTTP endpoints for interactive shell command approvals."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.container import container
from app.core.security.jwt_auth_service import require_authenticated_user

router = APIRouter(prefix="/api/v1/approvals", tags=["command approvals"])

class ApprovalDecisionPayload(BaseModel):
    choice: str

@router.get("/pending")
async def list_pending_approvals(user_id: str = Depends(require_authenticated_user)):
    return {"pending": await container.command_approval_service.list_pending(user_id)}

@router.post("/{pending_id}/decision")
async def decide_command_approval(
    pending_id: str,
    payload: ApprovalDecisionPayload,
    user_id: str = Depends(require_authenticated_user),
):
    try:
        return await container.command_approval_service.decide(pending_id, user_id, payload.choice)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
