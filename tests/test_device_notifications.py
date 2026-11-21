"""Gink's notifications on the device (0.1.162): every notification card also goes to Notification Center on a Mac
(Windows, Linux, Android and iPhone notifications too) when Gink isn't in front; quick confirmations stay in the window;
Settings turns it off and sends a test; the web app uses the browser's own notifications."""
import asyncio
import os
import re
import sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def _linux(monkeypatch):
    from ginkassistant.services import system_notify as sn
    from ginkassistant.services.actions import notify as n
    for name in ("MAC", "WIN", "IOS", "ANDROID"):
        monkeypatch.setattr(sn, name, False)
    sent = []
    monkeypatch.setattr(n, "notify", lambda title, body="", loud=False: sent.append((title, body)) or True)
    sn._state["recent"].clear()
    return sn, sent


def test_only_when_gink_isn_t_in_front_and_never_twice(monkeypatch):
    sn, sent = _linux(monkeypatch)
    assert not sn.post("Morning news", "Three stories", "task-1", page_visible=True)        # in front: the card is enough
    assert sn.post("Morning news", "Three stories", "task-1", page_visible=False)
    assert not sn.post("Morning news", "Three stories", "task-1", page_visible=False)       # the same again: once
    assert sn.post("Morning news", "Four stories", "task-1", page_visible=False)            # a new result: yes
    assert sn.post("Notifications work", "Test", "test", page_visible=True, force=True)      # Settings > Test: always
    assert sent == [("Morning news", "Three stories"), ("Morning news", "Four stories"), ("Notifications work", "Test")]
    monkeypatch.setattr(sn, "in_front", lambda: True)                                        # the system says it's in front
    assert not sn.post("Gink is having trouble", "Search isn't working", "status", page_visible=False)
    assert sn.where() == "desktop notifications" or not sys.platform.startswith("linux")


def test_mac_uses_its_own_notifications_in_the_app_and_respects_a_no(monkeypatch):
    sn, sent = _linux(monkeypatch)
    monkeypatch.setattr(sn, "MAC", True)
    monkeypatch.setattr(sn, "in_front", lambda: False)
    posted = []
    monkeypatch.setattr(sn, "_apple_center", lambda: None)                                    # from source: Script Editor's
    assert sn.post("Privacy policy and terms updated", "Plain words", "policy") and sent[-1][0] == "Privacy policy and terms updated"
    monkeypatch.setattr(sn, "_apple_center", lambda: object())                                # the built Gink.app
    monkeypatch.setattr(sn, "_apple_post", lambda t, b, i, q=False: posted.append((t, b, i)) or True)
    sn._state["recent"].clear()
    assert sn.post("Gink 0.1.162 is available", "Download it", "update") and posted == [("Gink 0.1.162 is available", "Download it", "update")]
    monkeypatch.setattr(sn, "_apple_post", lambda t, b, i, q=False: False)
    sn._state.update(granted=False, refused=False)                                            # they turned Gink's off
    sn._state["recent"].clear()
    count = len(sent)
    assert not sn.post("Morning news", "x", "task-2") and len(sent) == count                   # no Script Editor detour
    assert "System Settings > Notifications > Gink" in sn.status()
    sn._state.update(granted=None, refused=False)
    assert sn.where() == "Notification Center"
    # Gink in front: macOS 11+ puts it quietly in Notification Center's list (no banner, no sound); 10.15: not at all
    quiet = []
    monkeypatch.setattr(sn, "in_front", lambda: True)
    monkeypatch.setattr(sn, "_apple_post", lambda t, b, i, q=False: quiet.append((i, q)) or True)
    monkeypatch.setattr(sn, "mac_lists_quietly", lambda: True)
    sn._state["recent"].clear()
    assert sn.post("Privacy policy and terms updated", "Plain words", "policy") and quiet == [("policy", True)]
    monkeypatch.setattr(sn, "mac_lists_quietly", lambda: False)
    sn._state["recent"].clear()
    assert not sn.post("Morning news", "y", "task-3") and len(quiet) == 1
    assert sn.post("Notifications work", "Test", "test", force=True) and quiet[-1] == ("test", False)
    code = read("src", "ginkassistant", "services", "system_notify.py")
    assert '8 if ident.startswith("gink-quiet-") else 2 | 4 | 8 | 16' in code
    # the built app only: from source, asking for UNUserNotificationCenter would stop the process
    code = read("src", "ginkassistant", "services", "system_notify.py")
    assert 'path.endswith(".app") and "gink" in ident.lower()' in code
    assert "requestAuthorizationWithOptions_completionHandler_(7" in code and "Block(done, None, c_bool, objc_id)" in code


def test_the_chat_window_mirrors_its_cards_but_not_quick_confirmations():
    from ginkassistant.ui.web_chat_view import WebChatFeed
    feed = WebChatFeed.__new__(WebChatFeed)
    scripts, device = [], []

    async def js(script):
        scripts.append(script)
    feed._js = js
    feed.on_system_notify = lambda t, b, i: device.append((t, b, i))

    async def go():
        await feed.notify("Morning news", "Three stories", nid="task-1")
        await feed.notify("Undone", "Gink won't remember that.", nid="mem-auto", system=False)
        await feed.status_bar("ok", "")
        await feed.status_bar("degraded", "Search isn't working right now.")
        await feed.policy_notice("2026-11-20", "https://example.org/p", "https://example.org/t")
        await feed.show_update("v0.1.163")
    asyncio.run(go())
    assert [d[2] for d in device] == ["task-1", "status", "policy", "update"]
    assert device[1][0] == "Gink is having trouble" and device[3][0] == "Gink 0.1.163 is available"
    feed.on_system_notify = lambda *a: 1 / 0                                                   # never breaks the chat
    asyncio.run(feed.notify("x"))


def test_the_main_screen_settings_and_web_app_are_wired():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "web_chat.on_system_notify = device_notification" in main and "system_notify.ask_permission()" in main
    assert 'prefs.load(app).get("notify_system", True)' in main and 'page_seen["visible"] = value != "hidden"' in main
    assert "def system_notification(" not in main and "osascript" not in main                 # one way, the new one
    for confirm in ('"Undone"', '"Snoozed"', 'nid="task-action", system=False', 'nid="artifact-tab", system=False'):
        assert confirm in main, confirm
    assert re.search(r'system=False\)', main.split('"Snoozed"')[1][:200])
    from ginkassistant.services import prefs
    from ginkassistant.ui import settings_controller as sc
    assert prefs.DEFAULTS["notify_system"] is True and "notify_system" not in prefs.SYNCED      # this device only
    assert "notify_system" in sc.BOOL_KEYS and hasattr(sc.SettingsController, "_a_test_notify")
    page = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "key: 'notify_system'" in page and "action: 'test_notify'" in page and "'Browser notifications'" in page
    assert "ginkNotify({id: 'settings', system: false" in page
    chat = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "if (o.system !== false && typeof window.ginkSystemNotify === 'function')" in chat
    bridge = read("webapp", "bridge.js")
    assert "window.ginkSystemNotify = function (o)" in bridge and "W.prefs.notify_system === false" in bridge
    assert bridge.count("new Notification(") == 1                                             # one place for them all
    assert 'v.key === "notify_system" && v.value' in bridge
