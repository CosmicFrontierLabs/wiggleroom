"""The per-render checks: each one must catch its failure and stay quiet otherwise."""

from conftest import make_figure, make_project
from wiggleroom import Lane, render
from wiggleroom.cli import (
    check_arrowheads,
    check_collisions,
    check_details,
    check_prefixes,
    render_all,
)


def test_details_that_fit_pass(project):
    _, fig = project
    assert check_details(fig) == []


def test_truncated_detail_is_reported(tmp_path):
    fig = make_figure(lanes=[
        Lane("PUMP_LONG", "PUMP", "t",
             "A detail far too long for one lane. " * 12,
             lambda c: None, "measured"),
    ])
    findings = check_details(fig)
    assert len(findings) == 1
    assert "truncated" in findings[0]


def test_prefix_check_is_opt_in(tmp_path):
    bad_lane = Lane("DUTY", "PUMP", "t", "d", lambda c: None, "measured")
    silent = make_figure(lanes=[bad_lane])
    assert check_prefixes(silent) == []
    enforced = make_figure(lanes=[bad_lane], device_prefixed=True)
    findings = check_prefixes(enforced)
    assert len(findings) == 1
    assert "PUMP" in findings[0]


def test_matching_arrowheads_pass(project):
    proj, fig = project
    assert check_arrowheads(render(proj, fig), fig.slug) == []


def test_mismatched_arrowhead_is_reported():
    svg = ('<marker id="arrow_a"><path d="M0 0" fill="#ff0000"/></marker>'
           '<line x1="0" y1="0" x2="9" y2="0" stroke="#2a78d6" '
           'marker-end="url(#arrow_a)"/>')
    findings = check_arrowheads(svg, "slug")
    assert len(findings) == 1
    assert "#2a78d6" in findings[0]


def test_clean_render_has_no_collisions(project):
    proj, fig = project
    render(proj, fig)
    assert check_collisions(fig) == []


def test_overlapping_annotations_are_reported(tmp_path):
    def pile_up(c):
        c.note(10.0, "first label in the pile")
        c.note(10.0, "second label in the pile")

    fig = make_figure(lanes=[
        Lane("PUMP_PILE", "PUMP", "t", "d", pile_up, "measured"),
    ])
    proj = make_project(tmp_path, [fig])
    render(proj, fig)
    assert check_collisions(fig)


def test_render_all_writes_each_figure_and_runs_self_check(tmp_path, capsys):
    fig = make_figure(self_check=lambda: ["duty covers 25% of the cycle"])
    proj = make_project(tmp_path, [fig])
    render_all(proj)
    assert (tmp_path / f"{fig.slug}.svg").exists()
    out = capsys.readouterr().out
    assert "duty covers 25%" in out
    assert "!" not in out  # a clean project renders without findings
