"""0.1.157: a plain sidebar (the 0.1.156 one "looked too AI"), the new glowing logo in it and on the collapsed
sidebar (the icon rail), and older web engines fixed.

What people saw: a lit, card-like sidebar with badges and uppercase headings; and on an older Mac (its app window is
the system's WebKit, which ignored flex "gap") the sidebar's icons touching their labels, the "Temporary" icon
touching its word and the logo tile touching "Gink". Overlays written with `inset: 0` (the app lock among them) didn't
cover the window there either.
"""
import base64
import io
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _page():
    from ginkassistant.ui.web_chat_view import _build_page_html
    return _build_page_html("Hi Ibrahim", "How can I help today?")


def _no_gap(css):
    return not re.search(r"(?<![-\w])gap\s*:", css)


# ---------------------------------------------------------------- the sidebar
def test_sidebar_is_plain():
    h = _page()
    side = h[h.index('<aside id="side"'):h.index("</aside>")]
    assert '<div class="brand"><span class="gmark" aria-hidden="true"></span><span>Gink</span></div>' in side
    assert re.findall(r'class="srow" data-nav="(\w+)"', side) == ["new", "tasks", "media", "genie"]
    assert re.findall(r'<span class="lbl">([^<]+)</span>', side) == ["New chat", "Workspace", "Media Studio", "Gink Genie"]
    assert '<label class="srow" id="side-search">' in side and 'placeholder="Search chats"' in side
    for gone in ("brand-tile", 'class="side-sep"', 'class="new-chat"', ".new-chat {", 'class="nav"', ".nav button"):   # the 0.1.156 pieces
        assert gone not in h, gone
    css = h[h.index("/* ---------- the sidebar (0.1.157): plain and quiet"):h.index("/* ---------- delete dialog")]
    for gone in ("radial-gradient", "box-shadow", "backdrop-filter", "linear-gradient", ".recent.current::before", "font-weight: 600; box-shadow"):
        assert gone not in css, gone
    assert ".recent.current { background: var(--side-active); }" in css
    assert ".srow:hover .nk { opacity: 1; }" in css and ".nk { flex: none; margin-left: 8px;" in css   # shortcuts: only on hover
    extras = read("src", "ginkassistant", "ui", "chat_extras.py")
    head = extras[extras.index("  .recents-head {"):extras.index("\n", extras.index("  .recents-head {"))]
    assert "uppercase" not in head and "letter-spacing" not in head                  # "Today", not "TODAY"
    assert "\\1F4CC" not in extras                                                   # no pin emoji on pinned rows
    assert "background: var(--accent); color: var(--on-accent);" in h                # a plain avatar: no gradient, no ring
    # spacing: margins only -- older Mac web views ignore flex gap
    rail = h[h.index("/* ---------- icon rail: the sidebar, collapsed"):h.index("/* ---------- attachments")]
    temp = h[h.index("  #temp-btn {"):h.index("  #temp-banner span")]
    assert _no_gap(css) and _no_gap(rail) and _no_gap(temp), "flex gap in the sidebar, the rail or Temporary"
    assert ".srow svg { width: 18px; height: 18px; flex: none; margin-right: 10px; }" in css
    assert ".side-head .gmark { margin-right: 10px; }" in css and "#temp-btn svg { flex: none; margin-right: 6px; }" in h


def test_the_closed_sidebar_has_the_older_lighter_look():
    """0.1.158: "change this to this" -- the rail as it was before 0.1.157 (with the logo kept on top)."""
    h = _page()
    css = h[h.index("/* ---------- icon rail: the sidebar, collapsed"):h.index("/* ---------- attachments")]
    rule = css[css.index("  #rail {"):css.index("}", css.index("  #rail {"))]
    assert "background" not in rule and "border" not in rule                          # on the page: no tinted column, no line
    assert "#rail .ibtn { width: 40px; height: 40px; border-radius: 12px; margin: 0 0 4px; color: var(--text-muted);" in css
    assert "#rail .ibtn:hover { color: var(--text-main); background: var(--side-hover); }" in css
    rail = h[h.index('<nav id="rail">'):h.index("</nav>", h.index('<nav id="rail">'))]
    new = rail[rail.index('data-rail="new"'):rail.index("</button>", rail.index('data-rail="new"'))]
    assert '<path d="M12 20h8"/>' in new                                                # a pencil, not a pencil-in-a-square
    media = rail[rail.index('data-rail="media"'):rail.index("</button>", rail.index('data-rail="media"'))]
    assert '<path d="M20.5 16l-5-5-8 8.5"/>' in media
    side = h[h.index('<aside id="side"'):h.index("</aside>")]
    for nav, path in (("new", '<path d="M12 20h8"/>'), ("media", '<path d="M20.5 16l-5-5-8 8.5"/>')):
        row = side[side.index(f'data-nav="{nav}"'):side.index("</button>", side.index(f'data-nav="{nav}"'))]
        assert path in row, nav                                                       # the open sidebar: the same icons


