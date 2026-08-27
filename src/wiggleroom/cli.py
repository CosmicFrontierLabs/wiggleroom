"""Render a project's figures, with the checks that catch what eyes cannot.

The renderer will happily truncate prose, slide a label over its neighbour, or put
a grey arrowhead on a coloured line without anything looking obviously wrong - so
everything of that kind is checked here on every render and reported loudly.

Entry point for a project wrapper:

    from wiggleroom.cli import main
    main(PROJECT, sys.argv[1:])

Subcommands: `render` (the default), `export [--scale N]` for hi-DPI PNGs, and
`serve [port]` for the regenerate-on-refresh preview. Serving re-imports the
project script on every request, so it needs that script run directly
(`python3 project.py serve`) — the entry module is derived from the invocation.
"""

import argparse
import pathlib
import re
import sys
import textwrap

from . import core, export, serve
from .core import DETAIL_WRAP, render


def check_arrowheads(svg, slug):
    """Report lines whose arrowhead is a different colour from the line.

    Markers cannot inherit a stroke, so the head's colour is picked separately
    from the line's and the two can disagree without looking obviously wrong.
    """
    heads = {m.group(1): m.group(2).lower() for m in re.finditer(
        r'<marker id="([\w-]+)"[^>]*><path[^>]*fill="(#[0-9a-fA-F]+)"', svg)}
    return [f"{slug}: line {m.group(1)} carries a {heads.get(m.group(2))} arrowhead "
            f"({m.group(2)})"
            for m in re.finditer(r'<line [^>]*stroke="(#[0-9a-fA-F]+)"[^>]*marker-(?:end|start)='
                                 r'"url\(#([\w-]+)\)"', svg)
            if heads.get(m.group(2)) != m.group(1).lower()]


def check_prefixes(figure):
    """Report lanes whose name does not begin with their device."""
    if not figure.device_prefixed:
        return []
    return [f"{figure.slug} / {lane.key}: owned by {lane.device}, name does not say so"
            for lane in figure.lanes if not lane.key.startswith(lane.device + "_")]


def check_details(figure):
    """Report lane details the lane is not tall enough to show.

    The renderer truncates silently, which loses prose without anyone noticing -
    so the one thing that cannot be seen in the output gets checked here instead.
    """
    found = []
    for lane in figure.lanes:
        lines = textwrap.wrap(lane.detail, DETAIL_WRAP)
        if len(lines) > figure.detail_lines:
            dropped = " ".join(lines[figure.detail_lines:])
            found.append(f"{figure.slug} / {lane.key}: detail truncated, dropping "
                         f"{len(lines) - figure.detail_lines} line(s): {dropped!r}")
    return found


def check_collisions(figure):
    """Report annotation text overlapping other annotation text.

    Boxes are recorded as the text is drawn, so this sees exactly what the
    renderer placed - labels deliberately sitting inside bars opt out at the
    source. Header rows are spaced by the same width estimate and excluded.
    """
    boxes = [b for b in core.TEXT_BOXES if b[1] > core.HEADER_H]
    return [f"{figure.slug}: text collides: {a[4][:48]!r} / {b[4][:48]!r}"
            for i, a in enumerate(boxes) for b in boxes[i + 1:]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]]


def render_all(project):
    cwd = pathlib.Path.cwd()
    for figure in project.figures:
        path = project.out_dir / f"{figure.slug}.svg"
        svg = render(project, figure)
        path.write_text(svg)
        shown = path.relative_to(cwd) if path.is_relative_to(cwd) else path
        print(f"{shown}  {len(figure.lanes)} lanes, 0-{figure.tmax:g} {figure.unit}")
        findings = (check_details(figure) + check_prefixes(figure)
                    + check_arrowheads(svg, figure.slug) + check_collisions(figure)
                    + [f"{figure.slug}: annotation slid {shift:.0f} px right to fit: {text!r}"
                       for text, shift in core.OVERSET])
        for line in findings:
            print(f"  ! {line}")
        for line in (figure.self_check() if figure.self_check else []):
            print(f"    {line}")


def main(project, argv):
    parser = argparse.ArgumentParser(description=project.title)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("render", help="write the SVGs and run every check (the default)")
    exp = sub.add_parser("export", help="rasterise the figures at a device scale factor")
    exp.add_argument("--scale", type=int, default=4)
    exp.add_argument("--out", type=pathlib.Path, default=None,
                     help="defaults to the project cache's hidpi directory")
    srv = sub.add_parser("serve", help="preview server, regenerated on every refresh")
    srv.add_argument("port", nargs="?", type=int, default=8931)
    args = parser.parse_args(argv or ["render"])

    if args.command == "serve":
        entry = pathlib.Path(sys.argv[0]).resolve()
        if entry.suffix != ".py":
            parser.error("serve re-imports the project script per request, so it "
                         "needs that script run directly: python3 <project>.py serve")
        serve.main(entry.stem, entry.parent, [str(args.port)])
        return
    render_all(project)
    if args.command == "export":
        export.export(project, scale=args.scale, out_dir=args.out)
