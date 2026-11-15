"""Phones (0.1.155): the app and the web app look like the designs and behave on a phone.

What people saw: on iPhone the page zoomed in when they tapped the message box and stayed zoomed and shifted
sideways; a wide table widened the whole page; replies showed through the header; on Android a teal "Gink"
title bar sat on top, the keyboard pushed the message box to the top of the screen (the conversation gone),
the mic fell out of the box, there were no ideas under the box, and the sign-in card was cut off.
"""
import json
import os
import sys
import types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _page():
    from ginkassistant.ui.web_chat_view import _build_page_html
    return _build_page_html("Hi Ibrahim", "How can I help today?")


# ---------------------------------------------------------------- the shared chat page (apps + web app)
def test_page_is_built_for_phones():
    h = _page()
    head = h[:h.index("</head>")]
    assert '<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">' in head
    assert head.count('name="viewport"') == 1 and "viewport-fit" not in head        # no notch handling needed
    for must in ('<div id="shell">', '<div id="headbar" aria-hidden="true"></div>', '<div id="scroller">',
                 "  #composer-wrap {\n    position: absolute; left: 0; right: 0; bottom: 0; z-index: 5;",
                 "body:not(.home) #headbar { opacity: 1; }",                        # replies never show through the header
                 "function fitViewport()", "visualViewport.addEventListener('resize', fitViewport);",
                 "shell.style.transform = top ? 'translateY(' + top + 'px)' : '';",
                 "function wrapTables(root)", "    wrapTables(el);\n", "    wrapTables(st);\n",
                 "font-size: 16px !important; }",                                   # iPhone: no zoom when you tap a box
                 "if (on && NO_HOVER) return;",                                     # no sidebar from a tap at the edge
                 "refreshSend(); if (!NO_HOVER) t.focus();",                        # no keyboard popping up by itself
                 "body.home #cin { flex: 1; width: auto; min-width: 0;",            # the mic stays in the box
                 "ginkEmit('bars', {bg: bg, dark: dark});"):
        assert must in h, must
    assert "window.scrollTo(0, document.body.scrollHeight)" not in h                 # the page itself never scrolls
    assert "body.pinned #composer-wrap { left: var(--side-w); }" not in h and "body.pinned #shell { left: var(--side-w); }" in h


def test_apps_greet_like_the_designs():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    for must in ('return f"Hi {n}" if n else "Hi there"', "def welcome_sub() -> str:", "return ending[:1].upper() + ending[1:]",
                 "web_chat = WebChatFeed(welcome_title=welcome_title(), welcome_subtitle=welcome_sub(),",
                 "await web_chat.show_welcome(welcome_title(), welcome_sub())", "for full in (p.get(\"full_name\"), account_name()):",
                 'if kind == "bars" and isinstance(value, dict):'):
        assert must in main, must
    assert "WELCOME_SUB" not in main
    bridge = read("webapp", "bridge.js")
    assert 'showWelcome(first ? "Hi " + first : "Hi there", ending.charAt(0).toUpperCase() + ending.slice(1));' in bridge
    assert "tokenName(LS.getItem(\"gink_token\") || sessionStorage.getItem(\"gink_token\"))" in bridge
    assert "if (window.ginkScrollEnd) ginkScrollEnd(true);" in bridge
    build = read("tools", "build_web_app.py")
    assert '_build_page_html("Hi there", "How can I help today?")' in build and 'name="viewport"' not in build


def test_the_name_comes_from_the_sign_in_token():
    """No nickname or full name in the profile: the account's name (in the token) still says "Hi Ibrahim"."""
    import base64
    import re
    import textwrap
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    body = main[main.index("    def account_name() -> str:"):main.index("    def greet_name() -> str:")]
    ns = {}
    exec("def make(app):\n" + textwrap.indent(textwrap.dedent(body), "    ") + "    return account_name\n", ns)
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x@y.z", "name": "Ibrahim Kargbo"}).encode()).decode().rstrip("=")
    assert ns["make"](types.SimpleNamespace(session_token="h." + payload + ".s"))() == "Ibrahim Kargbo"
    assert ns["make"](types.SimpleNamespace(session_token="not-a-token"))() == ""
    assert ns["make"](types.SimpleNamespace())() == ""
    assert re.search(r"def welcome_title\(\) -> str:\n        n = greet_name\(\)", main)


