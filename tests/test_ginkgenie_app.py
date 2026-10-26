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
    assert "data:image/png;base64" not in page[page.index('data-nav="genie"') - 50:page.index('data-nav="genie"') + 300]
    genie = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    for part in ("@keyframes genie-appear", "@keyframes genie-float", "@keyframes genie-spark", "prefers-reduced-motion: reduce",
                 'role="button" tabindex="0"', "Your wish is my command!", "Working my magic"):
        assert part in genie, part
