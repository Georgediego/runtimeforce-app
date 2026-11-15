import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException, Request

from app.core.security.jwt_auth_service import (
    AuthVerificationUnavailable,
    JWTAuthService,
    _AUTH_CACHE,
)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, response=None, error=None, **kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def run_verify(monkeypatch, response=None, error=None):
    _AUTH_CACHE.clear()
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response, error=error, **kwargs),
    )
    return asyncio.run(JWTAuthService.verify_token("test-token"))


def test_invalid_or_expired_token_is_rejected(monkeypatch):
    assert run_verify(monkeypatch, response=FakeResponse(401)) is None
    assert run_verify(monkeypatch, response=FakeResponse(403)) is None


def test_auth_control_plane_error_is_not_reported_as_invalid_token(monkeypatch):
    with pytest.raises(AuthVerificationUnavailable):
        run_verify(monkeypatch, response=FakeResponse(503))


def test_auth_network_error_is_not_reported_as_invalid_token(monkeypatch):
    with pytest.raises(AuthVerificationUnavailable):
        run_verify(monkeypatch, error=httpx.ConnectError("offline"))


def test_valid_token_returns_only_verified_account_fields(monkeypatch):
    user = run_verify(
        monkeypatch,
        response=FakeResponse(
            200,
            {
                "id": "account-123",
                "email": "USER@example.com",
                "is_active": True,
                "tier": "pro",
                "untrusted_extra": "ignored",
            },
        ),
    )
    assert user == {
        "id": "account-123",
        "email": "user@example.com",
        "tier": "pro",
    }


def test_http_dependency_returns_503_when_control_plane_is_unavailable(monkeypatch):
    async def unavailable(token):
        raise AuthVerificationUnavailable("offline")

    monkeypatch.setattr(JWTAuthService, "verify_token", unavailable)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/models",
            "headers": [(b"authorization", b"Bearer test-token")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
            "scheme": "http",
        }
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(JWTAuthService.get_current_user(request, credentials=None))

    assert error.value.status_code == 503
