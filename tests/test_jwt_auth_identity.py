import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.security.jwt_auth_service import JWTAuthService


def _request_with_token() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", b"Bearer signed-token")],
        "query_string": b"",
    })


def test_current_user_uses_normalized_verified_email(monkeypatch):
    async def fake_verify_token(token):
        assert token == "signed-token"
        return {
            "id": "eb8cb0d0-d95d-4551-a235-ce753fe0f3c4",
            "email": "  Margvelan@Gmail.com ",
            "tier": "studio",
        }

    monkeypatch.setattr(
        JWTAuthService, "verify_token", staticmethod(fake_verify_token)
    )

    user_key = asyncio.run(
        JWTAuthService.get_current_user(_request_with_token(), credentials=None)
    )

    assert user_key == "margvelan@gmail.com"


def test_current_user_rejects_missing_verified_email(monkeypatch):
    async def fake_verify_token(token):
        return {
            "id": "eb8cb0d0-d95d-4551-a235-ce753fe0f3c4",
            "email": "",
            "tier": "studio",
        }

    monkeypatch.setattr(
        JWTAuthService, "verify_token", staticmethod(fake_verify_token)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            JWTAuthService.get_current_user(
                _request_with_token(), credentials=None
            )
        )

    assert exc_info.value.status_code == 401
