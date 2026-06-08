"""
JWT user extraction for local data isolation and subscription plans.
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

def extract_user_info_from_jwt(token: Optional[str]) -> dict:
    default_info = {"user_id": "anonymous", "plan": "free"}
    if not token:
        return default_info
    try:
        if token.startswith("Bearer "):
            token = token[7:]
        parts = token.split(".")
        if len(parts) != 3:
            return default_info
        
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
        # Извлекаем тарифный план (по умолчанию free, если не передан)
        plan = data.get("plan") or data.get("rf_plan") or "free"
        
        if user_id:
            return {
                "user_id": str(user_id).lower().strip(),
                "plan": str(plan).lower().strip()
            }
        return default_info
    except Exception as e:
        logger.warning(f"JWT decode failed: {e}")
        return default_info

async def get_current_user_info(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    token = None
    
    if credentials:
        token = credentials.credentials
    elif "authorization" in request.headers:
        auth = request.headers["authorization"]
        if auth.startswith("Bearer "):
            token = auth[7:]
        else:
            token = auth
    elif "jwt_token" in request.cookies:
        token = request.cookies.get("jwt_token")
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif "x-user-email" in request.headers:
        return {"user_id": request.headers["x-user-email"].lower().strip(), "plan": "free"}
        
    return extract_user_info_from_jwt(token)

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    info = await get_current_user_info(request, credentials)
    return info["user_id"]

async def require_authenticated_user(user_id: str = Depends(get_current_user)) -> str:
    if user_id == "anonymous":
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )
    return user_id