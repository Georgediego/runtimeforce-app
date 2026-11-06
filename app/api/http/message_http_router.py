"""
Authenticated message editing and cascading deletion with session-scoped memory invalidation.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_conversation_repo, get_graph_repo, get_context_cache_service
from app.repository.conversation_db_repository import ConversationDBRepository
from app.repository.graph_db_repository import GraphDBRepository
from app.services.memory.context_cache_service import ContextCacheService

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


class MessageUpdatePayload(BaseModel):
    content: str


def _owned_message(message_id: int, user_id: str, repo: ConversationDBRepository):
    message = repo.get_message_by_id(message_id)
    if not message or repo.get_session_owner(message["session_id"]) != user_id:
        raise HTTPException(404, "Message not found")
    return message


def _invalidate_session_memory(session_id, user_id, repo, graph_repo, context_cache):
    project_id = repo.get_session_project(session_id)
    graph_repo.delete_session_memory(session_id, user_id, project_id)
    context_cache.invalidate_session(session_id)


@router.get("/{message_id}")
async def get_message(message_id: int, user_id: str = Depends(require_authenticated_user),
                      repo: ConversationDBRepository = Depends(get_conversation_repo)):
    return _owned_message(message_id, user_id, repo)


@router.put("/{message_id}")
async def update_message(
    message_id: int, payload: MessageUpdatePayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    graph_repo: GraphDBRepository = Depends(get_graph_repo),
    context_cache: ContextCacheService = Depends(get_context_cache_service),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(400, "Content cannot be empty")
    message = _owned_message(message_id, user_id, repo)
    if message.get("role") != "user":
        raise HTTPException(400, "Only user messages can be edited")
    session_id = repo.edit_message_and_truncate_after(message_id, content)
    if not session_id:
        raise HTTPException(404, "Message not found")
    _invalidate_session_memory(session_id, user_id, repo, graph_repo, context_cache)
    return {"status": "success", "id": message_id, "session_id": session_id, "truncated_after": True}


@router.post("/{message_id}/truncate-from")
async def truncate_from_message(
    message_id: int, user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    graph_repo: GraphDBRepository = Depends(get_graph_repo),
    context_cache: ContextCacheService = Depends(get_context_cache_service),
):
    _owned_message(message_id, user_id, repo)
    session_id = repo.truncate_from_message(message_id)
    if not session_id:
        raise HTTPException(404, "Message not found")
    _invalidate_session_memory(session_id, user_id, repo, graph_repo, context_cache)
    return {"status": "success", "session_id": session_id, "truncated_from": message_id}


@router.post("/{message_id}/truncate")
async def truncate_messages(
    message_id: int, user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    graph_repo: GraphDBRepository = Depends(get_graph_repo),
    context_cache: ContextCacheService = Depends(get_context_cache_service),
):
    message = _owned_message(message_id, user_id, repo)
    if not repo.truncate_after_message(message_id):
        raise HTTPException(404, "Message not found")
    _invalidate_session_memory(message["session_id"], user_id, repo, graph_repo, context_cache)
    return {"status": "success", "id": message_id}


@router.delete("/{message_id}")
async def delete_message(
    message_id: int, user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    graph_repo: GraphDBRepository = Depends(get_graph_repo),
    context_cache: ContextCacheService = Depends(get_context_cache_service),
):
    message = _owned_message(message_id, user_id, repo)
    if not repo.delete_message_and_subsequent(message_id):
        raise HTTPException(404, "Message not found")
    _invalidate_session_memory(message["session_id"], user_id, repo, graph_repo, context_cache)
    return {"status": "success", "id": message_id, "session_id": message["session_id"]}
