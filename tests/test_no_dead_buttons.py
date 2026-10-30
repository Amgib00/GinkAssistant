"""Every button does something, on every platform (Upgrade in the apps and Delete account on the web did nothing)."""
import os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
read = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _actions():
    """{action: shown_on_web} for every Settings row/button."""
    sp = read("src", "ginkassistant", "ui", "settings_page.py")
    out = {}
    for line in sp.splitlines():
        for a in re.findall(r"action: '([a-z_]+)'", line) + re.findall(r'data-act="([a-z_]+)"', line):
            out[a] = out.get(a, False) or ("apps: true" not in line)
    return out


def test_every_settings_action_works_in_the_apps():
    ctl = read("src", "ginkassistant", "ui", "settings_controller.py")
    handled = set(re.findall(r"def _a_([a-z_]+)\(", ctl))
    web_only = {"passkey_add"}                                     # passkeys are added in a browser
    missing = sorted(a for a in _actions() if a not in handled and a not in web_only)
    assert missing == [], f"Settings buttons that do nothing in the apps: {missing}"


def test_every_settings_action_shown_on_the_web_works_there():
    bridge = read("webapp", "bridge.js")
    sa = bridge[bridge.index("settings_action: function"):]
    handled = set(re.findall(r'name === "([a-z_]+)"', sa))
    missing = sorted(a for a, on_web in _actions().items() if on_web and a not in handled)
    # hidden on the web by their structure (the line check can't see it): save_city is on the City row's second
    # line, forget_memory is inside the memories list, free_storage is in the apps' Storage panel, and
    # remove_photo belongs to the photo row -- all of them marked apps: true (checked below)
    explained = {"save_city", "forget_memory", "free_storage", "remove_photo"}
    sp = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "{apps: true, type: 'photo'" in sp and "{apps: true, type: 'list', items: (L.memories" in sp
    assert "{apps: true, type: 'input', key: 'city'" in sp and "sections: info.web ? [" in sp
    assert [a for a in missing if a not in explained] == [], f"buttons shown on the web that only say 'use the app': {missing}"


def test_every_page_event_is_handled_by_the_apps():
    ui = os.path.join(ROOT, "src", "ginkassistant", "ui")
    pages = ["web_chat_view.py", "chat_extras.py", "settings_page.py", "agent_ui.py", "voice_ui.py", "wake_ui.py", "update_ui.py"]
    sent = set()
    for f in pages:
        sent |= set(re.findall(r"ginkEmit\(\s*['\"]([a-z_]+)['\"]", read("src", "ginkassistant", "ui", f)))
    handled = set()
    for f in os.listdir(ui):
        if f.endswith(".py"):
            t = read("src", "ginkassistant", "ui", f)
            handled |= set(re.findall(r'kind\s*==\s*"([a-z_]+)"', t)) | set(re.findall(r'event\.get\("type"\)\s*==\s*"([a-z_]+)"', t))
            for grp in re.findall(r"kind\s+in\s+\(([^)]*)\)", t):
                handled |= set(re.findall(r'"([a-z_]+)"', grp))
    assert sorted(sent - handled) == [], f"page events nobody handles in the apps: {sorted(sent - handled)}"


def test_downloads_links_and_instructions_on_the_web():
    page = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "if (link.hasAttribute('download')) return;" in page          # the link catcher blocked every download
    bridge = read("webapp", "bridge.js")
    assert 'if (what === "pro") { window.open(PRICING' in bridge and "/^(mailto|tel|sms):/i.test(u)" in bridge
    assert "The person's own instructions for you" in bridge
    settings = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "if (S.info && S.info.web) panels.forEach" in settings       # S.info: `info` doesn't exist where Settings draws


def test_instructions_sync_allows_a_paragraph(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "src"))
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "i.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    text = "Keep answers short. " * 50                                  # 1000 characters
    r = c.put("/account/preferences", headers=h, json={"prefs": {"instructions": text, "theme": "x" * 1000}}).json()
    assert r["prefs"] == {"instructions": text}                          # a paragraph for instructions; other settings stay short


def test_no_window_title_and_chats_glide_open():
    app = read("src", "ginkassistant", "app.py")
    assert 'toga.MainWindow(title="")' in app                          # no "Gink" in the title bar, every platform
    page = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "window.loadChat = function" in page and "behavior: 'smooth'" in page and "@keyframes logo-land" in page
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "await web_chat.load_chat(history, _new_message_id)" in main  # one step: no "Thinking..." flicker
    assert "if (window.glideToEnd) glideToEnd();" in read("webapp", "bridge.js")
