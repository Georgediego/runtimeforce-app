"""Fetch server-verified dynamic entitlements with bounded, expiry-aware offline caching."""
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


def _timestamp(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


class LicenseService(ILicenseService):
    def __init__(self, subscription_repo=None):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.subscription_repo = subscription_repo

    @staticmethod
    def _invalid(reason):
        return {
            "valid": False, "plan": "free", "features": {}, "limits": {},
            "is_stale": True, "reason": reason,
        }

    async def get_entitlements(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        if not jwt_token:
            return self._invalid("No token provided")

        token = jwt_token.removeprefix("Bearer ").strip()
        token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user_id = JWTAuthService.extract_user_from_jwt(token)
        now = time.time()
        cached = self._cache.get(token_key)
        if cached and now - float(cached.get("validated_at", 0)) < ENTITLEMENT_REFRESH_SECONDS:
            if self._not_expired(cached, now):
                return cached
            self._cache.pop(token_key, None)

        url = f"{DEFAULT_SERVER_URL}/api/v1/billing/entitlements"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 401:
                self._cache.pop(token_key, None)
                if self.subscription_repo and user_id:
                    self.subscription_repo.delete("", user_id)
                return self._invalid("Authentication expired")
            response.raise_for_status()
            data = response.json()
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("features"), dict)
                or not isinstance(data.get("limits"), dict)
            ):
                raise ValueError("Invalid entitlements response")
            result = {
                **data,
                "valid": data.get("valid", True) is True,
                "features": data["features"],
                "limits": data["limits"],
                "is_stale": False,
                "validated_at": now,
            }
            if not result["valid"] or not self._not_expired(result, now):
                self._cache.pop(token_key, None)
                return self._invalid("Subscription is not active")
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
            # Prefer the most recently validated in-memory snapshot, otherwise SQLite.
            cached = self._cache.get(token_key)
            cached_at = None
            if not cached and self.subscription_repo and user_id:
                try:
                    row = self.subscription_repo.get_by_id("", user_id)
                    if row and row.get("entitlements_json"):
                        cached = json.loads(row["entitlements_json"])
                        cached_at = _timestamp(row.get("cached_at"))
                except Exception:
                    cached = None
            if cached and cached.get("valid") is True:
                validated_at = cached.get("validated_at")
                try:
                    validated_at = float(validated_at) if validated_at is not None else cached_at
                except (TypeError, ValueError):
                    validated_at = cached_at
                grace_value = (cached.get("limits") or {}).get("offline_grace_hours")
                if grace_value is None:
                    grace_value = cached.get("offline_grace_hours")
                if grace_value is None and isinstance(cached.get("offline_grace"), dict):
                    grace_value = cached["offline_grace"].get("hours")
                grace_hours = max(0, int(grace_value or 0))
                if validated_at is not None and grace_hours > 0:
                    age = max(0, now - validated_at)
                    if age <= grace_hours * 3600 and self._not_expired(cached, now):
                        return {**cached, "is_stale": True, "offline_age_seconds": int(age)}
            logger.warning("Server entitlement check failed (%s)", type(exc).__name__)
            return self._invalid("Entitlements could not be verified")

    @staticmethod
    def _not_expired(entitlements: Dict[str, Any], now: float) -> bool:
        raw_expiry = entitlements.get("valid_until")
        if raw_expiry in (None, ""):
            return True
        expiry = _timestamp(raw_expiry)
        return expiry is not None and expiry > now

    async def validate_license(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        return await self.get_entitlements(jwt_token)

    @staticmethod
    def has_feature(entitlements: Dict[str, Any], feature_key: str) -> bool:
        from app.core.security.entitlements import feature_enabled
        return feature_enabled(entitlements, feature_key)
