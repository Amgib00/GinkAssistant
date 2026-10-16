"""'Hey Gink': phrase matching, the listener (pause = mic released), engines, and a full wake turn."""
import asyncio, os, sys, threading, time
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))


def test_phrase_matching():
    from ginkassistant.services.wake_word import matches
    assert matches("hey gink") and matches("ok so hey king what's up") and matches("Hey, Gink!")
    assert not matches("hey") and not matches("thinking about it") and not matches("[unk]") and not matches("hey kingdom")


class FakeMic:
    def __init__(self, script):
        self.script, self.opened, self.closed = list(script), 0, 0
    def __call__(self, frame):
        self.opened += 1
        mic = self
        class S:
            def read(self):
                time.sleep(0.01)
                return mic.script.pop(0) if mic.script else b"\0" * 8
            def close(self): mic.closed += 1
        return S()


class FakeEngine:
    name, frame = "Fake", 512
    def process(self, pcm): return pcm == b"HEYGINK"


def test_listener_detects_pauses_and_releases_mic():
    from ginkassistant.services.wake_word import WakeWordListener
    mic, hits = FakeMic([b"noise", b"HEYGINK", b"HEYGINK", b"noise"]), []
    lst = WakeWordListener(FakeEngine(), lambda: hits.append(time.time()), open_stream=mic, cooldown=0.2)
    lst.start()
    time.sleep(0.3)
    assert hits and lst.paused and mic.closed >= 1            # heard it -> paused itself and let go of the mic
    assert len(hits) == 1                                       # nothing more while paused
    mic.script[:] = [b"HEYGINK"]
    lst.resume(); time.sleep(0.3)
    assert len(hits) == 2 and mic.opened >= 2                   # resumed -> mic reopened -> heard again
    lst.stop(); time.sleep(0.1)


def test_listener_reports_missing_microphone():
    from ginkassistant.services.wake_word import WakeWordListener
    def no_mic(frame): raise OSError("no input device")
    lst = WakeWordListener(FakeEngine(), lambda: None, open_stream=no_mic)
    lst.start(); time.sleep(0.15)
    assert "no microphone" in lst.error
    lst.stop()


def test_engine_reasons(tmp_path, monkeypatch):
    from ginkassistant.services import wake_word as ww
    monkeypatch.delenv("PICOVOICE_ACCESS_KEY", raising=False)
    engine, reason = ww.best_engine(tmp_path)
    try:
        import vosk  # noqa: F401
        assert engine is None and "isn't downloaded" in reason and "40 MB" in reason
    except ImportError:                       # e.g. a CI machine without the wake-word package
        assert engine is None and "isn't installed" in reason and "pip install vosk" in reason
    assert not ww.model_ready(tmp_path)


def test_full_wake_turn(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp, main_screen
    import ginkassistant.app as app_mod
    from ginkassistant.services import voice_bridge, wake_word, prefs
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    async def fake_poll(self): return []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    mic = FakeMic([b"noise", b"HEYGINK"])
    monkeypatch.setattr(wake_word, "best_engine", lambda base: (FakeEngine(), ""))
    real_listener = wake_word.WakeWordListener
    monkeypatch.setattr(wake_word, "WakeWordListener", lambda engine, cb: real_listener(engine, cb, open_stream=mic))
    heard = ["calculate 12 x 7", "what's 15% of 80000", ""]           # request, a follow-up, then silence
    async def fake_listen(on_amplitude=None):
        await asyncio.sleep(0.02); return heard.pop(0) if heard else ""
    monkeypatch.setattr(voice_bridge, "listen", fake_listen)
    said = []
    async def synth(t, k): said.append(t); return ("system", t)
    async def play(item, amp):
        if amp: amp(0.6)
        await asyncio.sleep(0.02)
    monkeypatch.setattr(voice_bridge, "_synth_sentence", synth)
    monkeypatch.setattr(voice_bridge, "_play_item", play)
    monkeypatch.setattr(main_screen.os.path, "exists", lambda p: False if p.endswith("Tink.aiff") else os.path.exists(p))
    prefs.save(app, wake_enabled=True)
    state = {}

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(60):
            await asyncio.sleep(0.05)
        state["listener_running"] = app.wake["listener"].running
        state["listener_paused_after"] = app.wake["listener"].paused
        app.wake["listener"].stop()
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    glow = [s.split("(")[1].split(")")[0] for s in js if s.startswith("wakeGlow(")]
    assert glow[0] == '"listening"' and '"thinking"' in glow and '"speaking"' in glow and glow[-1] == '"off"'
    assert any(s.startswith("wakeCaption(") and "12 x 7" in s for s in js)
    assert any("84" in t for t in said) and any("12,000" in t or "12000" in t for t in said)   # answered both, out loud
    assert any(s.startswith("addUserMessage(") and "12 x 7" in s for s in js)                    # and shown in the chat
    assert state["listener_running"] and state["listener_paused_after"] is False                 # listening for "Hey Gink" again


def test_maths_goes_to_the_exact_calculator():
    """Regression: '%' inside the \\b(...)\\b group never matched, so maths went to the AI."""
    from ginkassistant.services.actions import looks_like_action
    assert looks_like_action("what's 15% of 80000") and looks_like_action("what is 12 x 7") and looks_like_action("2+2")
    assert not looks_like_action("the score was 3-2") and not looks_like_action("I'm 25 years old")


def test_settings_switch_starts_and_stops_listening(tmp_path, monkeypatch):
    """Regression: the switch used to be saved without starting/stopping the listener."""
    from test_main_screen import GinkAssistantApp
    import ginkassistant.app as app_mod
    from ginkassistant.services import prefs
    from ginkassistant.ui.settings_controller import SettingsController
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()

    class Web:
        async def settings_toast(self, *a): pass
        async def set_settings_state(self, st): self.st = st
        async def set_appearance(self, *a): pass
        async def set_keyboard_prefs(self, p): pass
        async def set_voice_config(self, c): pass
    class Brain: preferred_model = "m"; memory_provider = None; reply_language_note = None
    sc = SettingsController(app, Web(), Brain(), {"value": "Female (Jenny)"}, type("A", (), {"voice_key": ""})(),
                            email="ib@x.co", display_name="Ib", models_fn=lambda: [], push_models=None, open_pro=None,
                            on_log_out=None, refresh_sidebar=None, clear_all_chats=None, brief_now=None, sync_fn=None, open_url=None)
    calls = []
    async def changed(): calls.append(prefs.load(app)["wake_enabled"])
    sc.on_wake_change = changed
    sc.wake_status_fn = lambda: "Listening for \u201cHey Gink\u201d \u00b7 Vosk (offline, free)"
    asyncio.run(sc.on_setting("wake_enabled", True))
    asyncio.run(sc.on_setting("wake_enabled", False))
    assert calls == [True, False]                                   # applied immediately, both ways
    assert prefs.load(app)["wake_enabled"] is False
