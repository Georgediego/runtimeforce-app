import pytest
from fastapi.testclient import TestClient
from app.services.git.github_api_service import GitHubApiService, GitHubApiError
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_list_repos_pagination_and_filtering(monkeypatch):
    service = GitHubApiService()
    pages_data = [
        [
            {
                "full_name": f"user/repo{i}",
                "private": False,
                "default_branch": "main",
                "clone_url": f"https://github.com/user/repo{i}.git",
                "html_url": f"https://github.com/user/repo{i}",
                "updated_at": "2026-01-01T00:00:00Z",
                "extra_field": "should_be_removed"
            }
            for i in range(100)
        ],
        [
            {
                "full_name": "user/repo100",
                "private": True,
                "default_branch": "dev",
                "clone_url": "https://github.com/user/repo100.git",
                "html_url": "https://github.com/user/repo100",
                "updated_at": "2026-01-02T00:00:00Z",
                "extra_field": "should_be_removed"
            }
        ]
    ]
    call_count = 0
    async def mock_get_json(session, url, headers, path_for_log):
        nonlocal call_count
        data = pages_data[call_count]
        call_count += 1
        return data

    monkeypatch.setattr(service, "_get_json", mock_get_json)

    repos = await service.list_repos("fake_token_xyz")
    assert len(repos) == 101
    assert "extra_field" not in repos[0]
    assert repos[0]["full_name"] == "user/repo0"
    assert repos[100]["private"] is True

@pytest.mark.asyncio
async def test_list_repos_stop_short_page(monkeypatch):
    service = GitHubApiService()
    async def mock_get_json(session, url, headers, path_for_log):
        return [{"full_name": "user/short", "private": False}]

    monkeypatch.setattr(service, "_get_json", mock_get_json)
    repos = await service.list_repos("fake_token_xyz")
    assert len(repos) == 1

def test_token_invalid_error_no_token_in_message():
    err = GitHubApiError(code="github_token_invalid")
    token = "secret_github_token_999"
    assert token not in str(err)
    assert err.code == "github_token_invalid"

def test_repo_name_validation():
    service = GitHubApiService()
    with pytest.raises(GitHubApiError) as excinfo:
        service._validate_repo_name("../x", "repo")
    assert excinfo.value.code == "invalid_repo_name"

    with pytest.raises(GitHubApiError) as excinfo:
        service._validate_repo_name("owner", "a/b")
    assert excinfo.value.code == "invalid_repo_name"

def test_github_repos_endpoint_not_connected(monkeypatch):
    from app.core.security.jwt_auth_service import require_authenticated_user
    app.dependency_overrides[require_authenticated_user] = lambda: "test_user"

    from app.container import get_project_service, get_license_service
    class MockProjectService:
        def get_active_project(self, user_id):
            return {"id": "proj1"}
        class repo:
            @staticmethod
            def get_project(pid, uid):
                return {"id": pid, "github_pat_enc": ""}

    app.dependency_overrides[get_project_service] = lambda: MockProjectService()

    class MockLicenseService:
        async def get_entitlements(self, token):
            return {"valid": True, "features": {"git": True}, "limits": {}}

    app.dependency_overrides[get_license_service] = lambda: MockLicenseService()

    from app.container import container
    class MockOAuthRepo:
        async def get_token(self, pid, provider):
            return None
    container.oauth_repo = MockOAuthRepo()

    response = client.get("/api/v1/git/github/repos")
    assert response.status_code == 409
    assert response.json() == {"error": "github_not_connected"}

    app.dependency_overrides.clear()
