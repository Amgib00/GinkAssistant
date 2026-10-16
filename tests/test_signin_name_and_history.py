"""Sign-in name -> profile (per account), and automatic history (save on send, titles, drafts)."""
import asyncio, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import toga


def _app(tmp_path, monkeypatch):
    app = toga.App("t", "org.t")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    return app


def test_signin_name_fills_profile_without_overwriting(tmp_path, monkeypatch):
    from ginkassistant.services.profile import ProfileStore, profile_path
    from ginkassistant.services.api_client import Session
    from ginkassistant.ui.login_screen import LoginController
    app = _app(tmp_path, monkeypatch)
    ctl = LoginController.__new__(LoginController)
    ctl.app, ctl.oauth, ctl.on_success = app, {"state": None}, lambda e: None
    ctl.finish(Session(token="t", email="ib@x.co", name="IBRAHIM A KARGBO"), remember=False)
    p = ProfileStore(profile_path(app, "ib@x.co"))
    assert p.get()["full_name"] == "Ibrahim A Kargbo" and p.get()["nickname"] == "Ibrahim"
    assert p.get()["updated"] == 1.0                          # stamped "older than any real edit"
    p.update(nickname="Ibra")                                  # the user's own choice...
    ctl.finish(Session(token="t", email="ib@x.co", name="Ibrahim Kargbo"), remember=False)
    assert ProfileStore(profile_path(app, "ib@x.co")).get()["nickname"] == "Ibra"        # ...is kept
    # a second person on the same device gets their own profile
    ctl.finish(Session(token="t", email="awa@x.co", name="Awa Diop"), remember=False)
    assert ProfileStore(profile_path(app, "awa@x.co")).call_name() == "Awa"
    assert ProfileStore(profile_path(app, "ib@x.co")).call_name() == "Ibra"
    assert profile_path(app, "ib@x.co") != profile_path(app, "awa@x.co")
    # odd provider names are ignored, never shown as a name
    ctl.finish(Session(token="t", email="x@x.co", name="x@x.co"), remember=False)
    assert ProfileStore(profile_path(app, "x@x.co")).get().get("full_name", "") == ""


def test_synced_profile_beats_signin_guess(tmp_path, monkeypatch):
    from ginkassistant.services.profile import ProfileStore, profile_path
    app = _app(tmp_path, monkeypatch)
    new_device = ProfileStore(profile_path(app, "ib@x.co"))
    new_device.seed_from_signin("Ibrahim Kargbo")
    other = ProfileStore(str(tmp_path / "other.json"))
    other.update(full_name="Ibrahim A Kargbo", nickname="Ibra")   # chosen earlier on the phone
    assert new_device.apply_remote(other.changes_since(0)) == 1
    assert new_device.call_name() == "Ibra"


def test_legacy_profile_moves_to_first_account(tmp_path, monkeypatch):
    from ginkassistant.services.profile import ProfileStore, profile_path
    app = _app(tmp_path, monkeypatch)
    (tmp_path / "profile.json").write_text(json.dumps({"full_name": "Ibrahim A Kargbo", "nickname": "Ibrahim", "updated": 5}))
    assert ProfileStore(profile_path(app, "ib@x.co")).call_name() == "Ibrahim"
    assert not (tmp_path / "profile.json").exists()
    assert ProfileStore(profile_path(app, "someone@else.co")).call_name() == ""    # not shared with others


def test_history_saves_on_send_once_titles_and_drafts(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp, main_screen
    import ginkassistant.app as app_mod
    from ginkassistant.services import groq_worker
    from ginkassistant.services.history import HistoryStore
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    seen = {}
    real_cloud = groq_worker.GroqBrain.ask

    async def slow_ask(self, query, on_token=None, save_user=True, **k):
        seen["mid_answer"] = [m["content"] for p in HistoryStore(app).get_all_sessions().values() for m in p["messages"]]
        seen["save_user"] = save_user
        await on_token("Here's a plan.")
        await asyncio.sleep(0.2)
        self.history.save_message(self.session_id, "assistant", "Here's a plan.")
        return "Here's a plan."
    monkeypatch.setattr(groq_worker.GroqBrain, "ask", slow_ask)
    async def fake_title(self, user_text, reply): return "Exam revision plan"
    monkeypatch.setattr(groq_worker.GroqBrain, "generate_title", fake_title)
    queued = [[{"type": "draft", "value": "half-typed thought"}], [],
              [{"type": "send", "value": "help me plan my exam revision"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    state = {}

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(30):
            await asyncio.sleep(0.05)
        sid = list(HistoryStore(app).get_all_sessions())[0]
        state["sid"] = sid
        # a draft typed in this chat, then come back to it
        queued.extend([[{"type": "draft", "value": "and maybe physics too"}], [{"type": "select_session", "value": sid}]])
        for _ in range(12):
            await asyncio.sleep(0.05)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert seen["mid_answer"] == ["help me plan my exam revision"]          # saved before the answer finished
    assert seen["save_user"] is False
    msgs = HistoryStore(app).get_all_sessions()[state["sid"]]["messages"]
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "help me plan my exam revision"), ("assistant", "Here's a plan.")]
    assert HistoryStore(app).get_meta()[state["sid"]]["title"] == "Exam revision plan"
    assert any(s.startswith("setComposerText(") and "maybe physics too" in s for s in js)   # draft restored


def test_brain_sends_presaved_message_once(tmp_path):
    from ginkassistant.services.groq_worker import GroqBrain
    from test_sync_attach_memory_briefing import _Hist
    sent = {}

    class Stream:
        def __init__(self): self.n = 0
        def __aiter__(self): return self
        async def __anext__(self):
            if self.n: raise StopAsyncIteration
            self.n = 1
            class C: pass
            c = C(); c.choices = [C()]; c.choices[0].delta = C(); c.choices[0].delta.content = "Hi!"
            return c

    class Completions:
        async def create(self, **kw):
            sent.update(kw); return Stream()
    brain = GroqBrain.__new__(GroqBrain)
    brain.api_key, brain.session_id, brain.active_models = "k", "s", ["llama-3.3-70b-versatile"]
    brain.preferred_model, brain.memory_provider, brain.city_fn = "llama-3.3-70b-versatile", None, None
    brain.client = type("X", (), {"chat": type("Y", (), {"completions": Completions()})()})()
    brain.history = _Hist(tmp_path / "h.db")
    brain.history.save_message("s", "user", "hello there")          # answer() saved it on send
    assert asyncio.run(brain.ask("hello there", save_user=False)) == "Hi!"
    users = [m for m in sent["messages"] if m["role"] == "user"]
    assert [m["content"] for m in users] == ["hello there"]           # once, not twice
    saved = brain.history.get_history("s")
    assert [m["role"] for m in saved] == ["user", "assistant"]        # not saved a second time
