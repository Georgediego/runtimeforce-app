from app.core.security.entitlements import chat_strategy_feature, feature_enabled


def test_chat_strategy_maps_to_admin_feature_keys():
    assert chat_strategy_feature("auto") == "auto"
    assert chat_strategy_feature("manual") == "manual"
    assert chat_strategy_feature("coding") == "atm"
    assert chat_strategy_feature("atm") == "atm"
    assert chat_strategy_feature("local") == "local_models"


def test_unknown_chat_strategy_is_not_granted():
    assert chat_strategy_feature("unknown-mode") is None


def test_feature_requires_server_verified_explicit_true():
    assert feature_enabled({"valid": True, "features": {"git": True}}, "git")
    assert not feature_enabled({"valid": False, "features": {"git": True}}, "git")
    assert not feature_enabled({"valid": True, "features": {"git": False}}, "git")
    assert not feature_enabled({"valid": True, "features": {}}, "git")
    assert not feature_enabled({"valid": True, "features": {"git": 1}}, "git")
