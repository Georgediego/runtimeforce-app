from app.core.security.entitlements import chat_strategy_feature, feature_enabled, tool_feature_key, provider_feature_key


def test_chat_strategy_maps_to_admin_feature_keys():
    assert chat_strategy_feature("auto") == "auto"
    assert chat_strategy_feature("manual") == "manual"
    assert chat_strategy_feature("coding") == "atm"
    assert chat_strategy_feature("atm") == "atm"
    assert chat_strategy_feature("local") == "local_llms"


def test_unknown_chat_strategy_is_not_granted():
    assert chat_strategy_feature("unknown-mode") is None


def test_feature_requires_server_verified_explicit_true():
    assert feature_enabled({"valid": True, "features": {"git": True}}, "git")
    assert not feature_enabled({"valid": False, "features": {"git": True}}, "git")
    assert not feature_enabled({"valid": True, "features": {"git": False}}, "git")
    assert not feature_enabled({"valid": True, "features": {}}, "git")
    assert not feature_enabled({"valid": True, "features": {"git": 1}}, "git")

def test_agent_tools_map_to_plan_features():
    assert tool_feature_key("execute_command") == "terminal"
    assert tool_feature_key("write_workspace_file") == "editor"
    assert tool_feature_key("apply_code_patch") == "editor"
    assert tool_feature_key("git_commit") == "git"
    assert tool_feature_key("unknown_tool") is None

def test_provider_access_uses_separate_local_and_byok_flags():
    assert provider_feature_key("ollama") == "local_llms"
    assert provider_feature_key("lm_studio") == "local_llms"
    assert provider_feature_key("openai") == "full_pro_byok"
    assert provider_feature_key("gemini") == "free_cloud_byok"
