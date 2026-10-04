"""
HTTP API Router for Sessions with Fast Smart Auto-Titling, Strict Whitelist & Direct SQLite Sync.
"""
import uuid
import logging
import re
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import (
    get_conversation_repo,
    get_llm_orchestrator,
    get_project_service,
    get_provider_keys_repo,
    get_llm_registry,
)
from app.repository.conversation_db_repository import ConversationDBRepository
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.services.llm.llm_orchestrator_service import LLMOrchestratorService
from app.services.llm.llm_registry_service import LLMRegistryService
from app.services.project.project_service import ProjectService
from app.api.schemas import SessionCreatePayload

logger = logging.getLogger("runtimeforce.api.http.sessions")
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

class AutoTitlePayload(BaseModel):
    text: str
    session_id: Optional[str] = None
    project_id: Optional[str] = None

class TerminalEntryPayload(BaseModel):
    entry_type: str
    content: str

def _get_active_project_id(user_id: str, project_service: ProjectService) -> str:
    active_proj = project_service.get_active_project(user_id)
    if active_proj:
        return active_proj.get("id", "")
    return ""

def _generate_heuristic_title(text: str) -> str:
    """High quality fallback title generator when LLM is unavailable or offline."""
    t_clean = text.strip()
    if not t_clean:
        return "New Chat"

    t_lower = t_clean.lower()

    if any(k in t_lower for k in ["python", "import ", "def ", "pip ", "pytest"]):
        if "test" in t_lower: return "Python Tests"
        if "fastapi" in t_lower: return "FastAPI Backend"
        if "refactor" in t_lower or "почини" in t_lower: return "Python Refactoring"
        return "Python Development"

    if any(k in t_lower for k in ["git ", "commit", "branch", "ветк", "коммит", "merge"]):
        return "Git Operations"

    if any(k in t_lower for k in ["docker", "container", "compose", "докер"]):
        return "Docker Environment"

    if any(k in t_lower for k in ["ssh", "vps", "server", "хост", "сервер"]):
        return "SSH & Infrastructure"

    if any(k in t_lower for k in ["css", "html", "tailwind", "дизайн", "ui", "кнопк"]):
        return "UI & Styling"

    if any(k in t_lower for k in ["database", "sqlite", "postgres", "миграц", "schema"]):
        return "Database Schema"

    stop_words = {
        "ты", "вы", "я", "он", "она", "опытный", "архитектор", "пожалуйста", 
        "runtimeforce", "система", "сделай", "напиши", "почини", "как", "что",
        "please", "make", "create", "fix", "the", "and", "for", "with", "this"
    }
    words = [w for w in re.findall(r"[a-zA-Zа-яА-Я0-9_-]+", t_clean) if w.lower() not in stop_words and len(w) > 2]
    if words:
        candidate = " ".join(words[:3])
        return candidate[:32].capitalize()

    return "Code Analysis"

@router.get("")
async def list_sessions(
    project_id: Optional[str] = None,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    project_service: ProjectService = Depends(get_project_service)
):
    target_project_id = project_id or _get_active_project_id(user_id, project_service)
    return {"sessions": repo.get_all_sessions(user_id, project_id=target_project_id)}

@router.post("")
async def create_session(
    payload: SessionCreatePayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    project_service: ProjectService = Depends(get_project_service)
):
    session_id = payload.id or str(uuid.uuid4())
    project_id = _get_active_project_id(user_id, project_service)
    repo.create_session(session_id, payload.title, user_id, project_id=project_id)
    return {
        "status": "success",
        "session_id": session_id,
        "title": payload.title,
        "project_id": project_id
    }

