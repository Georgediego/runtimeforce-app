from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security.plan_access import (
    command_creates_git_repo,
    command_clones_git_repo,
    command_requires_git,
    feature_enabled,
    model_allowed_by_plan,
    plan_limit,
    require_feature,
    require_limit,
)


def free_entitlements():
    return {
        "valid": True,
        "plan": "free",
        "features": {
            "auto": True,
            "manual": True,
            "atm": False,
            "local_llms": True,
            "free_cloud_byok": True,
            "full_pro_byok": False,
            "git": False,
            "terminal": True,
            "editor": True,
            "offline_grace": True,
            "software_updates": True,
        },
        "limits": {
            "max_projects": 1,
            "max_ssh_hosts": 1,
            "git_repos": 0,
            "offline_grace_hours": 48,
        },
    }


def test_free_plan_feature_flags_are_enforced():
    entitlements = free_entitlements()
    assert feature_enabled(entitlements, "auto")
    assert feature_enabled(entitlements, "manual")
    assert feature_enabled(entitlements, "local_llms")
    assert not feature_enabled(entitlements, "atm")
    assert not feature_enabled(entitlements, "full_pro_byok")
    assert not feature_enabled(entitlements, "git")


def test_unverified_entitlements_fail_closed():
    entitlements = free_entitlements()
    entitlements["valid"] = False
    assert not feature_enabled(entitlements, "auto")
    with pytest.raises(HTTPException) as error:
        require_feature(entitlements, "auto")
    assert error.value.status_code == 403


def test_model_access_uses_provider_classification_before_catalog_tier():
    entitlements = free_entitlements()
    assert model_allowed_by_plan(entitlements, SimpleNamespace(provider="openrouter", tier="standard"))
    assert not model_allowed_by_plan(entitlements, SimpleNamespace(provider="openai", tier="free"))
    assert model_allowed_by_plan(entitlements, SimpleNamespace(provider="ollama", tier="local"))
    entitlements["features"]["local_llms"] = False
    assert not model_allowed_by_plan(entitlements, SimpleNamespace(provider="ollama", tier="local"))


def test_zero_and_positive_plan_limits():
    entitlements = free_entitlements()
    assert plan_limit(entitlements, "max_projects") == 1
    assert plan_limit(entitlements, "max_ssh_hosts") == 1
    assert plan_limit(entitlements, "git_repos") == 0
    with pytest.raises(HTTPException) as error:
        require_limit(entitlements, "git_repos", 0, "Git Repositories")
    assert error.value.status_code == 403
    require_limit(entitlements, "max_projects", 0, "Active Projects")


def test_git_command_detection():
    assert command_requires_git("git status")
    assert command_requires_git("git push origin main")
    assert command_requires_git("gh repo clone owner/repo")
    assert command_requires_git('bash -c "git push origin main"')
    assert command_requires_git('python -c "subprocess.run([\'git\', \'push\'])"')
    assert command_clones_git_repo('bash -c "git clone https://example.com/repo.git"')
    assert not command_clones_git_repo("git init")
    assert command_creates_git_repo("git clone https://github.com/a/b.git")
    assert not command_creates_git_repo("git status")



def test_agent_coordinator_rejects_atm_before_running_tools():
    import asyncio

    from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator

    async def run():
        coordinator = AgentLoopCoordinator(orchestrator_service=None)
        stream = coordinator.run_agent_loop(
            session_id="plan-test",
            messages=[{"role": "user", "content": "run a task"}],
            driver=None,
            strategy="coding",
            plan="free",
            plan_entitlements=free_entitlements(),
        )
        first = await anext(stream)
        assert first["status"] == "error"
        assert first["code"] == 403
        assert first["feature"] == "atm"

    asyncio.run(run())



def test_project_access_keeps_only_projects_within_current_allowance(monkeypatch):
    from app.core.security import entitlements as entitlement_dependencies

    class ProjectRepo:
        def list_projects(self, user_id):
            return [{"id": "active"}, {"id": "older"}]

    monkeypatch.setattr(entitlement_dependencies.container, "project_repo", ProjectRepo())
    entitlements = free_entitlements()
    entitlement_dependencies.require_project_access("user-1", "active", entitlements)
    with pytest.raises(HTTPException) as error:
        entitlement_dependencies.require_project_access("user-1", "older", entitlements)
    assert error.value.status_code == 403
    assert error.value.detail["limit"] == "max_projects"



