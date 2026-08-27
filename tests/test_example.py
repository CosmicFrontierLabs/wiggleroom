"""The README's showcase project must keep rendering clean.

Rendered here in memory - the committed SVG itself is held in sync by CI, which
re-renders it and diffs the tree.
"""

import importlib.util
import pathlib

from wiggleroom import core, render
from wiggleroom.cli import check_arrowheads, check_collisions, check_details, check_prefixes

EXAMPLE = pathlib.Path(__file__).parent.parent / "examples" / "espresso" / "project.py"


def load_showcase():
    spec = importlib.util.spec_from_file_location("espresso_showcase", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PROJECT


def test_showcase_renders_without_findings():
    project = load_showcase()
    for figure in project.figures:
        svg = render(project, figure)
        findings = (check_details(figure) + check_prefixes(figure)
                    + check_arrowheads(svg, figure.slug) + check_collisions(figure)
                    + [f"annotation slid to fit: {text!r}" for text, _ in core.OVERSET])
        assert findings == []


def test_showcase_self_check_still_interlocks():
    project = load_showcase()
    lines = project.figures[0].self_check()
    assert any("1:2 ratio" in line for line in lines)
