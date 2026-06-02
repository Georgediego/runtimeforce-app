import json
import logging
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.api.schemas import ChatCompletionPayload
from app.core.stream.agent_loop import AgentLoopCoordinator
from app.core.crypto import decrypt
from app.memory.store import store
from app.core.llm.orchestrator import orchestrator
from app.core.auth import get_current_user

logger = logging.getLogger("ai_runtime.api.chat")
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat/stream")
async def stream_chat_events(payload: ChatCompletionPayload, user_id: str = Depends(get_current_user)):
    session_id = payload.session_id or str(uuid.uuid4())
    
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
                        "history": event.get("history_len")
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
