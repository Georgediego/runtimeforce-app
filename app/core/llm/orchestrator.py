"""
LLM Orchestrator with Smart Scoring + adaptive cooldown.
"""
import os
import time
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
import litellm
from app.core.llm.registry import model_registry
from app.memory.store import store

logger = logging.getLogger("ai_runtime.llm.orchestrator")

litellm.drop_params = True
litellm.telemetry = False
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

# Модели без поддержки tool calling (hardcoded filter)
MODELS_NO_TOOLS = {
    "groq/allam-2-7b",
    "groq/llama2-70b-4096",
    "groq/orpheus-arabic-saudi",
    "groq/orpheus-v1-english",
    "groq/orpheus-v1-hindi",
    "groq/orpheus-v1-italian",
    "groq/compound",
    "groq/compound-mini",
    "groq/playai-tts",
    "groq/playai-tts-arabic",
    "groq/whisper-large-v3",
    "groq/whisper-large-v3-turbo",
}

STRATEGY_PRIORITIES = {
    "auto": ["groq", "gemini", "deepseek", "openrouter", "ollama"],
    "local-first": ["ollama", "lm_studio", "deepseek", "gemini", "groq", "openrouter"],
    "coding": ["deepseek", "openrouter", "groq", "anthropic", "openai", "ollama"],
    "reasoning": ["anthropic", "openai", "deepseek", "gemini", "openrouter"],
    "combined": ["groq", "gemini", "deepseek", "openrouter"],
    "consilium": ["groq", "gemini", "deepseek"],
    "manual": [],
}

ENV_MAPPING = {
    "groq": "GROQ_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHERAI_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "cohere": "COHERE_API_KEY",
    "perplexity": "PERPLEXITYAI_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "nvidia": "NVIDIA_NIM_API_KEY",
}


