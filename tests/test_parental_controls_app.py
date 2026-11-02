"""Parental controls in the apps: Settings actions against a real server, the sign-up birth year,
and voice switched off on the device when a parent turns it off."""
import asyncio, json, os, sys, threading, time, types
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest

Y = time.gmtime().tm_year


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn
    old_db = os.environ.get("GINK_DB_PATH")
    os.environ["GINK_DB_PATH"] = str(tmp_path_factory.mktemp("fam") / "fam.db")
    from ginkassistant.services import backend_server as b
    real_send = b._send_email
    b._send_email = lambda *a, **k: ""
    srv = uvicorn.Server(uvicorn.Config(b.app, port=8815, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    time.sleep(1.5)
    try:
        yield b, "http://127.0.0.1:8815"
    finally:
        srv.should_exit = True
        b._send_email = real_send                       # other tests check real email behaviour
        if old_db is None:
            os.environ.pop("GINK_DB_PATH", None)
        else:
            os.environ["GINK_DB_PATH"] = old_db


def controller(base, email, b):
    from ginkassistant.ui.settings_controller import SettingsController
    c = SettingsController.__new__(SettingsController)
    c.app = types.SimpleNamespace(state=types.SimpleNamespace(base_url=base),
                                  session_token=b._token_response(email, email.split("@")[0])["token"])
    toasts, refreshed = [], []

    class Web:
        async def settings_toast(self, text, kind=None): toasts.append(text)
    c.web = Web()
    async def refresh(panel=""): refreshed.append(panel)
    c.refresh = refresh
    return c, toasts, refreshed


def test_settings_actions_link_and_control(server):
    b, base = server
    b._upsert_user("mum@x.co", "Aminata", None, "password")
    b._upsert_user("moussa@x.co", "Moussa", None, "password")
    b._set_birth_year("moussa@x.co", Y - 15)
    mum, mt, mr = controller(base, "mum@x.co", b)
    teen, tt, tr = controller(base, "moussa@x.co", b)
    run = asyncio.run
    run(mum._a_family_invite("moussa@x.co"))
    assert "birth year" in mt[-1]                                              # parents need a birth year first
    run(mum._a_family_birth_year("1986"))
    assert mt[-1] == "Saved." and mr[-1] == "family"
    run(mum._a_family_invite("moussa@x.co"))
    assert mt[-1].startswith("Invitation sent")
    run(teen._a_family_accept(None))
    assert tt[-1] == "Linked." and b._family_rules("moussa@x.co")["controls"] is not None
    tz = "Africa/Dakar"
    run(mum._a_family_set(json.dumps({"teen": "moussa@x.co", "key": "images", "value": False, "tz": tz})))
    run(mum._a_family_set(json.dumps({"teen": "moussa@x.co", "key": "quiet_from", "value": "22:00", "tz": tz})))
    run(mum._a_family_set(json.dumps({"teen": "moussa@x.co", "key": "daily_limit", "value": 30, "tz": tz})))
    c = b._controls("moussa@x.co")
    assert c["images"] is False and c["quiet_from"] == "22:00" and c["tz"] == tz and c["daily_limit"] == 30
    run(mum._a_family_set(json.dumps({"teen": "moussa@x.co", "key": "quiet_to", "value": "99:00", "tz": tz})))
    assert "21:30" in mt[-1]                                                   # "Use times like 21:30."
    run(teen._a_family_unlink(""))
    assert tt[-1] == "Unlinked." and b._link_of("moussa@x.co") is None


def test_app_sign_up_sends_the_birth_year(server):
    b, base = server
    from ginkassistant.services.api_client import ApiClient, ApiError
    async def go():
        with pytest.raises(ApiError, match="13 and older"):
            await ApiClient(base).register("Kid", "kid@x.co", "gink2026!", Y - 9)
    asyncio.run(go())
    assert "kid@x.co" not in b._pending_signups


def test_voice_off_on_the_device(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    spoke = []
    async def speak(text, voice_key="x", on_amplitude=None): spoke.append(text)
    async def listen(on_amplitude=None): return "hello"
    monkeypatch.setattr(vb, "_speak_any", speak)
    monkeypatch.setattr(vb, "_listen_any", listen)
    try:
        vb.blocked[0] = ""
        assert asyncio.run(vb.listen()) == "hello"
        asyncio.run(vb.speak("hi")); assert spoke == ["hi"]
        vb.blocked[0] = "Voice is turned off in your parental controls."
        asyncio.run(vb.speak("again")); assert spoke == ["hi"]
        with pytest.raises(vb.VoiceUnavailable, match="parental controls"):
            asyncio.run(vb.listen())
    finally:
        vb.blocked[0] = ""


def test_pages_have_the_pieces():
    root = os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant")
    login = open(os.path.join(root, "ui", "login_screen.py"), encoding="utf-8").read()
    auth = open(os.path.join(root, "services", "web_app", "auth.html"), encoding="utf-8").read()
    for page in (login, auth):
        assert "Gink is for people 13 and older." in page and "birth_year" in page
    settings = open(os.path.join(root, "ui", "settings_page.py"), encoding="utf-8").read()
    assert "id: 'family'" in settings and "function askBirthYear" in settings
    bridge = open(os.path.join(root, "..", "..", "webapp", "bridge.js"), encoding="utf-8").read()
    for name in ("family_birth_year", "family_invite", "family_accept", "family_decline", "family_unlink", "family_set",
                 "HANDLERS.birth_year", "checkFamily()"):
        assert name in bridge
