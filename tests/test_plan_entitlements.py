import pytest

from app.core.security.entitlements import (
    chat_strategy_feature,
    feature_enabled,
    plan_limit,
    enforce_plan_limit,
    provider_feature_key,
    tool_feature_key,
)


def entitlements(features):
    return {"valid": True, "features": features, "limits": {}}


@pytest.mark.parametrize(
    ("strategy", "feature"),
    [
        ("auto", "auto"),
        ("manual", "manual"),
        ("coding", "atm"),
        ("atm", "atm"),
        ("local", "local_llms"),
    ],
)
def test_chat_strategy_feature_map(strategy, feature):
    assert chat_strategy_feature(strategy) == feature


@pytest.mark.parametrize(
    ("provider", "feature"),
    [
        ("ollama", "local_llms"),
        ("lm_studio", "local_llms"),
        ("gemini", "free_cloud_byok"),
        ("groq", "free_cloud_byok"),
        ("sambanova", "free_cloud_byok"),
        ("cerebras", "free_cloud_byok"),
        ("openai", "full_pro_byok"),
        ("anthropic", "full_pro_byok"),
        ("openrouter", "free_cloud_byok"),
        ("unknown-provider", "full_pro_byok"),
    ],
)
def test_provider_feature_map(provider, feature):
    assert provider_feature_key(provider) == feature


def test_feature_flags_are_fail_closed():
    assert not feature_enabled({"valid": False, "features": {"atm": True}}, "atm")
    assert not feature_enabled({"valid": True, "features": {}}, "atm")
    assert not feature_enabled({"valid": True, "features": {"atm": False}}, "atm")


def test_canonical_feature_flag_overrides_legacy_alias():
    data = entitlements({"local_llms": False, "local_models": True})
    assert not feature_enabled(data, "local_models")
    assert not feature_enabled(data, "local_llms")


def test_legacy_local_models_alias_remains_supported():
    assert feature_enabled(entitlements({"local_models": True}), "local_llms")


@pytest.mark.parametrize(
    ("tool", "feature"),
    [
        ("execute_command", "terminal"),
        ("read_workspace_file", "editor"),
        ("write_workspace_file", "editor"),
        ("git_status", "git"),
        ("git_diff", "git"),
        ("git_commit", "git"),
        ("git_log", "git"),
    ],
)
def test_agent_tool_feature_map(tool, feature):
    assert tool_feature_key(tool) == feature



def test_plan_limit_aliases_and_fail_closed_defaults():
    assert plan_limit({"limits": {"active_projects": 1}}, "max_projects") == 1
    assert plan_limit({"limits": {"ssh_hosts": 1}}, "max_ssh_hosts") == 1
    assert plan_limit({"limits": {}}, "git_repos") == 0


def test_plan_limit_guard_rejects_overage():
    with pytest.raises(Exception) as exc:
        enforce_plan_limit({"limits": {"max_projects": 1}}, "max_projects", 1, adding=1)
    assert getattr(exc.value, "status_code", None) == 403
