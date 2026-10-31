"""JWT verification for the local RuntimeForce client.

Only RS256 tokens issued by RuntimeForce SaaS are accepted. The signing
private key never exists in this application; the public JWKS is cached locally
so already-issued tokens can be checked while offline.
"""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

import jwt
from fastapi import HTTPException, status

JWT_ISSUER = "https://runtimeforce.dev"
JWT_AUDIENCE = "runtimeforce-ide"
JWKS_URL = os.getenv("JWT_JWKS_URL", "https://runtimeforce.dev/api/v1/auth/jwks.json")
_JWKS_CACHE = None


def _jwks_cache_path() -> Path:
    return Path.home() / ".local" / "share" / "runtimeforce" / "jwks.json"


def _read_cached_jwks():
    path = _jwks_cache_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cached_jwks(data: dict) -> None:
    path = _jwks_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)


def _load_jwks():
    global _JWKS_CACHE
    if _JWKS_CACHE:
        return _JWKS_CACHE

    cached = _read_cached_jwks()
    try:
        if not JWKS_URL.startswith("https://"):
            raise RuntimeError("JWT JWKS URL must use HTTPS")
        request = Request(JWKS_URL, headers={"Accept": "application/json"})
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data.get("keys"), list) or not data["keys"]:
            raise ValueError("JWKS response has no signing keys")
        _write_cached_jwks(data)
        _JWKS_CACHE = data
        return data
    except Exception:
        if cached and isinstance(cached.get("keys"), list) and cached["keys"]:
            _JWKS_CACHE = cached
            return cached
        raise RuntimeError("Cannot load RuntimeForce signing keys; connect to the internet once")


def _get_verification_key(token: str):
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256":
        raise jwt.InvalidAlgorithmError("Only RS256 tokens are accepted")
    kid = header.get("kid")
    if not kid:
        raise jwt.InvalidTokenError("JWT kid is missing")
    for jwk_data in _load_jwks()["keys"]:
        if jwk_data.get("kid") == kid and jwk_data.get("alg") == "RS256":
            return jwt.PyJWK.from_dict(jwk_data, algorithm="RS256").key
    raise jwt.InvalidTokenError("JWT signing key is unknown")


def decode_token(token: str) -> dict:
    """Verify RS256 signature, issuer, audience and expiration."""
    try:
        return jwt.decode(
            token,
            _get_verification_key(token),
            algorithms=["RS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except RuntimeError:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired RuntimeForce token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def extract_user_id(payload: dict) -> str | None:
    """Keep the existing email-first local database namespace unchanged."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("email") or payload.get("sub") or payload.get("username")
    if value is None:
        return None
    user_id = str(value).strip().lower()
    if not user_id or user_id == "anonymous":
        return None
    return user_id
