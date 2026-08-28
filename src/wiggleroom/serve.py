"""Preview server for a wiggleroom project.

    from wiggleroom.serve import main
    main(entry="project", project_dir=HERE, argv=sys.argv[1:])

A watcher thread polls the project and engine sources, re-runs the generators
when anything changes, and pushes the result to every open page over
server-sent events - the figures swap in place, so a save shows up in the
browser without touching it, and pan/zoom positions survive the update. A
change that fails to render keeps the last good figures on screen and shows
the traceback in a banner instead; a full refresh always re-runs the
generators too, so the page can never be staler than the source.

Each figure gets a pan/zoom viewport: wheel to zoom about the cursor, drag to
pan, double-click to fit - the figures are wider than any window, so reading one
at full size means moving around inside it.

Intended to be paired with `agent-portal forward <port>`.
"""

import hashlib
import html
import http.server
import importlib
import json
import os
import pathlib
import sys
import threading
import time
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

# Live-update state, guarded by _STATE (which also wakes the event streams).
# The revision only moves when the rendered bytes do, so saves that don't
# change the output never make browsers refetch anything.
_RENDER = threading.Lock()
_STATE = threading.Condition()
_REVISION = 0
_DIGEST = None
_FIGURES = []
_ERROR = None

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<link id="fav" rel="icon">
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
  #gen-error { display: none; position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
               background: #fff0f0; border-top: 2px solid #d03b3b; color: #8a1f1f;
               padding: 10px 26px 14px; max-height: 45vh; overflow: auto; }
  #gen-error pre { margin: 8px 0 0; white-space: pre-wrap; }
</style>
<h1>__TITLE__</h1>
<p class="sub">Updates live as the source changes; a save that fails to render keeps the
last good figure and shows the error instead. Wheel to zoom about the cursor, drag to pan,
double-click to fit the width.</p>
<nav>__NAV__</nav>
__BODY__
<div id="gen-error"><strong>generator failed</strong> &mdash; showing the last good
render<pre></pre></div>
<script>
const MIN_REL = 0.5, MAX_REL = 40;   // zoom limits, relative to fit-width

