"""Settings window behaviour, account deletion, export, payment history."""
import asyncio, json, os, sys, time
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("GINK_SUPPORT_EMAIL", "help@gink.app")
    monkeypatch.setenv("GINK_PRIVACY_URL", "https://gink.app/privacy")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    return b, TestClient(b.app)


def test_delete_account_removes_everything_and_kills_old_tokens(server):
    b, c = server
    tok = b._token_response("ib@x.co", "Ibrahim")["token"]
    h = {"Authorization": "Bearer " + tok}
    c.post("/sync", json={"since": 0, "push": {"memories": [{"id": "m1", "updated": time.time(), "payload": {"text": "x"}}]}}, headers=h)
    with b._db_lock:
        con = b._billing_db()
        con.execute("INSERT INTO payments (reference, email, provider, plan, method, amount, currency, status, created, updated)"
                    " VALUES ('GINK1','ib@x.co','cinetpay','pro_1m','wave',3000,'XOF','success',?,?)", (time.time(), time.time()))
        con.commit(); con.close()
    assert c.get("/billing/history", headers=h).json()["payments"][0]["display"] == "3\u202f000 FCFA"
    assert c.post("/account/delete", json={"confirm": "yes"}, headers=h).status_code == 422     # must type DELETE
    assert c.post("/account/delete", json={"confirm": "DELETE"}, headers=h).json() == {"deleted": True}
    assert c.post("/sync", json={"since": 0, "push": {}}, headers=h).status_code == 401      # old token is dead
    with b._db_lock:
        con = b._billing_db()
        assert con.execute("SELECT COUNT(*) FROM users WHERE email='ib@x.co'").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM sync_docs WHERE email='ib@x.co'").fetchone()[0] == 0
        pay = con.execute("SELECT email FROM payments WHERE reference='GINK1'").fetchone()[0]
        con.close()
    assert pay.startswith("deleted:") and "ib@x.co" not in pay                        # kept for accounting, anonymised
    time.sleep(0.01)
    fresh = b._token_response("ib@x.co", "Ibrahim")["token"]                           # signing up again works
    assert c.get("/billing/history", headers={"Authorization": "Bearer " + fresh}).status_code == 200
    info = c.get("/info").json()
    assert info["support_email"] == "help@gink.app" and info["privacy_url"] == "https://gink.app/privacy"


def test_export_contains_everything(tmp_path):
    from ginkassistant.services import data_export
    from ginkassistant.services.actions import TaskStore
    from ginkassistant.services.memory import MemoryStore
    from test_sync_attach_memory_briefing import _Hist
    h = _Hist(tmp_path / "h.db"); h.save_message("s1", "user", "hello"); h.save_message("s1", "assistant", "hi!")
    st = TaskStore(str(tmp_path / "t.db")); t = st.add("task", "Revise"); st.add("task", "Notes", parent_id=t.id)
    mem = MemoryStore(str(tmp_path / "m.db")); mem.add("Lives in Dakar")
    data = data_export.build_export("ib@x.co", h, st, mem, {"theme": "dark", "briefing_last_date": "x"})
    path = data_export.write_export(str(tmp_path / data_export.export_filename()), data)
    back = json.loads(open(path, encoding="utf-8").read())
    assert back["chats"][0]["messages"][1]["content"] == "hi!" and back["workspace"][0]["steps"][0]["title"] == "Notes"
    assert back["memories"] == ["Lives in Dakar"] and back["settings"] == {"theme": "dark"}


