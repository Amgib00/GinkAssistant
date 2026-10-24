"""Spinner labels, chat rename/pin (+sync), feedback (no message text stored)."""
import asyncio, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))


def test_feedback_stores_no_text_and_summary_is_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("GINK_ADMIN_KEY", "owner-secret")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@x.co", "I")["token"]}
    assert c.post("/feedback", json={"rating": "down", "reason": "wrong", "model": "m", "chars": 120,
                                     "text": "my secret question"}, headers=h).status_code == 200
    assert c.post("/feedback", json={"rating": "meh"}, headers=h).status_code == 422
    assert c.post("/feedback", json={"rating": "up", "reason": "<script>"}, headers=h).status_code == 422
    assert c.post("/feedback", json={"rating": "up"}).status_code == 401
    with b._db_lock:
        con = b._feedback_db(); rows = con.execute("SELECT * FROM feedback").fetchall(); con.close()
    assert len(rows) == 1 and "secret" not in json.dumps(rows) and "ib@x.co" not in json.dumps(rows)
    assert c.get("/feedback/summary").status_code == 403
    s = c.get("/feedback/summary", headers={"x-admin-key": "owner-secret"}).json()["last_30_days"]
    assert s == [{"model": "m", "rating": "down", "reason": "wrong", "count": 1}]


def test_rename_and_pin_survive_new_messages_and_sync(tmp_path):
    from test_sync_attach_memory_briefing import _Hist
    h = _Hist(tmp_path / "a.db")
    h.save_message("s1", "user", "plan my exams")
    h.set_title("s1", "Exam plan")
    h.set_pinned("s1", True)
    h.save_message("s1", "assistant", "Here's a plan")          # must not wipe title/pin
    assert h.get_meta()["s1"] == {"title": "Exam plan", "pinned": True, "archived": False}
    other = _Hist(tmp_path / "b.db")
    other.apply_remote(h.changes_since(0))
    assert other.get_meta()["s1"] == {"title": "Exam plan", "pinned": True, "archived": False}
    h.clear_history("s1")
    assert "s1" not in h.get_meta()


def test_agent_answer_shows_spinner_steps_and_events(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp, main_screen, ActionResult
    import ginkassistant.app as app_mod
    from ginkassistant.ui import web_chat_view
    from ginkassistant.services import api_client
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    app.session_token = "tok"
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    async def fake_run(self, text, history=None, on_status=None, **agent_mode):
        await on_status("Checking the weather\u2026")
        from ginkassistant.services.actions.agent import AgentReply
        return AgentReply("It's sunny.", [{"tool": "get_weather", "args": {}, "result": {"ok": True}}], used_ai=True)
    monkeypatch.setattr(type(app.task_agent), "run", fake_run)
    sent = []
    async def fake_feedback(self, token, rating, reason="", model="", chars=0): sent.append((rating, reason, chars))
    monkeypatch.setattr(api_client.ApiClient, "feedback", fake_feedback)
    queued = [[{"type": "send", "value": "what's the weather like in Dakar?"}], [], [], [],
              [{"type": "feedback", "value": {"rating": "down", "reason": "too_long", "chars": 11}}], []]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(30):
            await asyncio.sleep(0.05)
        sid = list(main_screen_sessions(app))[0]
        queued.extend([[{"type": "rename_session", "value": {"id": sid, "title": "Dakar weather"}}],
                       [{"type": "pin_session", "value": {"id": sid, "pinned": True}}]])
        for _ in range(12):
            await asyncio.sleep(0.05)
        app._main_screen_token = None
        app.task_scheduler.stop()
        return sid
    def main_screen_sessions(app):
        from ginkassistant.services.history import HistoryStore
        return HistoryStore(app).get_all_sessions().keys()
    sid = asyncio.run(go())
    starts = [s for s in js if s.startswith("addAssistantMessage(")]
    assert len(starts) == 1 and "Thinking" in starts[0]                       # one row, labelled
    assert any(s.startswith("setSpinLabel(") and "Checking the weather" in s for s in js)
    assert any(s.startswith("finalizeMessage(") and "sunny" in s for s in js)
    assert sent == [("down", "too_long", 11)]
    from ginkassistant.services.history import HistoryStore
    assert HistoryStore(app).get_meta()[sid] == {"title": "Dakar weather", "pinned": True, "archived": False}
    last = [s for s in js if s.startswith("setSessions(")][-1]
    assert '"title": "Dakar weather"' in last and '"pinned": true' in last


def test_step_thumbnails_for_made_files(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp, main_screen
    import ginkassistant.app as app_mod
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    async def fake_run(self, text, history=None, on_status=None, **agent_mode):
        from ginkassistant.services.actions.agent import AgentReply
        await on_status("Making your file\u2026")
        res = self.runner._t_create_file("pdf", "Week plan", "# Week plan\n- Monday: revise")
        return AgentReply("Here's your plan:\n\n" + res["message"], [{"tool": "create_file", "args": {}, "result": res}], used_ai=True)
    monkeypatch.setattr(type(app.task_agent), "run", fake_run)
    queued = [[{"type": "send", "value": "make my week plan a pdf"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(30):
            await asyncio.sleep(0.05)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    media = [s for s in js if s.startswith("setStepMedia(")]
    assert media and "Making your file" in media[0] and '"kind": "file"' in media[0] and '"text": "PDF"' in media[0]
    fin = [s for s in js if s.startswith("finalizeMessage(")][-1]
    assert js.index(media[0]) < js.index(fin)                       # thumbnails arrive before the summary is built
    assert "gink://file/Week%20plan.pdf" in fin
