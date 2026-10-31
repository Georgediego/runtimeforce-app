"""Validate and cache SaaS-signed plan entitlements for 24-hour offline use."""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.auth import decode_token

logger = logging.getLogger("runtimeforce.service.billing.license")

ENTITLEMENT_TYPE = "entitlement"
GRACE_PERIOD_SECONDS = 24 * 60 * 60
ALLOWED_SUBSCRIPTION_STATES = {"active", "trialing"}


class LicenseService:
    def __init__(self):
        self.cache_path = (
            Path.home() / ".local" / "share" / "runtimeforce" / "entitlement.json"
        )

    def _read_cache(self) -> dict:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_cache(self, token: str, last_seen: int) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cache_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps({"token": token, "last_seen_utc": last_seen}),
            encoding="utf-8",
        )
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(self.cache_path)

    def validate_license(
        self,
        entitlement_token: Optional[str] = None,
        expected_subject: Optional[str] = None,
    ) -> Dict[str, Any]:
        cache = self._read_cache()
        token = entitlement_token or cache.get("token")
        if not token:
            return {"valid": False, "plan": "free", "reason": "No verified entitlement"}

        try:
            payload = decode_token(token)
            if payload.get("type") != ENTITLEMENT_TYPE:
                raise ValueError("Not an entitlement token")
            if payload.get("subscription_status", "active") not in ALLOWED_SUBSCRIPTION_STATES:
                raise ValueError("Subscription is not active")
            if expected_subject and payload.get("sub") != expected_subject:
                raise ValueError("Entitlement belongs to another account")

            now = int(time.time())
            last_seen = int(cache.get("last_seen_utc") or 0)
            if last_seen and now < last_seen - 300:
                raise ValueError("System clock moved backwards")

            expires_at = int(payload["exp"])
            if expires_at - int(payload["iat"]) > GRACE_PERIOD_SECONDS:
                raise ValueError("Entitlement exceeds the 24-hour offline limit")

            self._write_cache(token, max(now, last_seen))
            features = payload.get("features") or []
            return {
                "valid": True,
                "plan": str(payload.get("plan") or "free"),
                "features": features,
                "limits": payload.get("limits") or {},
                "byok_enabled": any("byok" in str(item).lower() for item in features),
                "subscription_status": payload.get("subscription_status", "active"),
                "expires_at": expires_at,
                "offline_grace_seconds": GRACE_PERIOD_SECONDS,
                "offline": entitlement_token is None,
            }
        except Exception as exc:
            logger.info("Entitlement validation failed: %s", exc)
            return {
                "valid": False,
                "plan": "free",
                "reason": str(exc),
            }

    def clear_cache(self) -> None:
        try:
            self.cache_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not clear entitlement cache: %s", exc)

    def is_offline_grace_valid(self) -> bool:
        return bool(self.validate_license().get("valid"))
