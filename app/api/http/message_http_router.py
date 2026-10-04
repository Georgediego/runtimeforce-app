"""
HTTP API Router for message editing, deletion, and clean truncation without duplication.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_conversation_repo, get_graph_repo
from app.repository.conversation_db_repository import ConversationDBRepository
from app.repository.graph_db_repository import GraphDBRepository

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])

class MessageUpdatePayload(BaseModel):
    content: str

@router.get("/{message_id}")
async def get_message(
    message_id: int,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    msg = repo.get_message_by_id(message_id)
    if not msg:
        raise HTTPException(404, "Message not found")
    return msg

@router.put("/{message_id}")
async def update_message(
    message_id: int,
    payload: MessageUpdatePayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    if not payload.content.strip():
        raise HTTPException(400, "Content cannot be empty")
    updated = repo.update_message(message_id, payload.content.strip())
    if not updated:
        raise HTTPException(404, "Message not found")
    return {"status": "success", "id": message_id}

@router.post("/{message_id}/truncate-from")
async def truncate_from_message(
    message_id: int,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    graph_repo: GraphDBRepository = Depends(get_graph_repo)
):
    """Truncate message and everything following it so resend does not duplicate."""
    session_id = repo.truncate_from_message(message_id)
    if not session_id:
        raise HTTPException(404, "Message not found")

    # Invalidate old summary/hypothesis graph nodes for this session
    try:
        conn = graph_repo.db.get_connection()
        conn.execute("DELETE FROM graph_nodes WHERE attributes_json LIKE ?", (f"%{session_id}%",))
        conn.commit()
    except Exception:
        pass

    return {"status": "success", "session_id": session_id, "truncated_from": message_id}

@router.post("/{message_id}/truncate")
async def truncate_messages(
    message_id: int,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    truncated = repo.truncate_after_message(message_id)
    if not truncated:
        raise HTTPException(404, "Message not found")
    return {"status": "success", "id": message_id}

@router.delete("/{message_id}")
async def delete_message(
    message_id: int,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    deleted = repo.delete_message_and_subsequent(message_id)
    if not deleted:
        raise HTTPException(404, "Message not found")
    return {"status": "success", "id": message_id}
