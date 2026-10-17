"""Every screen builds with the new theme; server address saving;
login-server health route."""
import asyncio, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import toga


def _app(tmp_path, monkeypatch):
    import ginkassistant.app as app_mod
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = app_mod.GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config", "cache", "logs"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self, a=attr: tmp_path / a), raising=False)
    return app


def test_server_address_saved_and_used(tmp_path, monkeypatch):
    from ginkassistant.services import server_config as sc
    monkeypatch.delenv("GINK_API_URL", raising=False)
    app = _app(tmp_path, monkeypatch)
    assert sc.resolve_base_url(app) == sc.platform_default()
    assert sc.save_url(app, "192.168.1.20:8001") == "http://192.168.1.20:8001"
    assert sc.resolve_base_url(app) == "http://192.168.1.20:8001"
    assert sc.save_url(app, "gink.onrender.com/") == "https://gink.onrender.com"
    sc.save_url(app, "")
    assert sc.saved_url(app) is None
    monkeypatch.setenv("GINK_API_URL", "http://override:1")
    assert sc.resolve_base_url(app) == "http://override:1"


def test_check_server_against_real_backend(monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server, server_config as sc
    assert TestClient(backend_server.app).get("/health").json()["status"] == "ok"
    transport = httpx.ASGITransport(app=backend_server.app)
    real = httpx.AsyncClient
    monkeypatch.setattr(sc.httpx, "AsyncClient", lambda **k: real(transport=transport, **k))
    ok, msg = asyncio.run(sc.check_server("http://testserver"))
    assert ok, msg
    ok, msg = asyncio.run(sc.check_server(""))
    assert not ok


def test_all_screens_build(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    from ginkassistant.ui.login_screen import build_login_screen
    from ginkassistant.ui.media_studio_screen import build_media_studio_screen
    from ginkassistant.ui.toga_live_tv import build_live_tv_view
    from ginkassistant.ui.settings_screen import build_settings_screen
    from ginkassistant.services.groq_worker import GroqBrain
    from ginkassistant.ui import theme

    async def go():
        login = build_login_screen(app, on_success=lambda e: None)
        assert isinstance(login.children[0], toga.WebView)    # whole login screen is one page
        build_media_studio_screen(app, on_back=lambda: None)
        build_live_tv_view(app, on_back=lambda: None)
        brain = GroqBrain(app, session_id="t")
        logged_out = []
        settings = build_settings_screen(app, brain, {"value": next(iter(__import__("ginkassistant.services.voice_bridge", fromlist=["VOICES"]).VOICES))},
                                         lambda v: None, on_back=lambda: None, on_log_out=lambda: logged_out.append(1))
        btns = []
        def walk(w):
            if isinstance(w, toga.Button): btns.append(w)
            for c in getattr(w, "children", []) or []: walk(c)
            if getattr(w, "content", None) is not None and not isinstance(w, toga.Window): walk(w.content)
        walk(settings)
        logout = [b for b in btns if b.text == "Log out"]
        assert logout, [b.text for b in btns]
        logout[0].on_press()
        assert logged_out == [1]
    asyncio.run(go())
    assert theme.LOGO_LIME.lower() == "#a8f03c"


def test_composer_page_has_claude_style_controls():
    from ginkassistant.ui import web_chat_view as w
    t = w._PAGE_TEMPLATE
    for el in ('id="composer"', 'id="cin"', 'id="plus"', 'id="model"', 'id="mic"', 'id="send"', 'id="acct-menu"', 'id="settings-back"',
               'data-act="tasks"', 'data-act="song"', "function ginkTake"):
        assert el in t if el not in ('id="acct-menu"', 'id="settings-back"') else el in w._build_page_html("Hi", ""), el
    assert 'id="orb"' not in t                    # status ring removed (matches the reference design)
    from ginkassistant.ui import theme
    assert theme.BG_MAIN == "#FFFFFF"


def test_welcome_starts_centred_and_moves_down_on_first_message():
    from ginkassistant.ui import web_chat_view as w
    html = w._build_page_html("Good afternoon, Ibrahim", "Just ask")
    assert '<body class="home">' in html                       # starts as the centred bar
    assert "Good afternoon, Ibrahim" in html
    hide = html[html.index("function hideWelcome"):html.index("function clearFeed")]
    assert "classList.remove('home')" in hide                  # first message -> glides down
    show = html[html.index("function showWelcome"):html.index("function addUserMessage")]
    assert "classList.add('home')" in show                     # new chat -> back to centre
    assert "function layoutComposer" in html and "Ask Gink" in html


def test_sidebar_page_has_hover_peek_recents_gear_and_delete_dialog():
    from ginkassistant.ui import web_chat_view as w
    html = w._build_page_html("Hi", "x")
    for el in ('id="side"', 'id="edge"', 'id="tb-toggle"', 'data-nav="new"',
               'data-nav="search"', 'id="recents"', 'id="gear"', 'Delete chat?', 'id="del-ok"',
               "function setSessions", "mouseenter", "ginkEmit('delete_session'"):
        assert el in html, el


def test_user_message_actions_and_live_rendering():
    from ginkassistant.ui import web_chat_view as w
    html = w._build_page_html("Hi", "x")
    for el in ('data-ua="retry"', 'data-ua="edit"', 'data-ua="copy"', 'data-ua="more"',
               'Branch to new chat', 'Read aloud', "function renderStream", "SPIN_URI",
               'data-nav="tasks"', ">Workspace<"):
        assert el in html, el
    assert 'data-nav="livetv"' not in html                      # Live TV removed from sidebar
    assert w._close_open_markdown("Automation **wi") == "Automation wi"
    assert w._close_open_markdown("```py\nx=1").endswith("```")


def test_workspace_filters_stats_and_clear_done(tmp_path):
    from ginkassistant.services.actions import TaskStore, TaskAgent, ToolRunner, DeviceActions
    from ginkassistant.ui.tasks_screen import TasksScreen
    from datetime import datetime, timedelta
    store = TaskStore(str(tmp_path / "t.db"))
    runner = ToolRunner(store, DeviceActions(str(tmp_path)))
    scr = TasksScreen(toga.App("t", "org.t"), store, TaskAgent(runner))
    t = store.add("task", "Revise maths")
    store.add("task", "Past papers", parent_id=t.id)
    store.add("alarm", "Wake up", due=datetime.now() + timedelta(hours=8))
    done = store.add("reminder", "Old one", due=datetime.now() - timedelta(hours=1))
    store.set_done(done.id, True)
    scr.refresh()
    assert scr.stat_labels["tasks"].text == "1" and scr.stat_labels["alarms"].text == "1"
    scr._set_kind("alarm")
    assert len(scr.list_box.children) == 1
    scr._set_kind(None)
    texts = []
    def walk(x):
        texts.append(getattr(x, "text", ""))
        for c in getattr(x, "children", []) or []: walk(c)
    walk(scr.list_box)
    assert any("0/1 steps done" in t for t in texts)
    scr._clear_done(None)
    assert all(not i.done for i in store.list(include_done=True))


def test_finish_logo_links_sidebar_toggle_and_history_animation():
    from ginkassistant.ui import web_chat_view as w
    html = w._build_page_html("Hi", "x")
    assert ".msg-logo { display: block; width: 26px; height: 26px; margin: 14px auto 0;" in html
    assert "ginkEmit('open_url'" in html and "window.open(" not in html
    assert html.count('id="tb-toggle"') == 1 and 'id="side-toggle"' not in html   # one button
    assert "function toggleSidebar" in html and "hoverBlocked" in html
    assert "function typeTitle" in html and ".recent.fresh" in html


def _asgi_api(monkeypatch, backend_app):
    """Point the app's ApiClient at the backend in-process (no network)."""
    import httpx
    from ginkassistant.services import api_client
    transport = httpx.ASGITransport(app=backend_app)
    real = httpx.AsyncClient
    monkeypatch.setattr(api_client.httpx, "AsyncClient", lambda **k: real(transport=transport, base_url="http://t", **k))


def test_login_page_signup_verify_login_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui import login_screen as ls
    app = _app(tmp_path, monkeypatch)
    app.state.base_url = "http://t"
    _asgi_api(monkeypatch, b.app)
    done = []
    calls = []

    async def go():
        box = ls.build_login_screen(app, on_success=lambda e: done.append(e))
        c = box._login_controller
        async def rec(fn, *args): calls.append((fn, args))
        c.call = rec
        async def nojs(script): calls.append(("js", (script,)))
        c.js = nojs
        await c.handle({"type": "ready"})
        assert calls[-1][0] == "setProviders" and "google" in calls[-1][1][0]
        await c.handle({"type": "signup", "value": {"name": "Ibrahim", "email": "ib@x.co", "password": "gink2026!"}})
        assert ("show", ("verify", {"email": "ib@x.co"})) in calls
        await c.handle({"type": "verify", "value": {"code": "000000"}})
        assert calls[-1][0] == "error"
        await c.handle({"type": "verify", "value": {"code": b._pending_signups["ib@x.co"]["code"]}})
        assert done == ["ib@x.co"] and ls.load_saved_session(app)["email"] == "ib@x.co"
        # wrong password, then right one
        c2 = ls.build_login_screen(app, on_success=lambda e: done.append("again:" + e))._login_controller
        c2.call = rec; c2.js = nojs
        await c2.handle({"type": "login", "value": {"email": "ib@x.co", "password": "wrong1234", "remember": False}})
        assert calls[-1] == ("error", ("Email or password is incorrect.",))
        await c2.handle({"type": "login", "value": {"email": "ib@x.co", "password": "gink2026!", "remember": False}})
        assert done[-1] == "again:ib@x.co"
        # forgot -> reset
        c3 = ls.build_login_screen(app, on_success=lambda e: done.append("reset:" + e))._login_controller
        c3.call = rec; c3.js = nojs
        await c3.handle({"type": "forgot", "value": {"email": "ib@x.co"}})
        await c3.handle({"type": "reset", "value": {"code": b._reset_codes["ib@x.co"]["code"], "password": "brandnew42"}})
        assert done[-1] == "reset:ib@x.co"
    asyncio.run(go())


def test_social_sign_in_round_trip(tmp_path, monkeypatch):
    """Browser part simulated: provider redirects back to /callback, app polls."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui import login_screen as ls
    monkeypatch.setattr(b, "_identity_from_code", lambda p, code, uri, user="": ("ada@example.com", "Ada"))
    server = TestClient(b.app)
    app = _app(tmp_path, monkeypatch)
    app.state.base_url = "http://t"
    _asgi_api(monkeypatch, b.app)

    def fake_browser(_app, url):        # the "browser": follow start -> provider -> callback
        start = server.get(url.replace("http://t", ""), follow_redirects=False)
        assert start.status_code in (302, 307) and "accounts.google.com" in start.headers["location"]
        state = url.split("state=")[1]
        assert "signed in" in server.get(f"/auth/google/callback?state={state}&code=abc").text
        return True
    monkeypatch.setattr(ls, "_open_in_browser", fake_browser)
    done = []

    async def go():
        c = ls.build_login_screen(app, on_success=lambda e: done.append(e))._login_controller
        async def rec(fn, *args): pass
        c.call = rec
        await c.handle({"type": "oauth", "value": "google"})
    asyncio.run(go())
    assert done == ["ada@example.com"]


def test_apple_client_secret_is_es256(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import jwt
    from ginkassistant.services import backend_server as b
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    for k, v in {"APPLE_CLIENT_ID": "com.amgib.gink", "APPLE_TEAM_ID": "TEAM123", "APPLE_KEY_ID": "KEY123",
                 "APPLE_PRIVATE_KEY": pem}.items():
        monkeypatch.setenv(k, v)
    tok = b._client_secret("apple")
    assert jwt.get_unverified_header(tok)["kid"] == "KEY123"
    claims = jwt.decode(tok, key.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com")
    assert claims["iss"] == "TEAM123" and claims["sub"] == "com.amgib.gink"


def test_social_sign_in_survives_a_slow_browser(tmp_path, monkeypatch):
    """Regression: the app used to poll before the browser reached /start,
    got 404 and showed "Sign-in expired". Here the browser only shows up
    after several polls."""
    import threading, time as _t
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui import login_screen as ls
    monkeypatch.setattr(b, "_identity_from_code", lambda p, code, uri, user="": ("slow@example.com", "Slow"))
    server = TestClient(b.app)
    app = _app(tmp_path, monkeypatch)
    app.state.base_url = "http://t"
    _asgi_api(monkeypatch, b.app)
    polls = []
    real_poll = ls.ApiClient.oauth_poll
    async def counting_poll(self, state):
        polls.append(state)
        return await real_poll(self, state)
    monkeypatch.setattr(ls.ApiClient, "oauth_poll", counting_poll)

    def slow_browser(_app, url):
        state = url.split("state=")[1]
        def later():
            while len(polls) < 2:              # app is already polling...
                _t.sleep(0.05)
            server.get(url.replace("http://t", ""), follow_redirects=False)
            server.get(f"/auth/google/callback?state={state}&code=abc")
        threading.Thread(target=later, daemon=True).start()
        return True
    monkeypatch.setattr(ls, "_open_in_browser", slow_browser)
    errors, done = [], []

    async def go():
        c = ls.build_login_screen(app, on_success=lambda e: done.append(e))._login_controller
        async def rec(fn, *args):
            if fn == "error": errors.append(args)
        c.call = rec
        await c.handle({"type": "oauth", "value": "google"})
    asyncio.run(go())
    assert errors == [] and done == ["slow@example.com"] and len(polls) >= 2


def test_phones_default_to_the_online_server(monkeypatch):
    """A real phone can't reach a server on the Mac (10.0.2.2 only works in the emulator)."""
    from ginkassistant.services import server_config as sc, platform_utils as pu
    monkeypatch.setattr(pu, "is_mobile", lambda: True)
    assert sc.platform_default() == sc.ONLINE_SERVER and sc.ONLINE_SERVER.startswith("https://")
    monkeypatch.setattr(pu, "is_mobile", lambda: False)
    assert sc.platform_default() == "http://127.0.0.1:8000"


def test_online_servers_get_time_to_wake_up():
    """Render's free plan sleeps; waking takes up to ~60 s. 8-15 s limits gave 'ReadTimeout'."""
    from ginkassistant.services import server_config as sc
    from ginkassistant.services.api_client import ApiClient
    assert ApiClient("https://gink-server.onrender.com").timeout >= 60
    assert ApiClient("http://127.0.0.1:8000").timeout <= 15
    assert "wake" in sc.WAKING_UP


def test_check_server_explains_a_timeout(monkeypatch):
    import asyncio, httpx
    from ginkassistant.services import server_config as sc
    class Slow:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(httpx, "AsyncClient", Slow)
    ok, msg = asyncio.run(sc.check_server("https://gink-server.onrender.com"))
    assert not ok and msg == sc.WAKING_UP
