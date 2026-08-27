"""A minimal two-device project the tests render for real."""

import pathlib

import pytest

from wiggleroom import Device, Figure, Lane, Mark, Project


def draw_duty(c):
    c.bar(0, 12.5, h=18)
    c.span(0, 12.5, "12.5 ms")


def draw_clock(c):
    c.logic(10.0, 2.0)


def make_project(tmp_path: pathlib.Path, figures) -> Project:
    devices = {d.key: d for d in (
        Device("PUMP", "#2a78d6", "PUMP", "coolant pump"),
        Device("CTRL", "#eda100", "CTRL", "controller"),
    )}
    provenance = {m.key: m for m in (
        Mark("measured", "●", "#046b04", "measured"),
        Mark("modelled", "◇", "#8a5a00", "a stand-in constant"),
    )}
    return Project(title="Fill cycle timing", subtitle="who moves when",
                   set_note="all figures share one clock", devices=devices,
                   provenance=provenance, status={}, figures=figures,
                   slug_prefix="fill", out_dir=tmp_path,
                   cache_dir=tmp_path / "cache")


def make_figure(**overrides) -> Figure:
    lanes = overrides.pop("lanes", [
        Lane("PUMP_DUTY", "PUMP", "Duty window", "What the pump is doing.",
             draw_duty, "measured"),
        Lane("CTRL_CLK", "CTRL", "Control clock", "The controller's cycle.",
             draw_clock, "modelled"),
    ])
    kwargs = dict(number=1, key="cycle", name="Fill cycle", blurb="one pass",
                  tmax=50.0, tstep=5.0, lanes=lanes)
    kwargs.update(overrides)
    return Figure(**kwargs)


@pytest.fixture
def project(tmp_path):
    figure = make_figure()
    return make_project(tmp_path, [figure]), figure
