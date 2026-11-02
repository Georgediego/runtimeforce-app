import pytest
from fastapi.testclient import TestClient
from app.config import config
from app.main import app

client = TestClient(app)

def test_app_config():
    assert config.APP_NAME == "RuntimeForce IDE"
    assert config.VERSION == "0.5.2"
    assert isinstance(config.PORT, int)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
