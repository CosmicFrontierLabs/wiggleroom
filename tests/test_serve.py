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
