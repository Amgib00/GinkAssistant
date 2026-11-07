"""Wake on "Hey Gink" or just "Gink" everywhere; Media Studio without video and with Ideas; only Gink's
models in the pickers."""
import asyncio
import os
import sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_desktop_wake_phrases():
    from ginkassistant.services import wake_word as w
    try:
        w.SHORT["on"] = True
        assert w.matches("hey ginkgo") and w.matches("ginkgo") and w.matches("gink what time is it")
        assert not w.matches("king") and not w.matches("the ginkgo tree")          # "Gink" must come first
        assert "ginkgo" in w.WAKE_PHRASES
        w.SHORT["on"] = False
        assert not w.matches("ginkgo") and w.matches("hey ginkgo")                  # switched off: Hey Gink only
    finally:
        w.SHORT["on"] = True


def test_android_wake_phrases():
    from ginkassistant.services import android_voice as av
    m = av.WAKE_SHORT_RE.match("Gink, what's the weather in Dakar?")
    assert m and "Gink, what's the weather in Dakar?"[m.end():] == "what's the weather in Dakar?"
    assert not av.WAKE_SHORT_RE.match("I think Gink is great")


def test_web_wake_phrases_and_glow():
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "function wakeHeard(" in bridge and "W.prefs.wake_short !== false" in bridge
    assert 'wakeGlow("listening")' in bridge and 'wakeGlow("off")' in bridge
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    assert "key: 'wake_short'" in page


def test_media_studio_ideas_without_video():
    from ginkassistant.ui import media_studio_screen as ms
    from ginkassistant.services.image_service import ASPECTS, STYLES
    assert "tab-video" not in ms.PAGE and "Video" not in ms.PAGE
    assert len(ms.IDEAS) == 11 and {i[1] for i in ms.IDEAS} >= {"Zen", "Chibi keychain", "Football figurine", "Underwater", "Cozy room"}
    for it in ms.IDEAS:
        assert "{subject}" in it[2] and it[4] in STYLES and it[5] in ASPECTS, it[0]
    assert "__IDEAS__" in ms.PAGE and "<img" not in ms.PAGE.split("ideas")[1][:400]   # drawn here, no borrowed pictures


def test_pickers_show_only_gink_models(tmp_path, monkeypatch):
    from ginkassistant.app import GinkAssistantApp
    import ginkassistant.app as app_mod
    from ginkassistant.ui import main_screen, web_chat_view
    from ginkassistant.services import groq_worker
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    monkeypatch.setattr(type(app.paths), "data", property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    pushed = []
    async def set_models(self, models, current):
        pushed.append(([m["id"] for m in models], current))
    monkeypatch.setattr(web_chat_view.WebChatFeed, "set_models", set_models)
    async def active(self):
        return ["llama3-70b-8192", "mixtral-8x7b-32768", "deepseek-r1-distill-llama-70b", "openai/gpt-oss-120b",
                "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "gink-1"]
    monkeypatch.setattr(groq_worker.GroqBrain, "refresh_active_models", active, raising=False)
    queued = [[{"type": "ready"}]]
    async def poll(self): return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", poll)
    async def no(*a, **k): return None
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", lambda self, s: no())
    orig = groq_worker.GroqBrain.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.preferred_model = "llama-3.3-70b-versatile"                         # an old choice
    monkeypatch.setattr(groq_worker.GroqBrain, "__init__", init)

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        await asyncio.sleep(1.5)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert pushed
    for ids, current in pushed:
        assert not any(x.startswith(("llama", "mixtral", "deepseek")) for x in ids), ids
        assert current == "openai/gpt-oss-120b"                                  # moved to Gink Crystal
    assert "gink-1" in pushed[-1][0]                                             # Gink's own model still offered
