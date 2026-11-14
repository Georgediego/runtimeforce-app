"""Pure plan-entitlement helpers shared by HTTP, WebSocket, and agent execution."""
from typing import Any, Dict
from fastapi import HTTPException


FEATURE_ALIASES = {
    "local_llms": ("local_llms", "local_models", "local llms"),
    "git": ("git", "github_git", "github_git_integration", "git_integration", "github / git integration"),
    "software_updates": ("software_updates", "software updates"),
    "free_cloud_byok": ("free_cloud_byok", "free cloud byok"),
    "full_pro_byok": ("full_pro_byok", "full pro byok"),
    "offline_grace": ("offline_grace", "offline grace"),
}
LOCAL_PROVIDERS = {"ollama", "lm_studio", "lm-studio", "local", "local_llm"}
FREE_CLOUD_PROVIDERS = {"gemini", "openrouter", "groq", "sambanova", "cerebras"}
PRO_BYOK_PROVIDERS = {"openai", "anthropic", "deepseek", "xai"}


def feature_enabled(entitlements: Dict[str, Any], feature_key: str) -> bool:
    if entitlements.get("valid") is not True:
        return False
    features = entitlements.get("features") or {}
    for key in FEATURE_ALIASES.get(feature_key, (feature_key,)):
        if key in features:
            return features[key] is True
    return False


def require_feature(entitlements: Dict[str, Any], feature_key: str) -> None:
    if not entitlements.get("valid"):
        raise HTTPException(status_code=403, detail={
            "code": "entitlements_unverified",
            "message": "Account entitlements could not be verified.",
        })
    if not feature_enabled(entitlements, feature_key):
        raise HTTPException(status_code=403, detail={
            "code": "feature_not_in_plan",
            "feature": feature_key,
            "plan": entitlements.get("plan", "unknown"),
            "message": f"Feature '{feature_key}' is not enabled for this plan.",
        })


def plan_limit(entitlements: Dict[str, Any], limit_key: str) -> int:
    limits = entitlements.get("limits") or {}
    aliases = {
        "max_projects": ("max_projects", "workspaces_limit"),
        "max_ssh_hosts": ("max_ssh_hosts",),
        "git_repos": ("git_repos", "git_repos_limit", "max_git_repos"),
    }
    for key in aliases.get(limit_key, (limit_key,)):
        if key in limits:
            try:
                return max(0, int(limits[key]))
            except (TypeError, ValueError):
                return 0
    return 0


def require_limit(entitlements: Dict[str, Any], limit_key: str, used: int, label: str) -> None:
    limit = plan_limit(entitlements, limit_key)
    if used >= limit:
        raise HTTPException(status_code=403, detail={
            "code": "plan_limit_reached",
            "limit": limit_key,
            "used": used,
            "maximum": limit,
            "plan": entitlements.get("plan", "unknown"),
            "message": f"{label} limit reached ({used}/{limit}) for this plan.",
        })


def provider_feature(provider_id: str) -> str:
    provider = (provider_id or "").strip().lower().replace("-", "_")
    if provider in LOCAL_PROVIDERS:
        return "local_llms"
    if provider in FREE_CLOUD_PROVIDERS:
        return "free_cloud_byok"
    return "full_pro_byok"


def model_allowed_by_plan(entitlements: Dict[str, Any], model: Any) -> bool:
    tier = str(getattr(model, "tier", "free") or "free").lower()
    provider = str(getattr(model, "provider", "") or "").lower()
    if tier == "local" or provider in LOCAL_PROVIDERS:
        return feature_enabled(entitlements, "local_llms")
    if tier in {"pro", "standard", "paid"} or provider in PRO_BYOK_PROVIDERS:
        return feature_enabled(entitlements, "full_pro_byok")
    return feature_enabled(entitlements, "free_cloud_byok")
