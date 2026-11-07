"""When the server offers Gink's own model to this account, the apps' model picker lists it."""
import asyncio
import os
import sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_picker_gets_the_own_model(tmp_path, monkeypatch):
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
        pushed.append([m["id"] if isinstance(m, dict) else m for m in models])
        pushed.append(models)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "set_models", set_models)
    async def active(self):
        return ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "gink-search", "gink-1"]
    monkeypatch.setattr(groq_worker.GroqBrain, "refresh_active_models", active, raising=False)
    queued = [[{"type": "ready"}]]
    async def poll(self): return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", poll)
    async def no(*a, **k): return None
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", lambda self, s: no())

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        await asyncio.sleep(1.5)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    lists = [p for p in pushed if p and isinstance(p[0], dict)]
    last = lists[-1]
    own = [m for m in last if m["id"] == "gink-1"]
    assert own and own[0]["name"] == "Gink 1" and own[0].get("own") is True
    assert not any(m["id"] == "gink-search" and m.get("own") for m in last)        # search isn't "own"


def test_page_and_web_know_own_models():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    bridge = open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "Gink\\u2019s own model" in page and "/^gink-/" in page
    assert "Gink's own model (tools/gink_model)" in bridge
