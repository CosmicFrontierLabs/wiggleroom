"""Rasterise a project's figures through a real browser.

A screenshot at a device scale factor re-rasterises the text rather than
upscaling it, so the smallest lane prose stays readable at 1:1. The results are
build artifacts: they go to the project's cache directory, never the tree - the
SVG is the source.
"""

import os
import pathlib
import subprocess

from .core import figure_size


def find_chromium():
    """A headless chromium: `WIGGLEROOM_CHROMIUM` if set, else playwright's cache."""
    override = os.environ.get("WIGGLEROOM_CHROMIUM")
    if override:
        return pathlib.Path(override)
    hits = sorted(pathlib.Path.home().glob(
        ".cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell"))
    if not hits:
        raise FileNotFoundError(
            "no headless chromium found; set WIGGLEROOM_CHROMIUM to a browser binary")
    return hits[-1]


def export(project, scale=4, out_dir=None):
    chromium = find_chromium()
    out_dir = out_dir or (project.cache_dir / "hidpi")
    out_dir.mkdir(parents=True, exist_ok=True)
    for figure in project.figures:
        svg = (project.out_dir / f"{figure.slug}.svg").resolve()
        width, height = figure_size(figure)
        png = out_dir / f"{figure.slug}-{scale}x.png"
        subprocess.run(
            [str(chromium), "--headless", "--disable-gpu", "--hide-scrollbars",
             "--no-sandbox", f"--force-device-scale-factor={scale}",
             f"--window-size={width},{height}", f"--screenshot={png}", f"file://{svg}"],
            check=True, capture_output=True)
        print(f"{png}  {width * scale}x{height * scale}")
