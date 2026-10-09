"""
HTTP API Router for local license validation and credit balance checking.
"""
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_license_service, get_credit_service
from app.services.billing.license_service import LicenseService
from app.services.billing.credit_balance_service import CreditBalanceService

logger = logging.getLogger("runtimeforce.api.http.billing")
router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

@router.get("/status")
async def billing_status(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    license_service: LicenseService = Depends(get_license_service)
):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    status_info = license_service.validate_license(token)
    return {"user_id": user_id, "license": status_info}

@router.get("/credits")
async def get_credits(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    credit_service: CreditBalanceService = Depends(get_credit_service)
):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        return await credit_service.get_balance(user_id, token)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@router.get("/account")
async def get_account(
    request: Request,
    user_id: str = Depends(require_authenticated_user),
    credit_service: CreditBalanceService = Depends(get_credit_service)
):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        return await credit_service.get_account_details(user_id, token)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
