"""The README's showcase project: one double espresso shot, every device on the clock.

The machine is fictional and the timings are illustrative; what the figure
demonstrates is the vocabulary — dense fills for motors, logic trains for PID
duty, curves for continuous quantities, pins for coincidence, arrows for cause,
and a self-check that keeps the interlocking numbers from drifting.
"""

import pathlib
import sys

from wiggleroom import Device, Figure, Guide, Lane, Link, Mark, Project

BREW_PRESSED = 0.0
GRIND_END = 8.0
PUMP_ON = 8.5
PREINFUSE_END = 13.5
RAMP_END = 15.0
FIRST_DROP = 18.0
PUMP_OFF = 35.0
DOSE_G = 18.0
YIELD_G = 36.0
TMAX = 45.0

DEVICES = {d.key: d for d in (
    Device("UI", "#7a51c2", "UI", "front panel"),
    Device("GRIND", "#a0672d", "GRIND", "burr grinder"),
    Device("PUMP", "#2a78d6", "PUMP", "rotary pump"),
    Device("BOIL", "#d03b3b", "BOIL", "brew boiler"),
    Device("VALVE", "#eda100", "VALVE", "brew solenoid"),
    Device("SCALE", "#0ca30c", "SCALE", "drip-tray scale"),
)}

PROVENANCE = {m.key: m for m in (
    Mark("measured", "●", "#046b04", "measured on the machine"),
    Mark("specified", "■", "#2a4b8a", "from the profile"),
    Mark("modelled", "◇", "#8a5a00", "a stand-in constant"),
)}


def ui(c):
    c.diamond(BREW_PRESSED, dy=-4)
    c.note(BREW_PRESSED + 0.4, "brew pressed", dy=-12, weight=700)
    c.diamond(PUMP_OFF + 1.0, dy=-4)
    c.note(PUMP_OFF + 1.4, "shot complete chime", dy=-12)


def grind(c):
    c.dense(BREW_PRESSED, GRIND_END, h=18)
    c.note(GRIND_END + 0.5, "burrs at 1400 rpm", dy=-14)
    c.span(BREW_PRESSED, GRIND_END, f"{GRIND_END:g} s grind", dy=24)


def pressure_dy(c, bar):
    peak = c.amplitude()
    return peak - (bar / 9.0) * 2 * peak


def pump(c):
    profile = [(PUMP_ON, 0.0), (9.5, 2.0), (PREINFUSE_END, 2.0),
               (RAMP_END, 9.0), (PUMP_OFF, 9.0), (35.8, 0.0)]
    c.curve([(t, pressure_dy(c, bar)) for t, bar in profile], width=2.6)
    c.note(9.3, "2 bar pre-infusion", dy=26)
    c.note(23.0, "9.0 bar", dy=-26, weight=700)


def boiler(c):
    c.logic(2.0, 0.7, h=20)
    c.note(37.2, "PID ≈ 35 % duty, 93.5 °C", dy=-16)


def valve(c):
    c.bar(PUMP_ON, PUMP_OFF, h=14, op=0.85)
    c.label_in_bar(PUMP_ON, PUMP_OFF, "open — brew path", frac=0.3)
    c.falling_edge(PUMP_OFF, dy=-16)


def scale(c):
    peak = c.amplitude()
    mass = [(0.0, 0.0), (FIRST_DROP, 0.0), (20.0, 3.0), (25.0, 14.0),
            (30.0, 25.0), (PUMP_OFF, YIELD_G), (37.5, YIELD_G + 0.8),
            (TMAX, YIELD_G + 0.8)]
    c.curve([(t, peak - (g / (YIELD_G + 0.8)) * 2 * peak) for t, g in mass],
            width=2.6)
    c.note(26.5, f"{YIELD_G:g} g target — 1:2 from an {DOSE_G:g} g dose", dy=-20,
           weight=700)


def interlock():
    dripping = PUMP_OFF - FIRST_DROP
    return [
        f"pump wetted {PUMP_OFF - PUMP_ON:g} s; dripping {dripping:g} s "
        f"at {YIELD_G / dripping:.2f} g/s mean",
        f"1:{YIELD_G / DOSE_G:g} ratio from an {DOSE_G:g} g dose",
    ]


FIG = Figure(
    number=1, key="shot", name="One double shot, fully accounted",
    blurb="18 g in, 36 g out: who moves when, and on whose say-so.",
    tmax=TMAX, tstep=5.0, unit="s", device_prefixed=True,
    lanes=[
        Lane("UI_CMD", "UI", "Operator events",
             "The two instants a human is involved: asking for the shot, and being told it "
             "is done.", ui, "measured"),
        Lane("GRIND_MOTOR", "GRIND", "Dose grind",
             "Burr motor run — individual revolutions are far too fast to resolve at this "
             "scale.", grind, "measured"),
        Lane("PUMP_PRESSURE", "PUMP", "Brew pressure",
             "Low-pressure pre-infusion, a ramp, then flat nine bar until the scale calls "
             "the stop.", pump, "specified"),
        Lane("BOIL_PID", "BOIL", "Heater duty",
             "The PID holds the setpoint with a slow duty train; the true loop is thermal, "
             "not per-cycle.", boiler, "modelled"),
        Lane("VALVE_BREW", "VALVE", "Brew solenoid",
             "Open exactly while the pump runs, so pressure has one path: through the "
             "puck.", valve, "specified"),
        Lane("SCALE_MASS", "SCALE", "Cup mass",
             "Nothing lands until the puck saturates; the last gram arrives after the pump "
             "stops.", scale, "measured"),
    ],
    guides=[
        Guide(PUMP_ON, "PUMP_PRESSURE", "VALVE_BREW", label="pump and valve together",
              colour=DEVICES["PUMP"].colour, arrow=False),
        Guide(FIRST_DROP, "VALVE_BREW", "SCALE_MASS", label="first drop",
              colour=DEVICES["VALVE"].colour),
        Guide(PUMP_OFF, "SCALE_MASS", "PUMP_PRESSURE", label="36 g reached → stop",
              colour=DEVICES["SCALE"].colour, label_anchor="end", label_at="start"),
    ],
    links=[
        Link(GRIND_END, PUMP_ON, "GRIND_MOTOR", "PUMP_PRESSURE",
             label="+0.5 s handoff", colour=DEVICES["GRIND"].colour),
    ],
    self_check=interlock,
)

PROJECT = Project(
    title="Espresso, accounted for",
    subtitle="One double shot through a fictional prosumer machine, every device on one clock",
    set_note="Timings are illustrative — the vocabulary is the point.",
    devices=DEVICES, provenance=PROVENANCE, status={},
    figures=[FIG], slug_prefix="espresso",
    out_dir=pathlib.Path(__file__).parent,
    cache_dir=pathlib.Path.home() / ".cache" / "wiggleroom-espresso",
)

if __name__ == "__main__":
    from wiggleroom.cli import main
    main(PROJECT, sys.argv[1:])
