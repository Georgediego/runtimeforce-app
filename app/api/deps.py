"""Shared API authentication dependency for signed SaaS access tokens."""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.core.auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Return the authenticated subject; the local IDE has no user DB."""
    try:
        payload = decode_token(token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Access token required")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="Invalid token subject")
    return subject.strip()
