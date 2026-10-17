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
