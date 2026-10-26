"""Gink on the web: the built page is current, /app is served safely, /render is protected and safe."""
import os, sys
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "tools"))
import pytest


def test_built_web_app_is_up_to_date():
    """Fails if webapp/* or the chat page changed without rebuilding. Code-highlight colours
    come from the installed pygments version, so those lines are ignored in the comparison."""
    import re, build_web_app
    strip = lambda h: re.sub(r"^\.codehilite[^\n]*\n", "", h, flags=re.M)
    built = open(build_web_app.OUT, encoding="utf-8").read()
    assert strip(built) == strip(build_web_app.build_html()), "run: python tools/build_web_app.py"
    assert open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read() in built


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    return b, c, {"Authorization": "Bearer " + b._token_response("ib@x.co", "Ib")["token"]}


def test_app_page_is_served_with_security_headers(client):
    b, c, h = client
    r = c.get("/app")
    assert r.status_code == 200 and "web-signin" in r.text and "ginkEmit" in r.text
    csp = r.headers["content-security-policy"]
    assert "connect-src 'self'" in csp and "frame-ancestors 'none'" in csp and r.headers["x-frame-options"] == "DENY"


def test_render_needs_sign_in_and_is_safe(client):
    b, c, h = client
    assert c.post("/render", json={"markdown": "x"}).status_code == 401
    r = c.post("/render", json={"markdown": "**hi** <script>alert(1)</script> [x](javascript:alert(1))"}, headers=h).json()["html"]
    assert "<strong>hi</strong>" in r and "<script" not in r and "javascript:" not in r
    batch = c.post("/render", json={"items": ["**a**", "`b`"]}, headers=h).json()["html"]
    assert len(batch) == 2 and "<strong>a</strong>" in batch[0]


def test_inactive_sign_in_forms_stay_hidden():
    """Regression: `.ws-card form {display:grid}` overrode the `hidden` attribute, so the
    Log in, Create account and code forms all showed at once on the live server."""
    css = open(os.path.join(ROOT, "webapp", "signin.html"), encoding="utf-8").read()
    assert ".ws-card form[hidden] { display: none; }" in css
    html = open(os.path.join(ROOT, "webapp", "signin.html"), encoding="utf-8").read()
    assert '<form id="ws-signup" hidden>' in html and '<form id="ws-code" hidden>' in html


def test_reading_attached_documents_for_the_web_app(client):
    import base64
    b, c, h = client
    as_url = lambda mime, raw: f"data:{mime};base64," + base64.b64encode(raw).decode()
    assert c.post("/attachments/read", json={"name": "a.txt", "data": as_url("text/plain", b"hi")}).status_code == 401
    r = c.post("/attachments/read", headers=h, json={"name": "notes.txt", "data": as_url("text/plain", b"Launch on Friday.")})
    assert r.status_code == 200 and r.json()["text"].strip() == "Launch on Friday."
    from fpdf import FPDF
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Helvetica", size=12); pdf.cell(0, 10, "Revenue grew 40 percent.")
    r = c.post("/attachments/read", headers=h, json={"name": "report.pdf", "data": as_url("application/pdf", bytes(pdf.output()))})
    assert r.status_code == 200 and "Revenue grew 40 percent." in r.json()["text"]
    r = c.post("/attachments/read", headers=h, json={"name": "x.exe", "data": as_url("application/octet-stream", b"MZ")})
    assert r.status_code == 422 and "can't read" in r.json()["detail"]
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.new("RGB", (8, 8)).save(buf, "PNG")
    r = c.post("/attachments/read", headers=h, json={"name": "p.png", "data": as_url("image/png", buf.getvalue())})
    assert r.status_code == 422                                              # photos stay in the browser


def test_full_sign_in_page_is_served_safely(client):
    b, c, h = client
    for path in ("/login", "/signup", "/forgot"):
        r = c.get(path)
        assert r.status_code == 200 and "connect-src 'self'" in r.headers["content-security-policy"]
        for view in ('id="v-login"', 'id="v-signup"', 'id="v-code"', 'id="v-forgot"', 'id="v-twofa"', "li-remember", "su-agree"):
            assert view in r.text, (path, view)
    page = c.get("/login").text
    assert "/^\\/(?!\\/)[^\\\\\\s]*$/" in page                     # next= only to Gink's own pages (no //evil.example)
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert 'location.replace("/login?next="' in bridge and 'sessionStorage.getItem("gink_token")' in bridge


