"""Preview server for a wiggleroom project.

    from wiggleroom.serve import main
    main(entry="project", project_dir=HERE, argv=sys.argv[1:])

Re-runs the generators on every request, so a browser refresh always shows the
current source rather than whatever was last written to disk. A generator that
fails to import renders as the traceback in the page instead of a stale figure,
which is the useful behaviour while iterating.

Each figure gets a pan/zoom viewport: wheel to zoom about the cursor, drag to
pan, double-click to fit - the figures are wider than any window, so reading one
at full size means moving around inside it.

Intended to be paired with `agent-portal forward <port>`.
"""

import html
import http.server
import importlib
import os
import pathlib
import sys
import traceback
import urllib.parse

# Set by main() and refreshed by regenerate(); module state rather than handler
# state because SimpleHTTPRequestHandler is constructed per request. The core
# module is re-imported per regenerate rather than imported here, so edits to the
# engine itself take effect on refresh like everything else.
_ENTRY = None
_PROJECT_DIR = None
_OUT_DIR = None
_HIDPI_DIR = None
_CORE = None

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  body { margin: 0; padding: 22px 26px 60px;
         font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
         background: #e8e8e4; color: #0b0b0b; }
  h1 { font-size: 19px; margin: 0 0 4px; }
  p.sub { margin: 0 0 18px; color: #52514e; }
  nav { margin: 0 0 20px; }
  nav a { display: inline-block; margin-right: 12px; padding: 5px 11px; border-radius: 6px;
          background: #fcfcfb; color: #0b0b0b; text-decoration: none;
          border: 1px solid rgba(11,11,11,.14); font-weight: 600; }
  nav a:hover { background: #fff; }
  section { margin: 0 0 30px; }
  .bar { display: flex; align-items: baseline; gap: 12px; margin: 0 0 7px; }
  .bar h2 { font-size: 14px; margin: 0; color: #52514e; font-weight: 600; }
  .bar code { color: #898781; font-weight: 400; font-size: 12px; }
  .bar .spacer { flex: 1; }
  .bar button { font: inherit; font-size: 12px; padding: 3px 10px; border-radius: 5px;
                border: 1px solid rgba(11,11,11,.16); background: #fcfcfb; cursor: pointer; }
  .bar button:hover { background: #fff; }
  .bar .zoom { font-variant-numeric: tabular-nums; color: #52514e; font-size: 12px;
               min-width: 52px; text-align: right; }
  .viewport { position: relative; overflow: hidden; background: #fcfcfb; border-radius: 10px;
              border: 1px solid rgba(11,11,11,.12); cursor: grab; touch-action: none; }
  .viewport.dragging { cursor: grabbing; }
  .viewport img { position: absolute; top: 0; left: 0; transform-origin: 0 0;
                  user-select: none; -webkit-user-drag: none; }
  pre.err { background: #fff0f0; border: 1px solid #d03b3b; border-radius: 8px;
            padding: 14px 16px; overflow-x: auto; color: #8a1f1f; }
</style>
<h1>__TITLE__</h1>
<p class="sub">Regenerated on every request &mdash; just refresh. Wheel to zoom about the
cursor, drag to pan, double-click to fit the width.</p>
<nav>__NAV__</nav>
__BODY__
<script>
const MIN_REL = 0.5, MAX_REL = 40;   // zoom limits, relative to fit-width

for (const vp of document.querySelectorAll('.viewport')) {
  const img = vp.querySelector('img');
  const out = vp.parentElement.querySelector('.zoom');
  const W = +img.dataset.w, H = +img.dataset.h;
  let k = 1, x = 0, y = 0, fit = 1;

  const apply = () => {
    img.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
    if (out) out.textContent = Math.round(k * 100) + '%';
  };
  const fitWidth = () => {
    fit = vp.clientWidth / W;
    // Tall figures get a window to move around in; short ones are shown whole.
    vp.style.height = Math.min(window.innerHeight * 0.78, H * fit) + 'px';
    k = fit; x = 0; y = 0;
    apply();
  };
  const zoomTo = (nk, cx, cy) => {
    nk = Math.min(fit * MAX_REL, Math.max(fit * MIN_REL, nk));
    x = cx - (cx - x) * (nk / k);
    y = cy - (cy - y) * (nk / k);
    k = nk;
    apply();
  };

  img.width = W; img.height = H;
  vp.addEventListener('wheel', e => {
    e.preventDefault();
    const r = vp.getBoundingClientRect();
    zoomTo(k * Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});

  let panning = false, lx = 0, ly = 0;
  vp.addEventListener('pointerdown', e => {
    panning = true; lx = e.clientX; ly = e.clientY;
    vp.setPointerCapture(e.pointerId); vp.classList.add('dragging');
  });
  vp.addEventListener('pointermove', e => {
    if (!panning) return;
    x += e.clientX - lx; y += e.clientY - ly;
    lx = e.clientX; ly = e.clientY;
    apply();
  });
  for (const ev of ['pointerup', 'pointercancel']) {
    vp.addEventListener(ev, () => { panning = false; vp.classList.remove('dragging'); });
  }
  vp.addEventListener('dblclick', fitWidth);

  const bar = vp.parentElement.querySelector('.bar');
  bar.querySelector('[data-act=fit]').onclick = fitWidth;
  bar.querySelector('[data-act=one]').onclick = () => {
    const r = vp.getBoundingClientRect();
    zoomTo(1, r.width / 2, r.height / 2);
  };

  window.addEventListener('resize', fitWidth);
  fitWidth();
}
</script>
"""


def regenerate():
    """Reimport the project and rewrite every SVG. Returns (project, error text).

    Everything under the project directory and under wiggleroom itself is purged
    first, so editing a figure, the project, or the engine all take effect on the
    next refresh - reload order stops mattering when nothing stale survives.
    """
    global _CORE, _HIDPI_DIR, _OUT_DIR
    engine_dir = str(pathlib.Path(__file__).resolve().parent)
    try:
        for name, module in list(sys.modules.items()):
            origin = getattr(module, "__file__", None)
            roots = (str(_PROJECT_DIR) + os.sep, engine_dir + os.sep)
            if origin and origin.startswith(roots):
                if name != __name__:
                    del sys.modules[name]
        _CORE = importlib.import_module("wiggleroom.core")
        project = importlib.import_module(_ENTRY).PROJECT
        _OUT_DIR = project.out_dir
        _HIDPI_DIR = project.cache_dir / "hidpi"
        for figure in project.figures:
            (project.out_dir / f"{figure.slug}.svg").write_text(_CORE.render(project, figure))
        return project, None
    except Exception:
        return None, traceback.format_exc()


def page(project, revision):
    hidpi = sorted(_HIDPI_DIR.glob("*.png")) if _HIDPI_DIR.is_dir() else []
    nav = "".join(
        f'<a href="{f.slug}.svg">{f.number} &middot; {html.escape(f.name.split("—")[-1].strip())}</a>'
        for f in project.figures
    )
    parts = []
    for f in project.figures:
        w, h = _CORE.figure_size(f)
        parts.append(
            f'<section><div class="bar"><h2>{html.escape(f.heading)}</h2>'
            f'<code>{len(f.lanes)} lanes &middot; 0&ndash;{f.tmax:g} {f.unit} '
            f'&middot; {w}&times;{h}</code><span class="spacer"></span>'
            f'<span class="zoom"></span>'
            f'<button data-act="fit">fit</button><button data-act="one">1:1</button></div>'
            f'<div class="viewport"><img src="{f.slug}.svg?r={revision}" '
            f'data-w="{w}" data-h="{h}" alt=""></div></section>'
        )
    if hidpi:
        links = " ".join(
            f'<a href="/hidpi/{f.name}">{f.name.split("-")[-1].replace(".png", "")} '
            f'({f.stat().st_size // 1024 // 1024} MB)</a>' for f in hidpi)
        nav += ('<span style="margin:0 8px 0 18px;color:#898781">high-DPI 4x:</span>' + links)
    return (PAGE.replace("__TITLE__", html.escape(project.title))
            .replace("__NAV__", nav).replace("__BODY__", "".join(parts)))


class Handler(http.server.SimpleHTTPRequestHandler):
    revision = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(_OUT_DIR), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/hidpi/"):
            return self.serve_hidpi()
        project, error = regenerate()
        if error:
            self.log_error("generator failed:\n%s", error)
        if self.path not in ("/", "/index.html"):
            return super().do_GET()

        Handler.revision += 1
        body = (PAGE.replace("__TITLE__", "figure generator error")
                .replace("__NAV__", "").replace("__BODY__",
                f'<pre class="err">{html.escape(error)}</pre>')
                if error else page(project, Handler.revision))
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def serve_hidpi(self):
        """Serve a rendered PNG out of the project cache.

        They are build artifacts rather than sources, so they live outside the tree
        and are fetched from here rather than committed - the repo rejects binaries.
        """
        # The path arrives percent-encoded, and browsers differ on whether they
        # encode characters like @ - so decode before matching a filename.
        name = pathlib.PurePosixPath(urllib.parse.unquote(self.path)).name
        path = _HIDPI_DIR / name
        if not name.endswith(".png") or not path.is_file():
            return self.send_error(404)
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{fmt % args}\n")


def main(entry, project_dir, argv=()):
    """Serve `project_dir`'s project (module `entry` exporting PROJECT).

    argv: optionally a port, defaulting to 8931.
    """
    global _ENTRY, _PROJECT_DIR
    _ENTRY, _PROJECT_DIR = entry, pathlib.Path(project_dir).resolve()
    if str(_PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(_PROJECT_DIR))
    port = int(argv[0]) if argv else 8931
    project, error = regenerate()
    if error:
        sys.stderr.write(error)
    print(f"serving {_OUT_DIR} on http://127.0.0.1:{port}/", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