class LLMOrchestrator:
    def __init__(self):
        self.provider_keys: Dict[str, str] = {}
        self.cooldown_models: Dict[str, float] = {}
        self.cooldown_duration = 60.0  # 1 минута для временных ошибок
        self.cooldown_no_tools = 3600.0  # 1 час для моделей без tools
        self.cooldown_terms = 10800.0  # 3 часа для моделей с terms acceptance

    def set_provider_keys(self, keys: Dict[str, str]):
        self.provider_keys = {k: v for k, v in keys.items() if v and v.strip()}
        self._apply_to_environment()

    def update_provider_keys(self, new_keys: Dict[str, str]):
        for provider, key in new_keys.items():
            if key and key.strip():
                self.provider_keys[provider] = key
            elif provider in self.provider_keys:
                del self.provider_keys[provider]
        self._apply_to_environment()
        logger.info(f"Updated keys for: {list(new_keys.keys())}")

    def _apply_to_environment(self):
        for provider, key in self.provider_keys.items():
            env_var = ENV_MAPPING.get(provider)
            if env_var:
                os.environ[env_var] = key

    def _get_route(self, strategy: str, model_lock: Optional[str], needs_tools: bool = False) -> List[str]:
        """
        Строит оптимальный маршрут с учётом:
        - Smart Scoring (рейтинг моделей)
        - Стратегии (приоритеты провайдеров)
        - Cooldown (временно недоступные модели)
        - Capabilities (код/рассуждения)
        - Tool support (фильтр моделей без tool calling)
        """
        logger.info(
            f"ROUTE BUILD: strategy={strategy}, needs_tools={needs_tools}, "
            f"keys={list(self.provider_keys.keys())}"
        )

        now = time.time()
        self.cooldown_models = {m: t for m, t in self.cooldown_models.items() if t > now}

        # Ручной режим (model_lock) — только эта модель + fallback
        if model_lock:
            meta = model_registry.get_model(model_lock)
            if (
                meta
                and (meta.provider in self.provider_keys or meta.provider in ["ollama", "lm_studio"])
                and model_lock not in self.cooldown_models
            ):
                return [model_lock]

        all_models = model_registry.get_available_models()
        candidates = [
            m
            for m in all_models
            if (m.provider in self.provider_keys or m.provider in ["ollama", "lm_studio"])
            and m.id not in self.cooldown_models
            and not (needs_tools and m.id in MODELS_NO_TOOLS)
        ]

        if not candidates:
            logger.warning(
                f"Route EMPTY! strategy={strategy}, keys={list(self.provider_keys.keys())}, "
                f"cooldown={list(self.cooldown_models.keys())}"
            )
            return []

        # Получаем Smart Scoring
        scores = store.get_model_scores()

        # Определяем приоритеты по стратегии
        priority_order = STRATEGY_PRIORITIES.get(strategy, STRATEGY_PRIORITIES["auto"])

        def sort_key(m):
            try:
                pr = priority_order.index(m.provider)
            except ValueError:
                pr = 100

            model_score = scores.get(m.id, {}).get("total", 50.0)
            tr = 0 if m.tier == "free" else 1 if m.tier == "standard" else 2

            cb = 0
            if strategy == "coding" and "code" in getattr(m, "capabilities", []):
                cb = -10
            elif strategy == "reasoning" and "reasoning" in getattr(m, "capabilities", []):
                cb = -10

            return (pr, (100 - model_score), tr, cb, m.name)

        candidates.sort(key=sort_key)

        # Разделяем на free и paid (free идут первыми для экономии)
        free = [m for m in candidates if m.tier == "free"]
        paid = [m for m in candidates if m.tier != "free"]

        route = [m.id for m in free + paid]
        logger.info(f"Route built: {len(route)} models, free={len(free)}, paid={len(paid)}")
        return route

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        strategy: str = "auto",
        model_lock: Optional[str] = None,
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        needs_tools = bool(tools)
        route = self._get_route(strategy, model_lock, needs_tools=needs_tools)

        if not route:
            yield {"status": "no_models", "error": "Нет доступных моделей для каскада."}
            return

        last_exception = None
        fallback_notified = False

        for model_id in route:
            meta = model_registry.get_model(model_id)
            if not meta:
                continue

            yield {
                "status": "model_try",
                "model": model_id,
                "provider": meta.provider,
                "tier": meta.tier,
                "timestamp": time.time(),
            }
            start_time = time.time()
            tokens_in = sum(len(m.get("content", "")) // 4 for m in messages)
            tokens_out = 0

            try:
                env_var = ENV_MAPPING.get(meta.provider)
                if env_var and meta.provider in self.provider_keys:
                    os.environ[env_var] = self.provider_keys[meta.provider]

                # Внедряем динамическое знание модели о себе перед отправкой в LiteLLM
                local_messages = list(messages)
                short_name = model_id.split("/")[-1]
                model_awareness = (
                    f"[System Note: You are RuntimeForce AI. You are currently running on the '{short_name}' model "
                    f"provided by '{meta.provider}'. If the user asks what model you are, answer openly and honestly that you "
                    f"are RuntimeForce AI, currently powered by '{short_name}' (via {meta.provider}). Do not say it is a commercial secret.]"
                )
                
                if local_messages and local_messages[0]["role"] == "system":
                    first_sys = dict(local_messages[0])
                    first_sys["content"] += f"\n\n{model_awareness}"
                    local_messages[0] = first_sys
                else:
                    local_messages.insert(0, {"role": "system", "content": model_awareness})

                # Безопасно вычисляем лимит токенов, даже если max_output_tokens равен None
                max_tokens_limit = min(meta.max_output_tokens, 8192) if meta.max_output_tokens else 4096

                kwargs: Dict[str, Any] = {
                    "model": model_id,
                    "messages": local_messages, # <-- Используем локальный массив с внедренной инструкцией
                    "temperature": temperature,
                    "max_tokens": max_tokens_limit,
                    "stream": True,
                }

                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                response = await litellm.acompletion(**kwargs)
                async for chunk in response:
                    if not chunk or not hasattr(chunk, "choices") or not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue

                    content = getattr(delta, "content", None) or ""
                    if content:
                        tokens_out += len(content) // 4

                    yield {
                        "model": model_id,
                        "provider": meta.provider,
                        "content": content,
                        "tool_calls": getattr(delta, "tool_calls", None),
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "status": "streaming",
                    }

                # ✅ УСПЕХ: логируем телеметрию
                elapsed = int((time.time() - start_time) * 1000)
                store.log_telemetry(
                    model_id=model_id,
                    provider=meta.provider,
                    latency_ms=elapsed,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    success=True,
                    strategy=strategy,
                    was_fallback=fallback_notified,
                    session_id=session_id,
                )

                yield {
                    "status": "model_success",
                    "model": model_id,
                    "provider": meta.provider,
                    "elapsed_ms": elapsed,
                    "tokens_out": tokens_out,
                }
                return

            except Exception as e:
                elapsed = int((time.time() - start_time) * 1000)
                last_exception = e
                error_type = type(e).__name__
                error_msg = str(e).lower()

                # Адаптивный cooldown в зависимости от типа ошибки
                cooldown_sec = self.cooldown_duration
                if "tool calling" in error_msg and "not supported" in error_msg:
                    cooldown_sec = self.cooldown_no_tools
                    logger.info(f"Model {model_id} does not support tools, 1h cooldown")
                elif "terms acceptance" in error_msg or "requires terms" in error_msg:
                    cooldown_sec = self.cooldown_terms
                    logger.info(f"Model {model_id} requires terms acceptance, 3h cooldown")

                self.cooldown_models[model_id] = time.time() + cooldown_sec

                # ❌ ОШИБКА: логируем телеметрию
                store.log_telemetry(
                    model_id=model_id,
                    provider=meta.provider,
                    latency_ms=elapsed,
                    tokens_in=tokens_in,
                    tokens_out=0,
                    success=False,
                    error_type=error_type,
                    strategy=strategy,
                    was_fallback=fallback_notified,
                    session_id=session_id,
                )

                yield {
                    "status": "model_error",
                    "model": model_id,
                    "provider": meta.provider,
                    "error": str(e)[:150],
                    "elapsed_ms": elapsed,
                    "error_type": error_type,
                }

                if not fallback_notified:
                    yield {"status": "fallback", "message": "Пробую альтернативные модели..."}
                    fallback_notified = True
                continue

        yield {"status": "failed", "error": f"Каскад исчерпан: {str(last_exception)}"}


orchestrator = LLMOrchestrator()