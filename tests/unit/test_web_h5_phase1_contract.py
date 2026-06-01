from __future__ import annotations

from pathlib import Path


def test_web_h5_has_openable_elder_entry_and_miniprogram_fallback() -> None:
    home = Path("apps/web-h5/app/page.tsx").read_text()
    entry = _read_optional("apps/web-h5/app/entry/page.tsx")
    fallback = _read_optional("apps/web-h5/app/entry/fallback/page.tsx")
    css = Path("apps/web-h5/app/globals.css").read_text()

    assert 'href="/entry"' in home
    assert "searchParams" in entry
    assert "project_id" in entry
    assert "pages/interview/interview" in entry
    assert "weixin://dl/business" in entry
    assert "encodeURIComponent(projectId)" in entry
    assert '"/entry/fallback' in entry
    assert "miniprogramFallbackPath" in entry
    assert "H5 采访兜底入口" in entry
    assert "fallbackPath" in fallback
    assert "继续用 H5 采访" in fallback
    assert "project_id" in fallback
    assert "录音权限" in entry
    assert "entry-panel" in css


def _read_optional(path: str) -> str:
    file_path = Path(path)
    return file_path.read_text() if file_path.exists() else ""
