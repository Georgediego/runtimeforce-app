"""
Registry Service for managing discovered LLM models with Pre-seeded Free Cloud Catalog.
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("runtimeforce.service.llm.registry")

DEFAULT_CAPABILITIES = ["chat_completion", "code", "text"]

@dataclass
class ModelMetadata:
    id: str
    provider: str
    name: str
    context_window: int = 0
    max_output_tokens: int = 4096
    pricing: Dict[str, float] = field(default_factory=lambda: {"input": 0.0, "output": 0.0})
    capabilities: List[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    tier: str = "free"
    description: str = ""
    supports_function_calling: bool = True

PRESEEDED_FREE_MODELS = [
    # Groq (500-1000 tok/s LPU)
    ModelMetadata("groq/llama-3.3-70b-versatile", "groq", "llama-3.3-70b-versatile", 128000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "reasoning"]),
    ModelMetadata("groq/llama-3.1-8b-instant", "groq", "llama-3.1-8b-instant", 128000, 8192, tier="free", capabilities=["chat_completion", "code", "text"]),
    ModelMetadata("groq/qwen-2.5-coder-32b", "groq", "qwen-2.5-coder-32b", 32768, 8192, tier="free", capabilities=["chat_completion", "code", "text"]),
    # Gemini (Google) - updated for 2026 endpoints
    ModelMetadata("gemini/gemini-2.5-flash", "gemini", "gemini-2.5-flash", 1000000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "vision"]),
    ModelMetadata("gemini/gemini-2.0-flash", "gemini", "gemini-2.0-flash", 1000000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "vision"]),
    ModelMetadata("gemini/gemini-1.5-flash", "gemini", "gemini-1.5-flash", 1000000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "vision"]),
    ModelMetadata("gemini/gemini-3.1-pro-preview", "gemini", "gemini-3.1-pro-preview", 2000000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "reasoning"]),
    ModelMetadata("gemini/gemini-1.5-pro", "gemini", "gemini-1.5-pro", 2000000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "reasoning"]),
    # Cerebras
    ModelMetadata("cerebras/llama3.1-8b", "cerebras", "llama3.1-8b", 8192, 4096, tier="free", capabilities=["chat_completion", "code", "text"]),
    ModelMetadata("cerebras/llama3.3-70b", "cerebras", "llama3.3-70b", 8192, 4096, tier="free", capabilities=["chat_completion", "code", "text", "reasoning"]),
    # SambaNova
    ModelMetadata("sambanova/Meta-Llama-3.1-8B-Instruct", "sambanova", "Meta-Llama-3.1-8B-Instruct", 8192, 4096, tier="free", capabilities=["chat_completion", "code", "text"]),
    ModelMetadata("sambanova/Qwen2.5-Coder-32B-Instruct", "sambanova", "Qwen2.5-Coder-32B-Instruct", 32768, 8192, tier="free", capabilities=["chat_completion", "code", "text"]),
    # OpenRouter Free
    ModelMetadata("openrouter/google/gemini-2.0-flash-exp:free", "openrouter", "google/gemini-2.0-flash-exp:free", 1000000, 8192, tier="free", capabilities=["chat_completion", "code", "text"]),
    ModelMetadata("openrouter/meta-llama/llama-3.3-70b-instruct:free", "openrouter", "meta-llama/llama-3.3-70b-instruct:free", 128000, 8192, tier="free", capabilities=["chat_completion", "code", "text", "reasoning"]),
]

class LLMRegistryService:
    def __init__(self):
        self._models: Dict[str, ModelMetadata] = {}
        self._cooldowns: Dict[str, float] = {}
        self._init_preseeded_models()

    def _init_preseeded_models(self):
        for m in PRESEEDED_FREE_MODELS:
            self._models[m.id] = m

    def set_cooldown(self, model_id: str, seconds: int = 180) -> None:
        self._cooldowns[model_id] = time.time() + seconds
        logger.warning(f"Model {model_id} placed in cooldown for {seconds}s")

    def is_cooled_down(self, model_id: str) -> bool:
        return self._cooldowns.get(model_id, 0.0) > time.time()

    def register_model(self, model: ModelMetadata):
        mid_lower = model.id.lower()
        if "deep-research" in mid_lower or "interactions" in mid_lower:
            model.capabilities = ["interactions_only"]
        elif not model.capabilities:
            model.capabilities = list(DEFAULT_CAPABILITIES)
        elif "chat_completion" not in model.capabilities and "interactions_only" not in model.capabilities:
            model.capabilities.append("chat_completion")

        self._models[model.id] = model

    def clear_provider_models(self, provider: str):
        to_remove = [mid for mid, m in self._models.items() if m.provider == provider]
        for mid in to_remove:
            del self._models[mid]

    def clear_all(self):
        self._models.clear()
        self._init_preseeded_models()

    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        return self._models.get(model_id)

    def get_available_models(self, provider_filter: Optional[str] = None, required_capability: Optional[str] = "chat_completion") -> List[ModelMetadata]:
        models = list(self._models.values())
        if provider_filter:
            models = [m for m in models if m.provider == provider_filter]
        
        if required_capability:
            models = [
                m for m in models 
                if required_capability in m.capabilities 
                and "interactions_only" not in m.capabilities
            ]

        models.sort(key=lambda m: (
            0 if m.tier == "free" else 1 if m.tier == "standard" else 2,
            m.provider, m.name,
        ))
        return models

    def get_providers_with_models(self) -> List[str]:
        return sorted(set(m.provider for m in self._models.values()))
