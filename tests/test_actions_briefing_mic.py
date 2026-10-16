"""Mic handover (AUHAL fix), more computer actions, app matching, smarter briefing, safe links."""
import asyncio, os, sys, time
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime
import pytest


def test_mic_is_released_before_gink_is_woken():
    from ginkassistant.services.wake_word import WakeWordListener
    from test_wake_word import FakeMic, FakeEngine
    mic, seen = FakeMic([b"noise", b"HEYGINK"]), {}
    lst = None
    def on_wake():
        seen["released"] = lst.mic_released                    # at the moment Gink is told...
        seen["closes"] = mic.closed
    lst = WakeWordListener(FakeEngine(), on_wake, open_stream=mic, cooldown=0.1)
    lst.start(); time.sleep(0.3)
    assert seen == {"released": True, "closes": 1}             # ...the mic is already closed
    lst.resume(); time.sleep(0.1)
    t0 = time.time(); assert lst.pause(wait=True) is True      # pause(wait) returns once it's really free
    assert time.time() - t0 < 1.0 and lst.mic_released
    lst.stop()


@pytest.fixture
def mac(monkeypatch, tmp_path):
    from ginkassistant.services.actions import computer as c
    for k, v in (("MAC", True), ("WIN", False), ("LINUX", False), ("MOBILE", False)):
        monkeypatch.setattr(c, k, v)
    calls = []
    monkeypatch.setattr(c, "run", lambda cmd, timeout=20: (calls.append(cmd), (True, ""))[1])
    home = tmp_path / "home"
    for d in ("Desktop", "Documents", "Downloads", "PycharmProjects/GinkAssistant"):
        (home / d).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return c, calls, home


def test_finder_terminal_settings(mac):
    c, calls, home = mac
    pc = c.ComputerControl()
    assert pc.open_folder("downloads")["ok"] and calls[-1] == ["open", str(home / "Downloads")]
    assert pc.open_folder("GinkAssistant")["path"] == str(home / "PycharmProjects" / "GinkAssistant")   # project by name
    assert pc.open_folder("nowhere-xyz")["ok"] is False
    r = pc.open_terminal("GinkAssistant")
    assert r["ok"] and calls[-1] == ["open", "-a", "Terminal", str(home / "PycharmProjects" / "GinkAssistant")]
    assert pc.open_settings_pane("wifi")["ok"] and calls[-1] == ["open", "x-apple.systempreferences:com.apple.preference.network"]
    assert pc.sleep_computer()["ok"] and calls[-1] == ["pmset", "sleepnow"]


def test_recent_files_and_open_by_number(mac):
    c, calls, home = mac
    old = home / "Documents" / "old.pdf"; old.write_text("x"); os.utime(old, (time.time() - 9 * 86400,) * 2)
    new = home / "Documents" / "Proposal.docx"; new.write_text("x")
    code = home / "PycharmProjects" / "GinkAssistant" / "app.py"; code.write_text("x")
    junk = home / "Downloads" / "movie.mkv"; junk.write_text("x")
    files = c.recent_files(days=2, limit=5, folders=("Desktop", "Documents", "Downloads", "PycharmProjects"))
    assert str(new) in files and str(code) in files and str(old) not in files and str(junk) not in files
    pc = c.ComputerControl()
    r = pc.show_recent_files(3)
    assert r["ok"] and "Proposal.docx" in r["message"] and pc.resolve_file("1") in (str(new), str(code))


def test_browser_search(mac, monkeypatch):
    c, calls, home = mac
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u) or True)
    assert c.ComputerControl().search_in_browser("cheap flights to Freetown")["ok"]
    assert opened == ["https://www.google.com/search?q=cheap+flights+to+Freetown"]


def test_open_app_matches_installed_and_falls_back_to_website(monkeypatch):
    from ginkassistant.services.actions import device as d
    dev = d.DeviceActions.__new__(d.DeviceActions); dev.platform = "macos"
    apps = ["PyCharm CE", "Google Chrome", "Adobe Photoshop 2024", "Calculator"]
    assert dev.resolve_mac_app("pycharm", apps) == "PyCharm CE" and dev.resolve_mac_app("photoshop", apps) == "Adobe Photoshop 2024"
    assert dev.resolve_mac_app("Calcuator", apps) == "Calculator"
    monkeypatch.setattr(d, "run", lambda cmd, timeout=20: (False, "Unable to find application"))
    monkeypatch.setattr(d.DeviceActions, "installed_mac_apps", staticmethod(lambda: apps))
    urls = []
    monkeypatch.setattr(d.DeviceActions, "open_url", lambda self, u: urls.append(u) or d.ActionResult(True, "Opening."))
    assert dev.open_app("youtube").ok and urls == ["https://www.youtube.com"]
    assert dev.open_app("nonexistentthing").ok is False