def test_logo_on_the_sidebar_and_the_rail():
    from ginkassistant.ui.branding import BRAND_TILE_BASE64, BRAND_TILE_DATA_URI
    h = _page()
    assert h.count(BRAND_TILE_BASE64) == 1 and "url(" + BRAND_TILE_DATA_URI + ")" in h          # one copy, as .gmark
    assert h.count('id="tb-toggle"') == 1
    toggle = h[h.index('<button class="ibtn tb-toggle" id="tb-toggle"'):h.index("</button>", h.index('id="tb-toggle"'))]
    assert '<span class="gmark" aria-hidden="true"></span>' in toggle and 'class="tb-panel"' in toggle
    rail = h[h.index('<nav id="rail">'):h.index("</nav>", h.index('<nav id="rail">'))]
    assert re.findall(r'data-rail="(\w+)"', rail) == ["new", "search", "tasks", "genie", "media", "settings", "settings"]
    for must in ("body:not(.pinned):not(.peek) #tb-toggle .gmark { display: block; }",
                 "body:not(.pinned):not(.peek) #tb-toggle:hover .tb-panel { display: block; }",
                 "body.pinned #tb-toggle, body.peek #tb-toggle { left: calc(var(--side-w) - 50px); }",
                 "body.pinned #tb-toggle, body.peek #tb-toggle { left: calc(min(86vw, 320px) - 50px); }",
                 "tb.title = sideOpen() ? 'Close sidebar' : 'Open sidebar';"):
        assert must in h, must
    assert "tb.addEventListener('mouseenter'" not in h        # pointing at the logo shows "open sidebar"; it doesn't slide it out
    # the picture: the neon snowflake on its dark tile, rounded corners see-through
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(BRAND_TILE_BASE64)))
    assert im.size == (96, 96) and im.mode == "RGBA"
    assert all(im.getpixel(c)[3] == 0 for c in ((0, 0), (95, 0), (0, 95), (95, 95)))
    r, g, b, a = im.getpixel((48, 48))
    assert a == 255 and g > r and g > b
    data = im.tobytes()
    lime = sum(1 for i in range(0, len(data), 4) if data[i + 3] == 255 and data[i + 1] > 200 and data[i] > 120 and data[i + 2] < 120)
    assert lime > 300                                         # the glowing lime strokes


# ---------------------------------------------------------------- older web engines
def test_gap_fix_is_on_every_app_page():
    import json
    from ginkassistant.ui import compat
    from ginkassistant.ui import media_studio_screen as ms
    from ginkassistant.ui.login_screen import _login_page_html
    js = compat.FLEX_GAP_JS
    assert _page().count(js) == 1 and _login_page_html().count(js) == 1
    assert "compat.inject(PAGE.replace(\"__THEME__\", css_vars()))" in read("src", "ginkassistant", "ui", "tasks_screen.py")
    assert 'self.web.set_content("https://gink.local/media", compat.inject(page))' in read("src", "ginkassistant", "ui", "media_studio_screen.py")
    assert json and ms.PAGE                                                       # (Media Studio's page is built at runtime)
    genie = read("src", "ginkassistant", "services", "web_app", "genie.html")
    copy = genie[genie.index("<!-- gink:compat"):genie.index("<!-- /gink:compat -->")]
    assert copy.split("<script>\n", 1)[1].rsplit("</script>", 1)[0] == js, "genie.html's copy differs from ui/compat.py"
    built = os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "index.html")
    assert open(built, encoding="utf-8").read().count(js) == 1, "rebuild the web app: python3 tools/build_web_app.py"
    assert "if (FORCE) start(); else decide();" in js and "if (h === 2) start();" in js and "catch (e) {}" in js
    # (decide: 3 = gap works -> nothing; 2 = it doesn't -> the fix; 0 = not laid out yet -> again on load/resize)


def test_no_inset_shorthand_or_bare_new_css_on_app_pages():
    """`inset`, `aspect-ratio` and `color-mix()` are newer than older Macs' WebKit: four sides, a fallback, a plain value first."""
    files = [("src", "ginkassistant", "ui", f) for f in os.listdir(os.path.join(ROOT, "src", "ginkassistant", "ui")) if f.endswith(".py")]
    files += [("src", "ginkassistant", "services", "web_app", f) for f in ("genie.html", "lock.js")] + [("webapp", "signin.html"), ("webapp", "bridge.js")]
    for parts in files:
        text = read(*parts)
        assert not re.search(r"(?<![-\w])inset\s*:\s*\d", text), os.path.join(*parts)
    h = _page()
    assert "@supports not (aspect-ratio: 1) { .pp-photo::before" in h
    ws = read("src", "ginkassistant", "ui", "workspace_page.py")
    for line in [ln for ln in ws.splitlines() if "color-mix(" in ln]:
        prop = re.search(r"([\w-]+):\s*color-mix\(", line).group(1)
        assert line.index(prop + ":") < line.index(prop + ": color-mix("), line          # a plain value comes first
    signin = read("webapp", "signin.html")
    assert ".ws-or::before { margin-right: 10px; } .ws-or::after { margin-left: 10px; }" in signin


