"""
Dynamic Model Registry.
Models are discovered from provider APIs when keys are provided.
NO HARDCODED MODELS. Everything comes from live introspection.
"""
import asyncio
import logging
import time
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
        except Exception as e:
            logger.error(f"Failed to fetch models from {provider}: {e}")
        return []

    def _parse_openai(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            caps = ["text"]
            ml = mid.lower()
            if any(x in ml for x in ["coder", "code", "wizard"]):
                caps.append("code")
            if any(x in ml for x in ["reason", "think", "r1"]):
                caps.append("reasoning")
            models.append(ModelMetadata(
                id=f"{provider}/{mid}", provider=provider, name=mid,
                tier="free" if provider in FREE_PROVIDERS else "standard",
                capabilities=caps,
            ))
        return models

    def _parse_openrouter(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
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
            models.append(ModelMetadata(
                id=f"{provider}/{mid}", provider=provider, name=mid,
                context_window=item.get("context_length", 0) or 0,
                pricing={"input": inp * 1000, "output": out * 1000},
                capabilities=caps,
                tier="free" if is_free else "standard",
                description=(item.get("description") or "")[:200],
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
            caps = ["text"]
            if "flash" in mid.lower() or "pro" in mid.lower():
                caps.append("vision")
            models.append(ModelMetadata(
                id=f"{provider}/{mid}", provider=provider, name=mid,
                context_window=item.get("inputTokenLimit", 1000000),
                max_output_tokens=item.get("outputTokenLimit", 8192),
                tier="free", capabilities=caps,
                description=item.get("description", ""),
            ))
        return models

    def _parse_anthropic(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid:
                continue
            caps = ["text", "reasoning"]
            if "claude-3" in mid.lower():
                caps.append("vision")
            models.append(ModelMetadata(
                id=f"{provider}/{mid}", provider=provider, name=mid,
                context_window=200000, max_output_tokens=8192,
                tier="pro", capabilities=caps,
            ))
        return models

    def _parse_cohere(self, provider: str, data: dict) -> List[ModelMetadata]:
        models = []
        for item in data.get("models", []):
            mid = item.get("name", "") or item.get("id", "")
            if not mid:
                continue
            models.append(ModelMetadata(
                id=f"{provider}/{mid}", provider=provider, name=mid,
                context_window=128000, tier="pro", capabilities=["text"],
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
            await asyncio.gather(*tasks, return_exceptions=True)

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
