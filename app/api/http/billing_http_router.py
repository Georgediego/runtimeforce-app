"""Local API for server-verified account entitlements."""
from fastapi import APIRouter, Depends, Request
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_license_service
from app.services.billing.license_service import LicenseService

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/status")
async def billing_status(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    license_service: LicenseService = Depends(get_license_service),
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.cookies.get("access_token", "").strip() or request.cookies.get("jwt_token", "").strip()
    entitlements = await license_service.get_entitlements(token, user_id=user_id)
    return {"user_id": user_id, "license": entitlements}


@router.get("/entitlements")
async def get_entitlements(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    license_service: LicenseService = Depends(get_license_service),
):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return await license_service.get_entitlements(token)
