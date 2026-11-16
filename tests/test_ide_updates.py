import pytest
import app.main as main_mod
from fastapi.testclient import TestClient


client = TestClient(main_mod.app)


@pytest.fixture(autouse=True)
def allow_software_updates_feature():
    """Override an entitlement dependency only when the route actually has one."""
    route = next(
        route
        for route in main_mod.app.routes
        if getattr(route, "path", None) == "/api/v1/updates/apply"
    )
    if not route.dependant.dependencies:
        yield
        return

    feature_dependency = route.dependant.dependencies[0].call
    previous = main_mod.app.dependency_overrides.get(feature_dependency)
    main_mod.app.dependency_overrides[feature_dependency] = lambda: "test-user"
    try:
        yield
    finally:
        if previous is None:
            main_mod.app.dependency_overrides.pop(feature_dependency, None)
        else:
            main_mod.app.dependency_overrides[feature_dependency] = previous


def test_update_apply_rejects_non_local_origin():
    response = client.post(
        "/api/v1/updates/apply",
        headers={
            "Host": "127.0.0.1:8000",
            "Origin": "https://attacker.example",
        },
    )

    assert response.status_code == 403


def test_update_apply_queues_local_update(monkeypatch, tmp_path):
    calls = []
    marker = tmp_path / "apt-managed"
    monkeypatch.setattr(main_mod, "APT_MANAGED_MARKER", marker)
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



def test_update_apply_accepts_matching_local_origin_on_dynamic_port(monkeypatch):
    calls = []
    monkeypatch.setattr(main_mod, "APT_MANAGED_MARKER", main_mod.Path("/nonexistent/runtimeforce-apt-marker"))
    monkeypatch.setattr(main_mod, "_update_state", {"status": "idle", "message": ""})
    monkeypatch.setattr(main_mod, "_apply_ide_update", lambda: calls.append(True))

    response = client.post(
        "/api/v1/updates/apply",
        headers={
            "Host": "127.0.0.1:23841",
            "Origin": "http://127.0.0.1:23841",
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert calls == [True]


def test_update_apply_rejects_apt_managed_install(monkeypatch, tmp_path):
    marker = tmp_path / "apt-managed"
    marker.write_text("APT\n", encoding="utf-8")
    monkeypatch.setattr(main_mod, "APT_MANAGED_MARKER", marker)

    response = client.post(
        "/api/v1/updates/apply",
        headers={
            "Host": "127.0.0.1:23841",
            "Origin": "http://127.0.0.1:23841",
        },
    )

    assert response.status_code == 409
    assert "APT" in response.json()["detail"]


def test_update_check_reports_apt_install_method(monkeypatch, tmp_path):
    marker = tmp_path / "apt-managed"
    marker.write_text("APT\n", encoding="utf-8")
    monkeypatch.setattr(main_mod, "APT_MANAGED_MARKER", marker)

    async def latest_version():
        return "v1.1.21", "test"

    monkeypatch.setattr(main_mod, "fetch_latest_ide_version", latest_version)
    response = client.get("/api/v1/updates/check")

    assert response.status_code == 200
    assert response.json()["install_method"] == "apt"


def test_self_updater_refuses_apt_managed_install(monkeypatch, tmp_path):
    marker = tmp_path / "apt-managed"
    marker.write_text("APT\n", encoding="utf-8")
    monkeypatch.setattr(main_mod, "APT_MANAGED_MARKER", marker)

    with pytest.raises(RuntimeError, match="managed by APT"):
        main_mod._apply_ide_update()
