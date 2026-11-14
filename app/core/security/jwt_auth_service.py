"""Authentication bridge: JWTs are trusted only after verification by RuntimeForce SaaS."""
import hashlib
import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("runtimeforce.security.jwt")
security = HTTPBearer(auto_error=False)

# Deliberately fixed: production authentication and entitlements must use the
# official RuntimeForce control plane, never a user-configurable endpoint.
RUNTIMEFORCE_AUTH_URL = "https://runtimeforce.dev/api/v1/auth/me"
AUTH_CACHE_TTL_SECONDS = 10
_AUTH_CACHE: Dict[str, Dict[str, Any]] = {}


class JWTAuthService:
    @staticmethod
    def get_local_user_id(user: Dict[str, Any]) -> str:
        """Use the verified email as the stable local SQLite ownership key."""
        return str(user.get("email") or "").strip().lower()

    @staticmethod
    async def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Ask the official SaaS server to verify the token signature and account."""
        if not token:
            return None
        token = token.removeprefix("Bearer ").strip()
        if not token:
            return None

        cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = _AUTH_CACHE.get(cache_key)
        if cached and now - cached["checked_at"] < AUTH_CACHE_TTL_SECONDS:
            return dict(cached["user"])

        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
                response = await client.get(
                    RUNTIMEFORCE_AUTH_URL,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
            if response.status_code in {401, 403}:
                _AUTH_CACHE.pop(cache_key, None)
                return None
            if response.status_code >= 500 or response.status_code in {408, 429}:
                raise httpx.HTTPStatusError(
                    f"RuntimeForce auth verification failed with HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            if response.status_code != 200:
                _AUTH_CACHE.pop(cache_key, None)
                return None
            data = response.json()
            if not isinstance(data, dict) or not data.get("id") or data.get("is_active") is not True:
                return None
            email = str(data.get("email") or "").strip().lower()
            if not email:
                return None
            # SaaS UUID verifies the account; local IDE data uses the verified,
            # normalized email as its stable SQLite ownership key.
            user = {
                "id": str(data["id"]),
                "email": email,
                "tier": str(data.get("tier") or "free"),
            }
            _AUTH_CACHE[cache_key] = {"checked_at": now, "user": user}
            if len(_AUTH_CACHE) > 512:
                oldest = sorted(_AUTH_CACHE, key=lambda key: _AUTH_CACHE[key]["checked_at"])[:128]
                for key in oldest:
                    _AUTH_CACHE.pop(key, None)
            return user
        except Exception as exc:
            logger.warning("RuntimeForce account verification failed (%s)", type(exc).__name__)
            # Offline authentication is permitted only for a token fingerprint
            # previously verified online and only while its cached plan allows grace.
            try:
                from app.container import container

                subscription_repo = getattr(container, "subscription_repo", None)
                license_service = getattr(container, "license_service", None)
                cached_email = (
                    subscription_repo.get_user_id_by_token_hash(cache_key)
                    if subscription_repo else None
                )
                if cached_email and license_service:
                    entitlements = await license_service.get_entitlements(token, user_id=cached_email)
                    if entitlements.get("valid") is True:
                        user = {
                            "id": cached_email,
                            "email": cached_email,
                            "tier": str(entitlements.get("plan") or "free"),
                        }
                        _AUTH_CACHE[cache_key] = {"checked_at": now, "user": user}
                        return user
            except Exception as offline_exc:
                logger.warning("Offline account verification failed (%s)", type(offline_exc).__name__)
            return None

    @staticmethod
    def extract_user_from_jwt(token: Optional[str]) -> Optional[str]:
        """Unverified local JWT decoding is intentionally disabled."""
        return None

    @staticmethod
    def extract_plan_from_jwt(token: Optional[str]) -> str:
        """Plan claims are never trusted from a locally decoded JWT."""
        return "free"

    @classmethod
    async def get_current_user(
        cls,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> str:
        token = credentials.credentials if credentials and credentials.credentials else None
        if not token:
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                token = authorization[7:].strip()
        if not token:
            token = request.cookies.get("access_token") or request.cookies.get("jwt_token")

        user = await cls.verify_token(token)
        email = str(user.get("email") or "").strip().lower() if user else ""
        if not email:
            raise HTTPException(status_code=401, detail="Authentication required")
        return email


def require_authenticated_user(user_id: str = Depends(JWTAuthService.get_current_user)) -> str:
    return user_id
