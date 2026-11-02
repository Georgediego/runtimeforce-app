"""
LLM Router Service — Validated 2026 Production Matrix with Gemini 3.1 Preview / 2.5 Flash Support.
"""
import logging
from typing import List, Dict, Any, Optional
from app.core.interfaces.rotation_service_interface import IRotationService
from app.services.llm.llm_registry_service import LLMRegistryService, ModelMetadata

logger = logging.getLogger("runtimeforce.service.llm.router")

NON_TEXT_CAPABILITIES = {"audio", "speech", "image_generation", "video", "music", "moderation", "embedding"}

AUTOSELECT_MATRIX: Dict[str, List[str]] = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen-2.5-coder-32b",
        "mixtral-8x7b-32768"
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3.1-pro-preview",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ],
    "cerebras": [
        "llama3.1-8b",
        "llama3.3-70b",
        "llama3.1-70b"
    ],
    "sambanova": [
        "Meta-Llama-3.1-8B-Instruct",
        "Qwen2.5-Coder-32B-Instruct"
    ],
    "openrouter": [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "mistralai/mistral-small-24b-instruct-2501:free",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "deepseek/deepseek-chat"
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1-mini"
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229"
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-coder"
    ],
    "xai": [
        "grok-2-1212",
        "grok-2-vision-1212",
        "grok-beta"
    ],
    "ollama": [
        "qwen2.5-coder:latest",
        "qwen2.5-coder:7b",
        "llama3.1:latest",
        "llama3.2:latest",
        "deepseek-r1:latest"
    ],
    "lm_studio": []
}

class LLMRouterService:
    def __init__(self, registry_service: LLMRegistryService, rotation_service: Optional[IRotationService] = None):
        self.registry = registry_service
        self.rotation_service = rotation_service

    @staticmethod
    def is_text_model(model: Any) -> bool:
        mid = (getattr(model, "id", None) or str(model) or "").lower()
        caps = set(getattr(model, "capabilities", []) or [])
        if NON_TEXT_CAPABILITIES.intersection(caps):
            return False
            
        blacklisted_substrings = [
            "whisper", "transcribe", "transcription", "diarize", "tts", "dall-e", "dalle",
            "embedding", "embed", "audio", "speech", "realtime", "guard", "moderation",
            "music", "video", "gpt-image", "sora", "sdxl", "stable-diffusion",
            ":batch", "customtools", "robotics", "bidi"
        ]
        return not any(kw in mid for kw in blacklisted_substrings)

    def autoselect_models_for_provider(self, provider_id: str) -> List[str]:
        p_clean = provider_id.lower().strip()
        available = self.registry.get_available_models(provider_filter=p_clean)
        if not available:
            return []

        avail_ids = [m.id for m in available if self.is_text_model(m)]
        matrix_targets = AUTOSELECT_MATRIX.get(p_clean, [])

        selected = []
        for target in matrix_targets:
            target_clean = target.lower()
            for mid in avail_ids:
                mid_clean = mid.lower()
                # Match the complete model ID, not a substring. For example,
                # gpt-4o must never select gpt-4o-transcribe-diarize.
                if mid_clean == target_clean or mid_clean.endswith("/" + target_clean):
                    if mid not in selected:
                        selected.append(mid)

        if not selected:
            selected = avail_ids[:5]

        return selected

    def build_route(
        self,
        strategy: str,
        model_lock: Optional[str],
        plan: str,
        provider_keys: Dict[str, str],
        scores: Dict[str, Dict[str, Any]],
        user_prompt: str = "",
        enabled_models: Optional[List[str]] = None,
        required_capability: str = "chat_completion"
    ) -> List[str]:
        strategy_clean = (strategy or "auto").strip().lower()

        if (strategy_clean == "manual" or model_lock) and model_lock and model_lock.lower() not in ("auto", "none", ""):
            if enabled_models is not None and len(enabled_models) > 0 and model_lock not in enabled_models:
                raise ValueError(f"Selected model '{model_lock}' is not enabled in settings.")
            logger.info(f"[LLMRouter] MANUAL strategy active: locked strictly to '{model_lock}'")
            return [model_lock]

        all_models = self.registry.get_available_models(required_capability=required_capability)
        candidates = []
        enabled_set = set(enabled_models) if enabled_models is not None else None
        prompt_tokens_est = len(user_prompt) // 4 if user_prompt else 0

        for m in all_models:
            if not self.is_text_model(m):
                continue
            if enabled_set is not None and m.id not in enabled_set:
                continue
            if self.rotation_service and not self.rotation_service.is_model_available(m.id):
                continue
            if self.rotation_service and not self.rotation_service.is_provider_available(m.provider):
                continue
            has_key = (m.provider in provider_keys or m.provider == "local" or m.tier == "local")
            if not has_key:
                continue

            if m.context_window > 0 and prompt_tokens_est > 0 and m.context_window < prompt_tokens_est:
                continue

            candidates.append(m)

        if not candidates:
            raise ValueError(f"No enabled models available for strategy '{strategy_clean}'. Please select models in Settings -> Providers.")



        if strategy_clean == "local":
            local_candidates = [
                m for m in candidates 
                if getattr(m, "tier", "") == "local" or getattr(m, "provider", "") == "local" or str(getattr(m, "id", "")).startswith("local/")
            ]
            if not local_candidates:
                raise ValueError("No enabled local models available. Please enable local models in Settings -> Providers.")
            return [m.id for m in local_candidates]

        if strategy_clean == "coding":
            def coding_score(m: ModelMetadata):
                is_coder = "code" in m.capabilities
                return (0 if is_coder else 1, -m.context_window)
            candidates.sort(key=coding_score)
            return [m.id for m in candidates]

        def router_score(m: ModelMetadata):
            is_fast_cloud = (m.provider in ("groq", "cerebras", "gemini", "sambanova"))
            is_free = (m.tier == "free" or ":free" in m.id.lower() or is_fast_cloud)
            smart_score = scores.get(m.id, {}).get("total", 50.0)
            return (0 if is_fast_cloud else (1 if is_free else 2), -m.context_window, (100 - smart_score))

        candidates.sort(key=router_score)
        return [m.id for m in candidates]