def test_sign_in_pages_scroll_instead_of_cutting_the_card():
    from ginkassistant.ui import login_screen
    html = login_screen._login_page_html()
    assert "max-height: calc(100vh - 32px)" not in html and "overflow-x: hidden; overflow-y: auto;" in html
    assert "position: relative; z-index: 2; width: 392px; max-width: calc(100vw - 32px); margin: auto 0;" in html
    assert "@media (hover: none) and (pointer: coarse) { .field input { font-size: 16px; } }" in html
    signin = read("webapp", "signin.html")
    assert "overflow-y: auto;" in signin and "margin: auto 0;" in signin
    for page in ("genie", "console", "auth", "device", "admin"):
        p = read("src", "ginkassistant", "services", "web_app", page + ".html")
        assert "@media (hover: none) and (pointer: coarse) { input:not([type=checkbox])" in p, page
        assert 'content="width=device-width, initial-scale=1, interactive-widget=resizes-content"' in p, page


# ---------------------------------------------------------------- the Android app's window
def test_android_build_has_no_teal_title_bar():
    import tomllib
    a = tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))["tool"]["briefcase"]["app"]["ginkassistant"]["android"]
    assert a["base_theme"] == "Theme.AppCompat.Light.NoActionBar"
    assert a["primary_color"] == "#3F8212" and a["primary_color_dark"] == "#151D23"   # Gink's colours, not the template's teal
    app = read("src", "ginkassistant", "app.py")
    assert "android_chrome.setup(self)" in app and "android_chrome.set_bars(self, android_chrome.LOGIN_BG, False)" in app


class _Insets:
    def __init__(self, bars, ime): self.bars, self.ime = bars, ime
    def getInsets(self, mask):
        l, t, r, b = self.ime if mask == 8 else self.bars
        return types.SimpleNamespace(left=l, top=t, right=r, bottom=b)


class _LP:
    def __init__(self, h=0): self.leftMargin = self.topMargin = self.rightMargin = self.bottomMargin = 0; self.height = h
    def setMargins(self, l, t, r, b): self.leftMargin, self.topMargin, self.rightMargin, self.bottomMargin = l, t, r, b


class _View:
    def __init__(self, cls="android.widget.FrameLayout"):
        self.cls, self.lp, self.parent, self.bg, self.set_lp = cls, _LP(), None, None, 0
    def getLayoutParams(self): return self.lp
    def setLayoutParams(self, lp): self.lp = lp; self.set_lp += 1
    def getParent(self): return self.parent
    def equals(self, other): return self is other
    def getClass(self): return types.SimpleNamespace(getName=lambda: self.cls)
    def setBackgroundColor(self, c): self.bg = c


class _Group(_View):
    def __init__(self, children):
        super().__init__("androidx.appcompat.widget.ContentFrameLayout")
        self.children = children
        for c in children: c.parent = self
    def getChildCount(self): return len(self.children)
    def getChildAt(self, i): return self.children[i]


