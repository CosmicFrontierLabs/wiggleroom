"""Style, layout and drawing vocabulary for lane-per-signal timing figures.

Every figure is the same thing with a different time axis: a column of named
signals on the left, a device badge, provenance icons, and one lane of marks per
signal. This module owns all of that. A project supplies its devices, its
provenance vocabulary and its header text; a figure module supplies only its lane
table and the marks each lane draws.

Two rules the drawing vocabulary enforces so figures cannot drift apart:

- Marks are placed in **time units**, never pixels. `Ctx` owns the mapping, so a
  figure never sees the plot geometry and a scale change cannot silently break
  half a lane.
- Annotations go through `Ctx.note`, which haloes them against whatever they cross
  and slides them inward rather than off the edge. Nothing else writes prose into
  the plot area. A halo rather than an opaque backing plate, so a label never
  blanks out the waveform it is describing - the trace runs on between the glyphs.
"""

import math
import pathlib
import textwrap
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

# --------------------------------------------------------------------- tokens
# Device hues are a project's choice (and its colourblind-validation burden); the
# lane badge exists so identity never rests on colour alone either way.
SURF = "#fcfcfb"
PAGE = "#f4f4f1"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
WARN = "#fab219"
WARN_INK = "#8a5a00"
CRIT = "#d03b3b"
GOOD = "#0ca30c"
GOOD_INK = "#046b04"


@dataclass(frozen=True)
class Device:
    key: str
    colour: str
    badge: str
    name: str


@dataclass(frozen=True)
class Mark:
    key: str
    glyph: str
    colour: str
    label: str


# ------------------------------------------------------------------- geometry
WIDTH = 2400
X_IDX = 28
X_NAME = 74
X_BADGE = 552
BADGE_W = 116
X_MARKS = X_BADGE + BADGE_W + 12
MARK_W = 19
X0 = 712
X1 = WIDTH - 46
PLOT_W = X1 - X0
LANE_H = 66
HEADER_H = 208
PANEL_HDR_H = 62
AXIS_H = 46
PAD_BOTTOM = 26
DETAIL_WRAP = 86
KEY_BASELINE = 19       # px below the lane top
TITLE_BASELINE = 34
DETAIL_BASELINE = 47
DETAIL_LEADING = 11.5
CHW = 0.525  # mean glyph advance as a fraction of font size, for this UI sans

# Below this, a measured span is two arrowheads meeting in the middle - all
# decoration, no measurement. `Ctx.span` contracts to its label alone at that
# width, so a lane cannot draw a useless one by accident.
SPAN_MIN_PX = 40

# Annotations that had to slide to fit, with how far. An end-anchored label too
# long for the room left of its anchor slides RIGHT, over whatever is there, so
# this is not a cosmetic slip - the render checks report it. Cleared per render.
OVERSET = []
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def arrow_marker(colour: str, devices) -> str:
    """The arrowhead id whose fill matches `colour`.

    Markers cannot inherit the stroke of the line that references them, so an id
    picked independently of the colour silently produces a two-tone arrow.
    """
    for device in devices.values():
        if device.colour == colour:
            return f"arrow_{device.key}"
    return {CRIT: "arrow_crit", INK: "arrow_ink"}.get(colour, "arrow")


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Surface-coloured outline drawn behind the glyphs, so in-plot text stays legible
# over a waveform without hiding it.
HALO_PX = 3.6


# Bounding boxes of every tracked text this render, for the collision check. Text
# deliberately drawn inside a bar (label_in_bar) opts out - it sits on a fill by
# design, and pairing it against annotations would be all false positives.
TEXT_BOXES = []


def text(x, y, s, size=11, col=MUTED, anchor="start", weight=400, halo=0.0, track=True):
    if track:
        w = text_width(s, size, bold=weight >= 600)
        x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
        TEXT_BOXES.append((x0, y - size * 0.78, x0 + w, y + size * 0.24, s))
    ring = (f' stroke="{SURF}" stroke-width="{halo}" stroke-linejoin="round" '
            f'stroke-linecap="round" paint-order="stroke fill"') if halo else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{col}" '
        f'text-anchor="{anchor}" font-weight="{weight}"{ring}>{esc(s)}</text>'
    )


