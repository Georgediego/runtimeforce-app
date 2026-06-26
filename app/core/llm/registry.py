"""
Dynamic Model Registry with Strict Function Calling Validation.
"""
import asyncio
import logging
import time
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
import httpx

logger = logging.getLogger("ai_runtime.llm.registry")


@dataclass
class ModelMetadata:
    id: str
    provider: str
    name: str
    context_window: int = 0
    max_output_tokens: int = 4096
    pricing: Dict[str, float] = field(default_factory=lambda: {"input": 0.0, "output": 0.0})
    capabilities: List[str] = field(default_factory=list)
    tier: str = "free"
    description: str = ""
    supports_function_calling: bool = False


# Белый список сертифицированных Tier-1 моделей с нативной поддержкой Tool Calling
TIER_1_FUNCTION_CALLING_MODELS = {
    # Anthropic
    "anthropic/claude-3-5-sonnet",
    "anthropic/claude-3-5-sonnet-20241022",
    "anthropic/claude-3-5-sonnet-latest",
    "anthropic/claude-3-5-haiku",
    "anthropic/claude-3-opus",
    # OpenAI
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4",
    "openai/gpt-4-turbo",
    # Gemini
    "gemini/gemini-1.5-pro",
    "gemini/gemini-1.5-flash",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-2.0-flash-exp",
    "gemini/gemini-2.0-pro-exp",
    # DeepSeek
    "deepseek/deepseek-coder",
    "deepseek/deepseek-chat",
    # OpenRouter Mappings
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/google/gemini-2.0-flash-exp:free",
    "openrouter/google/gemini-1.5-pro",
    "openrouter/google/gemini-1.5-flash",
    "openrouter/openai/gpt-4o",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/deepseek/deepseek-coder",
    # Groq Llama (Large variants with certified FC)
    "groq/llama3-70b-8192",
    "groq/llama-3.1-70b-versatile",
    "groq/llama-3.3-70b-versatile",
}


def _check_function_calling_support(model_id: str) -> bool:
    """Определяет нативную поддержку Function Calling по ID модели."""
    mid_lower = model_id.lower()
    
    # Прямое сопоставление по белому списку
    if model_id in TIER_1_FUNCTION_CALLING_MODELS:
        return True
        
    # Динамический поиск по ключевым паттернам Tier-1 моделей
    if any(m in mid_lower for m in [
        "claude-3-5-sonnet", "claude-3.5-sonnet", "claude-3-5-haiku", "claude-3.5-haiku", "claude-3-opus",
        "gpt-4o", "gpt-4-turbo", "gpt-4o-mini",
        "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0",
        "deepseek-coder", "deepseek-chat"
    ]):
        return True
        
    # Разрешенные крупные локальные модели с проверенным Tool Calling
    if "qwen2.5-coder:14b" in mid_lower or "qwen2.5-coder:32b" in mid_lower or "qwen2.5-coder:72b" in mid_lower:
        return True
    if "llama-3.1-70b" in mid_lower or "llama-3.3-70b" in mid_lower or "llama3-70b" in mid_lower:
        return True
        
    return False


