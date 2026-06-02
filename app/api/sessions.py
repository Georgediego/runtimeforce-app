"""
Sessions API router.
Endpoints:
  GET    /api/v1/sessions
  POST   /api/v1/sessions
  GET    /api/v1/sessions/{session_id}/messages
  DELETE /api/v1/sessions/{session_id}
  POST   /api/v1/sessions/{session_id}/generate-title
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends

from app.api.schemas import SessionCreatePayload
from app.memory.store import store
from app.core.auth import get_current_user
from app.core.llm.orchestrator import orchestrator

logger = logging.getLogger("ai_runtime.api.sessions")
router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.get("/sessions")
async def get_all_sessions(user_id: str = Depends(get_current_user)):
    """Returns sorted list of all chat sessions."""
    return {"sessions": store.get_all_sessions(user_id=user_id)}


@router.post("/sessions")
async def create_new_session(payload: SessionCreatePayload, user_id: str = Depends(get_current_user)):
    """Creates or updates a session."""
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
        with store._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return {"status": "success", "message": f"Session {session_id} deleted."}
    except Exception as e:
        logger.error(f"Session deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session deletion failed: {str(e)}")


@router.post("/sessions/{session_id}/generate-title")
async def generate_session_title(session_id: str, user_id: str = Depends(get_current_user)):
    """Интеллектуальная авто-генерация названия сессии на основе первых реплик."""
    messages = store.get_session_messages(session_id)
    if not messages:
        return {"title": "Новый чат"}
    
    # Составляем промпт для легковесной разметки темы
    prompt = (
        "Проанализируй диалог ниже и придумай для него краткое (2-4 слова) название на русском языке. "
        "Верни ТОЛЬКО название, без кавычек, знаков препинания в конце и лишнего текста.\n\n"
    )
    for m in messages[-4:]: # Используем последние реплики для точности контекста
        role_name = "Пользователь" if m["role"] == "user" else "Ассистент"
        prompt += f"{role_name}: {m['content']}\n"
        
    try:
        chunks = []
        async for chunk in orchestrator.stream_completion(
            messages=[{"role": "user", "content": prompt}],
            strategy="auto",
            temperature=0.3
        ):
            if chunk.get("content"):
                chunks.append(chunk["content"])
        
        generated_title = "".join(chunks).strip().strip('"').strip("'").strip("«").strip("»")
        if not generated_title or len(generated_title) > 50:
            generated_title = messages[0]["content"][:30] + "..."
            
        store.create_session(session_id, generated_title, user_id=user_id)
        return {"status": "success", "title": generated_title}
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        return {"status": "failed", "title": messages[0]["content"][:30]}