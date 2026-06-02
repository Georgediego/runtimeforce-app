"""
JWT user extraction for local data isolation.
Decodes JWT payload WITHOUT signature verification (local IDE trust model).
"""
import base64
import json
import logging
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("ai_runtime.auth")
security = HTTPBearer(auto_error=False)

def extract_user_from_jwt(token: Optional[str]) -> str:
    if not token:
        return "anonymous"
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        parts = token.split(".")
        if len(parts) != 3:
            return "anonymous"
        
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
            
        decoded = base64.urlsafe_b64decode(payload_b64)
        data = json.loads(decoded)
        
        user_id = (
            data.get("email") 
            or data.get("sub") 
            or data.get("username")
            or data.get("preferred_username")
        )
        if user_id:
            return str(user_id).lower().strip()
        return "anonymous"
    except Exception as e:
        logger.warning(f"JWT decode failed: {e}")
        return "anonymous"

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    token = None
    
    # 1. Проверка стандартного Bearer-токена
    if credentials:
        token = credentials.credentials
    # 2. Проверка заголовка Authorization напрямую
    elif "authorization" in request.headers:
        auth = request.headers["authorization"]
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = auth
    # 3. Новое: Автоматическая проверка Cookies (если токен там)
    elif "jwt_token" in request.cookies:
        token = request.cookies.get("jwt_token")
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    # 4. Fallback заголовок для отладки
    elif "x-user-email" in request.headers:
        return request.headers["x-user-email"].lower().strip()
        
    return extract_user_from_jwt(token)

async def require_authenticated_user(user_id: str = Depends(get_current_user)) -> str:
    if user_id == "anonymous":
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )
    return user_id