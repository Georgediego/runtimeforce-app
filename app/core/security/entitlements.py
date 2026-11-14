"""FastAPI dependency wrappers for centralized plan access policy."""
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from app.container import get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.core.security.plan_access import (
    feature_enabled, require_feature, plan_limit, require_limit,
    provider_feature, model_allowed_by_plan,
)
from app.services.billing.license_service import LicenseService


def request_token(request: Request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return token or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()


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
        if feature_key == "git":
            require_limit(entitlements, "max_projects", 0, "Active Projects")
        return user_id
    return dependency
