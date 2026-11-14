import pytest
import app.main as main_mod
from fastapi.testclient import TestClient

from app.core.security.entitlements import _license_service_dependency
from app.core.security.jwt_auth_service import require_authenticated_user


client = TestClient(main_mod.app)


class _TestLicenseService:
    async def get_entitlements(self, token):
        return {
            "valid": True,
            "features": {"software_updates": True},
        }


@pytest.fixture(autouse=True)
def authenticated_update_plan():
    original_overrides = main_mod.app.dependency_overrides.copy()
    main_mod.app.dependency_overrides[require_authenticated_user] = lambda: "test-user"
    main_mod.app.dependency_overrides[_license_service_dependency] = _TestLicenseService
    yield
    main_mod.app.dependency_overrides.clear()
    main_mod.app.dependency_overrides.update(original_overrides)


def test_update_apply_rejects_non_local_origin():
    response = client.post(
        "/api/v1/updates/apply",
        headers={
            "Host": "127.0.0.1:8000",
            "Origin": "https://attacker.example",
        },
    )

    assert response.status_code == 403


def test_update_apply_queues_local_update(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "_update_state", {"status": "idle", "message": ""})
    monkeypatch.setattr(main_mod, "_apply_ide_update", lambda: calls.append(True))

    response = client.post(
        "/api/v1/updates/apply",
        headers={
            "Host": "127.0.0.1:8000",
            "Origin": "http://127.0.0.1:8000",
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert calls == [True]
