import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.api.schemas import SessionCreatePayload
from app.memory.store import store
from app.core.auth import get_current_user

logger = logging.getLogger("ai_runtime.api.sessions")
router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.get("/sessions")
async def get_all_sessions(user_id: str = Depends(get_current_user)):
    return {"sessions": store.get_all_sessions(user_id=user_id)}


@router.post("/sessions")
async def create_new_session(payload: SessionCreatePayload, user_id: str = Depends(get_current_user)):
    session_id = payload.id or str(uuid.uuid4())
    success = store.create_session(session_id, payload.title, user_id=user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create session in DB.")
    return {"status": "success", "session_id": session_id, "title": payload.title}


@router.get("/sessions/{session_id}/messages")
async def get_session_history(session_id: str):
    """Returns full message history for specified session."""
    messages = store.get_session_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Deletes a session and all related messages (ON DELETE CASCADE)."""
    try:
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return {"status": "success", "message": f"Session {session_id} deleted."}
    except Exception as e:
        logger.error(f"Session deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session deletion failed: {str(e)}")
