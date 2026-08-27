"""wiggleroom - lane-per-signal timing figures, rendered from declarative Python.

A project declares its devices, its provenance vocabulary and its header once;
each figure is a lane table plus the marks every lane draws, placed in time units
against one axis. The renderer supplies the layout, dotted guides and diagonal
links between lanes, per-render checks for the failures no eye catches, a
regenerate-on-refresh preview server and hi-DPI export. See README.md here.
"""

from .core import (
    AXIS,
    CRIT,
    GOOD,
    GOOD_INK,
    GRID,
    INK,
    INK2,
    LANE_H,
    MUTED,
    PAGE,
    PLOT_W,
    SURF,
    WARN,
    WARN_INK,
    X0,
    X1,
    Ctx,
    Device,
    Figure,
    Guide,
    Lane,
    Link,
    Mark,
    Project,
    figure_size,
    instants,
    render,
)

__all__ = [
    "AXIS",
    "CRIT",
    "GOOD",
    "GOOD_INK",
    "GRID",
    "INK",
    "INK2",
    "LANE_H",
    "MUTED",
    "PAGE",
    "PLOT_W",
    "SURF",
    "WARN",
    "WARN_INK",
    "X0",
    "X1",
    "Ctx",
    "Device",
    "Figure",
    "Guide",
    "Lane",
    "Link",
    "Mark",
    "Project",
    "figure_size",
    "instants",
    "render",
]
