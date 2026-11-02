"""Fetch server-verified dynamic entitlements with bounded offline caching."""
import hashlib
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx
from app.core.interfaces.license_service_interface import ILicenseService

logger = logging.getLogger("runtimeforce.service.billing.license")
DEFAULT_SERVER_URL = os.getenv("RUNTIMEFORCE_SERVER_URL", "https://runtimeforce.dev").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 5.0


class LicenseService(ILicenseService):
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def get_entitlements(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        if not jwt_token:
            return {"valid": False, "plan": "free", "features": {}, "limits": {}, "reason": "No token provided"}

        token = jwt_token.removeprefix("Bearer ").strip()
        token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        url = f"{DEFAULT_SERVER_URL}/api/v1/billing/entitlements"

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self._cache.pop(token_key, None)
                return {"valid": False, "plan": "free", "features": {}, "limits": {}, "reason": "Authentication expired"}
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("features", {}), dict):
                raise ValueError("Invalid entitlements response")
            result = {
                **data,
                "valid": True,
                "is_stale": False,
                "validated_at": now,
            }
            self._cache[token_key] = result
            return result
        except Exception as exc:
            cached = self._cache.get(token_key)
            if cached:
                grace_hours = max(0, int((cached.get("limits") or {}).get("offline_grace_hours", 0) or 0))
                age = now - float(cached.get("validated_at", 0))
                if grace_hours and age <= grace_hours * 3600:
                    return {**cached, "is_stale": True}
            logger.warning("Server entitlement check failed (%s)", type(exc).__name__)
            return {
                "valid": False,
                "plan": "free",
                "features": {},
                "limits": {},
                "is_stale": True,
                "reason": "Entitlements could not be verified",
            }

    async def validate_license(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        return await self.get_entitlements(jwt_token)

    @staticmethod
    def has_feature(entitlements: Dict[str, Any], feature_key: str) -> bool:
        features = entitlements.get("features") or {}
        return entitlements.get("valid") is True and features.get(feature_key) is True
