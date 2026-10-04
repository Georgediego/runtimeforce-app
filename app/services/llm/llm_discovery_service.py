"""
Service for discovering models via external Provider APIs with strict Free-Tier & Chat-only whitelisting.
"""
import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from app.services.llm.llm_registry_service import ModelMetadata, LLMRegistryService

logger = logging.getLogger("runtimeforce.service.llm.discovery")

class DiscoveryError(Exception):
    pass

ALLOWED_GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen-2.5-coder-32b",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
}

ALLOWED_CEREBRAS_MODELS = {
    "llama3.1-8b",
    "llama3.3-70b",
    "llama-3.3-70b",
    "llama3.1-70b"
}

ALLOWED_SAMBANOVA_MODELS = {
    "meta-llama-3.1-8b-instruct",
    "qwen2.5-coder-32b-instruct",
    "qwen2.5-72b-instruct"
}

FREE_PROVIDERS = {"groq", "gemini", "sambanova", "cerebras"}

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
    "xai": {
        "url": "https://api.x.ai/v1/models",
        "headers": lambda k: {"Authorization": f"Bearer {k}"},
        "parser": "openai",
    },
}

FALLBACK_XAI_MODELS = ["grok-2-1212", "grok-2-vision-1212", "grok-beta"]

class LLMDiscoveryService:
    def __init__(self, registry_service: LLMRegistryService):
        self.registry = registry_service

    async def discover_local_provider(self, base_url: str, provider_name: str = "local") -> Dict[str, Any]:
        clean_url = base_url.rstrip("/")
        p_name = (provider_name or "local").lower().strip()
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            try:
                resp = await client.get(f"{clean_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    if "models" in data:
                        parsed = self._parse_ollama_format(data["models"], p_name)
                        for m in parsed:
                            meta = ModelMetadata(
                                id=m["id"], provider=p_name, name=m["name"],
                                context_window=m["context_window"], max_output_tokens=m["max_output_tokens"],
                                tier="local", capabilities=m["capabilities"],
                                description=m["description"], supports_function_calling=True
                            )
                            self.registry.register_model(meta)
                        return {"type": "ollama_compatible", "models": parsed}
            except Exception:
                pass

            try:
                resp = await client.get(f"{clean_url}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data:
                        parsed = self._parse_openai_format(data["data"], p_name)
                        for m in parsed:
                            meta = ModelMetadata(
                                id=m["id"], provider=p_name, name=m["name"],
                                context_window=m["context_window"], max_output_tokens=m["max_output_tokens"],
                                tier="local", capabilities=m["capabilities"],
                                description=m["description"], supports_function_calling=True
                            )
                            self.registry.register_model(meta)
                        return {"type": "openai_compatible", "models": parsed}
            except Exception:
                pass

        raise DiscoveryError(f"Could not detect local LLM provider at {base_url}")

    def _parse_ollama_format(self, models: list, provider_name: str) -> List[Dict[str, Any]]:
        result = []
        for model in models:
            name = model.get("name")
            if not name:
                continue
            details = model.get("details", {}) or {}
            caps = ["chat_completion", "text", "code"]
            display_name = name.split(":")[0]
            model_id = f"{provider_name}/{name}" if not name.startswith(f"{provider_name}/") else name
            result.append({
                "id": model_id,
                "name": display_name,
                "tier": "local",
                "context_window": details.get("context_length", 8192) or 8192,
                "max_output_tokens": 4096,
                "pricing": {"input": 0.0, "output": 0.0},
                "capabilities": caps,
                "description": f"Local model ({details.get('parameter_size', 'unknown')})"
            })
        return result

    def _parse_openai_format(self, models: list, provider_name: str) -> List[Dict[str, Any]]:
        result = []
        for model in models:
            model_id = model.get("id")
            if not model_id or ":batch" in model_id.lower():
                continue
            full_id = f"{provider_name}/{model_id}" if not model_id.startswith(f"{provider_name}/") else model_id
            result.append({
                "id": full_id,
                "name": model_id,
                "tier": "local",
                "context_window": 8192,
                "max_output_tokens": 4096,
                "pricing": {"input": 0.0, "output": 0.0},
                "capabilities": ["chat_completion", "text", "code"],
                "description": "Local OpenAI-compatible model"
            })
        return result

    async def discover_provider(self, provider: str, api_key: str):
        if api_key and (api_key.startswith("http://") or api_key.startswith("https://") or provider in ("ollama", "lm_studio")):
            try:
                await self.discover_local_provider(api_key, provider_name=provider)
                return
            except Exception as e:
                logger.debug(f"Background local scan skipped for {provider}: {e}")
                return

        discovery = PROVIDER_DISCOVERY.get(provider)
        if not discovery or not api_key or not api_key.strip():
            if provider == "xai" and api_key and api_key.strip():
                self._register_xai_fallbacks()
            return

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                headers = discovery["headers"](api_key)
                resp = await client.get(discovery["url"], headers=headers)

                if resp.status_code != 200:
                    logger.warning(f"[Discovery] Provider '{provider}' returned HTTP {resp.status_code}.")
                    if provider == "xai":
                        self._register_xai_fallbacks()
                    return

                data = resp.json()
                self.registry.clear_provider_models(provider)

                parser_name = discovery["parser"]
                if parser_name == "openai":
                    self._parse_openai(provider, data)
                elif parser_name == "openrouter":
                    self._parse_openrouter(provider, data)
                elif parser_name == "gemini":
                    self._parse_gemini(provider, data)
                elif parser_name == "anthropic":
                    self._parse_anthropic(provider, data)

                if provider == "xai" and not self.registry.get_available_models(provider_filter="xai"):
                    self._register_xai_fallbacks()

        except Exception as e:
            logger.warning(f"Discovery check for {provider} encountered non-critical error: {e}")
            if provider == "xai":
                self._register_xai_fallbacks()

    def _register_xai_fallbacks(self):
        self.registry.clear_provider_models("xai")
        for mid in FALLBACK_XAI_MODELS:
            model_id = f"xai/{mid}"
            caps = ["chat_completion", "text", "code", "reasoning"]
            meta = ModelMetadata(
                id=model_id, provider="xai", name=mid,
                context_window=128000, max_output_tokens=8192,
                tier="standard", capabilities=caps,
                supports_function_calling=True,
                description="xAI Grok model"
            )
            self.registry.register_model(meta)

    def _parse_openai(self, provider: str, data: dict):
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid or ":batch" in mid.lower():
                continue
            
            mid_lower = mid.lower()

            if provider == "groq":
                if not any(allowed in mid_lower for allowed in ALLOWED_GROQ_MODELS):
                    continue

            if provider == "cerebras":
                if not any(allowed in mid_lower for allowed in ALLOWED_CEREBRAS_MODELS):
                    continue

            if provider == "sambanova":
                if not any(allowed in mid_lower for allowed in ALLOWED_SAMBANOVA_MODELS):
                    continue

            model_id = mid if mid.startswith(f"{provider}/") else f"{provider}/{mid}"
            caps = ["chat_completion", "text", "code"]
            if any(x in mid_lower for x in ["reason", "think", "r1", "o1", "o3", "70b"]):
                caps.append("reasoning")

            meta = ModelMetadata(
                id=model_id, provider=provider, name=mid,
                tier="free" if provider in FREE_PROVIDERS else "standard",
                capabilities=caps,
                supports_function_calling=True
            )
            self.registry.register_model(meta)

    def _parse_openrouter(self, provider: str, data: dict):
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid or ":batch" in mid.lower():
                continue
            model_id = mid if mid.startswith(f"{provider}/") else f"{provider}/{mid}"
            pricing = item.get("pricing", {}) or {}
            inp = float(pricing.get("prompt", 0) or 0)
            out = float(pricing.get("completion", 0) or 0)
            is_free = (inp == 0 and out == 0) or ":free" in mid.lower()
            
            desc = (item.get("description") or "").lower()
            ml = mid.lower()

            if any(bad in ml for bad in ["audio", "image", "tts", "whisper", "video"]):
                continue

            caps = ["chat_completion", "text", "code"]
            if any(x in ml or x in desc for x in ["reason", "think"]):
                caps.append("reasoning")

            meta = ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=item.get("context_length", 0) or 0,
                pricing={"input": inp * 1000, "output": out * 1000},
                capabilities=caps,
                tier="free" if is_free else "standard",
                description=(item.get("description") or "")[:200],
                supports_function_calling=True
            )
            self.registry.register_model(meta)

    def _parse_gemini(self, provider: str, data: dict):
        unstable_markers = [
            "customtools", "preview", "image", "robotics", "live", 
            "audio", "embed", "tuning", "aqa", "vision", "bidi", "exp-", "3."
        ]

        for item in data.get("models", []):
            name = item.get("name", "")
            if not name or ":batch" in name.lower():
                continue
            mid = name.replace("models/", "")
            mid_lower = mid.lower()
            
            if any(marker in mid_lower for marker in unstable_markers):
                if "gemini-2.0-flash-exp" not in mid_lower:
                    continue

            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            model_id = mid if mid.startswith(f"{provider}/") else f"{provider}/{mid}"
            
            caps = ["chat_completion", "text", "code"]
            if "pro" in mid_lower or "2.5" in mid_lower:
                caps.append("reasoning")

            meta = ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=item.get("inputTokenLimit", 1000000),
                max_output_tokens=item.get("outputTokenLimit", 8192),
                tier="free", capabilities=caps,
                supports_function_calling=True
            )
            self.registry.register_model(meta)

    def _parse_anthropic(self, provider: str, data: dict):
        for item in data.get("data", []):
            mid = item.get("id", "")
            if not mid or ":batch" in mid.lower():
                continue
            model_id = mid if mid.startswith(f"{provider}/") else f"{provider}/{mid}"
            caps = ["chat_completion", "text", "reasoning", "code"]
            meta = ModelMetadata(
                id=model_id, provider=provider, name=mid,
                context_window=200000, max_output_tokens=8192,
                tier="pro", capabilities=caps,
                supports_function_calling=True
            )
            self.registry.register_model(meta)

    async def discover_all(self, provider_keys: Dict[str, str]):
        keys_copy = dict(provider_keys or {})
        if "ollama" not in keys_copy or not keys_copy["ollama"]:
            keys_copy["ollama"] = "http://localhost:11434"
        if "lm_studio" not in keys_copy or not keys_copy["lm_studio"]:
            keys_copy["lm_studio"] = "http://localhost:1234"

        tasks = [
            self.discover_provider(p, k)
            for p, k in keys_copy.items() if k and str(k).strip()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
