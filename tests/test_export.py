"""Hi-DPI export: browser discovery and the screenshot commands it builds."""

import pathlib

import pytest

from wiggleroom import export, figure_size


def test_chromium_env_override_wins(monkeypatch, tmp_path):
    fake = tmp_path / "my-chromium"
    monkeypatch.setenv("WIGGLEROOM_CHROMIUM", str(fake))
    assert export.find_chromium() == fake


def test_missing_chromium_says_how_to_provide_one(monkeypatch, tmp_path):
    monkeypatch.delenv("WIGGLEROOM_CHROMIUM", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)  # nothing cached there
    with pytest.raises(FileNotFoundError, match="WIGGLEROOM_CHROMIUM"):
        export.find_chromium()


def test_export_screenshots_each_figure_at_scale(monkeypatch, project):
    proj, fig = project
    calls = []
    monkeypatch.setenv("WIGGLEROOM_CHROMIUM", "/opt/fake/chromium")
    monkeypatch.setattr(export.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    export.export(proj, scale=3)

    assert len(calls) == len(proj.figures)
    cmd = calls[0]
    assert cmd[0] == "/opt/fake/chromium"
    assert "--headless" in cmd
    assert "--force-device-scale-factor=3" in cmd
    width, height = figure_size(fig)
    assert f"--window-size={width},{height}" in cmd
    shot = next(a for a in cmd if a.startswith("--screenshot="))
    assert shot.endswith(f"{fig.slug}-3x.png")
    assert (proj.cache_dir / "hidpi").is_dir()  # artifacts go to the cache, not the tree
