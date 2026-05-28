"""
LLM Orchestrator: uses dynamic ModelRegistry, NO hardcoded keys/models.
"""
import os
import time
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
import litellm
from app.core.llm.registry import model_registry

logger = logging.getLogger("ai_runtime.llm.orchestrator")

litellm.drop_params = True
litellm.telemetry = False
litellm.suppress_debug_info = True
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

STRATEGY_PRIORITIES = {
    "auto": ["groq", "gemini", "deepseek", "openrouter", "ollama"],
    "local-first": ["ollama", "lm_studio", "deepseek", "gemini", "groq", "openrouter"],
    "coding": ["deepseek", "openrouter", "groq", "anthropic", "openai", "ollama"],
    "reasoning": ["anthropic", "openai", "deepseek", "gemini", "openrouter"],
}

ENV_MAPPING = {
    "groq": "GROQ_API_KEY", "sambanova": "SAMBANOVA_API_KEY",
    "cerebras": "CEREBRAS_API_KEY", "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY", "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHERAI_API_KEY", "fireworks": "FIREWORKS_API_KEY",
    "cohere": "COHERE_API_KEY", "perplexity": "PERPLEXITYAI_API_KEY",
    "xai": "XAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
    "nvidia": "NVIDIA_NIM_API_KEY",
}


class LLMOrchestrator:
    def __init__(self):
        self.provider_keys: Dict[str, str] = {}
        self.cooldown_models: Dict[str, float] = {}
        self.cooldown_duration = 60.0

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

    def _get_route(self, strategy: str, model_lock: Optional[str]) -> List[str]:
        now = time.time()
        self.cooldown_models = {m: t for m, t in self.cooldown_models.items() if t > now}

        if model_lock:
            meta = model_registry.get_model(model_lock)
            if meta and (meta.provider in self.provider_keys or meta.provider in ["ollama", "lm_studio"]) and model_lock not in self.cooldown_models:
                return [model_lock]

        all_models = model_registry.get_available_models()
        candidates = [
            m for m in all_models
            if (m.provider in self.provider_keys or m.provider in ["ollama", "lm_studio"]) and m.id not in self.cooldown_models
        ]
        if not candidates:
            return []

        priority_order = STRATEGY_PRIORITIES.get(strategy, STRATEGY_PRIORITIES["auto"])

        def sort_key(m):
            try:
                pr = priority_order.index(m.provider)
            except ValueError:
                pr = 100
            tr = 0 if m.tier == "free" else 1 if m.tier == "standard" else 2
            cb = 0
            if strategy == "coding" and "code" in m.capabilities:
                cb = -1
            elif strategy == "reasoning" and "reasoning" in m.capabilities:
                cb = -1
            return (pr, tr, cb, m.name)

        candidates.sort(key=sort_key)
        free = [m for m in candidates if m.tier == "free"]
        paid = [m for m in candidates if m.tier != "free"]
        return [m.id for m in free + paid]

    async def stream_completion(
        self, messages: List[Dict[str, str]], strategy: str = "auto",
        model_lock: Optional[str] = None, temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        route = self._get_route(strategy, model_lock)
        if not route:
            yield {"status": "no_models", "error": "Нет доступных моделей для каскада."}
            return

        last_exception = None
        fallback_notified = False # Флаг для подавления спама

        for model_id in route:
            meta = model_registry.get_model(model_id)
            if not meta:
                continue
            
            try:
                env_var = ENV_MAPPING.get(meta.provider)
                if env_var and meta.provider in self.provider_keys:
                    os.environ[env_var] = self.provider_keys[meta.provider]
                
                kwargs: Dict[str, Any] = {
                    "model": model_id, "messages": messages,
                    "temperature": temperature,
                    "max_tokens": min(meta.max_output_tokens, 8192),
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
                    yield {
                        "model": model_id, "provider": meta.provider,
                        "content": getattr(delta, "content", None) or "",
                        "tool_calls": getattr(delta, "tool_calls", None),
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "status": "streaming",
                    }
                return # Успех
                
            except Exception as e:
                last_exception = e
                self.cooldown_models[model_id] = time.time() + self.cooldown_duration
                # Логируем ошибку, но уведомляем UI только один раз
                if not fallback_notified:
                    yield {"status": "fallback", "message": "Пробую альтернативные модели..."}
                    fallback_notified = True
                continue

        yield {"status": "failed", "error": f"Каскад исчерпан: {str(last_exception)}"}


orchestrator = LLMOrchestrator()