"""
HTTP API Router for Support Ticket submission and diagnostic intake.
"""
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_support_service
from app.services.support.support_ticket_service import SupportTicketService

logger = logging.getLogger("runtimeforce.api.http.support")
router = APIRouter(prefix="/api/v1/support", tags=["support"])

class TicketCreatePayload(BaseModel):
    subject: str
    description: str
    diagnostics: Optional[Dict[str, Any]] = None

@router.post("/tickets")
async def create_support_ticket(
    payload: TicketCreatePayload,
    user_id: str = Depends(require_authenticated_user),
    support_service: SupportTicketService = Depends(get_support_service)
):
    if not payload.subject.strip() or not payload.description.strip():
        raise HTTPException(status_code=400, detail="Subject and description cannot be empty")
    return support_service.create_ticket(user_id, payload.subject, payload.description, payload.diagnostics)

@router.get("/tickets")
async def list_support_tickets(
    user_id: str = Depends(require_authenticated_user),
    support_service: SupportTicketService = Depends(get_support_service)
):
    return {"tickets": support_service.list_tickets(user_id)}
