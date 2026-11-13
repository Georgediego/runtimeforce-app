"""Reusable dependency for server-verified dynamic plan feature checks."""
from fastapi import Depends, HTTPException, Request

from app.container import get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.billing.license_service import LicenseService


CHAT_STRATEGY_FEATURES = {
    "auto": "auto",
    "manual": "manual",
    "coding": "atm",
    "atm": "atm",
    "local": "local_models",
}

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
}


def tool_feature_key(tool_name: str) -> str | None:
    return TOOL_FEATURES.get(str(tool_name or "").strip())


def provider_feature_key(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    return "local_models" if normalized in {"ollama", "lm_studio"} else "local_byok"


def chat_strategy_feature(strategy: str) -> str | None:
    """Map the public chat strategy to its Admin-managed plan feature."""
    return CHAT_STRATEGY_FEATURES.get(str(strategy or "auto").strip().lower())


def feature_enabled(entitlements: dict, feature_key: str) -> bool:
    """Only an explicit server-verified boolean true grants a feature."""
    return (
        entitlements.get("valid") is True
        and (entitlements.get("features") or {}).get(feature_key) is True
    )


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
            raise HTTPException(status_code=403, detail="Account entitlements could not be verified")
        if not feature_enabled(entitlements, feature_key):
            raise HTTPException(status_code=403, detail=f"Feature '{feature_key}' is not enabled for this plan")
        return user_id

    return dependency