# ---------------------------------------------------------------- in a real browser
def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


@pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")
def test_rail_logo_toggle_and_gap_fix_in_a_browser(tmp_path):
    from PIL import Image, ImageChops
    (tmp_path / "p.html").write_text(_page(), encoding="utf-8")
    url = (tmp_path / "p.html").as_uri()
    sessions = "[{id: 'a', title: 'How do vaccines work?', current: true, when: Date.now()}, {id: 'b', title: 'Plan my week', when: Date.now() - 2 * 864e5}]"
    with _browser()() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no Chromium here ({type(exc).__name__})")
        shots = {}
        for force in (False, True):
            ctx = browser.new_context(viewport={"width": 1280, "height": 760})
            if force:                                   # an engine without flex gap, with the fix
                ctx.add_init_script("window.GINK_GAP_POLYFILL = true;")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_timeout(300)
            page.mouse.move(1200, 400)
            page.evaluate("() => { window.ginkEmit = function () {}; setPinned(false); setUser('Ibrahim Kargbo', '', 'Ibrahim'); setSessions(" + sessions + ");"
                          " hideWelcome(); }")                     # a chat: no moving glow behind the screenshots
            page.wait_for_timeout(500)
            if not force:
                # closed: the rail shows the logo; pointing at it shows "open sidebar"
                shown = "() => [getComputedStyle(document.querySelector('#tb-toggle .gmark')).display, getComputedStyle(document.querySelector('#tb-toggle .tb-panel')).display]"
                assert page.evaluate(shown) == ["block", "none"]
                assert page.evaluate("() => document.getElementById('tb-toggle').title") == "Open sidebar"
                page.hover("#tb-toggle")
                page.wait_for_timeout(200)
                assert page.evaluate(shown) == ["none", "block"]
                page.wait_for_timeout(500)
                assert not page.evaluate("() => document.body.classList.contains('peek')")      # no slide-out under the pointer
                assert page.evaluate("() => document.getElementById('rail').getBoundingClientRect().width") == 60
                page.click("#tb-toggle")
                page.wait_for_timeout(450)
                assert page.evaluate("() => document.body.classList.contains('pinned')")
                assert page.evaluate("() => document.getElementById('tb-toggle').title") == "Close sidebar"
                assert page.evaluate("() => Math.round(document.getElementById('tb-toggle').getBoundingClientRect().left)") == 260 - 50
                assert page.evaluate("() => document.documentElement.className.indexOf('no-flex-gap')") == -1
                assert page.evaluate("() => typeof window.ginkGapStats") == "undefined"        # gap works: the fix stays out
            else:
                page.evaluate("() => setPinned(true)")
                page.wait_for_timeout(450)
                assert "no-flex-gap" in page.evaluate("() => document.documentElement.className")
                assert page.evaluate("() => ginkGapStats.boxes") > 5
                # an icon never touches its label, and a flex container's gap is back as margins
                gaps = page.evaluate("""() => [...document.querySelectorAll('.srow')].map(r => {
                    const s = r.querySelector('svg').getBoundingClientRect(), t = (r.querySelector('.lbl') || r.querySelector('input')).getBoundingClientRect();
                    return Math.round(t.left - s.right); })""")
                assert gaps == [10] * 5
                crow = page.evaluate("""() => { const c = document.querySelector('.crow'); return [getComputedStyle(c).columnGap,
                    [...c.children].filter(x => getComputedStyle(x).display !== 'none' && getComputedStyle(x).position !== 'absolute').length]; }""")
                assert crow[0] == "0px" and crow[1] >= 2
            page.mouse.move(1200, 400)
            page.evaluate("() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); }")
            page.wait_for_timeout(900)
            path = tmp_path / f"{'fix' if force else 'native'}.png"
            page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": 1280, "height": 300})
            shots[force] = path
            assert not errors, errors
            ctx.close()
        browser.close()
    diff = ImageChops.difference(Image.open(shots[False]).convert("RGB"), Image.open(shots[True]).convert("RGB"))
    changed = sum(1 for v in diff.convert("L").tobytes() if v > 40)
    assert changed < 50, f"the fix doesn't reproduce the native gaps ({changed} pixels differ)"
