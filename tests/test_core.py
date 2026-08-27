"""The rendering engine, exercised through its public surface."""

import xml.etree.ElementTree as ET

from conftest import make_figure, make_project
from wiggleroom import CRIT, GOOD, INK2, Ctx, Guide, Lane, Link, figure_size, instants, render
from wiggleroom.core import HEADER_H, OVERSET, PLOT_W, SPAN_MIN_PX, X0, X1, esc, time_to_x


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


def logic_path(*, tmax, period, high, first, lane_h=66):
    """The `d` attribute of the one path `logic` emits, plus its rail positions."""
    sink = []
    ctx = Ctx(sink.append, tmax=tmax, cy=100.0, colour=GOOD, lane_h=lane_h)
    ctx.logic(period, high, first=first, h=18)
    d = ET.fromstring(sink[0]).get("d")
    return d, ctx.T(0.0), ctx.T(tmax), 100.0 - 9, 100.0 + 9


def test_logic_opens_at_the_level_the_signal_actually_holds():
    """A pulse still high when the window opens must not be drawn rising at t=0."""
    d, x_left, _, top, bot = logic_path(tmax=1000.0, period=500.0, high=250.0, first=400.0)
    assert d.startswith(f"M{x_left:.1f} {top:.1f}")
    assert f"M{x_left:.1f} {bot:.1f}" not in d


def test_logic_draws_a_falling_edge_landing_exactly_on_the_window_start():
    """The edge is at t=0 with no high time inside the window, and still real."""
    d, x_left, _, top, bot = logic_path(tmax=1000.0, period=500.0, high=250.0, first=250.0)
    assert d.startswith(f"M{x_left:.1f} {top:.1f}")
    assert f"L{x_left:.1f} {bot:.1f}" in d


def test_logic_opens_low_when_the_previous_pulse_ended_before_the_window():
    d, x_left, _, _, bot = logic_path(tmax=1000.0, period=500.0, high=100.0, first=250.0)
    assert d.startswith(f"M{x_left:.1f} {bot:.1f}")


def test_logic_closes_at_the_level_the_signal_holds():
    """A pulse still high at tmax must not gain a falling edge at the right edge."""
    d, _, x_right, top, bot = logic_path(tmax=1000.0, period=500.0, high=250.0, first=900.0)
    assert d.endswith(f"L{x_right:.1f} {top:.1f}")

    low, _, x_right, _, bot = logic_path(tmax=1000.0, period=500.0, high=100.0, first=250.0)
    assert low.endswith(f"L{x_right:.1f} {bot:.1f}")


def test_window_origin_defaults_to_zero_and_spans_the_plot():
    fig = make_figure(tmax=50.0)
    assert fig.tmin == 0.0
    assert time_to_x(0.0, fig.tmin, fig.tmax) == X0
    assert time_to_x(50.0, fig.tmin, fig.tmax) == X1


def test_window_origin_rescales_rather_than_offsetting():
    """tmin=-100 puts -100 at the left edge and keeps tmax at the right."""
    fig = make_figure(tmin=-100.0, tmax=900.0)
    assert time_to_x(-100.0, fig.tmin, fig.tmax) == X0
    assert time_to_x(900.0, fig.tmin, fig.tmax) == X1
    midpoint = time_to_x(400.0, fig.tmin, fig.tmax)
    assert abs(midpoint - (X0 + PLOT_W / 2)) < 1e-6


def test_axis_ticks_snap_to_the_step_across_a_negative_origin():
    """Opening the window early must not knock every label off its round number."""
    fig = make_figure(tmin=-100.0, tmax=200.0, tstep=100.0)
    assert fig.axis_ticks == [-100.0, 0.0, 100.0, 200.0]

    ragged = make_figure(tmin=-60.0, tmax=200.0, tstep=100.0)
    assert ragged.axis_ticks == [0.0, 100.0, 200.0]


def test_axis_labels_carry_the_time_not_the_tick_index(tmp_path):
    fig = make_figure(tmin=-100.0, tmax=200.0, tstep=100.0)
    proj = make_project(tmp_path, [fig])
    svg = render(proj, fig)
    assert ">-100<" in svg


def test_edges_and_instants_reach_before_the_origin():
    ctx = Ctx(lambda s: None, tmax=200.0, cy=0, colour=GOOD, tmin=-100.0)
    assert list(ctx.edges(100.0)) == [-100.0, 0.0, 100.0, 200.0]
    assert instants(0.0, 100.0, 200.0, -100.0) == [-100.0, 0.0, 100.0, 200.0]


def test_logic_gives_a_t_zero_falling_edge_a_visible_run_in():
    """The motivating case. With the window opening at 0 this edge has no high time
    to fall from; opening it early gives the edge width behind it, which is the
    whole reason to shift the origin."""
    top, bot = 91.0, 109.0
    sink = []
    ctx = Ctx(sink.append, tmax=1000.0, cy=100.0, colour=GOOD, tmin=-100.0)
    ctx.logic(500.0, 250.0, first=250.0, h=18)
    d = ET.fromstring(sink[0]).get("d")

    # The pulse spanning [-250, 0] holds the signal high across the whole run-in,
    # so the path opens high and the fall at t=0 is the first transition drawn.
    assert d.startswith(f"M{ctx.T(-100.0):.1f} {top:.1f}")
    assert f"L{ctx.T(0.0):.1f} {top:.1f} L{ctx.T(0.0):.1f} {bot:.1f}" in d
    assert ctx.T(0.0) - ctx.T(-100.0) > 100.0   # the run-in is real pixels, not a sliver


def test_guides_and_links_share_the_lane_mapping_under_a_shifted_window(tmp_path):
    """Guides and links are placed by the renderer, not a Ctx, so they are the
    thing most likely to skew against the lanes they point at."""
    lanes = [Lane("PUMP_A", "PUMP", "A", "first", lambda c: c.tick(0.0), "measured"),
             Lane("CTRL_B", "CTRL", "B", "second", lambda c: c.tick(0.0), "modelled")]
    fig = make_figure(tmin=-100.0, tmax=900.0, lanes=lanes,
                      guides=[Guide(0.0, "PUMP_A", "CTRL_B")],
                      links=[Link(0.0, 0.0, "PUMP_A", "CTRL_B")])
    svg = render(make_project(tmp_path, [fig]), fig)
    x = time_to_x(0.0, -100.0, 900.0)
    assert svg.count(f'x1="{x:.1f}"') >= 2
