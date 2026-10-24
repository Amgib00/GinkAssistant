"""Security history, Lockdown mode (server-enforced) and Personalization."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "gid"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gs")
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "qwen/qwen3.8-27b"}]})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._login_failures.clear(); b._code_sends.clear()
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "pro"})
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse 42"), "password")
    return b, TestClient(b.app)


def login(c, password="correct horse 42", **headers):
    r = c.post("/auth/login", json={"email": "ib@example.com", "password": password}, headers=headers)
    return {"Authorization": "Bearer " + r.json()["token"]} if r.status_code == 200 else r


def test_security_history(srv):
    b, c = srv
    me = login(c, **{"X-Gink-Device": "Gink for Mac"})
    login(c, password="wrong-pass-1")
    secret = c.post("/account/2fa/setup", headers=me).json()["secret"].replace(" ", "")
    c.post("/account/2fa/enable", headers=me, json={"code": b._totp(secret, int(time.time() // 30) - 1)})
    c.post("/account/api-keys", headers=me, json={"name": "backend"})
    c.post("/account/lockdown", headers=me, json={"on": True})
    events = c.get("/account/security-history", headers=me).json()["events"]
    texts = [e["text"] for e in events]
    assert texts == ["Lockdown mode turned on", "API key created: backend", "Two-step verification turned on",
                     "Wrong password entered", "Signed in"]                                       # newest first
    assert events[-1]["device"] == "Gink for Mac"
    b._upsert_user("eve@example.com", "Eve", b._hash_password("another pass 42"), "password")
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert [e["text"] for e in c.get("/account/security-history", headers=eve).json()["events"]] == ["Signed in"]
    c.post("/account/delete", headers=me, json={"confirm": "DELETE"})
    assert b._db().execute("SELECT COUNT(*) FROM security_events WHERE email='ib@example.com'").fetchone()[0] == 0


def test_lockdown_mode_is_enforced_by_the_server(srv):
    b, c = srv
    me = login(c)
    assert c.get("/account/lockdown", headers=me).json() == {"on": False}
    c.post("/account/lockdown", headers=me, json={"on": True})
    chat = lambda **kw: c.post("/ai/openai/v1/chat/completions", headers=me, json={"model": "gink-crystal", **kw})
    hello = [{"role": "user", "content": "hello"}]
    r = chat(messages=hello, gink_web=True)
    assert r.status_code == 403 and "Lockdown mode is on" in r.text and "web search" in r.text
    assert c.post("/web/search", headers=me, json={"query": "news"}).status_code == 403
    assert c.post("/connected/calendar/begin", headers=me).status_code == 403
    picture = [{"role": "user", "content": [{"type": "text", "text": "what's this?"},
                                            {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}}]}]
    assert chat(messages=picture).status_code == 403
    assert chat(messages=hello).status_code == 200                                               # normal chat works
    c.post("/account/lockdown", headers=me, json={"on": False})
    assert c.post("/connected/calendar/begin", headers=me).status_code == 200                     # back on


def test_personalization():
    from ginkassistant.services import personality
    assert personality.note({}) == "" and personality.note({"style_base": "default"}) == ""
    n = personality.note({"style_base": "concise", "style_emoji": "less", "style_headers": "more"})
    assert "Be brief" in n and "Don't use emoji" in n and "headers and lists" in n
    import types
    from ginkassistant.services import prefs
    from ginkassistant.ui.settings_controller import SettingsController
    ctl = SettingsController.__new__(SettingsController); ctl.app = types.SimpleNamespace()
    prefs_data = {"reply_language": "auto", "style_base": "friendly"}
    orig = prefs.load
    prefs.load = lambda app: dict(prefs_data)
    try:
        note = ctl.reply_language_note()                         # what the chat and the agent receive
    finally:
        prefs.load = orig
    assert "same language the user writes in" in note and "warm, friendly" in note


def test_passkey_server_rules(srv):
    b, c = srv
    me = login(c)
    opts = c.post("/account/passkeys/register/begin", headers=me).json()
    assert opts["rp"]["name"] == "Gink" and opts["authenticatorSelection"]["userVerification"] == "required"
    assert opts["authenticatorSelection"]["residentKey"] == "required" and opts["user"]["name"] == "ib@example.com"
    fake = {"id": "abc", "rawId": "abc", "type": "public-key", "response": {"clientDataJSON": "e30", "attestationObject": "oA"}}
    r = c.post("/account/passkeys/register/finish", headers=me, json={"credential": fake})
    assert r.status_code == 400 and "couldn't be added" in r.json()["detail"]
    assert c.post("/account/passkeys/register/finish", headers=me, json={"credential": fake}).status_code == 400   # challenge used up
    begin = c.post("/auth/passkey/signin/begin").json()
    assert begin["options"]["userVerification"] == "required" and begin["request_id"]
    r = c.post("/auth/passkey/signin/finish", json={"request_id": begin["request_id"], "credential": {"id": "nobody"}})
    assert r.status_code == 401 and "isn't linked" in r.json()["detail"]
    assert c.post("/auth/passkey/signin/finish", json={"request_id": begin["request_id"], "credential": {"id": "x"}}).status_code == 400
    b._pk_db(lambda con: con.execute("INSERT INTO passkeys (id, email, public_key, created) VALUES ('k1', 'ib@example.com', 'pk', 1)"))
    assert [k["id"] for k in c.get("/account/passkeys", headers=me).json()["passkeys"]] == ["k1"]
    b._upsert_user("eve@example.com", "Eve", b._hash_password("another pass 42"), "password")
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.delete("/account/passkeys/k1", headers=eve).status_code == 404                                       # not hers
    c.post("/account/delete", headers=me, json={"confirm": "DELETE"})
    assert b._pk_db(lambda con: con.execute("SELECT COUNT(*) FROM passkeys").fetchone()[0]) == 0
