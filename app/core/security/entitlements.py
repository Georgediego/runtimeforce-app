"""Centralized server-verified plan feature and limit enforcement."""
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from app.container import get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.billing.license_service import LicenseService


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


def request_token(request: Request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()


def feature_enabled(entitlements: Dict[str, Any], feature_key: str) -> bool:
    if entitlements.get("valid") is not True:
        return False
    features = entitlements.get("features") or {}
    aliases = FEATURE_ALIASES.get(feature_key, (feature_key,))
    for key in aliases:
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


async def get_plan_entitlements(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    license_service: LicenseService = Depends(get_license_service),
) -> Dict[str, Any]:
    entitlements = await license_service.get_entitlements(request_token(request))
    if not entitlements.get("valid"):
        raise HTTPException(status_code=403, detail={
            "code": "entitlements_unverified",
            "message": "Account entitlements could not be verified.",
        })
    return entitlements


def require_plan_feature(feature_key: str):
    async def dependency(
        user_id: str = Depends(require_authenticated_user),
        entitlements: Dict[str, Any] = Depends(get_plan_entitlements),
    ) -> str:
        require_feature(entitlements, feature_key)
        return user_id
    return dependency