def validate_custom_model(model_id: str, force_allow: bool = False) -> bool:
    """
    Проверяет подключаемую модель на соответствие минимальным требованиям качества.
    Блокирует устаревший или слабый хлам (< 14B параметров для Ollama, gpt-3.5-turbo для OpenAI).
    """
    mid_lower = model_id.lower()
    model_name = mid_lower.split("/")[-1] if "/" in mid_lower else mid_lower

    # 1. Блокировка устаревших облачных моделей
    if "gpt-3.5-turbo" in model_name or "text-davinci" in model_name:
        if not force_allow:
            raise ValueError(
                f"Подключение устаревшей модели '{model_id}' заблокировано. "
                f"Используйте современные Tier-1 альтернативы или передайте флаг 'force_allow': true."
            )

    # 2. Блокировка слабых локальных моделей (Ollama < 14B)
    is_weak = False
    reason = ""

    # Извлечение размера параметров (например, :8b, :7b, :1.5b)
    param_match = re.search(r':(\d+(\.\d+)?)[bM]', model_name)
    if param_match:
        params = float(param_match.group(1))
        if params < 14.0:
            is_weak = True
            reason = f"размер модели ({params}B) меньше минимального порога в 14B параметров"
    else:
        # Известные слабые модели по умолчанию (без указания тега размера)
        weak_patterns = [
            r"llama3(?::|$|latest|:8b)",
            r"llama2(?::|$|latest|:7b)",
            r"gemma(?::|$|latest|:[27]b)",
            r"gemma2(?::|$|latest|:9b)",
            r"phi3(?::|$|latest)",
            r"phi-3",
            r"phi3.5",
            r"mistral(?::|$|latest|:7b)",
            r"qwen2.5:7b",
            r"qwen2.5:3b",
            r"qwen2.5:1.5b",
            r"qwen2.5-coder:7b",
            r"qwen2.5-coder:3b",
            r"qwen2.5-coder:1.5b",
        ]
        for pattern in weak_patterns:
            if re.search(pattern, model_name):
                is_weak = True
                reason = f"модель '{model_name}' идентифицирована как слабая локальная модель"
                break

    if is_weak and not force_allow:
        raise ValueError(
            f"Подключение слабой локальной модели '{model_id}' заблокировано ({reason}). "
            f"Для надежной работы автономного агента требуется модель от 14B параметров (например, qwen2.5-coder:14b). "
            f"Если вы уверены в своем выборе, повторите попытку с флагом 'force_allow': true."
        )
    return True


