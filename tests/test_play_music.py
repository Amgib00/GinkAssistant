"""Playing a specific song, and recognising play / close requests."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.services.actions.device import DeviceActions, ActionResult
from ginkassistant.services.actions.agent import looks_like_action

SONG = "Floating (Genom V\u00e4rldar - English Version)"


def _device(platform, opened):
    d = DeviceActions.__new__(DeviceActions); d.platform = platform
    d.open_url = lambda u: (opened.append(u), ActionResult(True, "ok"))[1]
    d._android_view = lambda u: opened.append(u)
    return d


def test_computers_play_the_exact_song_or_open_spotify():
    opened = []
    d = _device("macos", opened)
    assert d.play_music(SONG, "", "abc123").ok and opened[-1] == "https://www.youtube.com/watch?v=abc123"
    r = d.play_music(SONG, "spotify")
    assert opened[-1].startswith("spotify:search:Floating") and "press play" in r.message
    d.play_music(SONG)                                                  # nothing found: YouTube Music's search
    assert opened[-1].startswith("https://music.youtube.com/search?q=Floating")
    assert not d.play_music("   ").ok


def test_the_agent_finds_the_song_first_and_android_falls_back(monkeypatch):
    from ginkassistant.services.actions.tools import ToolRunner, TOOL_SPECS
    assert any(t["function"]["name"] == "play_music" for t in TOOL_SPECS)
    opened, searched = [], []
    class Videos:
        async def search(self, q, n=3, live=False):
            searched.append(q); return [{"id": "vid42"}]
    r = ToolRunner.__new__(ToolRunner); r.videos = Videos(); r.device = _device("windows", opened)
    out = asyncio.run(r._t_play_music(SONG))
    assert out["ok"] and searched == [SONG + " official audio"] and opened[-1] == "https://www.youtube.com/watch?v=vid42"
    r.device = _device("android", opened)                               # no java here: the music request fails...
    out = asyncio.run(r._t_play_music(SONG))
    assert out["ok"] and opened[-1] == "https://music.youtube.com/watch?v=vid42"   # ...so it opens the song directly


def test_play_and_close_requests_reach_the_agent():
    for m in ["play " + SONG, "can you play some Burna Boy", "please play the song Calm Down", "close Safari", "exit the app", "open Spotify"]:
        assert looks_like_action(m), m
    for m in ["what is the capital of Senegal", "tell me about the album Thriller"]:
        assert not looks_like_action(m), m


def test_model_menu_effort_greeting_and_attachments():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    for part in ("GINK_MODELS", "'Gink Crystal'", "'Gink Flake'", "'Gink Prism'", "Higher effort means more thorough responses",
                 "matchMedia('(hover: hover)')", "ginkEmit('setting', {key: 'effort'", "body.home #atts { flex-basis: 100%",
                 ".att.pic img { width: 96px"):
        assert part in page, part
    from ginkassistant.services import prefs
    from ginkassistant.services.groq_worker import GroqBrain
    assert prefs.DEFAULTS["effort"] == "medium" and "effort" in prefs.SYNCED
    b = GroqBrain.__new__(GroqBrain); b.app = None
    assert b._effort_args("openai/gpt-oss-120b")["extra_body"]["reasoning_effort"] == "medium"
    assert b._effort_args("qwen/qwen3.8-27b") == {}                              # only GPT-OSS takes it
    main = open(os.path.join(root, "src", "ginkassistant", "ui", "main_screen.py"), encoding="utf-8").read()
    assert "def greet_name()" in main and "WELCOME_ENDINGS" in main             # never a name made from the email


def test_code_viewer_wiring():
    root = os.path.join(os.path.dirname(__file__), "..")
    extras = open(os.path.join(root, "src", "ginkassistant", "ui", "chat_extras.py"), encoding="utf-8").read()
    for part in ("window.openCodeViewer", "window.autoOpenCode", 'data-code="open"', "ginkEmit('save_code', {name: CV.name",
                 "#codeview .cvbody code { font-size: inherit; line-height: inherit; }", "body.viewer-open { padding-right"):
        assert part in extras, part
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    assert "if (!LOADING_CHAT && window.autoOpenCode) autoOpenCode(el);" in page and "window.__sentAt = Date.now();" in page
    assert "window.__sentAt = 0;" in open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()


def test_design_preview_is_sandboxed():
    root = os.path.join(os.path.dirname(__file__), "..")
    extras = open(os.path.join(root, "src", "ginkassistant", "ui", "chat_extras.py"), encoding="utf-8").read()
    assert "old.setAttribute('sandbox', 'allow-scripts allow-modals');" in extras        # never allow-same-origin
    assert "allow-same-origin" not in extras and "function cvShow(tab)" in extras
