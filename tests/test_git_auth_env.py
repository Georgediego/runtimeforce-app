import pytest
import base64
from fastapi.testclient import TestClient
from app.services.git.github_git_auth import git_auth_env
from app.services.workspace.workspace_local_driver import WorkspaceLocalDriver
from app.services.workspace.workspace_ssh_driver import WorkspaceSSHDriver
from app.main import app

client = TestClient(app)

def test_git_auth_env_structure():
    fake_token = "ghp_fake_token_12345"
    env = git_auth_env(fake_token)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    expected_raw = base64.b64encode(f"x-access-token:{fake_token}".encode()).decode()
    assert env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {expected_raw}"

@pytest.mark.asyncio
async def test_local_driver_env_passing(tmp_path):
    driver = WorkspaceLocalDriver(str(tmp_path))
    env_dict = {"GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic test_encoded"}
    res = await driver.execute_command('python3 -c "import os; print(os.environ.get(\'GIT_CONFIG_VALUE_0\', \'\'))"', env=env_dict)
    assert res["exit_code"] == 0
    assert "AUTHORIZATION: basic test_encoded" in res["stdout"]

@pytest.mark.asyncio
async def test_ssh_driver_env_raises():
    driver = WorkspaceSSHDriver("some_host")
    with pytest.raises(NotImplementedError):
        await driver.execute_command("git push origin main", env={"SOME": "env"})

def test_git_push_remote_validation_and_token_not_in_command(monkeypatch):
    from app.core.security.jwt_auth_service import require_authenticated_user
    app.dependency_overrides[require_authenticated_user] = lambda: "test_user"

    from app.container import get_project_service, get_workspace_manager
    class MockProjectService:
        def get_active_project(self, user_id):
            return {"id": "proj1"}
        class repo:
            @staticmethod
            def get_project(pid, uid):
                return {"id": pid, "github_pat_enc": ""}

    class MockDriver:
        async def execute_command(self, command, env=None):
            assert "x-access-token" not in command
            assert "fake_token" not in command
            return {"exit_code": 0, "stdout": "", "stderr": ""}

    class MockWorkspaceManager:
        async def get_driver(self, user_id):
            return MockDriver()

    app.dependency_overrides[get_project_service] = lambda: MockProjectService()
    app.dependency_overrides[get_workspace_manager] = lambda: MockWorkspaceManager()

    from app.container import container
    class MockOAuthRepo:
        async def get_token(self, pid, provider):
            return {"access_token": "fake_token_999"}
    container.oauth_repo = MockOAuthRepo()

    # 1. Test remote validation with invalid remote name (space/semicolon)
    response = client.post("/api/v1/git/push", json={"remote": "origin; rm -rf /", "branch": "main"})
    assert response.status_code == 400

    # 2. Test valid push with token not in command string
    response = client.post("/api/v1/git/push", json={"remote": "origin", "branch": "main"})
    assert response.status_code == 200
    assert response.json()["success"] is True

    app.dependency_overrides.clear()

def test_git_push_caplog_no_token(monkeypatch, caplog):
    import logging
    caplog.set_level(logging.DEBUG)

    from app.core.security.jwt_auth_service import require_authenticated_user
    app.dependency_overrides[require_authenticated_user] = lambda: "test_user"

    from app.container import get_project_service, get_workspace_manager
    class MockProjectService:
        def get_active_project(self, user_id):
            return {"id": "proj1"}
        class repo:
            @staticmethod
            def get_project(pid, uid):
                return {"id": pid, "github_pat_enc": ""}

    class MockDriver:
        async def execute_command(self, command, env=None):
            return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    class MockWorkspaceManager:
        async def get_driver(self, user_id):
            return MockDriver()

    app.dependency_overrides[get_project_service] = lambda: MockProjectService()
    app.dependency_overrides[get_workspace_manager] = lambda: MockWorkspaceManager()

    secret_token = "secret_github_token_xyz_888"
    encoded_secret = base64.b64encode(f"x-access-token:{secret_token}".encode()).decode()

    from app.container import container
    class MockOAuthRepo:
        async def get_token(self, pid, provider):
            return {"access_token": secret_token}
    container.oauth_repo = MockOAuthRepo()

    response = client.post("/api/v1/git/push", json={"remote": "origin", "branch": "main"})
    assert response.status_code == 200

    log_text = caplog.text
    assert secret_token not in log_text
    assert encoded_secret not in log_text

    app.dependency_overrides.clear()
