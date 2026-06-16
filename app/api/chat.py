"""
Chat streaming API router for runtimeforce-app.
Uses unified JSON-SSE format to guarantee perfect markdown formatting, linebreaks and tables.
"""
import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.api.schemas import ChatCompletionPayload
from app.core.stream.agent_loop import AgentLoopCoordinator
from app.core.crypto import decrypt
from app.memory.store import store
from app.core.llm.orchestrator import orchestrator
from app.core.auth import get_current_user_info

logger = logging.getLogger("ai_runtime.api.chat")
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/stream")
async def stream_chat_events(
    payload: ChatCompletionPayload, 
    user_info: dict = Depends(get_current_user_info)
):
    user_id = user_info["user_id"]
    plan = user_info["plan"]
    
    # 1. Проверяем суточный лимит 100 сообщений для Бесплатного тарифа (Client NOT Trusted)
    if plan == "free" and user_id != "anonymous":
        stats = store.get_telemetry_stats(hours=24, user_id=user_id)
        if stats.get("total_calls", 0) >= 100:
            async def limit_generator():
                yield f"data: {json.dumps({'status': 'failed', 'error': 'Вы исчерпали суточный лимит в 100 сообщений для Бесплатного тарифа ($0). Пожалуйста, перейдите на тариф PRO ($19) или EXPERT ($45).'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(limit_generator(), media_type="text/event-stream")

    # 2. Проверяем ограничения стратегий и режимов по тарифным сеткам (Client NOT Trusted)
    strategy_val = payload.strategy or "auto"
    strategies = [s.strip() for s in strategy_val.split(",")]

    # Фильтруем Аналитику и Комбинированный режим (требуется PRO+)
    if "reasoning" in strategies or len(strategies) > 1:
        if plan == "free":
            async def pro_generator():
                yield f"data: {json.dumps({'status': 'failed', 'error': 'Режимы «Аналитика» и «Комбинированный» доступны только на тарифах PRO ($19/мес) и EXPERT ($45/мес).'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(pro_generator(), media_type="text/event-stream")

    # Фильтруем Консилиум и Ручной выбор (требуется EXPERT)
    if "consilium" in strategies or "manual" in strategies or payload.model_lock:
        if plan in ("free", "pro"):
            async def expert_generator():
                yield f"data: {json.dumps({'status': 'failed', 'error': 'Режимы «Консилиум» (Дебаты) и «Ручной выбор моделей» доступны только на тарифе EXPERT ($45/мес).'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(expert_generator(), media_type="text/event-stream")

    # Гарантируем наличие session_id: если клиент прислал null, генерируем новый UUID
    session_id = payload.session_id or str(uuid.uuid4())
    is_new_chat = len(store.get_session_messages(session_id)) == 0

    first_msg = payload.messages[0]["content"][:40] if payload.messages else "New Chat Session"
    store.create_session(session_id, first_msg, user_id=user_id)

    try:
        encrypted_keys = store.get_all_provider_keys()
        decrypted_keys = {}
        for provider, key_enc in encrypted_keys.items():
            try:
                decrypted_keys[provider] = decrypt(key_enc)
            except Exception as e:
                logger.warning(f"Failed to decrypt key for {provider}: {e}")

        if decrypted_keys:
            orchestrator.set_provider_keys(decrypted_keys)
            logger.info(f"Loaded {len(decrypted_keys)} provider keys")
        else:
            logger.warning("No provider keys found in store!")
    except Exception as e:
        logger.error(f"Key loading failed: {e}")

    async def event_generator():
        try:
            async for event in AgentLoopCoordinator.run_agent_loop(
                session_id=session_id,
                messages=payload.messages,
                strategy=payload.strategy,
                model_lock=payload.model_lock,
                temperature=payload.temperature,
                consilium_draft_model=payload.consilium_draft_model,
                consilium_critic_model=payload.consilium_critic_model,
                consilium_synth_model=payload.consilium_synth_model,
                plan=plan,
            ):
                # Отдаем события в чистом JSON-SSE формате
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # КОНЕЦ ГЕНЕРАЦИИ: Автоматически подбираем умное название на бэкенде
            if is_new_chat:
                try:
                    from app.api.sessions import auto_generate_session_title
                    title = await auto_generate_session_title(session_id, user_id=user_id)
                    # Уведомляем клиент об успешном завершении авто-нейминга
                    yield f"data: {json.dumps({'status': 'title_generated', 'title': title}, ensure_ascii=False)}\n\n"
                except Exception as ex:
                    logger.error(f"Auto title generation inside generator failed: {ex}")

        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield f"data: {json.dumps({'status': 'failed', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )