"""
License service for validating Studio plan entitlements and managing 7-day offline grace periods.
"""
import time
import logging
from typing import Dict, Any, Optional
from app.core.security.jwt_auth_service import JWTAuthService

logger = logging.getLogger("runtimeforce.service.billing.license")

GRACE_PERIOD_SECONDS = 7 * 24 * 3600

class LicenseService:
    def __init__(self):
        self._cached_license: Dict[str, Any] = {}

    def validate_license(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        if not jwt_token:
            return {"valid": False, "plan": "free", "reason": "No token provided"}

        plan = JWTAuthService.extract_plan_from_jwt(jwt_token)
        now = time.time()

        if plan in ("studio", "expert"):
            self._cached_license = {
                "valid": True,
                "plan": plan,
                "validated_at": now,
                "token": jwt_token,
            }
            return self._cached_license

        if self._cached_license.get("valid") and (now - self._cached_license.get("validated_at", 0)) < GRACE_PERIOD_SECONDS:
            return self._cached_license

        return {"valid": False, "plan": plan, "reason": "Studio subscription required for BYOK"}
