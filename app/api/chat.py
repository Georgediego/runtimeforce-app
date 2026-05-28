"""
Chat streaming API router.
Single endpoint: POST /api/v1/chat/stream.
"""
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatCompletionPayload
from app.core.stream.agent_loop import AgentLoopCoordinator
from app.memory.store import store

logger = logging.getLogger("ai_runtime.api.chat")
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/stream")
async def stream_chat_events(payload: ChatCompletionPayload):
    """
    Высокопроизводительный стриминг текста и системных событий (роутинга).
    Отдает данные в raw text формате, который на лету парсится фронтендом.
    """
    first_msg = payload.messages[0]["content"][:40] if payload.messages else "New Chat Session"
    store.create_session(payload.session_id, first_msg)

    async def text_generator():
        current_model = None
        is_fallback = False

        try:
            async for event in AgentLoopCoordinator.run_agent_loop(
                session_id=payload.session_id,
                messages=payload.messages,
                strategy=payload.strategy,
                model_lock=payload.model_lock,
                temperature=payload.temperature
            ):
                status = event.get("status")

                if status == "fallback":
                    is_fallback = True
                    msg = event.get("message", "Переключение провайдера...")
                    yield f"\nSYSTEM_NOTICE:{msg}\n"
                    continue

                if status in ("failed", "no_models"):
                    err = event.get("error", "Неизвестная ошибка")
                    yield f"\nSYSTEM_ERROR:{err}\n"
                    continue

                if status == "streaming":
                    model = event.get("model")
                    provider = event.get("provider", "unknown")
                    content = event.get("content", "")

                    # Сигнализируем фронтенду о смене модели/провайдера для плашки
                    if model and model != current_model:
                        current_model = model
                        meta = {"provider": provider, "model": model, "fallback": is_fallback}
                        yield f"\nMETADATA:{json.dumps(meta, ensure_ascii=False)}\n"

                    # Стримим чистый контент (токены от LLM)
                    if content:
                        yield content

                if status == "tool_start":
                    meta = {
                        "tool_name": event.get("tool_name"),
                        "tool_id": event.get("tool_id"),
                        "arguments": event.get("arguments"),
                        "model": event.get("model")
                    }
                    yield f"\nTOOL_START:{json.dumps(meta, ensure_ascii=False)}\n"

                if status == "tool_end":
                    meta = {
                        "tool_name": event.get("tool_name"),
                        "tool_id": event.get("tool_id"),
                        "result": event.get("result"),
                        "model": event.get("model")
                    }
                    yield f"\nTOOL_END:{json.dumps(meta, ensure_ascii=False)}\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"\nSYSTEM_ERROR:Внутренняя ошибка рантайма: {str(e)}\n"

    return StreamingResponse(text_generator(), media_type="text/plain")