def test_briefing_picks_up_where_you_left_off(tmp_path):
    from ginkassistant.services import briefing
    from ginkassistant.services.actions import TaskStore
    store = TaskStore(str(tmp_path / "t.db"))
    t = store.add("task", "Exam revision")
    steps = [store.add("task", n, parent_id=t.id) for n in ("Maths", "Physics", "Past papers", "Flashcards")]
    store.set_done(steps[0].id, True); store.set_done(steps[1].id, True); store.set_done(steps[2].id, True)
    chats = [{"id": "s9", "title": "Portfolio website", "when": "yesterday"}]
    files = ["/Users/ib/Documents/Proposal.docx"]
    sent = {}
    async def writer(facts):
        sent["facts"] = facts
        return "Morning Ibrahim! One step left on Exam revision \u2014 the flashcards will wrap it up."
    md, said = asyncio.run(briefing.build_briefing(store, {"briefing_city": ""}, "Ibrahim", now=datetime(2026, 10, 13, 7, 40),
                                                  chats=chats, files=files, writer=writer))
    assert md.splitlines()[1] == "Morning Ibrahim! One step left on Exam revision \u2014 the flashcards will wrap it up."
    assert "**Pick up where you left off**" in md and "**Exam revision** \u2014 3/4 steps done. Next: *Flashcards*" in md
    assert "nearly there, finish this one first" in md
    assert "[Continue](gink://chat/s9)" in md and "[Open](gink://open/%2FUsers%2Fib%2FDocuments%2FProposal.docx)" in md
    assert "Proposal" not in sent["facts"] and "Exam revision" in sent["facts"]        # file names never sent to the AI
    assert "3 of 4 steps into Exam revision" in said
    async def broken(facts): raise RuntimeError("AI down")
    md2, _ = asyncio.run(briefing.build_briefing(store, {}, "Ibrahim", chats=chats, writer=broken))
    assert "You're 3 of 4 steps into **Exam revision**" in md2                         # still personal without the AI


def test_briefing_links_only_open_your_own_files(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp, main_screen
    import ginkassistant.app as app_mod
    from ginkassistant.ui import web_chat_view
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    home = tmp_path / "home"; (home / "Documents").mkdir(parents=True)
    mine = home / "Documents" / "Proposal.docx"; mine.write_text("x")
    monkeypatch.setenv("HOME", str(home))
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path / "data"), raising=False)
    app._setup_task_system()
    opened = []
    app.task_runner.device.open_file = lambda p: opened.append(p)
    async def nojs(self, s): pass
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", nojs)
    from urllib.parse import quote
    queued = [[{"type": "open_url", "value": "gink://open/" + quote("/etc/passwd")}], [],
              [{"type": "open_url", "value": "gink://open/" + quote(str(home / "Documents" / ".." / ".." / "secret"))}], [],
              [{"type": "open_url", "value": "gink://open/" + quote(str(mine))}]]
    async def fake_poll(self): return queued.pop(0) if queued else []
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", fake_poll)
    async def go():
        main_screen.build_main_screen(app, "ib@example.com")
        for _ in range(30): await asyncio.sleep(0.05)
        app._main_screen_token = None; app.task_scheduler.stop()
    asyncio.run(go())
    assert opened == [os.path.realpath(str(mine))]                    # outside home / tricks: refused


def test_briefing_lists_render_as_real_lists(tmp_path):
    """Regression: no blank line before '- ...' made every briefing list plain text with dashes."""
    from ginkassistant.services import briefing
    from ginkassistant.services.actions import TaskStore
    from ginkassistant.services.markdown_render import render_markdown_body
    store = TaskStore(str(tmp_path / "t.db"))
    store.add("event", "Study group", due=datetime(2026, 10, 13, 16, 0))
    store.add("task", "Revise maths")
    md, _ = asyncio.run(briefing.build_briefing(store, {}, "Ib", now=datetime(2026, 10, 13, 7, 40)))
    html = render_markdown_body(md)
    assert html.count("<ul>") >= 2 and "<li>" in html and "- 16:00" not in html
