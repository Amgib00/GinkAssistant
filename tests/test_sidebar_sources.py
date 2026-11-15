"""0.1.156: a sidebar without a People button (People works by itself), a sidebar button that looks like a panel,
and sources that show each site's REAL logo with the official ones first -- and a Sources button that opens.
(0.1.157 made the sidebar itself plain again: tests/test_plain_sidebar_compat.py.)

What people saw: "5 sources" with coloured letters, and tapping it did nothing (a capture-phase click listener on the
answer's action row swallowed the click); the sidebar's toggle looked like a code "<>" sign; People sat in the sidebar.
"""
import base64
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAF0lEQVR4nGP4z8DwnwGNMBAUGhUlqhQAvz8f4UvdnhwAAAAASUVORK5CYII=")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _page():
    from ginkassistant.ui.web_chat_view import _build_page_html
    return _build_page_html("Hi Ibrahim", "How can I help today?")


# ---------------------------------------------------------------- the sidebar
def test_sidebar_has_no_people_button():
    h = _page()
    side = h[h.index('<aside id="side"'):h.index("</aside>")]
    for must in ('class="srow" data-nav="new"', '<label class="srow" id="side-search">', 'id="nk-new"', 'id="nk-search"',
                 'data-nav="tasks"', 'data-nav="media"', 'data-nav="genie"', 'class="side-foot"'):
        assert must in side, must
    assert "people" not in side.lower() and 'data-rail="people"' not in h and 'data-nav="search"' not in h
    toggle = h[h.index('id="tb-toggle"'):h.index("</button>", h.index('id="tb-toggle"'))]
    assert '<path d="M9.5 4.5v15"/>' in toggle and "M10 9l-3 3 3 3" not in toggle            # a panel, not "<>"
    for must in ("#side-scrim {", "body.pinned #side-scrim, body.peek #side-scrim { opacity: 1; pointer-events: auto; }",
                 "function dayGroup(ms)", "'Previous 7 days'", "side.addEventListener('click', function (e) {"):
        assert must in h, must
    assert '"when": _when(_ts)' in read("src", "ginkassistant", "ui", "main_screen.py")
    assert "when: Math.round((s.updated || 0) * 1000)" in read("webapp", "bridge.js")
    settings = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "action: 'people_open'" in settings and "if (name === 'people_open') { closeSettings();" in settings
    assert "sidebar > People" not in settings and ".side-foot { cursor: pointer; border-radius: 0; }" not in settings


# ---------------------------------------------------------------- sources: the server
@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._ICON_CACHE.clear(); b._ICON_ASKS.clear()
    return b, TestClient(b.app)


def test_source_logos_come_from_gink_and_are_safe(server, monkeypatch):
    b, c = server
    asked = []

    async def fake_fetch(host):
        asked.append(host)
        return ("image/png", PNG) if host != "nologo.example" else ("", b"")
    monkeypatch.setattr(b, "_fetch_icon", fake_fetch)
    r = c.get("/icon/WWW.CENA.sn")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert "max-age=604800" in r.headers["cache-control"] and r.headers["access-control-allow-origin"] == "*"
    assert r.headers["content-security-policy"] == "default-src 'none'" and r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/icon/cena.sn").status_code == 200 and asked == ["cena.sn"]          # cached: fetched once
    assert c.get("/icon/nologo.example").status_code == 404
    for bad in ("localhost", "127.0.0.1", "10.0.0.1", "a..b", "-x.com", "x_y.com", "%2E%2E", "evil.com%2F..%2F"):
        assert c.get("/icon/" + bad).status_code == 404, bad
    for i in range(130):                                                                 # one device: 120 new ones per 10 minutes
        last = c.get(f"/icon/site{i}.example")
    assert last.status_code == 429


def test_only_real_images_are_served(monkeypatch):
    from ginkassistant.services import backend_server as b
    assert b._icon_kind(PNG) == "image/png" and b._icon_kind(b"\x00\x00\x01\x00rest") == "image/x-icon"
    assert b._icon_kind(b"<svg onload=alert(1)>") == "" and b._icon_kind(b"<html>") == ""

    class Resp:
        def __init__(self, status, content): self.status_code, self.content = status, content

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            if "google" in url:
                return Resp(200, b"<svg xmlns='http://www.w3.org/2000/svg'/>")              # not an image we serve
            return Resp(200, PNG)
    import httpx
    import asyncio
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert asyncio.run(b._fetch_icon("cena.sn")) == ("image/png", PNG)                    # the next service had a real one


