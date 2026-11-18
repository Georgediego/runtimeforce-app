from app.services.llm.bitnet_provider import BitNetProvider


def test_normalize_base_url_removes_v1_suffix():
    assert BitNetProvider.normalize_base_url("http://localhost:8080/v1") == "http://localhost:8080"


def test_normalize_base_url_rejects_invalid_scheme():
    try:
        BitNetProvider.normalize_base_url("localhost:8080")
    except ValueError as exc:
        assert "http://" in str(exc)
    else:
        raise AssertionError("invalid URL should be rejected")


def test_normalize_base_url_rejects_empty_value():
    try:
        BitNetProvider.normalize_base_url("")
    except ValueError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("empty URL should be rejected")
