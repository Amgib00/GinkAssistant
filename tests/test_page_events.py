"""Page -> Python events are handled exactly once, even when a slow phone answers late or twice
(ui/page_events.py). Before: an answer that came after Python stopped waiting was lost (a sent
message vanished), and nothing stopped the same event being handled twice."""
import asyncio, json, os, re, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.ui.page_events import QUEUE_JS, EventQueue


class Page:
    """The page side of QUEUE_JS, in Python (same rules), with a WebView that can be slow."""
    def __init__(self, page_id="p1"):
        self.events, self.seq, self.page, self.delay, self.scripts = [], 0, page_id, 0.0, []

    def emit(self, type_, value=None):
        self.seq += 1
        self.events.append({"seq": self.seq, "type": type_, "value": value})

    def take(self, ack, page):
        if page == self.page:
            self.events = [e for e in self.events if e["seq"] > ack]
        return json.dumps({"page": self.page, "events": self.events})

    async def evaluate_javascript(self, script):
        self.scripts.append(script)
        m = re.match(r"ginkTake\((\d+), (\".*\")\)$", script)
        if not m:
            return None
        out = self.take(int(m.group(1)), json.loads(m.group(2)))                 # the page runs it at once...
        await asyncio.sleep(self.delay)                                          # ...the answer may come late
        return out


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_every_page_uses_the_numbered_queue():
    ui = os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "ui")
    for f in ("web_chat_view.py", "login_screen.py", "media_studio_screen.py"):
        text = open(os.path.join(ui, f), encoding="utf-8").read()
        assert QUEUE_JS in text and "ginkTake()" not in text, f


def test_each_event_once():
    page, q = Page(), EventQueue()
    page.emit("send", "hello")
    assert run(q.take(page)) == [{"type": "send", "value": "hello"}]
    assert run(q.take(page)) == []                                               # not again
    page.emit("send", "second")
    assert [e["value"] for e in run(q.take(page))] == ["second"]


def test_late_answer_is_not_lost():
    """Regression: the page emptied its queue, Python had stopped waiting -> the message was gone."""
    page, q = Page(), EventQueue()
    page.emit("send", "are you there?")
    page.delay = 0.3
    assert run(q.take(page, timeout=0.05)) == []                                 # the phone was too slow
    page.delay = 0
    assert run(q.take(page)) == [{"type": "send", "value": "are you there?"}]    # ...it arrives next time
    assert run(q.take(page)) == []


def test_the_same_answer_twice_is_handled_once():
    q = EventQueue()
    answer = json.dumps({"page": "p1", "events": [{"seq": 1, "type": "send", "value": "hi"}]})
    assert q.accept(answer) == [{"type": "send", "value": "hi"}]
    assert q.accept(answer) == []
    assert q.accept(json.dumps(answer)) == []                                     # double-encoded too


def test_a_reloaded_page_starts_again():
    q = EventQueue()
    q.accept(json.dumps({"page": "p1", "events": [{"seq": 5, "type": "send", "value": "a"}]}))
    fresh = q.accept(json.dumps({"page": "p2", "events": [{"seq": 1, "type": "send", "value": "b"}]}))
    assert fresh == [{"type": "send", "value": "b"}]


def test_old_page_format_still_works():
    assert EventQueue().accept(json.dumps([{"type": "send", "value": "x"}])) == [{"type": "send", "value": "x"}]
    assert EventQueue().accept("not json") == [] and EventQueue().accept(None) == []


def test_main_screen_shows_and_saves_a_message_once_on_a_slow_phone(tmp_path, monkeypatch):
    """The whole chat screen on a WebView that answers later than Python waits: one bubble, one save."""
    import toga
    from ginkassistant.app import GinkAssistantApp
    import ginkassistant.app as app_mod
    from ginkassistant.ui import main_screen
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    monkeypatch.setattr(type(app.paths), "data", property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    page = Page()
    bubbles = []

    async def evaluate(self, script):
        if script.startswith("addUserMessage("):
            bubbles.append(script)
        return await page.evaluate_javascript(script)
    monkeypatch.setattr(toga.WebView, "evaluate_javascript", evaluate)
    async def no(*a, **k): return ""
    monkeypatch.setattr(main_screen.voice_bridge, "speak", no)

    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        await asyncio.sleep(0.8)
        page.emit("send", "wake me up at 6:30")
        page.delay = 2.3                                                          # longer than Python waits
        await asyncio.sleep(2.6)
        page.delay = 0
        for _ in range(150):                                                      # generous: CI machines are busy
            await asyncio.sleep(0.1)
            if bubbles:
                break
        await asyncio.sleep(0.6)
        app._main_screen_token = None
        app.task_scheduler.stop()
    asyncio.run(go())
    assert len([b for b in bubbles if "6:30" in b]) == 1, bubbles
    from ginkassistant.services.history import HistoryStore
    msgs = [m for s in HistoryStore(app).get_all_sessions().values() for m in s.get("messages", [])]
    assert [m["content"] for m in msgs if m["role"] == "user"] == ["wake me up at 6:30"]
