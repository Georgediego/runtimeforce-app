import app.main as main_mod
from fastapi.testclient import TestClient


client = TestClient(main_mod.app)


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