def text_width(s, size, *, bold=False):
    return len(s) * size * (CHW * 1.09 if bold else CHW)


# ----------------------------------------------------------------- lane table
@dataclass
class Lane:
    key: str
    device: str
    title: str
    detail: str
    draw: Callable[["Ctx"], None]
    provenance: str
    status: Sequence[str] = field(default_factory=tuple)


@dataclass
class Guide:
    """A dotted line dropped from one lane to another at a single instant.

    Lanes are addressed by key rather than index so reordering a figure cannot
    silently repoint a linkage. Guides draw above every lane, since their whole
    job is to be followed across them.
    """

    t: float
    from_key: str
    to_key: str
    label: str = ""
    colour: str = INK2
    dash: str = "2 4"
    arrow: bool = True      # False for a pin: two instants that coincide, not one causing the other
    label_anchor: str = "start"
    label_at: str = "end"   # "end" puts the label at the arrowhead, "start" at the origin


@dataclass
class Link:
    """A diagonal connector between two lanes at two different times.

    A `Guide` is vertical because it marks one instant across several lanes. This
    is the other case: something that moves forward in time as it moves down, so
    the slope itself carries the delay. Drawn between the lanes' inner edges, so
    it does not cross either lane's marks.
    """

    t_from: float
    t_to: float
    from_key: str
    to_key: str
    label: str = ""
    colour: str = INK2
    dash: str = ""