def test_offline_grace_accepts_only_cached_verified_entitlements_inside_window():
    import asyncio
    import time

    from app.services.billing.license_service import LicenseService

    async def run():
        now = time.time()
        service = LicenseService()
        service._cache["token-key"] = {
            "valid": True,
            "plan": "free",
            "features": {"offline_grace": True},
            "limits": {"offline_grace_hours": 48},
            "validated_at": now - (47 * 3600),
        }
        result = await service._offline_entitlements("token-key", None, now, RuntimeError("offline"))
        assert result["valid"] is True
        assert result["is_stale"] is True

    asyncio.run(run())


def test_offline_grace_fails_closed_when_flag_disabled_or_window_expired():
    import asyncio
    import time

    from app.services.billing.license_service import LicenseService

    async def run():
        now = time.time()
        service = LicenseService()
        service._cache["disabled"] = {
            "valid": True,
            "features": {"offline_grace": False},
            "limits": {"offline_grace_hours": 48},
            "validated_at": now,
        }
        disabled = await service._offline_entitlements("disabled", None, now, RuntimeError("offline"))
        assert disabled["valid"] is False

        service._cache["expired"] = {
            "valid": True,
            "features": {"offline_grace": True},
            "limits": {"offline_grace_hours": 48},
            "validated_at": now - (49 * 3600),
        }
        expired = await service._offline_entitlements("expired", None, now, RuntimeError("offline"))
        assert expired["valid"] is False

    asyncio.run(run())



def test_ssh_host_allowance_prioritizes_active_host_after_downgrade(monkeypatch):
    from app.core.security import entitlements as entitlement_dependencies

    class ProjectRepo:
        def list_projects(self, user_id):
            return [
                {"id": "active", "ssh_host": "z-active.example"},
                {"id": "older", "ssh_host": "a-older.example"},
            ]

        def get_active_project(self, user_id):
            return {"id": "active", "ssh_host": "z-active.example"}

    class WorkspaceRepo:
        def get_all_workspaces(self, user_id, project_id):
            return []

        def get_workspace_by_project_id(self, project_id, user_id):
            return None

    monkeypatch.setattr(entitlement_dependencies.container, "project_repo", ProjectRepo())
    monkeypatch.setattr(entitlement_dependencies.container, "workspace_repo", WorkspaceRepo())
    entitlements = free_entitlements()
    assert entitlement_dependencies.allowed_ssh_hosts("user-1", entitlements) == {"z-active.example"}
    entitlement_dependencies.require_ssh_host_access("user-1", "z-active.example", entitlements)
    with pytest.raises(HTTPException) as error:
        entitlement_dependencies.require_ssh_host_access("user-1", "a-older.example", entitlements)
    assert error.value.status_code == 403



def test_git_repo_quota_blocks_existing_repository_outside_allowance(monkeypatch):
    import asyncio

    from app.core.security import entitlements as entitlement_dependencies

    async def fake_repo_ids(user_id, workspace_manager, entitlements):
        return ["oldest-repo", "over-limit-repo"]

    monkeypatch.setattr(entitlement_dependencies, "user_git_repo_ids", fake_repo_ids)
    entitlements = free_entitlements()
    entitlements["features"]["git"] = True
    entitlements["limits"]["git_repos"] = 1

    async def run():
        state = await entitlement_dependencies.git_repo_quota_state(
            "user-1", "over-limit-repo", object(), entitlements
        )
        assert state["used"] == 2
        assert state["current_project_has_repo"] is True
        assert state["current_project_allowed"] is False
        assert state["can_use_git"] is False
        with pytest.raises(HTTPException) as error:
            await entitlement_dependencies.require_git_repo_access(
                "user-1", "over-limit-repo", object(), entitlements
            )
        assert error.value.status_code == 403
        assert error.value.detail["limit"] == "git_repos"

    asyncio.run(run())



def test_ssh_allowance_uses_allowed_project_host_when_active_project_is_locked(monkeypatch):
    from app.core.security import entitlements as entitlement_dependencies

    class ProjectRepo:
        def list_projects(self, user_id):
            return [
                {"id": "older", "ssh_host": "older.example", "created_at": "2025-01-01"},
                {"id": "active-newer", "ssh_host": "newer.example", "created_at": "2025-02-01"},
            ]

        def get_active_project(self, user_id):
            return {"id": "active-newer", "ssh_host": "newer.example"}

    class WorkspaceRepo:
        def get_all_workspaces(self, user_id, project_id):
            return []

        def get_workspace_by_project_id(self, project_id, user_id):
            return None

    monkeypatch.setattr(entitlement_dependencies.container, "project_repo", ProjectRepo())
    monkeypatch.setattr(entitlement_dependencies.container, "workspace_repo", WorkspaceRepo())
    assert entitlement_dependencies.allowed_ssh_hosts("user-1", free_entitlements()) == {"older.example"}