def test_official_sources_first_with_their_logos(monkeypatch):
    from ginkassistant.services import backend_server as b
    assert b._is_official("https://www.cena.sn/elections") and b._is_official("https://www.ansd.sn/x")
    assert not b._is_official("https://electionstracker.com/senegal") and not b._is_official("https://en.wikipedia.org/wiki/X")
    assert "Find the OFFICIAL source first" in b._SEARCH_NOTE and "electoral commission" in b._SEARCH_NOTE
    monkeypatch.setenv("GINK_PUBLIC_URL", "https://gink.example")
    data = {"choices": [{"message": {"content": "Answer.", "executed_tools": [{"search_results": {"results": [
        {"url": "https://electionstracker.com/sn", "title": "Elections Tracker"},
        {"url": "https://www.cena.sn/elections", "title": "CENA"}]}}]}}]}
    b._tidy_search_answer(data)
    assert data["sources"][0] == {"title": "CENA", "url": "https://www.cena.sn/elections", "official": True,
                                  "icon": "https://gink.example/icon/cena.sn"}
    assert data["sources"][1]["official"] is False
    assert "- [CENA](https://www.cena.sn/elections) · official" in data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------- sources + People in a real browser
def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


ANSWER = ("<p>The next national vote is in 2027.</p><p><strong>Sources</strong></p><ul>"
          "<li><a href=\"https://www.cena.sn/elections\">CENA</a> · official</li>"
          "<li><a href=\"https://en.wikipedia.org/wiki/X\">Wikipedia</a></li>"
          "<li><a href=\"https://nologo.example/x\">No logo</a></li></ul>")


@pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")
def test_sources_button_opens_with_real_logos_and_people_works_by_itself(tmp_path):
    (tmp_path / "p.html").write_text(_page(), encoding="utf-8")
    (tmp_path / "icon").mkdir()
    for host in ("cena.sn", "en.wikipedia.org"):
        (tmp_path / "icon" / host).write_bytes(PNG)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
        def guess_type(self, path): return "image/png" if "/icon/" in str(path) else super().guess_type(path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with _browser()() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"no Chromium here ({type(exc).__name__})")
            page = browser.new_page()
            page.goto(base + "/p.html")
            page.evaluate("(b) => { window.__ev = []; window.ginkEmit = function (t, v) { window.__ev.push([t, v]); }; window.GINK_ICONS = b; }", base)
            page.evaluate("(a) => { hideWelcome(); addUserMessage('When is the election?'); addAssistantMessage('a1'); finalizeMessage('a1', a); }", ANSWER)
            page.wait_for_function("() => document.querySelectorAll('.gsrc .stack span.logo').length === 2", timeout=10000)
            stack = page.evaluate("() => [...document.querySelectorAll('.gsrc .stack span')].map(s => [s.className, s.querySelector('b').textContent])")
            assert stack == [["logo", "C"], ["logo", "E"], ["", "N"]]                     # real logos; a letter when a site has none
            assert page.evaluate("() => !!document.querySelector('.gsrc .stack .ok')")    # the first source is official
            page.click(".gsrc")                                                           # it opens now
            page.wait_for_timeout(200)
            opened = page.evaluate("""() => { const p = document.querySelector('.gsources');
                return {hidden: p.hidden, rows: [...p.querySelectorAll('a')].map(a => [a.querySelector('.st b').textContent, !!a.querySelector('.off'),
                        a.querySelector('.si').classList.contains('logo')]), expanded: document.querySelector('.gsrc').getAttribute('aria-expanded')}; }""")
            assert opened == {"hidden": False, "expanded": "true",
                              "rows": [["CENA", True, True], ["Wikipedia", False, True], ["No logo", False, False]]}
            page.click(".gsrc"); page.wait_for_timeout(100)
            assert page.evaluate("() => document.querySelector('.gsources').hidden")
            # the day groups in the sidebar
            now = int(time.time() * 1000)
            page.evaluate("""(n) => setSessions([{id: 'p', title: 'Pinned one', pinned: true, when: n - 9e8},
                {id: 'a', title: 'Today one', current: true, when: n}, {id: 'b', title: 'Old one', when: n - 3 * 864e5}])""", now)
            assert page.evaluate("() => [...document.querySelectorAll('.recents-head')].map(h => h.textContent)") == \
                ["Pinned", "Today", "Previous 7 days"]
            # People without a button: asking opens it; a shared photo while it's off -> one offer, once
            assert page.evaluate("() => peopleIntercept('show my people')") is True
            assert page.evaluate("() => !!document.getElementById('people-back')")
            page.evaluate("() => document.getElementById('people-back').remove()")
            assert page.evaluate("() => peopleIntercept('who is in my photos?')") is True
            page.evaluate("() => document.getElementById('people-back').remove()")
            assert page.evaluate("() => peopleIntercept('show me photos of the Eiffel Tower')") is False   # that's for the AI
            photo = "data:image/png;base64," + base64.b64encode(PNG).decode()
            page.evaluate("() => { try { localStorage.removeItem('gink-people-offered'); } catch (e) {} }")
            page.evaluate("(d) => peoplePending([d])", photo)
            assert page.evaluate("() => !!document.querySelector('.gnote[data-id=\"people-offer\"]')")
            page.evaluate("() => ginkDismiss('people-offer')"); page.wait_for_timeout(400)
            page.evaluate("(d) => peoplePending([d])", photo)
            assert not page.evaluate("() => !!document.querySelector('.gnote[data-id=\"people-offer\"]')")  # once
            page.evaluate("() => { PEOPLE.queue = []; PEOPLE.busy = false; peopleNext = function () {}; peopleSetOn(true); }")
            assert page.evaluate("() => PEOPLE.queue.length") == 1                        # a yes groups the photo just shared
            page.evaluate("() => { setCareMode(true); peopleSetOn(false); PEOPLE.queue = []; }")
            page.evaluate("(d) => peoplePending([d])", photo)
            assert page.evaluate("() => PEOPLE_PENDING.list.length") == 0                 # a healthcare workspace: nothing kept
            browser.close()
    finally:
        server.shutdown()


# ---------------------------------------------------------------- developers: the SDKs
def test_python_sdk_gives_sources_with_logos():
    import httpx
    import gink
    text = ("Answer.\n\n**Sources**\n- [Elections Tracker](https://electionstracker.com/sn)\n"
            "- [CENA](https://www.cena.sn/x) · official")
    assert [s["host"] for s in gink.sources(text, "https://gink.example/v1")] == ["cena.sn", "electionstracker.com"]
    assert gink.sources(text, "https://gink.example/v1")[0]["icon"] == "https://gink.example/icon/cena.sn"

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}],
                                         "sources": [{"url": "https://www.cena.sn/x", "official": True, "icon": "https://s/icon/cena.sn"}]})
    client = gink.Client(api_key="k", base_url="https://gink.example/v1", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.search("When?") == text                                                 # unchanged by default
    found = client.search("When?", with_sources=True)
    assert found["answer"] == text and found["sources"][0] == {"title": "CENA", "url": "https://www.cena.sn/x", "host": "cena.sn",
                                                                 "official": True, "icon": "https://s/icon/cena.sn"}


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node 18+")
def test_js_sdk_gives_sources_with_logos(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text("""
import { sources, Gink } from %s;
const t = "A.\\n\\n**Sources**\\n- [Tracker](https://electionstracker.com/sn)\\n- [CENA](https://www.cena.sn/x) \\u00b7 official";
const s = sources(t, "https://gink.example/v1");
if (s[0].host !== "cena.sn" || !s[0].official || s[0].icon !== "https://gink.example/icon/cena.sn") throw new Error(JSON.stringify(s));
const g = new Gink({ apiKey: "k", fetch: async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: t } }] }) }) });
if (await g.search("q") !== t) throw new Error("plain search changed");
const r = await g.search("q", { withSources: true });
if (r.answer !== t || r.sources.length !== 2 || r.sources[1].host !== "electionstracker.com") throw new Error(JSON.stringify(r));
console.log("ok");
""" % json.dumps(os.path.abspath(os.path.join(ROOT, "sdk", "js", "index.js"))), encoding="utf-8")
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    types_ = read("sdk", "js", "index.d.ts")
    assert "export interface Source { title: string; url: string; host: string; official: boolean; icon: string }" in types_
