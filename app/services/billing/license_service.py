"""Fetch server-verified dynamic entitlements with bounded offline caching."""
import hashlib
import json
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional

import httpx
from app.core.security.jwt_auth_service import JWTAuthService
from app.core.interfaces.license_service_interface import ILicenseService

logger = logging.getLogger("runtimeforce.service.billing.license")
DEFAULT_SERVER_URL = "https://runtimeforce.dev"
REQUEST_TIMEOUT_SECONDS = 5.0
ENTITLEMENT_REFRESH_SECONDS = 30


class LicenseService(ILicenseService):
    def __init__(self, subscription_repo=None):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.subscription_repo = subscription_repo

    async def get_entitlements(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        if not jwt_token:
            return {"valid": False, "plan": "free", "features": {}, "limits": {}, "reason": "No token provided"}

        token = jwt_token.removeprefix("Bearer ").strip()
        token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user_id = JWTAuthService.extract_user_from_jwt(token)
        now = time.time()
        fresh = self._cache.get(token_key)
        if fresh and now - float(fresh.get("validated_at", 0)) < ENTITLEMENT_REFRESH_SECONDS:
            return fresh
        url = f"{DEFAULT_SERVER_URL}/api/v1/billing/entitlements"

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self._cache.pop(token_key, None)
                if self.subscription_repo and user_id:
                    self.subscription_repo.delete("", user_id)
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
            if self.subscription_repo and user_id:
                self.subscription_repo.save_subscription(
                    user_id=user_id,
                    plan=str(result.get("plan") or "free"),
                    valid_until=result.get("valid_until"),
                    entitlements=result,
                )
            return result
        except Exception as exc:
            cached = self._cache.get(token_key)
            cached_at = now
            if not cached and self.subscription_repo and user_id:
                try:
                    row = self.subscription_repo.get_by_id("", user_id)
                    if row and row.get("entitlements_json"):
                        cached = json.loads(row["entitlements_json"])
                        stamp = row.get("cached_at")
                        if stamp:
                            cached_at = datetime.fromisoformat(str(stamp)).replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    cached = None
            if cached:
                grace_hours = max(0, int((cached.get("limits") or {}).get("offline_grace_hours", 0) or 0))
                age = now - float(cached.get("validated_at", cached_at))
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
