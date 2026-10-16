"""Voice never breaks a reply; videos stop without about:blank."""
import asyncio, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import toga


def test_speak_falls_back_to_system_voice(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    class Refused:
        def __init__(self, *a, **k): pass
        async def save(self, path): raise RuntimeError("403, message='Invalid response status'")
    monkeypatch.setattr(vb.edge_tts, "Communicate", Refused)
    spoken = []
    async def fake_system(text, on_amp): spoken.append(text)
    monkeypatch.setattr(vb, "_system_voice", fake_system)
    vb._edge_down_until[0] = 0
    asyncio.run(vb.speak("**Done** \u2014 alarm set for 06:30.\n\n[\u25b6 Video \u2014 X](https://youtube.com/watch?v=AAAAAAAAAAA)"))
    assert spoken == ["Done \u2014 alarm set for 06:30."]          # no '**', no video line, no crash
    # second call skips the refused service entirely (no delay)
    monkeypatch.setattr(vb.edge_tts, "Communicate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("retried")))
    asyncio.run(vb.speak("Again"))
    assert spoken[-1] == "Again"


def test_speakable_cleans_markdown():
    from ginkassistant.services.voice_bridge import _speakable
    assert _speakable("# Title\n- **one**\n- see [docs](https://x.y)\n```py\nx=1\n```") == \
        "Title\none\nsee docs\n(code shown on screen)"


def test_stop_webview_and_live_tv_back(tmp_path, monkeypatch):
    from ginkassistant.ui import toga_live_tv as tv
    from ginkassistant.ui.viewer_util import stop_webview
    app = toga.App("t", "org.t")
    monkeypatch.setattr(type(app.paths), "config", property(lambda self: tmp_path), raising=False)
    went_back = []
    screen = tv.build_live_tv_view(app, on_back=lambda: went_back.append(1))
    back = screen.children[0].children[0]
    back.on_press()                         # used to raise "WebView can only display http(s) URLs"
    assert went_back == [1]
    w = toga.WebView(); w.url = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    calls = []
    w.set_content = lambda root, html: calls.append(root)     # what the real WebView gets asked to do
    stop_webview(w)                                            # must not raise (about:blank did)
    assert calls == ["https://gink.local/blank"]


def test_stop_speaking_during_preparation_and_hook(monkeypatch):
    """Stop while the voice is still being prepared -> nothing is played; the ring hook fires on/off."""
    from ginkassistant.services import voice_bridge as vb
    events, played = [], []
    vb.on_speaking = events.append
    class Slow:
        def __init__(self, *a, **k): pass
        async def save(self, path):
            vb.stop_speaking()                     # user presses Stop while it's being prepared
    monkeypatch.setattr(vb.edge_tts, "Communicate", Slow)
    monkeypatch.setattr(vb.pygame.mixer.music, "load", lambda p: played.append(p))
    async def sys_voice(text, amp): played.append("system")
    monkeypatch.setattr(vb, "_system_voice", sys_voice)
    vb._edge_down_until[0] = 0
    asyncio.run(vb.speak("A long reply being read aloud."))
    vb.on_speaking = None
    assert played == [] and events == [True, False]
