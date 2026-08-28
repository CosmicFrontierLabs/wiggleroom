"""Command wiring: the default subcommand, export, and the --strict gate."""

import pytest

from conftest import make_figure, make_project
from wiggleroom import Lane, cli


def test_no_arguments_means_render(project):
    proj, fig = project
    cli.main(proj, [])
    assert (proj.out_dir / f"{fig.slug}.svg").exists()


def test_export_renders_first_then_hands_off(monkeypatch, project):
    proj, fig = project
    calls = []
    monkeypatch.setattr(cli.export, "export",
                        lambda p, scale, out_dir: calls.append((p, scale, out_dir)))
    cli.main(proj, ["export", "--scale", "2"])
    assert (proj.out_dir / f"{fig.slug}.svg").exists()  # the SVGs exist to rasterise
    assert calls == [(proj, 2, None)]


def test_strict_render_passes_a_clean_project(project):
    proj, fig = project
    cli.main(proj, ["render", "--strict"])
    assert (proj.out_dir / f"{fig.slug}.svg").exists()


def test_strict_render_fails_on_a_finding(tmp_path, capsys):
    fig = make_figure(lanes=[
        Lane("PUMP_LONG", "PUMP", "t",
             "A detail far too long for one lane to ever show. " * 12,
             lambda c: None, "measured"),
    ])
    proj = make_project(tmp_path, [fig])
    with pytest.raises(SystemExit) as excinfo:
        cli.main(proj, ["render", "--strict"])
    assert excinfo.value.code != 0
    assert "truncated" in capsys.readouterr().out


def test_findings_do_not_fail_a_plain_render(tmp_path):
    fig = make_figure(lanes=[
        Lane("PUMP_LONG", "PUMP", "t",
             "A detail far too long for one lane to ever show. " * 12,
             lambda c: None, "measured"),
    ])
    proj = make_project(tmp_path, [fig])
    cli.main(proj, ["render"])  # reported, not fatal
    assert (tmp_path / f"{fig.slug}.svg").exists()
