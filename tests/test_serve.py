"""The preview page and its regenerate-on-refresh loop, against real projects."""

import textwrap

from wiggleroom import core, render, serve


def test_page_lists_every_figure(tmp_path, project, monkeypatch):
    proj, fig = project
    render(proj, fig)
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_HIDPI_DIR", tmp_path / "hidpi")
    html_page = serve.page(proj, revision=1)
    assert f"{fig.slug}.svg" in html_page
    assert proj.title in html_page


def test_page_carries_the_wave_favicon(tmp_path, project, monkeypatch):
    proj, fig = project
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_HIDPI_DIR", tmp_path / "hidpi")
    html_page = serve.page(proj, revision=1)
    assert '<link id="fav" rel="icon">' in html_page
    assert "FAV('2a78d6')" in html_page       # healthy colour; broken pages get red


def test_page_navigation_survives_a_name_without_an_em_dash(tmp_path, project, monkeypatch):
    proj, fig = project
    assert "—" not in fig.name
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_HIDPI_DIR", tmp_path / "hidpi")
    html_page = serve.page(proj, revision=1)
    assert fig.name in html_page


def test_describe_matches_what_the_page_shows(project, monkeypatch):
    proj, fig = project
    monkeypatch.setattr(serve, "_CORE", core)
    (info,) = serve.describe(proj)
    w, h = core.figure_size(fig)
    assert info["slug"] == fig.slug
    assert (info["w"], info["h"]) == (w, h)
    assert info["heading"] == fig.heading


def reset_live_state(monkeypatch, proj):
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_OUT_DIR", proj.out_dir)
    monkeypatch.setattr(serve, "_REVISION", 0)
    monkeypatch.setattr(serve, "_DIGEST", None)
    monkeypatch.setattr(serve, "_FIGURES", [])
    monkeypatch.setattr(serve, "_ERROR", None)


def test_refresh_bumps_the_revision_only_when_the_output_changes(project, monkeypatch):
    proj, fig = project
    reset_live_state(monkeypatch, proj)
    monkeypatch.setattr(serve, "regenerate", lambda: (proj, None))
    svg = proj.out_dir / f"{fig.slug}.svg"

    svg.write_text("<svg>a</svg>")
    serve.refresh()
    assert serve._REVISION == 1
    serve.refresh()                      # same bytes: browsers must not refetch
    assert serve._REVISION == 1
    svg.write_text("<svg>b</svg>")
    serve.refresh()
    assert serve._REVISION == 2


def test_refresh_keeps_the_last_good_revision_across_a_failed_render(project, monkeypatch):
    proj, fig = project
    reset_live_state(monkeypatch, proj)
    (proj.out_dir / f"{fig.slug}.svg").write_text("<svg>a</svg>")
    monkeypatch.setattr(serve, "regenerate", lambda: (proj, None))
    serve.refresh()

    monkeypatch.setattr(serve, "regenerate", lambda: (None, "boom"))
    serve.refresh()
    assert serve._ERROR == "boom"
    assert serve._REVISION == 1

    monkeypatch.setattr(serve, "regenerate", lambda: (proj, None))
    serve.refresh()
    assert serve._ERROR is None
    assert serve._REVISION == 1          # output identical to before the break


def test_page_links_hidpi_exports_when_they_exist(tmp_path, project, monkeypatch):
    proj, fig = project
    hidpi = tmp_path / "hidpi"
    hidpi.mkdir()
    (hidpi / f"{fig.slug}-4x.png").write_bytes(b"png bytes")
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_HIDPI_DIR", hidpi)
    html_page = serve.page(proj, revision=1)
    assert f"/hidpi/{fig.slug}-4x.png" in html_page


def test_regenerate_renders_the_project_from_source(tmp_path, monkeypatch):
    (tmp_path / "tinyproj.py").write_text(textwrap.dedent("""
        import pathlib

        from wiggleroom import Device, Figure, Lane, Mark, Project

        HERE = pathlib.Path(__file__).parent
        PROJECT = Project(
            title="Tiny", subtitle="s", set_note="n",
            devices={"PUMP": Device("PUMP", "#2a78d6", "PUMP", "pump")},
            provenance={"measured": Mark("measured", "*", "#046b04", "measured")},
            status={},
            figures=[Figure(number=1, key="one", name="One", blurb="b",
                            tmax=10.0, tstep=2.0,
                            lanes=[Lane("PUMP_X", "PUMP", "t", "d",
                                        lambda c: c.bar(0, 5), "measured")])],
            slug_prefix="tiny", out_dir=HERE, cache_dir=HERE / "cache",
        )
    """))
    monkeypatch.setattr(serve, "_ENTRY", "tinyproj")
    monkeypatch.setattr(serve, "_PROJECT_DIR", tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    proj, error = serve.regenerate()
    assert error is None
    assert (tmp_path / "tiny-1-one.svg").read_text().startswith("<svg")
    assert serve._OUT_DIR == proj.out_dir


def test_regenerate_returns_the_traceback_of_a_broken_project(tmp_path, monkeypatch):
    (tmp_path / "broken.py").write_text("raise ValueError('the generator is broken')\n")
    monkeypatch.setattr(serve, "_ENTRY", "broken")
    monkeypatch.setattr(serve, "_PROJECT_DIR", tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    proj, error = serve.regenerate()
    assert proj is None
    assert "the generator is broken" in error
