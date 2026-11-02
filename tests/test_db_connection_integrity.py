import ast
import glob
import os
import pytest
from fastapi.testclient import TestClient
from app.repository.db_connection import DatabaseConnectionManager
from app.repository.oauth_db_repository import OAuthDBRepository
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_oauth_repository_connection_integrity(tmp_path):
    db_path = str(tmp_path / "test_oauth.db")
    db_manager = DatabaseConnectionManager(db_path=db_path)
    conn = db_manager.get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_oauth_tokens (
            project_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            token_data TEXT NOT NULL,
            expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT DEFAULT 'anonymous',
            UNIQUE(project_id, provider)
        )
    """)
    conn.commit()

    repo = OAuthDBRepository(db_manager)
    pid = "proj_test_1"
    provider = "github"
    token_data = {"access_token": "fake_token_123"}

    # 1. save_token
    res = await repo.save_token(pid, provider, token_data)
    assert res is True
    assert db_manager.get_connection().execute("SELECT 1").fetchone()[0] == 1

    # 2. get_token
    token = await repo.get_token(pid, provider)
    assert token is not None
    assert db_manager.get_connection().execute("SELECT 1").fetchone()[0] == 1

    # 3. delete_token
    deleted = await repo.delete_token(pid, provider)
    assert deleted is True
    assert db_manager.get_connection().execute("SELECT 1").fetchone()[0] == 1


def test_static_ast_no_close_on_shared_connections():
    """
    Static analysis test: ensure that in app/repository/*.py, connections retrieved via get_connection()
    are never closed with .close() within the same function scope.
    """
    repo_files = glob.glob("app/repository/*.py")
    assert len(repo_files) > 0, "No repository files found"

    for filepath in repo_files:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                conn_vars = set()
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Assign):
                        is_get_conn = False
                        for child in ast.walk(subnode.value):
                            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "get_connection":
                                is_get_conn = True
                                break
                        if is_get_conn:
                            for target in subnode.targets:
                                if isinstance(target, ast.Name):
                                    conn_vars.add(target.id)

                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Attribute) and subnode.func.attr == "close":
                        if isinstance(subnode.func.value, ast.Name) and subnode.func.value.id in conn_vars:
                            pytest.fail(f"Found forbidden connection .close() on shared connection '{subnode.func.value.id}' in {filepath}:{node.name}")


def test_integration_endpoints_connection_alive(monkeypatch):
    """
    Integration test: call GET /api/v1/git/github/repos, then GET /api/v1/projects and GET /api/v1/workspaces,
    verifying all return 200 and connection remains active.
    """
    from app.core.security.jwt_auth_service import require_authenticated_user
    app.dependency_overrides[require_authenticated_user] = lambda: "test_user_int"

    from app.container import get_project_service, get_license_service
    class MockProjectRepo:
        def get_active_project(self, user_id):
            return {"id": "proj_int_1", "user_id": user_id, "github_pat_enc": ""}
        def get_project(self, pid, uid):
            return {"id": pid, "user_id": uid, "github_pat_enc": ""}
        def list_projects(self, user_id):
            return [{"id": "proj_int_1", "user_id": user_id}]

    class MockProjectService:
        def __init__(self):
            self.repo = MockProjectRepo()
        def get_active_project(self, user_id):
            return self.repo.get_active_project(user_id)
        def list_projects(self, user_id):
            return self.repo.list_projects(user_id)

    app.dependency_overrides[get_project_service] = lambda: MockProjectService()

    class MockLicenseService:
        async def get_entitlements(self, token):
            return {"valid": True, "features": {"git": True}, "limits": {}}

    app.dependency_overrides[get_license_service] = lambda: MockLicenseService()

    from app.services.git.github_api_service import GitHubApiService
    async def mock_list_repos(self, token):
        return [{"full_name": "test/repo", "private": False, "default_branch": "main"}]
    monkeypatch.setattr(GitHubApiService, "list_repos", mock_list_repos)

    from app.container import container
    class MockOAuthRepo:
        async def get_token(self, pid, provider):
            return {"access_token": "fake_oauth_token_999"}
    container.oauth_repo = MockOAuthRepo()

    res_repos = client.get("/api/v1/git/github/repos?project_id=proj_int_1")
    assert res_repos.status_code == 200, f"Repos failed: {res_repos.text}"

    res_projects = client.get("/api/v1/projects")
    assert res_projects.status_code == 200, f"Projects failed: {res_projects.text}"

    res_workspaces = client.get("/api/v1/workspaces?project_id=proj_int_1")
    assert res_workspaces.status_code == 200, f"Workspaces failed: {res_workspaces.text}"

    app.dependency_overrides.clear()
