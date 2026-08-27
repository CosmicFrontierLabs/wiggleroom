"""The rendering engine, exercised through its public surface."""

import xml.etree.ElementTree as ET

from conftest import make_figure, make_project
from wiggleroom import CRIT, GOOD, INK2, Ctx, Guide, Lane, Link, figure_size, instants, render
from wiggleroom.core import HEADER_H, OVERSET, SPAN_MIN_PX, X0, X1, esc


def test_instants_covers_the_window():
    assert instants(0.0, 5.0, 20.0) == [0.0, 5.0, 10.0, 15.0, 20.0]


def test_instants_clamps_a_phase_shifted_train_to_the_window():
    got = instants(-3.0, 5.0, 20.0)
    assert got == [2.0, 7.0, 12.0, 17.0]
    assert all(0.0 <= t <= 20.0 for t in got)


def test_figure_size_grows_with_the_lane_count():
    one = make_figure(lanes=make_figure().lanes[:1])
    two = make_figure()
    w1, h1 = figure_size(one)
    w2, h2 = figure_size(two)
    assert w1 == w2
    assert h2 - h1 == two.lane_h


def test_render_is_wellformed_svg_at_the_declared_size(project):
    proj, fig = project
    svg = render(proj, fig)
    root = ET.fromstring(svg)
    width, height = figure_size(fig)
    assert root.tag.endswith("svg")
    assert (int(root.get("width")), int(root.get("height"))) == (width, height)


def test_render_carries_every_lane_and_the_header(project):
    proj, fig = project
    svg = render(proj, fig)
    for lane in fig.lanes:
        assert lane.key in svg
        assert lane.title in svg
    assert proj.title in svg
    assert fig.unit in svg


def test_slugs_carry_the_project_prefix(project):
    proj, fig = project
    assert fig.slug == "fill-1-cycle"
    assert fig.heading.startswith("Figure 1")


def test_guides_and_links_resolve_lanes_by_key(tmp_path):
    fig = make_figure(
        guides=[Guide(10.0, "PUMP_DUTY", "CTRL_CLK", label="handoff")],
        links=[Link(10.0, 22.0, "PUMP_DUTY", "CTRL_CLK", label="+12 ms")],
    )
    svg = render(make_project(tmp_path, [fig]), fig)
    assert "handoff" in svg
    assert "+12 ms" in svg


def test_span_contracts_below_the_minimum_width(tmp_path):
    def tiny(c):
        c.span(0.0, 0.1, "tiny")

    def wide(c):
        c.span(0.0, 40.0, "wide")

    fig = make_figure(lanes=[
        Lane("PUMP_TINY", "PUMP", "t", "d", tiny, "measured"),
        Lane("PUMP_WIDE", "PUMP", "t", "d", wide, "measured"),
    ])
    px_per_unit = (X1 - X0) / fig.tmax
    assert 0.1 * px_per_unit < SPAN_MIN_PX < 40.0 * px_per_unit
    svg = render(make_project(tmp_path, [fig]), fig)
    spans = [line for line in svg.splitlines()
             if 'marker-start' in line and 'marker-end' in line]
    assert len(spans) == 1
    assert "tiny" in svg  # the label survives the contraction


def test_note_overset_is_recorded_when_a_label_cannot_fit(tmp_path):
    def cramped(c):
        c.note(0.0, "an end-anchored label with no room to its left",
               anchor="end")

    fig = make_figure(lanes=[
        Lane("PUMP_NOTE", "PUMP", "t", "d", cramped, "measured"),
    ])
    render(make_project(tmp_path, [fig]), fig)
    assert len(OVERSET) == 1
    assert OVERSET[0][1] > 0


def test_render_clears_check_state_between_renders(project):
    proj, fig = project
    render(proj, fig)
    first = len(OVERSET)
    render(proj, fig)
    assert len(OVERSET) == first


def test_logic_reports_the_high_time_as_drawn():
    sink = []
    ctx = Ctx(sink.append, tmax=50.0, cy=HEADER_H + 100, colour=GOOD)
    assert ctx.logic(10.0, 2.0) == 2.0
    widened = ctx.logic(10.0, 0.001, min_high_px=6.0)
    assert widened > 0.001


def test_amplitude_stays_inside_the_lane():
    ctx = Ctx(lambda s: None, tmax=10.0, cy=0, colour=CRIT, lane_h=66)
    assert ctx.amplitude() < 66 / 2
    assert ctx.amplitude(1.0) == 33


def test_esc_neutralises_markup():
    assert esc("a < b & c > d") == "a &lt; b &amp; c &gt; d"
    assert INK2 != CRIT  # tokens exported and distinct
