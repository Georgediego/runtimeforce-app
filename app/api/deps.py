"""Shared API authentication dependency for signed SaaS access tokens."""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.core.auth import decode_token, extract_user_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Return the normalized local data owner from a verified access token."""
    try:
        payload = decode_token(token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Access token required")

    user_id = extract_user_id(payload)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token user identity")
    return user_id
