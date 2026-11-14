"""Fetch server-verified dynamic entitlements with bounded offline caching."""
import hashlib
import json
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional

import httpx
from app.core.interfaces.license_service_interface import ILicenseService
from app.core.security.plan_access import feature_enabled

logger = logging.getLogger("runtimeforce.service.billing.license")
DEFAULT_SERVER_URL = "https://runtimeforce.dev"
REQUEST_TIMEOUT_SECONDS = 5.0
ENTITLEMENT_REFRESH_SECONDS = 10


class LicenseService(ILicenseService):
    def __init__(self, subscription_repo=None):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.subscription_repo = subscription_repo

    async def get_entitlements(self, jwt_token: Optional[str], user_id: Optional[str] = None) -> Dict[str, Any]:
        if not jwt_token:
            return {"valid": False, "plan": "free", "features": {}, "limits": {}, "reason": "No token provided"}

        token = jwt_token.removeprefix("Bearer ").strip()
        token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
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
            if not isinstance(data, dict) or not isinstance(data.get("features", {}), dict) or not isinstance(data.get("limits", {}), dict):
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
        except httpx.HTTPStatusError as exc:
            # A definitive 4xx response is not an outage: never extend old privileges.
            if exc.response.status_code < 500:
                self._cache.pop(token_key, None)
                if self.subscription_repo and user_id:
                    self.subscription_repo.delete("", user_id)
                logger.warning("Entitlements rejected by server (HTTP %s)", exc.response.status_code)
                return {
                    "valid": False, "plan": "free", "features": {}, "limits": {},
                    "is_stale": False, "reason": "Entitlements rejected by server",
                }
            return await self._offline_entitlements(token_key, user_id, now, exc)
        except Exception as exc:
            return await self._offline_entitlements(token_key, user_id, now, exc)

    async def _offline_entitlements(self, token_key: str, user_id: Optional[str], now: float, exc: Exception) -> Dict[str, Any]:
        cached = self._cache.get(token_key)
        cached_at = now
        if not cached and self.subscription_repo and user_id:
            try:
                row = self.subscription_repo.get_by_id("", user_id)
                if row and row.get("entitlements_json"):
                    cached = json.loads(row["entitlements_json"])
                    stamp = row.get("cached_at")
                    if stamp:
                        parsed = datetime.fromisoformat(str(stamp))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        cached_at = parsed.timestamp()
            except Exception:
                cached = None

        if cached and cached.get("valid") is True and feature_enabled(cached, "offline_grace"):
            limits = cached.get("limits") or {}
            try:
                grace_hours = max(0, int(limits.get("offline_grace_hours", 0) or 0))
                validated_at = float(cached.get("validated_at", cached_at))
                age = max(0.0, now - validated_at)
            except (TypeError, ValueError):
                grace_hours, age = 0, float("inf")
            if grace_hours > 0 and age <= grace_hours * 3600:
                return {**cached, "is_stale": True}

        logger.warning("Server entitlement check failed (%s)", type(exc).__name__)
        return {
            "valid": False, "plan": "free", "features": {}, "limits": {},
            "is_stale": True, "reason": "Entitlements could not be verified",
        }

    async def validate_license(self, jwt_token: Optional[str]) -> Dict[str, Any]:
        return await self.get_entitlements(jwt_token)

    @staticmethod
    def has_feature(entitlements: Dict[str, Any], feature_key: str) -> bool:
        return feature_enabled(entitlements, feature_key)
