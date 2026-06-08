"""
Chat streaming API router.
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
    
    # 1. Проверяем суточный лимит 100 сообщений для Бесплатного тарифа
    if plan == "free" and user_id != "anonymous":
        stats = store.get_telemetry_stats(hours=24, user_id=user_id)
        if stats.get("total_calls", 0) >= 100:
            async def limit_generator():
                yield "SYSTEM_ERROR:Вы исчерпали суточный лимит в 100 сообщений для Бесплатного тарифа ($0). Пожалуйста, перейдите на тариф PRO ($19) или EXPERT ($45).\n"
            return StreamingResponse(limit_generator(), media_type="text/event-stream")

    # 2. Проверяем ограничения стратегий и режимов по тарифным сеткам
    strategy_val = payload.strategy or "auto"
    strategies = [s.strip() for s in strategy_val.split(",")]

    # Фильтруем Аналитику и Комбинированный режим (требуется PRO+)
    if "reasoning" in strategies or len(strategies) > 1:
        if plan == "free":
            async def pro_generator():
                yield "SYSTEM_ERROR:Режимы 'Аналитика' и 'Комбинированный' доступны только на тарифах PRO ($19/мес) и EXPERT ($45/мес).\n"
            return StreamingResponse(pro_generator(), media_type="text/event-stream")

    # Фильтруем Консилиум и Ручной выбор (требуется EXPERT)
    if "consilium" in strategies or "manual" in strategies or payload.model_lock:
        if plan in ("free", "pro"):
            async def expert_generator():
                yield "SYSTEM_ERROR:Режимы 'Консилиум' (Дебаты) и 'Ручной выбор моделей' доступны только на тарифе EXPERT ($45/мес).\n"
            return StreamingResponse(expert_generator(), media_type="text/event-stream")

    # Гарантируем наличие session_id: если клиент прислал null, генерируем новый UUID
    session_id = payload.session_id or str(uuid.uuid4())
    is_new_chat = len(store.get_session_messages(session_id)) == 0

    first_msg = payload.messages[0]["content"][:40] if payload.messages else "New Chat"
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
        current_model = None
        is_fallback = False

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
                plan=plan, # Пробрасываем тариф в агентский цикл
            ):
                status = event.get("status")

                if status == "fallback":
                    is_fallback = True
                    msg = event.get("message", "Switching...")
                    yield f"SYSTEM_NOTICE:{msg}\n"
                    continue

                if status in ("failed", "no_models"):
                    err = event.get("error", "Unknown error")
                    yield f"SYSTEM_ERROR:{err}\n"
                    continue

                if status == "model_try":
                    meta = {
                        "model": event.get("model"),
                        "provider": event.get("provider"),
                        "tier": event.get("tier")
                    }
                    yield f"MODEL_TRY:{json.dumps(meta, ensure_ascii=False)}\n"
                    continue

                if status == "model_error":
                    meta = {
                        "model": event.get("model"),
                        "error": event.get("error"),
                        "elapsed_ms": event.get("elapsed_ms")
                    }
                    yield f"MODEL_ERROR:{json.dumps(meta, ensure_ascii=False)}\n"
                    continue

                if status == "model_success":
                    meta = {
                        "model": event.get("model"),
                        "provider": event.get("provider"),
                        "elapsed_ms": event.get("elapsed_ms")
                    }
                    yield f"MODEL_SUCCESS:{json.dumps(meta, ensure_ascii=False)}\n"
                    continue

                if status == "iteration_start":
                    meta = {
                        "iteration": event.get("iteration"),
                        "max": event.get("max_iterations"),
                        "history_len": event.get("history_len")
                    }
                    yield f"ITERATION:{json.dumps(meta, ensure_ascii=False)}\n"
                    continue

                if status == "streaming":
                    model = event.get("model")
                    provider = event.get("provider", "unknown")
                    content = event.get("content", "")

                    if model and model != current_model:
                        current_model = model
                        meta = {"provider": provider, "model": model, "fallback": is_fallback}
                        yield f"METADATA:{json.dumps(meta, ensure_ascii=False)}\n"

                    if content:
                        yield f"CONTENT:{content}\n"

                if status == "tool_start":
                    meta = {
                        "tool_name": event.get("tool_name"),
                        "tool_id": event.get("tool_id"),
                        "arguments": event.get("arguments"),
                        "model": event.get("model"),
                    }
                    yield f"TOOL_START:{json.dumps(meta, ensure_ascii=False)}\n"

                if status == "tool_end":
                    meta = {
                        "tool_name": event.get("tool_name"),
                        "tool_id": event.get("tool_id"),
                        "result": event.get("result"),
                        "model": event.get("model"),
                    }
                    yield f"TOOL_END:{json.dumps(meta, ensure_ascii=False)}\n"

            # КОНЕЦ ГЕНЕРАЦИИ: Автоматически подбираем умное название на бэкенде
            if is_new_chat:
                try:
                    from app.api.sessions import auto_generate_session_title
                    await auto_generate_session_title(session_id, user_id=user_id)
                except Exception as ex:
                    logger.error(f"Auto title generation inside generator failed: {ex}")

        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield f"SYSTEM_ERROR:Runtime error: {str(e)}\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )