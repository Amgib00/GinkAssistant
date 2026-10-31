"""Gink Genie as its own app (src/ginkgenie) and its builds."""
import glob, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest
from ginkgenie import app as G

S = "https://gink-server.onrender.com"


def test_links_that_leave_the_app():
    assert not G.leaves_the_app(S + "/genie", S) and not G.leaves_the_app(S + "/login?next=/genie", S)
    assert G.leaves_the_app("https://github.com/login/oauth/authorize?x=1", S)          # GitHub: the real browser
    assert G.leaves_the_app(S + "/genie/p/key123/", S)                                 # previews too
    assert not G.leaves_the_app("about:blank", S) and not G.leaves_the_app("", S)
    assert G.leaves_the_app("https://gink-server.onrender.com.evil.example/x", S)       # look-alike hosts leave


def test_server_address(tmp_path, monkeypatch):
    monkeypatch.delenv("GINK_SERVER_URL", raising=False)
    assert G.server_url(None) == S
    (tmp_path / "server.txt").write_text("http://192.168.1.20:8000/\n")
    assert G.server_url(tmp_path) == "http://192.168.1.20:8000"
    monkeypatch.setenv("GINK_SERVER_URL", "ftp://nope")
    assert G.server_url(tmp_path) == S                                                  # only http(s)
    assert "&lt;b&gt;" in G.status_page("<b>", "x", False) and "retry" in G.status_page("t", "x", True)


def test_the_app_window_and_toolbar(monkeypatch):
    toga = pytest.importorskip("toga")
    monkeypatch.setattr(G.GinkGenie, "connect", lambda self: _noop())
    app = G.main()
    texts = [c.text for c in app.commands if getattr(getattr(c, "group", None), "text", "") == "Genie"]
    assert texts == ["Home", "Back", "Reload", "Open in browser"]
    assert app.formal_name == "Gink Genie" and app.app_id == "com.amgib.ginkgenie" and app.home == S + "/genie"
    assert app.web.user_agent == toga.WebView().user_agent + " " + G.APP_MARK            # added, never replacing it
    opened = []
    monkeypatch.setattr(G.webbrowser, "open", opened.append)
    assert app.navigating(app.web, url="https://github.com/login/oauth/authorize") is False and opened
    assert app.navigating(app.web, url=S + "/genie") is True


async def _noop():
    return None


def test_builds_name_their_app_and_genie_has_every_icon():
    wf = os.path.join(ROOT, ".github", "workflows")
    for name in ("macos.yml", "windows.yml", "linux.yml", "android.yml", "ios.yml"):
        for line in re.findall(r"briefcase (?:create|build|package) [^\n]*", open(os.path.join(wf, name)).read()):
            assert "-a ginkassistant" in line, (name, line)                             # Gink's builds: only Gink
    genie = open(os.path.join(wf, "genie.yml")).read()
    cmds = re.findall(r"briefcase (?:create|build|package) [^\n]*", genie)
    assert len(cmds) == 11 and all("-a ginkgenie" in c for c in cmds)
    yaml = pytest.importorskip("yaml")
    rel = yaml.safe_load(open(os.path.join(wf, "release.yml")))
    assert "genie" in rel["jobs"]["publish"]["needs"] and rel["jobs"]["genie"]["uses"].endswith("genie.yml")
    gink = {os.path.basename(p)[len("ginkassistant"):] for p in glob.glob(os.path.join(ROOT, "icons", "ginkassistant*"))}
    genie_icons = {os.path.basename(p)[len("ginkgenie"):] for p in glob.glob(os.path.join(ROOT, "icons", "ginkgenie*"))}
    assert gink == genie_icons and len(genie_icons) >= 45


def test_lamp_icon_and_living_genie():
    """The sidebar uses the drawn lamp (not the photo); the genie animates but stays still for reduced motion."""
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    assert page.count('<circle cx="13.2" cy="5.9" r="1.1" fill="currentColor" stroke="none"/>') == 2      # rail + list
    assert page.count('<g transform="matrix(-1 0 0 1 24 0)"><path d="M2 10.2') == 2                    # the lamp faces right
    assert "data:image/png;base64" not in page[page.index('data-nav="genie"') - 50:page.index('data-nav="genie"') + 300]
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for part in ("@keyframes genie-appear", "@keyframes genie-float", "@keyframes genie-spark", "prefers-reduced-motion: reduce",
                 'role="button" tabindex="0"', "Your wish is my command!", "Working my magic",
                 "transform-origin:50% 100%", "drop-shadow"):          # the full genie leans from its tail
        assert part in genie, part


def test_genie_page_commands_steps_and_files():
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    assert "Upload ZIP" not in genie and 'id="upload2" multiple' in genie and 'id="upload3" multiple' in genie
    for part in ('<h1>Start building with<br>Gink Genie</h1>', 'id="open-btn"', "function stepsBlock", "function runCommand", "/ask/continue",
                 "function addFiles", 'addEventListener("drop"', "Available: python FILE, pytest, node FILE, ls, cat FILE"):
        assert part in genie, part


def test_search_in_project_wiring():
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for part in ("function searchProject", "function openAtLine", 'e.shiftKey && e.key.toLowerCase() === "f"', "function goToFile"):
        assert part in genie, part


def test_editor_line_numbers_and_position():
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for part in ('id="gutter"', 'id="cursor"', "function gutter", "function cursorPos", '"Ln " + before.length'):
        assert part in genie, part
    # the numbers and the code must use the same font and line height, or they drift apart
    assert "font:13px/1.55 ui-monospace,Menlo,Consolas,monospace; user-select:none" in genie
    assert "font:13px/1.55 ui-monospace,Menlo,Consolas,monospace; white-space:pre" in genie


def test_phone_layout_wiring():
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for part in ("@media (max-width: 700px)", 'id="mtabs"', 'id="more"', "header .hb { display:none !important; }", "function tab(name)"):
        assert part in genie, part
    for bid in ("new", "preview", "download", "share", "github", "rename", "duplicate", "del"):    # every action reachable on phones
        assert re.search(r'<button class="[^"]* hb\b[^"]*" id="%s"' % bid, genie), bid



def test_studio_layout():
    """AI Studio-style: projects sidebar, the four buttons only in the "more" menu, Share + GitHub as icons."""
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for bid in ("preview", "download", "rename", "duplicate"):
        assert re.search(r'<button class="[^"]* dm[^"]*" id="%s"' % bid, genie), bid          # hidden from the header
    assert "header .brand, header #pick, header .dm { display:none !important; }" in genie
    for bid in ("share", "github"):
        m = re.search(r'<button class="([^"]*)" id="%s"[^>]*>(.*?)</button>' % bid, genie, re.S)
        assert " ic" in m.group(1) and m.group(2).lstrip().startswith("<svg"), bid             # icons, not words
    for part in ('id="side"', 'id="plist"', 'id="ctabs"', "function renderSide", "function dview", 'class="hero"', 'class="card big c1"'):
        assert part in genie, part


def test_preview_tab_and_no_stray_escapes():
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    assert 'sandbox="allow-scripts allow-forms allow-modals allow-popups"' in genie and "allow-same-origin" not in genie
    assert 'data-v="preview"' in genie and "function reloadPreview" in genie and "previewChanged();" in genie
    html_only = re.sub(r"<script>.*?</script>", "", genie, flags=re.S)
    assert not re.findall(r"\\u[0-9a-fA-F]{4}", html_only), "JavaScript escapes show up as text in HTML"


def test_preview_may_only_be_framed_by_gink(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "pf.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    pid = c.post("/genie/projects", headers=h, json={"name": "P"}).json()["project"]["id"]
    c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "index.html", "content": "<h1>x</h1>"})
    url = c.get(f"/genie/projects/{pid}", headers=h).json()["project"]["preview_url"].replace("http://testserver", "")
    csp = c.get(url).headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp and "sandbox allow-scripts" in csp