def test_no_route_is_shadowed_by_an_earlier_pattern():
    """/auth/{provider}/begin once caught /auth/passkey/begin: an earlier route with a {parameter}
    must never match a later fixed route with the same method (it would never be reached)."""
    import re
    from ginkassistant.services import backend_server as b
    routes = [(r.path, m) for r in b.app.routes for m in (getattr(r, "methods", None) or set()) if m not in ("HEAD", "OPTIONS")]
    shadowed = []
    for i, (path, method) in enumerate(routes):
        for earlier, m2 in routes[:i]:
            if m2 != method or "{" not in earlier or earlier == path:
                continue
            pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", earlier.replace(".", r"\.")) + "$"
            if re.match(pattern, path):
                shadowed.append(f"{method} {path} is caught by {earlier}")
    assert shadowed == [], shadowed


def test_the_shadow_check_itself_catches_the_old_bug():
    import re
    pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", "/auth/{provider}/begin") + "$"
    assert re.match(pattern, "/auth/passkey/begin") and not re.match(pattern, "/auth/passkey/signin/begin")


def test_no_server_function_is_defined_twice():
    """A second `_check_code` (phone) silently replaced the email one and froze email sign-up: Python
    keeps the last definition, and pyflakes stays quiet when the first one is used."""
    import ast, collections
    tree = ast.parse(open(os.path.join(ROOT, "src", "ginkassistant", "services", "backend_server.py"), encoding="utf-8").read())
    names = collections.Counter(n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert [n for n, c in names.items() if c > 1] == []


def test_old_chats_show_answers_without_waiting_for_the_server():
    """Opening an old chat showed every answer as "Thinking..." until /render answered -- forever when
    the (free-plan) server was slow. Answers must appear as text first, with a time limit on /render."""
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    i = bridge.index("function openSession(")
    body = bridge[i:bridge.index("\n  }\n", i)]
    assert body.index("setPlainText(a[0]") < body.index('api("/render"')          # text first, then formatting
    assert "Promise.race" in body and "10000" in body                             # never waits forever
    assert "Array.isArray(j.html)" in body and "W.current !== opened" in body     # no "undefined", no wrong chat


def test_website_follow_ups_change_that_website():
    """'good add more to it' after building a website went to the plain chat, which said it couldn't edit."""
    import re, json as _j
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    hint = re.search(r"var SITE_HINT_RE = /(.*)/i;", bridge).group(1).replace("\\\\", "\\")
    not_edit = re.search(r"var NOT_EDIT_RE = /(.*)/i;", bridge).group(1).replace("\\\\", "\\")
    is_edit = lambda t: bool(re.search(hint, t, re.I)) and not re.search(not_edit, t, re.I)
    for t in ("good add more to it", "make it blue", "add a photo gallery", "change the title to Gink Shop"):
        assert is_edit(t), t
    for t in ("thanks!", "how much does hosting it cost?", "ok", "what is a domain?"):
        assert not is_edit(t), t
    assert "siteFollowUp(s, text) ? makeSite(text, aid, true, s.site, s)" in bridge
    assert "never say you can't change their website" in bridge


def test_no_javascript_escapes_inside_html():
    """'\\u2026' in an HTML attribute shows literally ("explain app.js\\u2026") -- only JavaScript decodes it."""
    import re, glob
    for path in glob.glob(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "*.html")):
        if path.endswith("index.html"):
            continue                                     # built from webapp/, checked there
        html = open(path, encoding="utf-8").read()
        html = re.sub(r"<script>.*?</script>", "", html, flags=re.S)        # escapes are fine inside scripts
        assert not re.search(r"\\u[0-9a-fA-F]{4}", html), os.path.basename(path)


def test_docker_image_has_every_module_the_server_imports():
    """Render runs backend_server.py in Docker with only the files deploy/Dockerfile copies: a module the
    server imports but the image lacks would break the live server while every test here passes."""
    import re
    server = open(os.path.join(ROOT, "src", "ginkassistant", "services", "backend_server.py"), encoding="utf-8").read()
    docker = open(os.path.join(ROOT, "deploy", "Dockerfile"), encoding="utf-8").read()
    local = set(re.findall(r"from \.([a-z_]+) import", server)) | set(re.findall(r"^\s*import (billing_catalog)\b", server, re.M))
    copied = set(re.findall(r"COPY src/ginkassistant/services/([a-z_]+)\.py", docker))
    assert local and local <= copied, f"not in the Docker image: {sorted(local - copied)}"
    assert "COPY src/ginkassistant/services/web_app ./web_app" in docker
