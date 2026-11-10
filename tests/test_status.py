"""Is Gink working right now? /status from recent failures and what's set up; shown across the suite."""
import os, sys, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "BREVO_API_KEY"):
        monkeypatch.setenv(k, "x")
    monkeypatch.delenv("GINK_STATUS_MESSAGE", raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._upstream_fails.clear()
    return b, TestClient(b.app)


def test_ok_degraded_down_and_notice(srv, monkeypatch):
    b, c = srv
    assert c.get("/status").json()["status"] == "ok"
    for _ in range(3):
        b._ai_error(502, "The image service had a problem.", "upstream")
    st = c.get("/status").json()
    assert st["status"] == "degraded" and st["components"]["images"] == "degraded" and "image making" in st["message"]
    for _ in range(15):
        b._ai_error(502, "The AI service didn't answer.", "upstream")
    assert c.get("/status").json()["status"] == "down"
    b._upstream_fails[:] = [(time.time() - 3600, "chat")] * 20                  # an hour ago: forgotten
    assert c.get("/status").json()["status"] == "ok"
    monkeypatch.setenv("GINK_STATUS_MESSAGE", "Planned maintenance tonight 22:00-22:30 UTC.")
    st = c.get("/status").json()
    assert st["status"] == "notice" and st["message"].startswith("Planned maintenance")
    monkeypatch.delenv("GINK_STATUS_MESSAGE")
    monkeypatch.delenv("GROQ_API_KEY")
    assert c.get("/status").json()["status"] == "down"                          # not set up


def test_every_surface_shows_it(srv, monkeypatch, capsys):
    b, c = srv
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    main = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "main_screen.py"), encoding="utf-8").read()
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "function statusBar(" in page and "check_status()" in main and "checkStatus();" in bridge
    for f in ("genie.html", "console.html"):
        assert 'fetch("/status")' in open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", f), encoding="utf-8").read()
    from gink import Client
    assert Client(api_key="k", base_url="http://testserver/v1", http=c).status()["status"] == "ok"
    from gink_cli import main as m
    import httpx
    monkeypatch.setattr(m, "settings", lambda: ("", "https://x/v1"))
    monkeypatch.setattr(httpx, "get", lambda url, timeout=15: types.SimpleNamespace(json=lambda: c.get("/status").json()))
    assert m.main(["status"]) == 0 and "working normally" in capsys.readouterr().out
    js = open(os.path.join(ROOT, "sdk", "js", "index.js"), encoding="utf-8").read()
    assert "async status()" in js