def test_settings_change_real_behaviour(tmp_path, monkeypatch):
    import toga
    from ginkassistant.services import prefs, voice_bridge
    from ginkassistant.services.actions import DeviceActions, ReminderScheduler, TaskStore, ToolRunner, TaskAgent
    from ginkassistant.services.memory import MemoryStore
    from ginkassistant.ui.settings_controller import SettingsController
    app = toga.App("t", "org.t")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app.task_store = TaskStore(str(tmp_path / "t.db")); app.memory = MemoryStore(str(tmp_path / "m.db"))
    app.task_runner = ToolRunner(app.task_store, DeviceActions(str(tmp_path)), memory=app.memory)
    app.task_scheduler = ReminderScheduler(app.task_store)
    class St: base_url = "http://t"
    app.state = St()
    app.memory.add("Lives in Dakar")

    class Brain:
        preferred_model = "llama-3.3-70b-versatile"; memory_provider = None; reply_language_note = None; history = None
    class Web:
        def __init__(self): self.calls = []
        async def set_settings_state(self, st): self.calls.append(("state", st))
        async def settings_toast(self, t, k="ok"): self.calls.append(("toast", t, k))
        async def set_appearance(self, *a): self.calls.append(("appearance", a))
        async def set_keyboard_prefs(self, p): self.__dict__.setdefault('kb', []).append(p)
        async def set_voice_config(self, c): self.__dict__.setdefault('vc', []).append(c)
    class Audio: voice_key = None
    web, brain, voice = Web(), Brain(), {"value": "Female (Jenny)"}
    pushed = []
    async def push_models(): pushed.append(1)
    ctl = SettingsController(app, web, brain, voice, Audio(), email="ib@x.co", display_name="Ibrahim",
                             models_fn=lambda: [], push_models=push_models, open_pro=lambda: None, on_log_out=lambda: None,
                             refresh_sidebar=lambda: None, clear_all_chats=lambda: 0, brief_now=None, sync_fn=None,
                             open_url=None)
    run = asyncio.run
    assert "Lives in Dakar" in brain.memory_provider()
    run(ctl.on_setting("use_memory", False))
    assert brain.memory_provider() == "" and app.task_runner.use_memory is False
    run(ctl.on_setting("web_search", False)); run(ctl.on_setting("video_suggestions", False))
    assert app.task_runner.disabled_tools == {"web_search", "find_video"}
    run(ctl.on_setting("reply_language", "fr"))
    assert "Always reply in French" in brain.reply_language_note()
    run(ctl.on_setting("reply_language", "klingon"))                     # ignored
    assert prefs.load(app)["reply_language"] == "fr"
    run(ctl.on_setting("voice_speed", "fast"))
    assert voice_bridge.speed[0] == "fast"
    run(ctl.on_setting("notify_reminders", False))
    assert app.task_scheduler.notifications_enabled() is False
    run(ctl.on_setting("theme", "dark"))
    assert ("appearance", ("dark", "sans", "system")) in web.calls
    run(ctl.on_setting("model", "openai/gpt-oss-120b"))
    assert brain.preferred_model == "openai/gpt-oss-120b" and pushed
    run(ctl.on_action("save_briefing_time", "7.05"))
    assert prefs.load(app)["briefing_time"] == "07:05"
    run(ctl.on_action("save_briefing_time", "25:00"))
    assert web.calls[-1] == ("toast", "Use a 24-hour time like 07:30.", "err")
    run(ctl.on_action("forget_memory", app.memory.list()[0]["uid"]))
    assert app.memory.list() == []
    # the agent really hides switched-off tools from the AI
    sent = {}
    agent = TaskAgent(app.task_runner, api_key="k")
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": "ok"}}]}
    class H:
        async def post(self, url, json=None, headers=None): sent.update(json); return R()
    agent._http = H()
    run(agent.run("tell me something interesting"))
    names = [t["function"]["name"] for t in sent["tools"]]
    assert "web_search" not in names and "find_video" not in names and "set_alarm" in names
    assert "Always reply in French" in sent["messages"][0]["content"]


def test_settings_styles_and_markup_are_really_on_the_page():
    from ginkassistant.ui import web_chat_view as w
    page = w._build_page_html("Hi", "")
    style = page[page.index("<style>"):page.index("</style>")]
    for rule in ("#settings-back", ".s-nav", ".sw input:checked", "body.theme-dark", "#acct-menu"):
        assert rule in style, rule                                  # CSS inside the <style> block
    assert page.count('id="settings-back"') == 1 and "function openSettings" in page
