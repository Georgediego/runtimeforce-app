"""JWT verification helpers used by the local RuntimeForce client.

The local IDE does not own the SaaS user database and must not import the
legacy SQLAlchemy authentication stack. Configure JWT_SECRET_KEY with the
same signing secret used by the token issuer.
"""
import os

import jwt
from fastapi import HTTPException, status


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. Set it to the token issuer's "
            "signing secret; MASTER_KEY is not a JWT signing key."
        )
    return secret


def decode_token(token: str) -> dict:
    """Decode and verify a signed JWT, including its expiration."""
    try:
        return jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[os.getenv("JWT_ALGORITHM", "HS256")],
            options={"require": ["exp", "sub"]},
        )
    except RuntimeError:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def extract_user_id(payload: dict) -> str | None:
    """Resolve the local data owner using the historical email-first contract.

    Existing RuntimeForce data is keyed by normalized email. SaaS JWTs may
    also contain a UUID in sub; preferring it would hide existing data.
    """
    if not isinstance(payload, dict):
        return None

    value = payload.get("email") or payload.get("sub") or payload.get("username")
    if value is None:
        return None

    user_id = str(value).strip().lower()
    if not user_id or user_id == "anonymous":
        return None
    return user_id
