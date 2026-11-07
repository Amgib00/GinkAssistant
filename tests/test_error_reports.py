"""Problems are found without anyone reporting them: the apps, the web app and the server send what
broke (never chats), grouped on the owner dashboard; people can switch it off."""
import asyncio
import os
import sys
import types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "e.db"))
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 32)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._admin_failures.clear(); b._error_rate.clear()
    return b, TestClient(b.app)


FAKE_KEY = "gsk_" + "A" * 27                     # built here: a real-looking key in a file would stop publishing
STACK = '''Traceback (most recent call last):
  File "/app/ginkassistant/ui/main_screen.py", line 812, in handle_composer_event
    await answer(text)
  File "/app/ginkassistant/services/groq_worker.py", line 401, in ask
    raise ValueError(msg)
ValueError: bad reply for ib@example.com with token=abc123 key ''' + FAKE_KEY


def test_reports_are_grouped_and_scrubbed(srv):
    b, c = srv
    for v, plat in (("v0.1.110", "android"), ("v0.1.111", "android"), ("v0.1.111", "macos")):
        r = c.post("/errors", json={"kind": "ValueError", "message": "bad reply for ib@example.com token=abc123",
                                    "stack": STACK, "platform": plat, "version": v})
        assert r.json()["ok"] is True
    errs = c.get("/admin/errors", headers={"x-admin-key": "k" * 32}).json()["errors"]
    assert len(errs) == 1                                                        # one bug, one row
    e = errs[0]
    assert e["count"] == 3 and e["where"] == "services/groq_worker.py:ask" and e["platforms"] == "android,macos"
    assert e["versions"] == "v0.1.110,v0.1.111"
    text = str(e)
    assert "ib@example.com" not in text and "abc123" not in text and "gsk_AAAA" not in text
    assert c.get("/admin/errors").status_code == 403                            # owner only
    dash = c.get("/admin/dashboard", headers={"x-admin-key": "k" * 32})
    if dash.status_code == 200:
        assert dash.json()["app_errors"][0]["count"] == 3


def test_rate_limited(srv, monkeypatch):
    b, c = srv
    monkeypatch.setattr(b, "ERRORS_PER_HOUR", 2)
    assert [c.post("/errors", json={"kind": "E", "stack": "x"}).json()["ok"] for _ in range(3)] == [True, True, False]


def test_server_crashes_are_recorded(srv):
    b, c = srv
    from fastapi.testclient import TestClient

    @b.app.get("/__boom_for_test")
    def boom():
        raise RuntimeError("kaboom")
    with pytest.raises(RuntimeError):
        TestClient(b.app).get("/__boom_for_test")
    b.app.router.routes = [r for r in b.app.router.routes if getattr(r, "path", "") != "/__boom_for_test"]
    errs = c.get("/admin/errors", headers={"x-admin-key": "k" * 32}).json()["errors"]
    assert any(e["kind"] == "RuntimeError" and e["platforms"] == "server" for e in errs)


def test_app_reports_once_and_respects_the_setting(monkeypatch):
    from ginkassistant.services import error_reports as er
    sent, prefs_store = [], {"send_errors": True}
    monkeypatch.setattr(er, "_sent", set())
    monkeypatch.setitem(er._state, "count", 0)
    app = types.SimpleNamespace(state=types.SimpleNamespace(base_url="https://gink.example"), version="0.1.111")
    monkeypatch.setitem(er._state, "app", app)
    import ginkassistant.services.prefs as prefs
    monkeypatch.setattr(prefs, "load", lambda a: prefs_store)
    async def fake_send(data): sent.append(data)
    monkeypatch.setattr(er, "_send", fake_send)

    async def go():
        try:
            raise KeyError("model")
        except KeyError as exc:
            er.report(exc); er.report(exc)                                       # the same error: once
        await asyncio.sleep(0)
    asyncio.run(go())
    assert len(sent) == 1 and sent[0]["kind"] == "KeyError" and sent[0]["version"] == "0.1.111"
    assert "test_error_reports.py" in sent[0]["stack"]
    prefs_store["send_errors"] = False
    async def again():
        try:
            raise ZeroDivisionError("x")
        except ZeroDivisionError as exc:
            er.report(exc)
        await asyncio.sleep(0)
    asyncio.run(again())
    assert len(sent) == 1                                                        # switched off: nothing


def test_pieces_in_place():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    bridge = open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()
    admin = open(os.path.join(root, "src", "ginkassistant", "services", "web_app", "admin.html"), encoding="utf-8").read()
    assert "key: 'send_errors'" in page and 'addEventListener("unhandledrejection"' in bridge and 'id="apperrors"' in admin
