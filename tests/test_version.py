import pytest
from pathlib import Path
from unittest.mock import patch
from app.main import get_app_version
import app.main as main_mod


def test_get_app_version_with_changelog(tmp_path, monkeypatch):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [0.3.0] - 2026-10-26\n\n### Added\n- Stuff\n")
    
    monkeypatch.setattr(main_mod, "_cached_app_version", None)
    
    class FakePath(Path):
        def __truediv__(self, other):
            if other == "CHANGELOG.md":
                return changelog
            return super().__truediv__(other)

    with patch("app.main.BASE_DIR", tmp_path / "app"):
        ver = get_app_version()
        assert ver in ("v0.3.0", "0.3.0")


def test_get_app_version_missing_file(monkeypatch):
    monkeypatch.setattr(main_mod, "_cached_app_version", None)
    with patch.object(Path, "exists", return_value=False):
        ver = get_app_version()
        assert ver == "0.0.0"
