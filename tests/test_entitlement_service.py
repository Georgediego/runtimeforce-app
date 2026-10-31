import json
import time

from app.services.billing import license_service as license_module


def _claims(subject="user-123", issued_at=None, expires_at=None):
    now = int(time.time())
    issued_at = issued_at or now
    expires_at = expires_at or issued_at + 86400
    return {
        "iss": "https://runtimeforce.dev",
        "aud": "runtimeforce-ide",
        "sub": subject,
        "type": "entitlement",
        "plan": "studio",
        "subscription_status": "active",
        "features": ["Full Pro BYOK"],
        "limits": {"workspaces": 5},
        "iat": issued_at,
        "exp": expires_at,
    }


def test_entitlement_is_cached_locally_and_reused_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(license_module, "decode_token", lambda token: _claims())
    service = license_module.LicenseService()
    service.cache_path = tmp_path / "entitlement.json"

    online = service.validate_license("signed-entitlement", expected_subject="user-123")
    assert online["valid"] is True
    assert online["plan"] == "studio"
    assert online["byok_enabled"] is True
    assert online["limits"]["workspaces"] == 5

    cached = json.loads(service.cache_path.read_text())
    assert cached["token"] == "signed-entitlement"
    assert service.cache_path.exists()

    offline_service = license_module.LicenseService()
    offline_service.cache_path = service.cache_path
    offline = offline_service.validate_license(expected_subject="user-123")
    assert offline["valid"] is True
    assert offline["offline"] is True


def test_entitlement_cannot_be_used_for_another_account(tmp_path, monkeypatch):
    monkeypatch.setattr(license_module, "decode_token", lambda token: _claims())
    service = license_module.LicenseService()
    service.cache_path = tmp_path / "entitlement.json"

    result = service.validate_license("signed-entitlement", expected_subject="another-user")
    assert result["valid"] is False


def test_entitlement_cannot_extend_beyond_24_hours(tmp_path, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(
        license_module,
        "decode_token",
        lambda token: _claims(issued_at=now, expires_at=now + 86401),
    )
    service = license_module.LicenseService()
    service.cache_path = tmp_path / "entitlement.json"

    result = service.validate_license("signed-entitlement", expected_subject="user-123")
    assert result["valid"] is False
    assert "24-hour" in result["reason"]


def test_clock_rollback_invalidates_cached_entitlement(tmp_path, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(license_module, "decode_token", lambda token: _claims())
    service = license_module.LicenseService()
    service.cache_path = tmp_path / "entitlement.json"
    service.cache_path.parent.mkdir(parents=True, exist_ok=True)
    service.cache_path.write_text(json.dumps({
        "token": "signed-entitlement",
        "last_seen_utc": now + 3600,
    }))

    result = service.validate_license(expected_subject="user-123")
    assert result["valid"] is False
    assert "backwards" in result["reason"]
