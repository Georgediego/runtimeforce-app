"""
Role Selector Service — Smart Cloud Priority with Automatic Free Cloud Fallback.
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.interfaces.role_selector_interface import IRoleSelectorService
from app.services.llm.llm_registry_service import LLMRegistryService, ModelMetadata
from app.services.llm.llm_rotation_service import LLMRotationService
from app.services.llm.llm_router_service import LLMRouterService
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository

logger = logging.getLogger("runtimeforce.service.llm.role_selector")

FREE_PROVIDERS = {"groq", "gemini", "sambanova", "cerebras", "ollama", "lm_studio"}
FAST_CLOUD_FREE_PROVIDERS = {"groq", "cerebras", "gemini", "sambanova"}

CAPABILITY_KEYWORDS = {
    "reasoning": ["reason", "think", "r1", "o1", "o3", "opus", "pro", "deep", "heavy", "analysis"],
    "code": ["code", "coder", "dev", "python", "typescript", "javascript", "engineering"],
    "fast": ["flash", "haiku", "mini", "turbo", "small", "lite", "instant", "groq", "cerebras"],
    "heavy": ["opus", "pro", "ultra", "max", "large", "sonnet", "gpt-4"],
    "cheap": ["free", "flash", "mini", "haiku", "nano", "lite"],
}

def _get_attr(obj: Any, key: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _model_to_dict(model: Any) -> Dict[str, Any]:
    if isinstance(model, dict):
        d = dict(model)
        if "id" in d and "model_id" not in d:
            d["model_id"] = d["id"]
        return d
    mid = getattr(model, "id", "")
    return {
        "id": mid,
        "model_id": mid,
        "provider": getattr(model, "provider", ""),
        "name": getattr(model, "name", ""),
        "context_window": getattr(model, "context_window", 8000),
        "capabilities": getattr(model, "capabilities", []),
        "tier": getattr(model, "tier", "free"),
    }

def _is_free_model(model: Any) -> bool:
    mid = str(_get_attr(model, "id", "")).lower()
    prov = str(_get_attr(model, "provider", "")).lower()
    tier = str(_get_attr(model, "tier", "")).lower()
    return tier == "free" or ":free" in mid or prov in FREE_PROVIDERS

def _model_matches_capabilities(model: Any, required: List[str]) -> bool:
    if not required:
        return True
    m_caps = [str(c).lower() for c in _get_attr(model, "capabilities", [])]
    m_id = str(_get_attr(model, "id")).lower()
    
    text_to_check = f"{m_id} {' '.join(m_caps)}"
    matched = 0
    for cap in required:
        cap_lower = cap.lower()
        if cap_lower in m_caps:
            matched += 1
            continue
        keywords = CAPABILITY_KEYWORDS.get(cap_lower, [cap_lower])
        if any(kw in text_to_check for kw in keywords):
            matched += 1
            
    return matched >= max(1, len(required) // 2)

def _score_model(model: Any, required: List[str], prompt_tokens: int = 0, mode: str = "AUTO") -> float:
    score = 0.0
    m_caps = [str(c).lower() for c in _get_attr(model, "capabilities", [])]
    prov = str(_get_attr(model, "provider", "")).lower()
    mid = str(_get_attr(model, "id")).lower()
    
    for cap in required:
        cap_lower = cap.lower()
        if cap_lower in m_caps:
            score += 15.0
        else:
            keywords = CAPABILITY_KEYWORDS.get(cap_lower, [cap_lower])
            if any(kw in f"{mid} {' '.join(m_caps)}" for kw in keywords):
                score += 8.0

    ctx = _get_attr(model, "context_window", 8000)
    if prompt_tokens > 0:
        if ctx < prompt_tokens * 1.2:
            score -= 40.0
        else:
            score += min(15.0, ctx / 10000.0)
    else:
        if ctx >= 128000:
            score += 10.0

    if mode.upper() != "LOCAL":
        if prov == "groq":
            score += 100.0
        elif prov == "cerebras":
            score += 90.0
        elif prov == "gemini":
            score += 80.0
        elif prov == "sambanova":
            score += 70.0
        elif prov in ("ollama", "lm_studio", "local") or mid.startswith("local/"):
            score -= 50.0

    if _is_free_model(model):
        score += 15.0

    return score

class RoleSelectorService(IRoleSelectorService):
    def __init__(
        self,
        llm_registry: LLMRegistryService,
        rotation_service: Optional[LLMRotationService] = None,
        provider_keys_repo: Optional[ProviderKeysDBRepository] = None,
    ):
        self._registry = llm_registry
        self._rotation = rotation_service
        self._provider_keys_repo = provider_keys_repo

    def _resolve_enabled_models(self, enabled_models: Optional[List[str]], user_id: str) -> Optional[List[str]]:
        if enabled_models is not None and len(enabled_models) > 0:
            return enabled_models
        if self._provider_keys_repo and user_id:
            all_selected = self._provider_keys_repo.get_all_selected_models(user_id)
            if all_selected:
                flat = []
                for mlist in all_selected.values():
                    flat.extend(mlist)
                if flat:
                    return flat
        return None

    def _get_eligible_models(
        self, enabled_models: Optional[List[str]], mode: Optional[str] = None, user_plan: str = "free", user_id: str = "anonymous"
    ) -> List[Any]:
        all_models = self._registry.get_available_models()
        all_models = [m for m in all_models if LLMRouterService.is_text_model(_get_attr(m, "id"))]

        resolved_enabled = self._resolve_enabled_models(enabled_models, user_id)

        if resolved_enabled is not None and len(resolved_enabled) > 0:
            enabled_set = set(m for m in resolved_enabled if LLMRouterService.is_text_model(m))
            eligible = [m for m in all_models if _get_attr(m, "id") in enabled_set]
        else:
            eligible = all_models

        # If strict selection returned 0 matches, fallback to all available models for connected keys
        if not eligible:
            eligible = all_models

        if user_plan == "free":
            eligible = [m for m in eligible if _is_free_model(m)]

        # Include connected free cloud models if available
        if mode and mode.upper() in ("AUTO", "CODING") and user_plan == "free":
            if self._provider_keys_repo:
                keys = self._provider_keys_repo.get_all_provider_keys(user_id)
                available_free_cloud = [
                    m for m in all_models 
                    if str(_get_attr(m, "provider")).lower() in FAST_CLOUD_FREE_PROVIDERS 
                    and str(_get_attr(m, "provider")).lower() in keys
                ]
                existing_ids = set(_get_attr(m, "id") for m in eligible)
                for m in available_free_cloud:
                    if _get_attr(m, "id") not in existing_ids:
                        eligible.append(m)

        if mode and mode.upper() == "LOCAL":
            eligible = [m for m in eligible if str(_get_attr(m, "provider")).lower() in ("ollama", "lm_studio") or _get_attr(m, "tier") == "local"]
            return eligible

        if self._rotation:
            active_eligible = [
                m for m in eligible
                if self._rotation.is_model_available(_get_attr(m, "id"))
            ]
            if active_eligible:
                return active_eligible

        return eligible

    def _round_robin_by_provider(self, models: List[Any]) -> List[Dict[str, Any]]:
        by_provider: Dict[str, List[Dict[str, Any]]] = {}
        for m in models:
            d = _model_to_dict(m)
            p = (d.get("provider", "unknown") or "unknown").lower()
            by_provider.setdefault(p, []).append(d)

        providers = list(by_provider.keys())
        providers.sort(key=lambda p: (
            2 if p in ("ollama", "lm_studio", "local") else 
            (1 if self._rotation and self._rotation.is_provider_degraded(p) else 0),
            0 if p in ("groq", "cerebras", "gemini") else 1
        ))

        result = []
        max_len = max((len(lst) for lst in by_provider.values()), default=0)
        for i in range(max_len):
            for p in providers:
                if i < len(by_provider[p]):
                    result.append(by_provider[p][i])
        return result

    async def select_candidate_models_for_role(
        self,
        role: str,
        required_capabilities: List[str],
        mode: str,
        user_plan: str,
        user_id: str,
        enabled_models: Optional[List[str]] = None,
        limit: int = 10,
        prompt_tokens: int = 0,
    ) -> List[Dict[str, Any]]:
        eligible = self._get_eligible_models(enabled_models, mode=mode, user_plan=user_plan, user_id=user_id)
        if not eligible:
            logger.warning(f"[RoleSelector] No eligible text models enabled for mode={mode}")
            return []

        matching = [m for m in eligible if _model_matches_capabilities(m, required_capabilities)]
        if not matching:
            matching = eligible

        scored = [(m, _score_model(m, required_capabilities, prompt_tokens=prompt_tokens, mode=mode)) for m in matching]
        scored.sort(key=lambda x: x[1], reverse=True)

        top_n = [m for m, _ in scored[:max(limit * 2, 20)]]
        distributed = self._round_robin_by_provider(top_n)
        return distributed[:limit]

    async def select_model_for_role(
        self, role: str, required_capabilities: List[str],
        mode: str, user_plan: str, user_id: str,
        enabled_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        candidates = await self.select_candidate_models_for_role(
            role=role, required_capabilities=required_capabilities,
            mode=mode, user_plan=user_plan, user_id=user_id,
            enabled_models=enabled_models, limit=1,
        )
        if not candidates:
            return {"model_id": "none", "provider": "none"}
        return {"model_id": candidates[0].get("model_id", "none"), "provider": candidates[0].get("provider", "none")}

    async def select_cheapest_model(
        self, required_capabilities: List[str],
        user_plan: str, user_id: str,
        enabled_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        eligible = self._get_eligible_models(enabled_models, user_plan=user_plan, user_id=user_id)
        if not eligible:
            return {"model_id": "none", "provider": "none"}

        scored = []
        for m in eligible:
            if not _model_matches_capabilities(m, required_capabilities):
                continue
            score = _score_model(m, required_capabilities)
            if _is_free_model(m):
                score += 30.0
            scored.append((m, score))

        if not scored:
            scored = [(m, _score_model(m, required_capabilities)) for m in eligible]

        if not scored:
            return {"model_id": "none", "provider": "none"}
        scored.sort(key=lambda x: x[1], reverse=True)
        best = _model_to_dict(scored[0][0])
        return {"model_id": best.get("model_id", "none"), "provider": best.get("provider", "none")}

    async def select_most_powerful_model(
        self, required_capabilities: List[str],
        user_plan: str, user_id: str,
        enabled_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        eligible = self._get_eligible_models(enabled_models, user_plan=user_plan, user_id=user_id)
        if not eligible:
            return {"model_id": "none", "provider": "none"}

        scored = []
        for m in eligible:
            if not _model_matches_capabilities(m, required_capabilities):
                continue
            score = _score_model(m, required_capabilities)
            ctx = _get_attr(m, "context_window", 8000)
            if ctx >= 128000:
                score += 15.0
            scored.append((m, score))

        if not scored:
            scored = [(m, _score_model(m, required_capabilities)) for m in eligible]

        if not scored:
            return {"model_id": "none", "provider": "none"}
        scored.sort(key=lambda x: x[1], reverse=True)
        best = _model_to_dict(scored[0][0])
        return {"model_id": best.get("model_id", "none"), "provider": best.get("provider", "none")}
