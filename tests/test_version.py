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


def test_fetch_latest_ide_version_uses_github_main_first(monkeypatch):
    import asyncio

    class FakeResponse:
        text = "## [1.0.1] - 2026-11-05\\n"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url == main_mod.IDE_CHANGELOG_URL
            return FakeResponse()

    monkeypatch.setattr(main_mod.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    version, source = asyncio.run(main_mod.fetch_latest_ide_version())

    assert version == "v1.0.1"
    assert source == "github-main-changelog"
