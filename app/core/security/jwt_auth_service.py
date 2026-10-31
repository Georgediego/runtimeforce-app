"""
Service for extracting and validating user identification and plan claims from JWT tokens.
"""
import logging
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.auth import decode_token

logger = logging.getLogger("runtimeforce.security.jwt")
security = HTTPBearer(auto_error=False)

class JWTAuthService:
    @staticmethod
    def _verified_payload(token: Optional[str]) -> Optional[dict]:
        if not token:
            return None
        try:
            clean = token[7:] if token.startswith("Bearer ") else token
            payload = decode_token(clean)
            if payload.get("type") != "access":
                return None
            return payload
        except Exception:
            return None

    @classmethod
    def extract_user_from_jwt(cls, token: Optional[str]) -> Optional[str]:
        data = cls._verified_payload(token)
        if not data:
            return None
        user_id = data.get("sub") or data.get("email") or data.get("username")
        if not user_id or str(user_id).lower().strip() == "anonymous":
            return None
        return str(user_id).lower().strip()

    @classmethod
    def extract_plan_from_jwt(cls, token: Optional[str]) -> str:
        data = cls._verified_payload(token)
        if not data:
            return "free"
        return str(data.get("plan") or data.get("tier") or "free").lower().strip()

    @classmethod
    async def get_current_user(
        cls,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> str:
        token = None
        if credentials and credentials.credentials:
            token = credentials.credentials
        elif request.query_params.get("token"):
            token = request.query_params.get("token")
        elif "authorization" in request.headers:
            auth = request.headers["authorization"]
            token = auth[7:] if auth.startswith("Bearer ") else auth
        elif request.cookies.get("jwt_token"):
            token = request.cookies.get("jwt_token")
        elif request.cookies.get("access_token"):
            token = request.cookies.get("access_token")

        user_id = cls.extract_user_from_jwt(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user_id

def require_authenticated_user(user_id: str = Depends(JWTAuthService.get_current_user)) -> str:
    return user_id
