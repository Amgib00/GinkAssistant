"""The owner's requests: Apple-style notifications everywhere, a premium Workspace, and "Hey Gink" that keeps
working by itself; storage problems no longer alarm people."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_one_notification_style_for_everything():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert "function ginkNotify(o)" in html and "backdrop-filter: blur(28px) saturate(180%)" in html
    assert "ginkNotify({id: 'status'" in html and "ginkNotify({id: 'policy'" in html        # status + policy notices
    assert "ginkNotify({id: 'update'" in html and "ginkNotify({id: 'settings'" in html      # update offer + Settings
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "await web_chat.notify(item.kind.capitalize(), item.title" in main            # reminders: a card, not a dialog
    assert 'kind == "item_done"' in main and 'kind == "item_snooze"' in main and "display notification" in main
    for f in ("genie.html", "console.html"):
        assert "backdrop-filter:blur(28px)" in read("src", "ginkassistant", "services", "web_app", f), f


def test_status_keeps_storage_out_of_peoples_notifications(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "BREVO_API_KEY"):
        monkeypatch.setenv(k, "x")
    monkeypatch.delenv("GINK_STATUS_MESSAGE", raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._upstream_fails.clear()
    monkeypatch.setattr(b, "_storage_status", lambda: {"ok": False, "mode": "temporary"})
    st = TestClient(b.app).get("/status").json()
    assert st["status"] == "ok" and st["components"]["storage"] == "degraded" and "saving files" not in st["message"]


def test_workspace_page_is_the_new_design():
    from ginkassistant.ui.workspace_page import PAGE
    for part in ('id="cmd"', 'class="cards"', 'class="seg"', "function setData(d)", "All clear", "Overdue",
                 "prefers-color-scheme: dark", "@media (max-width: 640px)"):
        assert part in PAGE or part in read("src", "ginkassistant", "ui", "tasks_screen.py"), part


def test_hey_gink_hears_more_and_comes_back_by_itself():
    from ginkassistant.services import wake_word as w
    for said in ("hey gin", "hey jinx", "hey ink", "hey king", "hey ginkgo", "ginkgo"):
        assert w.matches(said), said
    for not_wake in ("ink jet printer", "the king of the hill", "i like gin"):
        assert not w.matches(not_wake), not_wake
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "async def wake_watchdog():" in main and "asyncio.create_task(wake_watchdog())" in main