def _fake_android(monkeypatch, edge_to_edge=True, action_bar=True):
    log = {"hidden": 0, "mode": None, "listener": None, "applied": 0, "bars": {}}
    content = _View()
    status = _View("android.view.View")
    _Group([content, status] if edge_to_edge else [content])

    class Controller:
        def setAppearanceLightStatusBars(self, v): log["bars"]["light_status"] = v
        def setAppearanceLightNavigationBars(self, v): log["bars"]["light_nav"] = v

    decor = _View("com.android.internal.policy.DecorView")
    window = types.SimpleNamespace(setSoftInputMode=lambda m: log.__setitem__("mode", m), getDecorView=lambda: decor,
                                   setStatusBarColor=lambda c: log["bars"].__setitem__("status", c),
                                   setNavigationBarColor=lambda c: log["bars"].__setitem__("nav", c))
    bar = types.SimpleNamespace(hide=lambda: log.__setitem__("hidden", log["hidden"] + 1))
    act = types.SimpleNamespace(getSupportActionBar=lambda: bar if action_bar else None, getWindow=lambda: window,
                                findViewById=lambda i: content if i == 16908290 else None)
    classes = {
        "android.R$id": types.SimpleNamespace(content=16908290),
        "android.view.WindowManager$LayoutParams": types.SimpleNamespace(SOFT_INPUT_ADJUST_RESIZE=16),
        "androidx.core.view.ViewCompat": types.SimpleNamespace(
            setOnApplyWindowInsetsListener=lambda v, l: log.__setitem__("listener", l),
            requestApplyInsets=lambda v: log.__setitem__("applied", log["applied"] + 1)),
        "androidx.core.view.WindowInsetsCompat$Type": types.SimpleNamespace(systemBars=lambda: 1, displayCutout=lambda: 2, ime=lambda: 8),
        "android.view.ViewGroup$MarginLayoutParams": object, "android.view.ViewGroup": object,
        "androidx.core.view.OnApplyWindowInsetsListener": "listener-interface",
        "android.graphics.Color": types.SimpleNamespace(parseColor=lambda s: int(s[1:], 16)),
        "androidx.core.view.WindowCompat": types.SimpleNamespace(getInsetsController=lambda w, d: Controller()),
    }
    java = types.ModuleType("java")
    java.jclass = lambda name: classes[name]
    java.cast = lambda cls, obj: obj
    java.dynamic_proxy = lambda iface: object
    monkeypatch.setitem(sys.modules, "java", java)
    from ginkassistant.services import android_chrome
    monkeypatch.setattr(android_chrome, "is_android", lambda: True)
    monkeypatch.setitem(android_chrome._state, "bars", None)
    app = types.SimpleNamespace(_impl=types.SimpleNamespace(native=act))
    return android_chrome, app, log, content, status, decor


def test_android_hides_the_title_bar_and_the_keyboard_makes_room(monkeypatch):
    ac, app, log, content, status, decor = _fake_android(monkeypatch)
    assert ac.setup(app) is True and ac.state()["error"] == ""
    assert log["hidden"] == 1 and log["mode"] == 16 and log["applied"] == 1
    listener = log["listener"]
    # keyboard closed: the template's own margins (status bar on top, navigation bar at the bottom)
    listener.onApplyWindowInsets(content, _Insets((0, 63, 0, 48), (0, 0, 0, 0)))
    assert (content.lp.topMargin, content.lp.bottomMargin, status.lp.height) == (63, 48, 63)
    # keyboard open: the app ends at the top of the keyboard -- the page is resized, not covered or panned
    listener.onApplyWindowInsets(content, _Insets((0, 63, 0, 48), (0, 0, 0, 870)))
    assert (content.lp.topMargin, content.lp.bottomMargin) == (63, 870)
    n = content.set_lp
    listener.onApplyWindowInsets(content, _Insets((0, 63, 0, 48), (0, 0, 0, 870)))
    assert content.set_lp == n                                   # nothing changed: no extra layout pass
    listener.onApplyWindowInsets(content, None)                  # a bad call never reaches Android as a crash
    assert "keyboard insets" in ac.state()["error"]


def test_android_bars_take_the_page_colour(monkeypatch):
    ac, app, log, content, status, decor = _fake_android(monkeypatch)
    assert ac.set_bars(app, "#ffffff", False) is True
    assert log["bars"] == {"status": 0xFFFFFF, "nav": 0xFFFFFF, "light_status": True, "light_nav": True}
    assert status.bg == 0xFFFFFF and decor.bg == 0xFFFFFF       # Android 15+: the template paints the status bar itself
    assert ac.set_bars(app, "#161917", True) is True and log["bars"]["light_status"] is False and status.bg == 0x161917
    assert ac.set_bars(app, "#121815", True) is True             # the lock screen
    assert ac.set_bars(app, "rgb(1,2,3)", False) is False and ac.set_bars(app, "", False) is False
    assert ac.normal_hex("#abc") == "#AABBCC" and ac.normal_hex("#12345") == ""


