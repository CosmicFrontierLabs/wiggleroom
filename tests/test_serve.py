"""The preview page, built against a real rendered project."""

from wiggleroom import core, render, serve


def test_page_lists_every_figure(tmp_path, project, monkeypatch):
    proj, fig = project
    render(proj, fig)
    monkeypatch.setattr(serve, "_CORE", core)
    monkeypatch.setattr(serve, "_HIDPI_DIR", tmp_path / "hidpi")
    html_page = serve.page(proj, revision=1)
    assert f"{fig.slug}.svg" in html_page
    assert proj.title in html_page


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
