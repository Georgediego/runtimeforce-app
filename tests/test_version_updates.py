from app.core.version_utils import is_newer_version, parse_version


def test_parse_version_accepts_optional_v_prefix():
    assert parse_version("v0.6.2") == (0, 6, 2)
    assert parse_version("0.6.2") == (0, 6, 2)


def test_newer_release_is_detected():
    assert is_newer_version("v0.6.2", "v0.6.1")
    assert is_newer_version("v1.0.0", "v0.99.99")


def test_same_older_or_invalid_versions_are_not_updates():
    assert not is_newer_version("v0.6.1", "v0.6.1")
    assert not is_newer_version("v0.6.0", "v0.6.1")
    assert not is_newer_version("unknown", "v0.6.1")