@router.post("/auto-title")
async def auto_title(
    payload: AutoTitlePayload,
    user_id: str = Depends(require_authenticated_user),
    orchestrator: LLMOrchestratorService = Depends(get_llm_orchestrator),
    llm_registry: LLMRegistryService = Depends(get_llm_registry),
    provider_keys_repo: ProviderKeysDBRepository = Depends(get_provider_keys_repo),
    repo: ConversationDBRepository = Depends(get_conversation_repo),
    project_service: ProjectService = Depends(get_project_service)
):
    text = payload.text.strip()
    if not text:
        return {"title": "New Chat"}

    # Strict whitelist check for auto-titling model
    selected_map = provider_keys_repo.get_all_selected_models(user_id)
    selected_models_set = set()
    for mlist in selected_map.values():
        selected_models_set.update(mlist)

    keys = provider_keys_repo.get_all_provider_keys(user_id)
    available_models = [m for m in llm_registry.get_available_models() if m.id in selected_models_set]
    
    fast_model_id = None
    fast_provider = None

    # Priority to ultra-fast sub-second providers from ONLY selected models
    for m in available_models:
        if m.provider in keys:
            m_lower = m.id.lower()
            if m.provider in ("groq", "cerebras") and ("instant" in m_lower or "8b" in m_lower):
                fast_model_id = m.id
                fast_provider = m.provider
                break
            elif m.provider == "gemini" and "flash" in m_lower:
                fast_model_id = m.id
                fast_provider = m.provider
                break

    if not fast_model_id and available_models:
        for m in available_models:
            if m.provider in keys or m.tier == "local":
                fast_model_id = m.id
                fast_provider = m.provider
                break

    title = _generate_heuristic_title(text)

    if fast_model_id and fast_provider:
        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the user prompt into a short 2 to 4 word title in the prompt's language. "
                    "CRITICAL: Output ONLY the 2-4 words title without quotes, punctuation or conversational filler."
                ),
            },
            {"role": "user", "content": text[:300]},
        ]

        title_acc = ""
        try:
            async def _run_stream():
                nonlocal title_acc
                async for chunk in orchestrator.stream_completion(
                    messages=prompt,
                    model_id=fast_model_id,
                    provider=fast_provider,
                    temperature=0.1,
                    user_id=user_id,
                    max_tokens=30,
                ):
                    if chunk.get("content"):
                        title_acc += chunk["content"]

            await asyncio.wait_for(_run_stream(), timeout=3.0)

            clean = re.sub(r"(?i)\b(runtimeforce|ai|assistant|system|опытный|архитектор|чат)\b", "", title_acc)
            clean = clean.strip().strip('"').strip("'").rstrip(".").strip()
            words = [w for w in clean.split() if len(w) > 1][:4]
            if words:
                title = " ".join(words).capitalize()
        except Exception as e:
            logger.debug(f"AI auto-title generation fallback to heuristic: {e}")

    # Persist in SQLite
    if payload.session_id:
        target_project_id = payload.project_id or _get_active_project_id(user_id, project_service)
        repo.create_session(payload.session_id, title, user_id, project_id=target_project_id)

    return {"status": "success", "title": title}

@router.get("/{session_id}/messages")
async def get_session_history(
    session_id: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    return {"session_id": session_id, "messages": repo.get_session_messages(session_id)}

@router.get("/{session_id}/traces")
async def get_session_traces(
    session_id: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    return {"session_id": session_id, "traces": repo.get_session_traces(session_id)}

@router.get("/{session_id}/tools")
async def get_session_tools(
    session_id: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    return {"session_id": session_id, "tools": repo.get_session_tools(session_id)}

@router.get("/{session_id}/terminal")
async def get_session_terminal(
    session_id: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    return {"session_id": session_id, "terminal": repo.get_session_terminal(session_id)}

@router.post("/{session_id}/terminal")
async def save_session_terminal(
    session_id: str,
    payload: TerminalEntryPayload,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    repo.append_terminal(session_id, payload.entry_type, payload.content)
    return {"status": "success"}

@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(require_authenticated_user),
    repo: ConversationDBRepository = Depends(get_conversation_repo)
):
    repo.delete_session(session_id)
    return {"status": "success", "message": f"Session {session_id} deleted."}