// The favicon is a little wave, defined once here so the tab can change colour
// with the generator's health: blue while rendering cleanly, red while broken.
const FAV = c => "data:image/svg+xml," + encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>` +
  `<rect width='32' height='32' rx='7' fill='#${c}'/>` +
  `<path d='M5 20.5C8.5 20.5 8.5 11.5 12 11.5S15.5 20.5 19 20.5 22.5 11.5 26 11.5' ` +
  `fill='none' stroke='#fff' stroke-width='4' stroke-linecap='round'/></svg>`);
const fav = document.getElementById('fav');
fav.href = FAV('__FAVC__');

for (const vp of document.querySelectorAll('.viewport')) {
  const img = vp.querySelector('img');
  const out = vp.parentElement.querySelector('.zoom');
  let W = +img.dataset.w, H = +img.dataset.h;
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

  vp._size = () => [W, H];
  vp._setSize = (w, h) => { W = w; H = h; img.width = w; img.height = h; fitWidth(); };

  window.addEventListener('resize', fitWidth);
  fitWidth();
}

// Live updates: swap the images in place when a new render lands, so pan/zoom
// survives a save. A shape change (figures added, removed, reordered) reloads.
let rev = __REV__;
const banner = document.getElementById('gen-error');
new EventSource('events').onmessage = e => {
  const d = JSON.parse(e.data);
  banner.style.display = d.error ? 'block' : 'none';
  fav.href = FAV(d.error ? 'd03b3b' : '2a78d6');
  if (d.error) { banner.querySelector('pre').textContent = d.error; return; }
  if (d.revision === rev) return;
  rev = d.revision;
  const sections = [...document.querySelectorAll('section[data-slug]')];
  if (d.figures.length !== sections.length ||
      d.figures.some((f, i) => f.slug !== sections[i].dataset.slug)) {
    location.reload();
    return;
  }
  const links = document.querySelectorAll('nav a');
  d.figures.forEach((f, i) => {
    const s = sections[i], vp = s.querySelector('.viewport');
    s.querySelector('h2').textContent = f.heading;
    s.querySelector('.bar code').textContent = f.meta;
    if (links[i]) links[i].textContent = f.nav;
    vp.querySelector('img').src = `${f.slug}.svg?r=${rev}`;
    const [w, h] = vp._size();
    if (w !== f.w || h !== f.h) vp._setSize(f.w, f.h);
  });
};
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


def describe(project):
    """What the live-update script needs to swap a figure in place."""
    figures = []
    for f in project.figures:
        w, h = _CORE.figure_size(f)
        figures.append({
            "slug": f.slug, "w": w, "h": h, "heading": f.heading,
            "nav": f"{f.number} · {f.name.split('—')[-1].strip()}",
            "meta": f"{len(f.lanes)} lanes · {f.tmin:g}–{f.tmax:g} {f.unit} · {w}×{h}",
        })
    return figures


def refresh():
    """Regenerate, then wake the event streams if anything actually changed.

    The revision only advances when the rendered bytes differ, so a save that
    leaves the output identical (or reverts a change) never makes browsers
    refetch. A failed render leaves the last good revision in place and carries
    the traceback instead.
    """
    global _REVISION, _DIGEST, _FIGURES, _ERROR
    with _RENDER:
        project, error = regenerate()
        if not error:
            digest = hashlib.sha256()
            for figure in project.figures:
                digest.update((_OUT_DIR / f"{figure.slug}.svg").read_bytes())
            digest = digest.hexdigest()
        with _STATE:
            if error:
                changed = _ERROR != error
                _ERROR = error
            else:
                changed = _ERROR is not None or digest != _DIGEST
                _ERROR = None
                if digest != _DIGEST:
                    _DIGEST = digest
                    _REVISION += 1
                    _FIGURES = describe(project)
            if changed:
                _STATE.notify_all()
    return project, error


def watch(poll=0.5):
    """Poll the source mtimes, refreshing whenever anything changes.

    Polling rather than inotify keeps this dependency-free and editor-agnostic;
    at two scans a second over a handful of files the cost is nothing.
    """
    engine_dir = pathlib.Path(__file__).resolve().parent

    def snapshot():
        seen = {}
        for root in (_PROJECT_DIR, engine_dir):
            for path in root.rglob("*.py"):
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                try:
                    seen[path] = path.stat().st_mtime_ns
                except OSError:
                    pass  # deleted mid-scan; the dict difference is signal enough
        return seen

    last = snapshot()
    while True:
        time.sleep(poll)
        current = snapshot()
        if current != last:
            last = current
            refresh()


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
            f'<section data-slug="{f.slug}"><div class="bar"><h2>{html.escape(f.heading)}</h2>'
            f'<code>{len(f.lanes)} lanes &middot; {f.tmin:g}&ndash;{f.tmax:g} {f.unit} '
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
            .replace("__NAV__", nav).replace("__BODY__", "".join(parts))
            .replace("__REV__", str(revision)).replace("__FAVC__", "2a78d6"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(_OUT_DIR), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def do_GET(self):
        if self.path == "/events":
            return self.serve_events()
        if self.path.startswith("/hidpi/"):
            return self.serve_hidpi()
        if self.path not in ("/", "/index.html"):
            # SVGs are served as written; the watcher (or the page load that
            # linked here) has already regenerated them.
            return super().do_GET()

        project, error = refresh()
        if error:
            self.log_error("generator failed:\n%s", error)
        # A broken-at-load page carries revision -1 so the first successful
        # render (whatever its revision) makes it reload into the figures.
        body = (PAGE.replace("__TITLE__", "figure generator error")
                .replace("__NAV__", "").replace("__BODY__",
                f'<pre class="err">{html.escape(error)}</pre>')
                .replace("__REV__", "-1").replace("__FAVC__", "d03b3b")
                if error else page(project, _REVISION))
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def serve_events(self):
        """Server-sent events: one message per state change, plus keep-alives.

        Each open page holds one of these; the browser reconnects on its own if
        the stream drops, and a reconnect immediately receives the current state
        so nothing rendered while it was away is missed.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        last = None
        try:
            while True:
                with _STATE:
                    if (_REVISION, _ERROR) == last:
                        _STATE.wait(timeout=15)
                    state = (_REVISION, _ERROR)
                    payload = {"revision": _REVISION, "error": _ERROR,
                               "figures": _FIGURES}
                if state == last:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    last = state
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

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
    project, error = refresh()
    if error:
        sys.stderr.write(error)
    threading.Thread(target=watch, daemon=True, name="wiggleroom-watch").start()
    print(f"serving {_OUT_DIR} on http://127.0.0.1:{port}/", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
