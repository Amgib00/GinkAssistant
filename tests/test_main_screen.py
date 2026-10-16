"""Builds the real main screen (Toga dummy backend) and drives it:
an alarm request through the input box, Enter-to-send, Tasks screen,
and the single-save fix for chat history."""
import asyncio, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import toga
from ginkassistant.app import GinkAssistantApp
from ginkassistant.ui import main_screen
from ginkassistant.services.actions import ActionResult


def test_main_screen_end_to_end(tmp_path, monkeypatch):
    import ginkassistant.app as app_mod
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)   # don't start the local FastAPI backend in tests
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    monkeypatch.setattr(type(app.paths), "data", property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    calls = []
    dev = app.task_runner.device
    dev.set_alarm = lambda h, m, *a, **k: calls.append((h, m)) or ActionResult(True, "sys", by_system=True)

    async def no_speak(*a, **k): pass
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", no_speak)   # dummy WebView never answers JS
    # The composer is HTML now; feed it events exactly as the page would.
    queued = [[{"type": "send", "value": "wake me up at 6:30"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    import json as _json
    pushed = []
    async def record_js(self, script):
        name = script.split("(", 1)[0]
        if name in ("setUser", "setSessions"):
            pushed.append((name, _json.loads("[" + script[len(name) + 1:-1] + "]")[0]))
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", record_js)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    monkeypatch.setattr(main_screen.voice_bridge, "speak", no_speak)

    async def go():
        root = main_screen.build_main_screen(app, "ibrahim.kargbo@example.com")
        # whole screen is the chat page: sidebar, top bar and composer are HTML
        assert len(root.children) == 1 and isinstance(root.children[0], toga.WebView)
        for _ in range(30):                               # composer loop picks up the send
            await asyncio.sleep(0.05)
        assert ("setUser", "Ibrahim Kargbo") in pushed
        recents = [v for k, v in pushed if k == "setSessions"][-1]
        assert recents and recents[0]["title"] == "wake me up at 6:30" and recents[0]["current"]
        recents_first_id = recents[0]["id"]
        from ginkassistant.services.history import HistoryStore
        msgs = [m for p in HistoryStore(app).get_all_sessions().values() for m in p.get("messages", [])]
        assert len([m for m in msgs if m.get("role") == "user"]) == 1, msgs   # saved exactly once
        # user message "..." -> Branch to new chat copies the chat into a new one
        queued.append([{"type": "branch", "value": 0}])
        for _ in range(10):
            await asyncio.sleep(0.05)
        recents = [v for k, v in pushed if k == "setSessions"][-1]
        assert len(recents) == 2 and [r for r in recents if r["current"]][0]["id"] != recents_first_id
        for r in recents:
            if r["id"] != recents_first_id:
                queued.append([{"type": "delete_session", "value": r["id"]}])
        for _ in range(10):
            await asyncio.sleep(0.05)
        recents = [v for k, v in pushed if k == "setSessions"][-1]
        # sidebar delete dialog -> delete_session event removes the chat
        queued.append([{"type": "delete_session", "value": recents[0]["id"]}])
        for _ in range(10):
            await asyncio.sleep(0.05)
        assert [v for k, v in pushed if k == "setSessions"][-1] == []
        # clicking a link in a reply opens it via the device helper
        opened = []
        dev.open_url = lambda url: opened.append(url) or ActionResult(True, "opened")
        queued.append([{"type": "open_url", "value": "mailto:hello@example.com"}])   # web links open in the viewer now
        for _ in range(10):
            await asyncio.sleep(0.05)
        assert opened == ["mailto:hello@example.com"]
        # sidebar "Tasks & alarms" opens the Tasks screen showing the new alarm
        queued.append([{"type": "open", "value": "tasks"}])
        for _ in range(10):
            await asyncio.sleep(0.05)
        content = app.main_window.content
        assert content is not root and "Workspace" in content.children[0].children[1].children[0].text
        app.task_scheduler.stop()
        return root
    asyncio.run(go())
    assert calls == [(6, 30)]
    alarms = app.task_store.list("alarm")
    assert len(alarms) == 1 and alarms[0].system_scheduled
    from ginkassistant.services.history import HistoryStore
    assert HistoryStore(app).get_all_sessions() == {}   # deleted from the sidebar


def test_song_recognition_degrades_gracefully():
    from ginkassistant.services import song_recognition
    # no shazamio/librosa here: must return None, never raise
    assert asyncio.run(song_recognition._identify_with_local_engine()) is None


def test_attach_photo_and_briefing_through_main_screen(tmp_path, monkeypatch):
    import base64, io, json as _json
    from PIL import Image
    import ginkassistant.app as app_mod
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    app.memory.add("Lives in Dakar")

    async def no_speak(*a, **k): pass
    from ginkassistant.ui import web_chat_view
    from ginkassistant.services import groq_worker, briefing
    js = []
    async def record_js(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", record_js)
    monkeypatch.setattr(main_screen.voice_bridge, "speak", no_speak)
    asked = []
    async def fake_ask(self, query, on_token=None, system_prompt=None, on_status=None, attachments=None, **k):
        asked.append((query, [a.name for a in attachments or []], self.memory_provider()))
        return "It's a green square."
    monkeypatch.setattr(groq_worker.GroqBrain, "ask", fake_ask)
    async def no_weather(city): return None
    monkeypatch.setattr(briefing, "fetch_weather", no_weather)
    async def fake_news(): return "", [{"title": "Headline", "link": "https://x.y"}]
    monkeypatch.setattr(main_screen, "fetch_world_news", fake_news)

    buf = io.BytesIO(); Image.new("RGB", (40, 40), (0, 200, 0)).save(buf, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    queued = [[{"type": "attach_data", "value": {"name": "square.png", "data": data_url}}], [],
              [{"type": "send", "value": "What colour is this?"}], [], [], [],
              [{"type": "send", "value": "brief me"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)

    async def go():
        main_screen.build_main_screen(app, "ibrahim@example.com")
        for _ in range(60):
            await asyncio.sleep(0.05)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert asked and asked[0][0] == "What colour is this?" and asked[0][1] == ["square.png"]
    assert "Lives in Dakar" in asked[0][2]                                    # memory reaches the AI
    chips = [s for s in js if s.startswith("setAttachments(") and "square.png" in s]
    assert chips, "photo chip shown in the composer"
    assert any(s.startswith("addUserMessage(") and "square.png" in s for s in js)   # shown on the bubble
    assert any(s.startswith("addCompleteAssistantMessage(") and "Headline" in s for s in js) or \
        any("Headline" in s for s in js)                                    # briefing rendered


def test_video_card_and_links_open_viewer(tmp_path, monkeypatch):
    import ginkassistant.app as app_mod
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    from ginkassistant.ui import web_chat_view
    async def nojs(self, script): pass
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", nojs)
    external = []
    app.task_runner.device.open_url = lambda url: external.append(url) or ActionResult(True, "ok")
    queued = [[{"type": "play_video", "value": {"id": "AAAAAAAAAAA", "title": "Tyre"}}], [],
              [{"type": "open_url", "value": "https://www.wikihow.com/Change-a-Tire"}], [],
              [{"type": "open_url", "value": "mailto:me@example.com"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    seen = {}

    async def go():
        root = main_screen.build_main_screen(app, "ibrahim@example.com")
        for _ in range(40):
            await asyncio.sleep(0.05)
            if len(root.children) == 3 and "first" not in seen:
                seen["first"] = root.children[2].children[1].url
        seen["final"] = root.children[2].children[1].url
        seen["children"] = len(root.children)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert seen["first"] == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert seen["final"] == "https://www.wikihow.com/Change-a-Tire" and seen["children"] == 3
    assert external == ["mailto:me@example.com"]


def test_stop_ring_cancels_answer_and_voice(tmp_path, monkeypatch):
    import ginkassistant.app as app_mod
    from ginkassistant.services import groq_worker, voice_bridge
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    async def slow_ask(self, query, on_token=None, **k):      # writes a bit, then keeps "thinking"
        await on_token("The first part of a long ")
        await on_token("answer")
        await asyncio.sleep(30)
        return "never finished"
    monkeypatch.setattr(groq_worker.GroqBrain, "ask", slow_ask)
    stopped = []
    monkeypatch.setattr(voice_bridge, "stop_speaking", lambda: stopped.append(1))
    queued = [[{"type": "send", "value": "explain everything"}], [], [], [], [], [], [{"type": "stop"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(40):
            await asyncio.sleep(0.05)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert stopped, "voice silenced"
    final = [s for s in js if s.startswith("finalizeMessage(")][-1]
    assert "The first part of a long answer" in final and "Stopped." in final          # partial kept, marked
    assert js.index([s for s in js if s.startswith("setComposerBusy(false)")][-1]) > js.index(final)   # box unlocked
    from ginkassistant.services.history import HistoryStore
    msgs = [m for p in HistoryStore(app).get_all_sessions().values() for m in p.get("messages", [])]
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["content"].endswith("*Stopped.*")


def test_voice_session_states_and_end_mid_speech(tmp_path, monkeypatch):
    import ginkassistant.app as app_mod
    from ginkassistant.services import groq_worker, voice_bridge, prefs
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    js = []
    async def rec(self, script): js.append(script)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", rec)
    heard = ["What should I cook tonight?"]
    async def fake_listen(on_amplitude=None):
        if heard:
            return heard.pop(0)
        await asyncio.sleep(0.05)
        return ""
    monkeypatch.setattr(voice_bridge, "listen", fake_listen)
    spoken = []
    async def fake_synth(text, voice_key):
        spoken.append(voice_key)
        return ("system", text)
    async def fake_play(item, on_amplitude):
        if on_amplitude:
            on_amplitude(0.6)
        await asyncio.sleep(0.6)                 # Gink is mid-sentence when End arrives
    monkeypatch.setattr(voice_bridge, "_synth_sentence", fake_synth)
    monkeypatch.setattr(voice_bridge, "_play_item", fake_play)
    async def fake_ask(self, query, on_token=None, **k):
        await on_token("How about thieboudienne?")
        return "How about thieboudienne?"
    monkeypatch.setattr(groq_worker.GroqBrain, "ask", fake_ask)
    queued = [[{"type": "voice_start", "value": {"voice": "ezinne"}}]] + [[]] * 8 + [[{"type": "voice_end"}]]
    async def fake_poll(self):
        return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    state = {}

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(50):
            await asyncio.sleep(0.05)
        state["listening"] = app.audio_engine._is_listening if hasattr(app, "audio_engine") else None
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert prefs.load(app)["voice"] == "ezinne" and spoken and spoken[0] == "ezinne"
    states = [s for s in js if s.startswith("voiceUiState(")]
    assert any('"listening"' in s for s in states) and any('"thinking"' in s for s in states) and any('"speaking"' in s for s in states)
    assert any(s.startswith("voiceUiCaption(") and "cook tonight" in s for s in js)
    assert any(s.startswith("voiceUiCaption(") and "thieboudienne" in s for s in js)
    assert any(s.startswith("voiceUiLevel(") for s in js)
    assert any(s.startswith("addUserMessage(") and "cook tonight" in s for s in js)   # shown in the chat too
    assert state["listening"] is False                                  # End mid-speech: the mic stays off