PROVIDER_DISCOVERY = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openrouter",
    },
    "sambanova": {
        "url": "https://api.sambanova.ai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "headers": lambda k: {"x-goog-api-key": k},
        "parser": "gemini",
    },
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/models",
        "headers": lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"},
        "parser": "anthropic",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "together": {
        "url": "https://api.together.xyz/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "fireworks": {
        "url": "https://api.fireworks.ai/inference/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "xai": {
        "url": "https://api.x.ai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
    "cohere": {
        "url": "https://api.cohere.ai/v2/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "cohere",
    },
    "perplexity": {
        "url": "https://api.perplexity.ai/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
}

FREE_PROVIDERS = {"groq", "gemini", "sambanova", "cerebras"}


class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, ModelMetadata] = {}
        self._provider_last_refresh: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.refresh_interval = 3600
        self.last_refresh = 0.0
        self.force_allow = False  # Флаг ручного пропуска валидации (BYOK/Ollama)

    async def discover_provider(self, provider: str, api_key: str) -> List[ModelMetadata]:
        discovery = PROVIDER_DISCOVERY.get(provider)
        if not discovery or not api_key or not api_key.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = discovery["headers"](api_key)
                resp = await client.get(discovery["url"], headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"{provider} returned {resp.status_code}")
                    return []
                data = resp.json()
                parser = getattr(self, f"_parse_{discovery['parser']}", None)
                if parser:
                    return parser(provider, data)
        except ValueError as ve:
            # Пробрасываем ошибку валидации наверх для API ключей
            raise ve
        except Exception as e:
            logger.error(f"Failed to fetch models from {provider}: {e}")
        return []

    def _parse_openai(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            model_id = f"{provider}/{mid}"
            
            # Прогон через Guardrail валидатор
            try:
                validate_custom_model(model_id, force_allow=self.force_allow)
            except ValueError as ve:
                logger.warning(f"Model excluded: {ve}")
                if provider in ("openai", "ollama", "lm_studio") and not self.force_allow:
                    raise ve
                continue

            caps = ["text"]
            ml = mid.lower()
            if any(x in ml for x in ["coder", "code", "wizard"]):
                caps.append("code")
            if any(x in ml for x in ["reason", "think", "r1"]):
                caps.append("reasoning")
            
            supports_fc = _check_function_calling_support(model_id)

            models.append(ModelMetadata(
                id=model_id, provider=provider, name=mid,
                tier="free" if provider in FREE_PROVIDERS else "standard",
                capabilities=caps,
                supports_function_calling=supports_fc
            ))
        return models

    def _parse_openrouter(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            model_id = f"{provider}/{mid}"

            # Прогон через Guardrail валидатор
            try:
                validate_custom_model(model_id, force_allow=self.force_allow)
            except ValueError:
                continue  # Для агрегатора OpenRouter просто пропускаем слабые модели, не роняя весь импорт

            pricing = item.get("pricing", {}) or {}
            inp = float(pricing.get("prompt", 0) or 0)
            out = float(pricing.get("completion", 0) or 0)
            is_free = inp == 0 and out == 0
            caps = ["text"]
            desc = (item.get("description") or "").lower()
            ml = mid.lower()
            if any(x in ml or x in desc for x in ["coder", "code"]):
                caps.append("code")
            if any(x in ml or x in desc for x in ["reason", "think"]):
                caps.append("reasoning")
            if any(x in ml or x in desc for x in ["vision", "image"]):
                caps.append("vision")
                
            supports_fc = _check_function_calling_support(model_id)

            models.append(ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=item.get("context_length", 0) or 0,
                pricing={"input": inp * 1000, "output": out * 1000},
                capabilities=caps,
                tier="free" if is_free else "standard",
                description=(item.get("description") or "")[:200],
                supports_function_calling=supports_fc
            ))
        return models

    def _parse_gemini(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("models", []):
            name = item.get("name", "")
            if not name:
                continue
            mid = name.replace("models/", "")
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            model_id = f"{provider}/{mid}"
            
            caps = ["text"]
            if "flash" in mid.lower() or "pro" in mid.lower():
                caps.append("vision")
                
            supports_fc = _check_function_calling_support(model_id)

            models.append(ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=item.get("inputTokenLimit", 1000000),
                max_output_tokens=item.get("outputTokenLimit", 8192),
                tier="free", capabilities=caps,
                description=item.get("description", ""),
                supports_function_calling=supports_fc
            ))
        return models

    def _parse_anthropic(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            model_id = f"{provider}/{mid}"
            caps = ["text", "reasoning"]
            if "claude-3" in mid.lower():
                caps.append("vision")
                
            supports_fc = _check_function_calling_support(model_id)

            models.append(ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=200000, max_output_tokens=8192,
                tier="pro", capabilities=caps,
                supports_function_calling=supports_fc
            ))
        return models

    def _parse_cohere(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("models", []):
            mid = item.get("name", "") or item.get("id", "")
            if not mid:
                continue
            model_id = f"{provider}/{mid}"
            supports_fc = _check_function_calling_support(model_id)
            models.append(ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=128000, tier="pro", capabilities=["text"],
                supports_function_calling=supports_fc
            ))
        return models

    async def refresh_provider(self, provider: str, api_key: str, force: bool = False):
        now = time.time()
        last = self._provider_last_refresh.get(provider, 0)
        if not force and (now - last) < self.refresh_interval:
            return
        to_remove = [mid for mid, m in self._models.items() if m.provider == provider]
        for mid in to_remove:
            del self._models[mid]
        if not api_key or not api_key.strip():
            self._provider_last_refresh[provider] = now
            return
        async with self._lock:
            new_models = await self.discover_provider(provider, api_key)
            for m in new_models:
                self._models[m.id] = m
            self._provider_last_refresh[provider] = time.time()
            self.last_refresh = time.time()
            logger.info(f"Discovered {len(new_models)} models from {provider}")

    async def refresh_all(self, provider_keys: Dict[str, str], force: bool = False):
        tasks = [
            self.refresh_provider(p, k, force=force)
            for p, k in provider_keys.items() if k and k.strip()
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, ValueError):
                    raise r

    def get_available_models(self, provider_filter: Optional[str] = None) -> List[ModelMetadata]:
        models = list(self._models.values())
        if provider_filter:
            models = [m for m in models if m.provider == provider_filter]
        models.sort(key=lambda m: (
            0 if m.tier == "free" else 1 if m.tier == "standard" else 2,
            m.provider, m.name,
        ))
        return models

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        return self._models.get(model_id)

    def get_providers_with_models(self) -> List[str]:
        return sorted(set(m.provider for m in self._models.values()))


model_registry = ModelRegistry()