@dataclass
class Figure:
    number: int
    key: str
    name: str
    blurb: str
    lanes: Sequence[Lane]
    tmax: float
    tstep: float
    unit: str = "ms"
    lane_h: int = LANE_H
    # Whether this figure has adopted the convention that a lane's name begins with
    # its device. Opt-in per figure, since older figures may predate it; the render
    # checks enforce it on the ones that declare it.
    device_prefixed: bool = False
    guides: Sequence["Guide"] = field(default_factory=tuple)
    links: Sequence["Link"] = field(default_factory=tuple)
    # Stamped by the owning Project, so slugs carry the project name without every
    # figure restating it.
    slug_prefix: str = ""
    # Figure-specific facts worth printing at render time - numbers that interlock
    # across lanes and would otherwise drift silently. Returns printable lines.
    self_check: Optional[Callable[[], Sequence[str]]] = None

    @property
    def detail_lines(self):
        """How many wrapped detail lines actually fit under the title.

        Derived from the lane height rather than asserted next to it, because the
        renderer truncates anything past this and silently losing prose is the one
        failure a reader cannot see. The render checks hold each lane to it.
        """
        room = self.lane_h - 4 - DETAIL_BASELINE
        return 1 + max(0, int(room // DETAIL_LEADING))

    @property
    def slug(self):
        return f"{self.slug_prefix}-{self.number}-{self.key}"

    @property
    def heading(self):
        return f"Figure {self.number} — {self.name}"


@dataclass
class Project:
    """One set of figures sharing a header, a device table and a mark vocabulary.

    Every lane names exactly one `provenance` mark, so the icon column is never
    empty and a reader is never left guessing whether an untagged figure was
    measured or assumed; `status` marks are additional standing beyond that.
    `extra_patterns` are project hatches beyond the per-device dense fills, as
    (name, colour, angle, gap, wide, op_bg, op_fg) rows.
    """

    title: str
    subtitle: str
    set_note: str
    devices: dict
    provenance: dict
    status: dict
    figures: Sequence[Figure]
    slug_prefix: str
    out_dir: pathlib.Path    # where the SVGs are written
    cache_dir: pathlib.Path  # build artifacts (hi-DPI renders); never the tree
    extra_patterns: Sequence[tuple] = ()

    def __post_init__(self):
        for figure in self.figures:
            figure.slug_prefix = self.slug_prefix


def instants(first, step, tmax):
    """Every `first + k*step` inside [0, tmax].

    The drawing side has `Ctx.edges` for this, but marks referenced by guides have
    to be listed before any `Ctx` exists. Deriving them from the window rather than
    a hand-picked range of k means widening a figure cannot quietly leave the last
    few unpinned.
    """
    out, t = [], first + math.floor((0.0 - first) / step) * step
    while t <= tmax + 1e-9:
        if t >= -1e-9:
            out.append(t)
        t += step
    return out


# --------------------------------------------------------- drawing vocabulary
class Ctx:
    """The one thing a lane's marks draw into.

    Positions are times in the figure's unit; `Ctx` maps them. Vertical offsets
    are pixels from the lane centre, since lane height is a layout property and
    has no meaning in the time domain.
    """

    def __init__(self, emit, tmax, cy, colour, lane_h=LANE_H, device=None, devices=None):
        self._emit = emit
        self.devices = devices or {}
        self.tmax = tmax
        self.cy = cy
        self.colour = colour
        self.lane_h = lane_h
        self.device = device
        self.px = PLOT_W / tmax
        self.x0 = X0
        self.x1 = X1

    def T(self, t):
        return X0 + t * self.px

    def amplitude(self, fraction=0.62):
        """A peak offset that stays inside the lane. Waveforms use this instead of
        a literal, so a lane-height change cannot clip them."""
        return self.lane_h / 2 * fraction

    def raw(self, svg):
        self._emit(svg)

    # -- blocks ------------------------------------------------------------
    def bar(self, t0, t1, *, h=18, op=1.0, dy=0, rx=3.5, stroke=None, colour=None,
            min_px=2.0):
        xa, xb = self.T(t0), self.T(t1)
        w = max(xb - xa, min_px)
        st = f' stroke="{stroke}" stroke-width="1.6"' if stroke else ""
        self.raw(
            f'<rect x="{xa:.1f}" y="{self.cy + dy - h/2:.1f}" width="{w:.1f}" height="{h}" '
            f'rx="{min(rx, w/2):.1f}" fill="{colour or self.colour}" fill-opacity="{op}"{st}/>'
        )

    def outline(self, t0, t1, *, h=22, dy=0, colour=None, dash="3 2", width=1.8):
        xa, xb = self.T(t0), self.T(t1)
        self.raw(
            f'<rect x="{xa:.1f}" y="{self.cy + dy - h/2:.1f}" width="{max(xb-xa, 6):.1f}" '
            f'height="{h}" rx="3" fill="none" stroke="{colour or self.colour}" '
            f'stroke-width="{width}" stroke-dasharray="{dash}"/>'
        )

    def fill_pattern(self, t0, t1, pattern, *, h=24, dy=0, colour=None):
        xa, xb = self.T(t0), self.T(t1)
        self.raw(
            f'<rect x="{xa:.1f}" y="{self.cy + dy - h/2:.1f}" width="{xb-xa:.1f}" height="{h}" '
            f'rx="4" fill="url(#{pattern})" stroke="{colour or self.colour}" stroke-opacity="0.5"/>'
        )

    def dense(self, t0, t1, *, h=20, dy=0):
        """A clock too fast to resolve at this scale, in the lane's own colour.

        The hatch is decorative in the sense that no individual cycle is real -
        the point is that the rate is orders of magnitude above everything below
        it - so a caller is expected to say what the true rate is.
        """
        self.fill_pattern(t0, t1, f"dense_{self.device}", h=h, dy=dy)

    def label_in_bar(self, t0, t1, s, *, size=11, dy=0, col="#ffffff", frac=0.5):
        """Text inside a filled bar. `frac` moves it off centre, which a lane needs
        when a guide is pinned to the bar's midpoint and would strike through it."""
        x = self.T(t0) + (self.T(t1) - self.T(t0)) * frac
        self.raw(text(x, self.cy + dy + size * 0.36, s, size, col, "middle", 700, track=False))

    # -- lines and events --------------------------------------------------
    def tick(self, t, *, h=28, w=3.4, op=1.0, dy=0, colour=None, dash=None):
        x = self.T(t)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(
            f'<line x1="{x:.1f}" y1="{self.cy + dy - h/2:.1f}" x2="{x:.1f}" '
            f'y2="{self.cy + dy + h/2:.1f}" stroke="{colour or self.colour}" '
            f'stroke-width="{w}" stroke-opacity="{op}"{da}/>'
        )

    def tick_train(self, step, *, first=0.0, h=28, w=3.4, op=1.0, dy=0, colour=None):
        t = first
        while t <= self.tmax + 1e-9:
            self.tick(t, h=h, w=w, op=op, dy=dy, colour=colour)
            t += step

    def logic(self, period, high, *, first=0.0, h=18, dy=0, colour=None, width=2.0,
              min_high_px=0.0):
        """A logic waveform: low, going high for `high` at every period boundary.

        `first` is any rising edge; the train is extended both ways to fill the
        figure, so a phase-shifted clock needs no special casing. `min_high_px`
        lets a pulse far below the figure's resolution still read as a pulse -
        the caller is expected to say so on the lane. Returns the high time as
        drawn, so a caller can compare it against the real one.
        """
        drawn_high = max(high, min_high_px / self.px)
        top = self.cy + dy - h / 2
        bot = self.cy + dy + h / 2
        d = [f"M{self.T(0):.1f} {bot:.1f}"]
        k = math.floor((0.0 - first) / period)
        while first + k * period < self.tmax:
            rise = first + k * period
            fall = rise + drawn_high
            if fall > 0:
                r, f = max(rise, 0.0), min(fall, self.tmax)
                d.append(f"L{self.T(r):.1f} {bot:.1f} L{self.T(r):.1f} {top:.1f} "
                         f"L{self.T(f):.1f} {top:.1f} L{self.T(f):.1f} {bot:.1f}")
            k += 1
        d.append(f"L{self.T(self.tmax):.1f} {bot:.1f}")
        self.raw(f'<path d="{" ".join(d)}" fill="none" stroke="{colour or self.colour}" '
                 f'stroke-width="{width}"/>')
        return drawn_high

    def edges(self, period, *, first=0.0):
        """Every instant of `first + k*period` that lands inside the figure."""
        k = math.floor((0.0 - first) / period)
        while first + k * period <= self.tmax + 1e-9:
            t = first + k * period
            if t >= -1e-9:
                yield t
            k += 1

    def falling_edge(self, t, *, dy=0, colour=None, size=5.0):
        """A downward chevron under an edge: the instant a device actually acts."""
        x, y = self.T(t), self.cy + dy
        col = colour or self.colour
        self.raw(
            f'<path d="M{x-size:.1f} {y-size:.1f} L{x:.1f} {y+size*0.9:.1f} '
            f'L{x+size:.1f} {y-size:.1f}" fill="none" stroke="{col}" stroke-width="2.2" '
            f'stroke-linejoin="miter"/>'
        )

    def diamond(self, t, *, r=5.4, dy=0, colour=None):
        x, y = self.T(t), self.cy + dy
        self.raw(
            f'<path d="M{x:.1f} {y-r:.1f} L{x+r:.1f} {y:.1f} L{x:.1f} {y+r:.1f} '
            f'L{x-r:.1f} {y:.1f} Z" fill="{colour or self.colour}"/>'
        )

    def curve(self, samples, *, colour=None, width=2.2, dash=None, op=1.0):
        """`samples` is an iterable of (time, pixel offset from lane centre)."""
        pts = " ".join(f"{self.T(t):.1f},{self.cy + dy:.1f}" for t, dy in samples)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<polyline points="{pts}" fill="none" stroke="{colour or self.colour}" '
                 f'stroke-width="{width}" stroke-opacity="{op}"{da}/>')

    def arrow(self, t0, t1, *, dy=0, colour=None, marker=None):
        col = colour or self.colour
        self.raw(
            f'<line x1="{self.T(t0):.1f}" y1="{self.cy + dy:.1f}" x2="{self.T(t1):.1f}" '
            f'y2="{self.cy + dy:.1f}" stroke="{col}" stroke-width="2.2" '
            f'marker-end="url(#{marker or arrow_marker(col, self.devices)})"/>'
        )

    # -- measurements and prose -------------------------------------------
    def span(self, t0, t1, label, *, dy=0, above=True, colour=None, size=10.5):
        """A measured interval, or just its label when the interval is too narrow
        to measure. See [`SPAN_MIN_PX`]."""
        col = colour or self.colour
        xa, xb, y = self.T(t0), self.T(t1), self.cy + dy
        if abs(xb - xa) < SPAN_MIN_PX:
            self.note((t0 + t1) / 2, label, dy=dy + (-10 if above else 16), size=size,
                      col=col, anchor="middle", weight=700)
            return
        head = arrow_marker(col, self.devices)
        self.raw(
            f'<line x1="{xa:.1f}" y1="{y:.1f}" x2="{xb:.1f}" y2="{y:.1f}" stroke="{col}" '
            f'stroke-width="1.8" marker-start="url(#{head})" marker-end="url(#{head})"/>'
            f'<line x1="{xa:.1f}" y1="{y-7:.1f}" x2="{xa:.1f}" y2="{y+7:.1f}" stroke="{col}" stroke-width="1.4"/>'
            f'<line x1="{xb:.1f}" y1="{y-7:.1f}" x2="{xb:.1f}" y2="{y+7:.1f}" stroke="{col}" stroke-width="1.4"/>'
        )
        self.note((t0 + t1) / 2, label, dy=dy + (-10 if above else 16), size=size,
                  col=col, anchor="middle", weight=700)

    def bracket(self, t0, t1, label, *, dy=14, colour=None):
        col = colour or self.colour
        xa, xb, y = self.T(t0), self.T(t1), self.cy + dy
        self.raw(
            f'<path d="M{xa:.1f} {y-5:.1f} L{xa:.1f} {y:.1f} L{xb:.1f} {y:.1f} '
            f'L{xb:.1f} {y-5:.1f}" fill="none" stroke="{col}" stroke-width="1.5"/>'
        )
        self.note((t0 + t1) / 2, label, dy=dy + 12, anchor="middle", weight=600)

    def note(self, t, s, *, dy=4, size=10.5, col=INK2, anchor="start", weight=400,
             halo=HALO_PX):
        """Prose in the plot area: haloed so it survives what it crosses, and slid
        inward rather than allowed to run off the right edge."""
        w = text_width(s, size, bold=weight >= 600)
        x = self.T(t)
        if anchor == "start":
            x = min(x, X1 - w - 4)
        elif anchor == "end":
            if x < X0 + w + 4:
                OVERSET.append((s, (X0 + w + 4) - x))
            x = max(x, X0 + w + 4)
        else:
            x = min(max(x, X0 + w / 2 + 4), X1 - w / 2 - 4)
        self.raw(text(x, self.cy + dy, s, size, col, anchor, weight, halo=halo))


# ---------------------------------------------------------------- the renderer
def _defs(project):
    parts = ['<defs>']
    for name, col in [("arrow", INK2), ("arrow_crit", CRIT), ("arrow_ink", INK)] + [
        (f"arrow_{d.key}", d.colour) for d in project.devices.values()
    ]:
        parts.append(
            f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
            f'markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
            f'fill="{col}"/></marker>'
        )
    dense = [(f"dense_{d.key}", d.colour, 0, 6, 2.0, 0.10, 0.55)
             for d in project.devices.values()]
    for name, col, angle, gap, wide, op_bg, op_fg in dense + list(project.extra_patterns):
        rot = f' patternTransform="rotate({angle})"' if angle else ""
        parts.append(
            f'<pattern id="{name}" width="{gap}" height="{gap if angle else 8}" '
            f'patternUnits="userSpaceOnUse"{rot}>'
            f'<rect width="{gap}" height="{gap if angle else 8}" fill="{col}" fill-opacity="{op_bg}"/>'
            f'<rect width="{wide}" height="{gap if angle else 8}" fill="{col}" fill-opacity="{op_fg}"/>'
            f'</pattern>'
        )
    parts.append('</defs>')
    return "".join(parts)


def _header(emit, project):
    emit(text(X_IDX, 54, project.title, 31, INK, "start", 650))
    emit(text(X_IDX, 84, project.subtitle, 14.5, INK2))
    emit(text(X_IDX, 106, project.set_note, 14.5, INK2))

    x = X_IDX
    for d in project.devices.values():
        emit(f'<rect x="{x}" y="{128}" width="14" height="14" rx="3" fill="{d.colour}"/>')
        emit(text(x + 21, 140, d.badge, 13, INK, "start", 700))
        emit(text(x + 21 + text_width(d.badge, 13, bold=True) + 11, 140, d.name, 12.5, MUTED))
        x += 56 + text_width(d.badge, 13, bold=True) + text_width(d.name, 12.5)

    for row_y, heading, marks in ((170, "Provenance", project.provenance),
                                  (194, "Status", project.status)):
        emit(text(X_IDX, row_y, heading, 12.5, INK, "start", 700))
        x = X_IDX + 92
        for m in marks.values():
            emit(text(x, row_y + 1, m.glyph, 14.5, m.colour, "start", 700))
            emit(text(x + 20, row_y, m.label, 12.5, INK2))
            x += 44 + text_width(m.label, 12.5)


def _lane(emit, project, fig, lane, index, lane_top):
    device = project.devices[lane.device]
    col = device.colour
    cy = lane_top + fig.lane_h / 2

    emit(f'<rect x="{X_IDX-10}" y="{lane_top}" width="{WIDTH - 2*X_IDX + 20}" '
         f'height="{fig.lane_h}" fill="{col}" fill-opacity="0.055"/>')
    emit(f'<line x1="{X_IDX-10}" y1="{lane_top}" x2="{WIDTH-X_IDX+10}" y2="{lane_top}" '
         f'stroke="{GRID}" stroke-width="1"/>')
    emit(f'<rect x="{X_IDX-10}" y="{lane_top}" width="5" height="{fig.lane_h}" fill="{col}"/>')

    emit(f'<text x="{X_IDX+6}" y="{lane_top+KEY_BASELINE+2}" font-size="13" font-weight="700" '
         f'fill="{MUTED}" font-variant-numeric="tabular-nums">{index:02d}</text>')
    emit(f'<text x="{X_NAME}" y="{lane_top+KEY_BASELINE}" font-size="14" font-weight="700" '
         f'fill="{INK}" letter-spacing="0.4">{esc(lane.key)}</text>')
    emit(text(X_NAME, lane_top + TITLE_BASELINE, lane.title, 11.5, INK2, "start", 600))
    for i, line in enumerate(textwrap.wrap(lane.detail, DETAIL_WRAP)[:fig.detail_lines]):
        emit(text(X_NAME, lane_top + DETAIL_BASELINE + i * DETAIL_LEADING, line, 9.8, MUTED))

    emit(f'<rect x="{X_BADGE}" y="{cy-12}" width="{BADGE_W}" height="24" rx="6" '
         f'fill="{col}" fill-opacity="0.18" stroke="{col}" stroke-opacity="0.5"/>')
    emit(f'<text x="{X_BADGE + BADGE_W/2}" y="{cy+5}" font-size="12" font-weight="700" '
         f'fill="{INK}" text-anchor="middle" letter-spacing="0.5">{esc(device.badge)}</text>')

    marks = [project.provenance[lane.provenance]] + [project.status[s] for s in lane.status]
    for i, m in enumerate(marks):
        emit(text(X_MARKS + i * MARK_W, cy + 6, m.glyph, 15.5, m.colour, "start", 700))

    lane.draw(Ctx(emit, fig.tmax, cy, col, fig.lane_h, device=lane.device,
                  devices=project.devices))


def figure_size(fig: Figure):
    """Intrinsic pixel size of the rendered SVG, for anything that has to lay it
    out before it has been drawn."""
    panel_h = PANEL_HDR_H + len(fig.lanes) * fig.lane_h + AXIS_H
    return WIDTH, HEADER_H + panel_h + PAD_BOTTOM


def render(project: Project, fig: Figure) -> str:
    OVERSET.clear()
    TEXT_BOXES.clear()
    out = []
    emit = out.append

    lanes_h = len(fig.lanes) * fig.lane_h
    panel_h = PANEL_HDR_H + lanes_h + AXIS_H
    _, height = figure_size(fig)

    emit(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
         f'viewBox="0 0 {WIDTH} {height}" font-family="{FONT}">')
    emit(_defs(project))
    emit(f'<rect width="{WIDTH}" height="{height}" fill="{PAGE}"/>')
    _header(emit, project)

    top = HEADER_H
    emit(f'<rect x="{X_IDX-10}" y="{top}" width="{WIDTH - 2*X_IDX + 20}" height="{panel_h}" '
         f'rx="12" fill="{SURF}" stroke="rgba(11,11,11,0.10)"/>')
    emit(text(X_IDX + 10, top + 30, fig.heading, 18.5, INK, "start", 650))
    emit(text(X_IDX + 10, top + 50, fig.blurb, 12.5, INK2))

    lanes_top = top + PANEL_HDR_H
    steps = int(round(fig.tmax / fig.tstep))
    for i in range(steps + 1):
        x = X0 + i * fig.tstep * (PLOT_W / fig.tmax)
        emit(f'<line x1="{x:.1f}" y1="{lanes_top}" x2="{x:.1f}" y2="{lanes_top + lanes_h + 12}" '
             f'stroke="{GRID}" stroke-width="1"/>')

    for i, lane in enumerate(fig.lanes):
        _lane(emit, project, fig, lane, i + 1, lanes_top + i * fig.lane_h)

    lane_row = {lane.key: i for i, lane in enumerate(fig.lanes)}
    for guide in fig.guides:
        x = X0 + guide.t * (PLOT_W / fig.tmax)
        y_from = lanes_top + lane_row[guide.from_key] * fig.lane_h + fig.lane_h / 2
        y_to = lanes_top + lane_row[guide.to_key] * fig.lane_h + fig.lane_h / 2
        marker = (f' marker-end="url(#{arrow_marker(guide.colour, project.devices)})"'
                  if guide.arrow else "")
        emit(f'<line x1="{x:.1f}" y1="{y_from:.1f}" x2="{x:.1f}" y2="{y_to:.1f}" '
             f'stroke="{guide.colour}" stroke-width="1.4" stroke-opacity="0.75" '
             f'stroke-dasharray="{guide.dash}"{marker}/>')
        if guide.label:
            size = 10.5
            w = text_width(guide.label, size, bold=True)
            lx = x + 9 if guide.label_anchor == "start" else x - 9
            if guide.label_anchor == "start":
                lx = min(lx, X1 - w - 4)
            else:
                lx = max(lx, X0 + w + 4)
            ly = (y_to - fig.lane_h / 2 + 13 if guide.label_at == "end"
                  else y_from + fig.lane_h / 2 - 6)
            emit(text(lx, ly, guide.label, size, guide.colour, guide.label_anchor, 700,
                      halo=HALO_PX))

    for link in fig.links:
        x1 = X0 + link.t_from * (PLOT_W / fig.tmax)
        x2 = X0 + link.t_to * (PLOT_W / fig.tmax)
        y1 = lanes_top + lane_row[link.from_key] * fig.lane_h + fig.lane_h * 0.78
        y2 = lanes_top + lane_row[link.to_key] * fig.lane_h + fig.lane_h * 0.22
        da = f' stroke-dasharray="{link.dash}"' if link.dash else ""
        emit(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
             f'stroke="{link.colour}" stroke-width="2.2"{da} '
             f'marker-end="url(#{arrow_marker(link.colour, project.devices)})"/>')
        if link.label:
            size = 10.5
            w = text_width(link.label, size, bold=True)
            lx = min(max((x1 + x2) / 2 + 10, X0 + 4), X1 - w - 4)
            emit(text(lx, (y1 + y2) / 2 + 4, link.label, size, link.colour, "start", 700,
                      halo=HALO_PX))

    axis_y = lanes_top + lanes_h + 24
    emit(f'<line x1="{X0}" y1="{axis_y}" x2="{X1}" y2="{axis_y}" stroke="{AXIS}" stroke-width="1.4"/>')
    for i in range(steps + 1):
        x = X0 + i * fig.tstep * (PLOT_W / fig.tmax)
        emit(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y+5}" '
             f'stroke="{AXIS}" stroke-width="1.4"/>')
        emit(text(x, axis_y + 19, f"{i * fig.tstep:g}", 11, MUTED, "middle"))
    emit(text(X0 - 14, axis_y + 19, fig.unit, 11.5, MUTED, "end", 700))

    emit('</svg>')
    return "\n".join(out)
