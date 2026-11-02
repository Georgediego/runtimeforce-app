"""Reusable dependency for server-verified dynamic plan feature checks."""
from fastapi import Depends, HTTPException, Request

from app.container import get_license_service
from app.core.security.jwt_auth_service import require_authenticated_user
from app.services.billing.license_service import LicenseService


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
        if (entitlements.get("features") or {}).get(feature_key) is not True:
            raise HTTPException(status_code=403, detail=f"Feature '{feature_key}' is not enabled for this plan")
        return user_id

    return dependency
