from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security.plan_access import (
    command_creates_git_repo,
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
    assert command_creates_git_repo("git clone https://github.com/a/b.git")
    assert not command_creates_git_repo("git status")
