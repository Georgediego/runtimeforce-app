"""Centralized, fail-closed plan feature and provider entitlement checks."""
from fastapi import Depends, HTTPException, Request

from app.container import get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.billing.license_service import LicenseService

CHAT_STRATEGY_FEATURES = {
    "auto": "auto",
    "manual": "manual",
    "coding": "atm",
    "atm": "atm",
    "local": "local_llms",
}

# Tool permissions are enforced again at dispatch time, not only in the LLM tool list.
TOOL_FEATURES = {
    "execute_command": "terminal",
    "read_workspace_file": "editor",
    "write_workspace_file": "editor",
    "scan_workspace": "editor",
    "search_grep": "editor",
    "apply_code_patch": "editor",
    "git_status": "git",
    "git_diff": "git",
    "git_commit": "git",
    "git_log": "git",
    "git_branch": "git",
    "git_push": "git",
    "git_pull": "git",
    "git_init": "git",
    "github_create_repo": "git",
    "github_list_repos": "git",
}

FEATURE_ALIASES = {
    "local_llms": ("local_llms", "local_models", "local_llm"),
    "git": ("git", "github_git", "github_integration"),
    "software_updates": ("software_updates", "updates"),
    "free_cloud_byok": ("free_cloud_byok", "local_byok"),
    "full_pro_byok": ("full_pro_byok", "pro_byok"),
}

LOCAL_PROVIDERS = {"ollama", "lm_studio", "lm-studio", "local"}
FREE_CLOUD_PROVIDERS = {"gemini", "openrouter", "groq", "sambanova", "cerebras"}
PRO_CLOUD_PROVIDERS = {"openai", "anthropic", "deepseek", "xai"}


def tool_feature_key(tool_name: str):
    return TOOL_FEATURES.get(str(tool_name or "").strip().lower())


def provider_feature_key(provider: str) -> str:
    normalized = str(provider or "").strip().lower().replace("-", "_")
    if normalized in LOCAL_PROVIDERS or normalized in {"lm_studio"}:
        return "local_llms"
    if normalized in FREE_CLOUD_PROVIDERS:
        return "free_cloud_byok"
    if normalized in PRO_CLOUD_PROVIDERS:
        return "full_pro_byok"
    # Unknown providers are denied unless the administrator explicitly grants
    # the full BYOK capability.
    return "full_pro_byok"


def chat_strategy_feature(strategy: str):
    return CHAT_STRATEGY_FEATURES.get(str(strategy or "auto").strip().lower())


def feature_enabled(entitlements: dict, feature_key: str) -> bool:
    if not isinstance(entitlements, dict) or entitlements.get("valid") is not True:
        return False
    features = entitlements.get("features")
    if not isinstance(features, dict):
        return False
    canonical = next((key for key, values in FEATURE_ALIASES.items() if feature_key == key or feature_key in values), feature_key)
    aliases = FEATURE_ALIASES.get(canonical, (feature_key,))
    # Canonical admin keys win over legacy aliases, including explicit false.
    if canonical in features:
        return features.get(canonical) is True
    if feature_key in features:
        return features.get(feature_key) is True
    for alias in aliases:
        if alias in features:
            return features.get(alias) is True
    return False


def require_plan_feature(feature_key: str):
    async def dependency(
        request: Request,
        user_id: str = Depends(require_authenticated_user),
        license_service: LicenseService = Depends(get_license_service),
    ) -> str:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        token = token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
        entitlements = await license_service.get_entitlements(token)
        if not entitlements.get("valid"):
            raise HTTPException(status_code=403, detail={
                "code": "entitlements_unavailable",
                "message": "Account entitlements could not be verified.",
            })
        if not feature_enabled(entitlements, feature_key):
            raise HTTPException(status_code=403, detail={
                "code": "feature_not_enabled",
                "feature": feature_key,
                "plan": entitlements.get("plan", "unknown"),
                "message": f"Feature '{feature_key}' is not enabled for this plan.",
            })
        return user_id
    return dependency
