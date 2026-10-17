"""Gink Developer API: keys (shown once, stored hashed), OpenAI-compatible endpoints, limits, isolation."""
import json, os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

LIVE = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "whisper-large-v3", "groq/compound"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    sent = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in LIVE]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler),
                                                                    **{x: y for x, y in k.items() if x != "transport"}))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._api_recent.clear()
    c = TestClient(b.app)
    session = lambda email: {"Authorization": "Bearer " + b._token_response(email, "U")["token"]}
    return b, c, session, sent


def chat(c, key, **extra):
    return c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}", **extra.pop("headers", {})},
                  json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "hello"}], **extra})


def test_key_is_shown_once_and_stored_only_as_a_fingerprint(api):
    b, c, session, sent = api
    made = c.post("/account/api-keys", json={"name": "My app"}, headers=session("dev@x.co")).json()
    key = made["key"]
    assert key.startswith("gink_live_") and len(key) > 40
    listed = c.get("/account/api-keys", headers=session("dev@x.co")).json()["keys"]
    assert len(listed) == 1 and "key" not in listed[0] and listed[0]["hint"].endswith(key[-4:])
    dump = "\n".join(sqlite3.connect(os.environ["GINK_DB_PATH"]).iterdump())
    assert key not in dump and b._key_hash(key) in dump


def test_chat_works_with_a_key_and_uses_current_models(api):
    b, c, session, sent = api
    key = c.post("/account/api-keys", json={}, headers=session("dev@x.co")).json()["key"]
    r = chat(c, key)
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "hi"
    assert sent[-1]["model"] == "openai/gpt-oss-120b"                 # retired model swapped, as for the app


def test_wrong_credentials_are_refused(api):
    b, c, session, sent = api
    assert chat(c, "nope").status_code == 401
    assert chat(c, "gink_live_madeup").json()["error"]["code"] == "invalid_api_key"
    token = session("dev@x.co")["Authorization"][7:]
    assert chat(c, token).status_code == 401                            # a session token is not an API key
    key = c.post("/account/api-keys", json={}, headers=session("dev@x.co")).json()["key"]
    assert c.post("/sync", json={"since": 0, "push": {}}, headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_revoked_keys_stop_and_users_cant_touch_each_others_keys(api):
    b, c, session, sent = api
    made = c.post("/account/api-keys", json={}, headers=session("a@x.co")).json()
    assert c.delete(f"/account/api-keys/{made['id']}", headers=session("b@x.co")).status_code == 404
    assert chat(c, made["key"]).status_code == 200
    assert c.delete(f"/account/api-keys/{made['id']}", headers=session("a@x.co")).status_code == 200
    assert chat(c, made["key"]).status_code == 401


def test_per_minute_limit(api, monkeypatch):
    b, c, session, sent = api
    monkeypatch.setattr(b, "API_PER_MINUTE", 3)
    key = c.post("/account/api-keys", json={}, headers=session("dev@x.co")).json()["key"]
    codes = [chat(c, key).status_code for _ in range(4)]
    r = chat(c, key)
    assert codes[:3] == [200, 200, 200] and r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_daily_allowance_is_shared_and_turn_grouping_cant_bypass_it(api, monkeypatch):
    b, c, session, sent = api
    monkeypatch.setitem(b.DAILY_LIMIT, "free", 2) if hasattr(b, "DAILY_LIMIT") else monkeypatch.setenv("GINK_FREE_DAILY", "2")
    key = c.post("/account/api-keys", json={}, headers=session("dev@x.co")).json()["key"]
    same_turn = {"X-Gink-Turn": "t1234567890abcdef"}
    codes = [chat(c, key, headers=same_turn).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429


def test_models_and_images_speak_openai(api, monkeypatch):
    b, c, session, sent = api
    key = c.post("/account/api-keys", json={}, headers=session("dev@x.co")).json()["key"]
    ids = [m["id"] for m in c.get("/v1/models", headers={"Authorization": f"Bearer {key}"}).json()["data"]]
    assert "openai/gpt-oss-120b" in ids and not any("whisper" in i or "compound" in i for i in ids)
    async def fake_image(request):
        assert b._email_from_auth(request) == "dev@x.co"
        return {"image_b64": "aGVsbG8=", "mime_type": "image/png"}
    monkeypatch.setattr(b, "media_image", fake_image)
    r = c.post("/v1/images/generations", json={"prompt": "a snowflake"}, headers={"Authorization": f"Bearer {key}"}).json()
    assert r["data"][0]["b64_json"] == "aGVsbG8=" and "created" in r


def test_deleting_the_account_deletes_its_keys(api):
    b, c, session, sent = api
    h = session("gone@x.co")
    key = c.post("/account/api-keys", json={}, headers=h).json()["key"]
    assert c.post("/account/delete", json={"confirm": "DELETE"}, headers=h).status_code == 200
    assert chat(c, key).status_code == 401


def test_developers_page_is_served_safely(api):
    b, c, session, sent = api
    r = c.get("/developers")
    assert r.status_code == 200 and "Build with Gink" in r.text and "connect-src 'self'" in r.headers["content-security-policy"]
