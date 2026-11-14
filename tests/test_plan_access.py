from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security.plan_access import (
    command_creates_git_repo,
    command_requires_git,
    feature_enabled,
    model_allowed_by_plan,
    plan_limit,
    provider_feature,
    require_feature,
    require_limit,
)


def plan(features=None, limits=None):
    return {
        "valid": True,
        "plan": "free",
        "features": features or {},
        "limits": limits or {},
    }


def test_atm_is_denied_when_feature_is_missing():
    entitlements = plan({"auto": True, "manual": True})
    assert not feature_enabled(entitlements, "atm")
    with pytest.raises(HTTPException) as error:
        require_feature(entitlements, "atm")
    assert error.value.status_code == 403


def test_local_llms_accepts_server_feature_key_alias():
    assert feature_enabled(plan({"local_llms": True}), "local_llms")
    assert feature_enabled(plan({"local llms": True}), "local_llms")


def test_limits_match_authoritative_server_payload_names():
    entitlements = plan(limits={
        "max_projects": 1,
        "max_ssh_hosts": 1,
        "git_repos": 1,
        "offline_grace_hours": 48,
    })
    assert plan_limit(entitlements, "max_projects") == 1
    assert plan_limit(entitlements, "max_ssh_hosts") == 1
    assert plan_limit(entitlements, "git_repos") == 1
    with pytest.raises(HTTPException):
        require_limit(entitlements, "max_projects", 1, "Active Projects")


def test_zero_limit_blocks_creation():
    entitlements = plan(limits={"max_ssh_hosts": 0})
    with pytest.raises(HTTPException) as error:
        require_limit(entitlements, "max_ssh_hosts", 0, "SSH Hosts")
    assert error.value.status_code == 403


def test_provider_feature_classification():
    assert provider_feature("ollama") == "local_llms"
    assert provider_feature("local_custom") == "local_llms"
    assert provider_feature("gemini") == "free_cloud_byok"
    assert provider_feature("openrouter") == "free_cloud_byok"
    assert provider_feature("openai") == "full_pro_byok"


def test_model_access_is_checked_by_model_tier():
    free_plan = plan({
        "free_cloud_byok": True,
        "full_pro_byok": False,
        "local_llms": True,
    })
    assert model_allowed_by_plan(free_plan, SimpleNamespace(tier="free", provider="gemini"))
    assert not model_allowed_by_plan(free_plan, SimpleNamespace(tier="standard", provider="openrouter"))
    assert not model_allowed_by_plan(free_plan, SimpleNamespace(tier="pro", provider="openai"))
    assert model_allowed_by_plan(free_plan, SimpleNamespace(tier="local", provider="ollama"))


def test_terminal_git_commands_are_classified():
    assert command_requires_git("git push origin main")
    assert command_requires_git("cd repo && git clone https://example.test/repo.git")
    assert command_creates_git_repo("git init")
    assert command_creates_git_repo("git clone https://example.test/repo.git")
    assert not command_requires_git("python manage.py test")