def test_android_older_template_and_off_android(monkeypatch):
    ac, app, log, content, status, decor = _fake_android(monkeypatch, edge_to_edge=False, action_bar=False)
    assert ac.setup(app) is True
    assert log["listener"] is None and log["mode"] == 16          # not edge-to-edge: adjustResize alone shrinks the app
    monkeypatch.setattr(ac, "is_android", lambda: False)
    assert ac.setup(app) is False and ac.set_bars(app, "#FFFFFF", False) is False


def test_gink_genie_gets_the_keyboard_fix_and_keeps_its_bar(monkeypatch):
    """Gink Genie (its own app, its own copy of the module): the keyboard makes room; the bar stays (Home, Back, Reload)."""
    assert read("src", "ginkgenie", "android_chrome.py") == read("src", "ginkassistant", "services", "android_chrome.py")
    assert "android_chrome.setup(self, hide_title_bar=False)" in read("src", "ginkgenie", "app.py")
    import tomllib
    g = tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))["tool"]["briefcase"]["app"]["ginkgenie"]["android"]
    assert "base_theme" not in g and g["primary_color"] == "#151D23"            # Gink's dark, not teal
    ac, app, log, content, status, decor = _fake_android(monkeypatch)
    assert ac.setup(app, hide_title_bar=False) is True
    assert log["hidden"] == 0 and log["listener"] is not None and log["bars"] == {}


def test_the_page_tells_the_app_its_colours():
    h = _page()
    assert "if (window.syncBars) syncBars();" in h                  # light / dark theme (Settings)
    assert "document.documentElement.classList.remove('gink-locked'); syncBars(); return; }" in h    # unlocked
    assert "var bg = locked ? '#121815'" in h


# ---------------------------------------------------------------- in a real browser, at phone sizes
def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


TABLE = ("<p>Senegal's next votes:</p><table><thead><tr><th>Election type</th><th>Expected date</th><th>What we know</th></tr></thead>"
         "<tbody><tr><td><strong>Parliamentary</strong> (Assemblée Nationale)</td><td>Saturday 31 July 2027</td><td>This is the date most "
         "sources list for the 2027 legislative election. No official decree has been published yet, so the date could still shift.</td></tr>"
         "<tr><td><strong>Presidential</strong></td><td>Sometime in 2029</td><td>The constitution sets a five-year term, so the next poll must "
         "occur in 2029. No exact day has been announced.</td></tr></tbody></table><p>https://example.org/a/very/long/link/that/should/wrap/"
         "instead/of/widening/the/page/at/all/ever</p>")


@pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")
def test_phone_layout_in_a_browser(tmp_path):
    (tmp_path / "p.html").write_text(_page(), encoding="utf-8")
    with _browser()() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no Chromium here ({type(exc).__name__})")
        phone = dict(p.devices["iPhone 13"]); phone.pop("default_browser_type", None)
        ctx = browser.new_context(**phone)
        page = ctx.new_page()
        page.goto((tmp_path / "p.html").as_uri())
        page.evaluate("() => { window.__ev = []; window.ginkEmit = function (t, v) { window.__ev.push([t, v]); }; }")
        page.wait_for_timeout(300)
        # home: like the design -- greeting, the box with the mic inside, the ideas under it, nothing off-screen
        home = page.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
            document.getElementById('model-name').textContent = 'Gink Crystal';
            return {h1: r('#welcome h1').bottom, pill: [r('#composer').top, r('#composer').right], mic: r('#mic').right,
                    sug: getComputedStyle(document.getElementById('suggest')).display, sw: document.documentElement.scrollWidth, w: innerWidth,
                    font: getComputedStyle(document.getElementById('cin')).fontSize}; }""")
        assert home["h1"] < home["pill"][0] and home["mic"] <= home["pill"][1] and home["sug"] == "flex"
        assert home["sw"] == home["w"] and home["font"] == "16px"
        # a wide table scrolls in its own box; the page never gets wider than the phone
        page.evaluate("(t) => { hideWelcome(); addUserMessage('When is the election'); addAssistantMessage('a1'); finalizeMessage('a1', t);"
                      " for (let i = 0; i < 12; i++) { addUserMessage('more ' + i); addAssistantMessage('b' + i); finalizeMessage('b' + i, '<p>line</p>'); } }", TABLE)
        page.wait_for_timeout(700)
        chat = page.evaluate("""() => { const w = document.querySelector('.table-wrap'), s = document.getElementById('scroller');
            const head = document.getElementById('headbar'), wrap = document.getElementById('composer-wrap').getBoundingClientRect();
            return {sw: document.documentElement.scrollWidth, w: innerWidth, wrapped: !!w, tableScrolls: w.scrollWidth > w.clientWidth,
                    widest: Math.max(...[...w.querySelectorAll('th')].map(t => t.getBoundingClientRect().width)),
                    pageScroll: document.scrollingElement.scrollHeight <= innerHeight, headOpacity: getComputedStyle(head).opacity,
                    headBg: getComputedStyle(head).backgroundColor, atEnd: s.scrollTop + s.clientHeight >= s.scrollHeight - 2,
                    composerBottom: Math.round(wrap.bottom), h: innerHeight}; }""")
        assert chat["sw"] == chat["w"] and chat["wrapped"] and chat["tableScrolls"] and chat["widest"] >= 200
        assert chat["pageScroll"] and chat["headOpacity"] == "1" and chat["headBg"] == "rgb(255, 255, 255)"
        assert chat["atEnd"] and chat["composerBottom"] == chat["h"]
        # iPhone keyboard: Safari keeps the page's height and pans what you see -- the shell follows what you see,
        # the newest message stays above the box, and the box sits right on top of the keyboard
        kb = page.evaluate("""() => {
            const fake = {height: 420, offsetTop: 260, scale: 1, addEventListener() {}};
            Object.defineProperty(window, 'visualViewport', {value: fake, configurable: true});
            document.getElementById('cin').focus(); fitViewport();
            const shell = document.getElementById('shell'), s = document.getElementById('scroller');
            const out = {h: Math.round(shell.getBoundingClientRect().height), t: shell.style.transform, kb: document.body.classList.contains('kb'),
                         bottom: Math.round(document.getElementById('composer-wrap').getBoundingClientRect().bottom),
                         atEnd: s.scrollTop + s.clientHeight >= s.scrollHeight - 2};
            fake.height = innerHeight; fake.offsetTop = 0; document.getElementById('cin').blur(); fitViewport();
            out.after = [shell.style.transform, document.body.classList.contains('kb'), Math.round(shell.getBoundingClientRect().height) === innerHeight];
            return out; }""")
        assert kb["h"] == 420 and kb["t"] == "translateY(260px)" and kb["kb"] and kb["bottom"] == 680 and kb["atEnd"]
        assert kb["after"] == ["", False, True]                     # the keyboard closed: back to the whole screen
        ctx.close()
        # the sign-in card on a small Android phone: the page scrolls to the last line, nothing is cut off
        from ginkassistant.ui import login_screen
        (tmp_path / "login.html").write_text(login_screen._login_page_html(), encoding="utf-8")
        ctx = browser.new_context(viewport={"width": 360, "height": 560}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto((tmp_path / "login.html").as_uri())
        page.wait_for_timeout(700)
        login = page.evaluate("""() => { const card = document.getElementById('card'); window.scrollTo(0, 1e6); document.body.scrollTop = 1e6;
            const r = card.getBoundingClientRect();
            return {cardBottom: Math.round(r.bottom), h: innerHeight, clipped: card.scrollHeight > card.clientHeight + 1, sw: document.documentElement.scrollWidth}; }""")
        assert login["cardBottom"] <= login["h"] and not login["clipped"] and login["sw"] == 360
        ctx.close()
        # desktop is unchanged: the box and the conversation in the same 760px column, beside the icon rail
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto((tmp_path / "p.html").as_uri())
        page.mouse.move(640, 400)
        page.evaluate("() => { window.ginkEmit = function () {}; setPinned(false); hideWelcome(); addUserMessage('Hi'); }")
        page.wait_for_timeout(700)
        desk = page.evaluate("""() => { const c = document.getElementById('composer').getBoundingClientRect(), f = document.getElementById('feed').getBoundingClientRect();
            return [Math.round(c.left), Math.round(c.width), Math.round(f.left), Math.round(f.width), Math.round(c.bottom) <= innerHeight]; }""")
        assert desk == [290, 760, 290, 760, True]
        browser.close()
