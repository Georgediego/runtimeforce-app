"""
Service for extracting and validating user identification and plan claims from JWT tokens.
"""
import base64
import json
import logging
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("runtimeforce.security.jwt")
security = HTTPBearer(auto_error=False)

class JWTAuthService:
    @staticmethod
    def extract_user_from_jwt(token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        try:
            if token.startswith("Bearer "):
                token = token[7:]
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            decoded = base64.urlsafe_b64decode(payload_b64)
            data = json.loads(decoded)
            user_id = (
                data.get("email") or data.get("sub") or data.get("username")
            )
            if not user_id or str(user_id).lower().strip() == "anonymous":
                return None
            return str(user_id).lower().strip()
        except Exception as e:
            logger.warning(f"JWT decode user failed: {e}")
            return None

    @staticmethod
    def extract_plan_from_jwt(token: Optional[str]) -> str:
        if not token:
            return "free"
        try:
            if token.startswith("Bearer "):
                token = token[7:]
            parts = token.split(".")
            if len(parts) != 3:
                return "free"
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            decoded = base64.urlsafe_b64decode(payload_b64)
            data = json.loads(decoded)
            plan = data.get("plan") or data.get("tier") or "free"
            return str(plan).lower().strip()
        except Exception as e:
            logger.warning(f"JWT decode plan failed: {e}")
            return "free"

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
