"""Age and parental controls reach every AI feature, not just chat (Genie missed them until 0.1.101;
websites, images and search missed quiet hours and the teen limit/safety until 0.1.102)."""
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest

Y = time.gmtime().tm_year
# every endpoint that makes something with AI (or listens/speaks): method, path, body
AI_FEATURES = [("POST", "/ai/openai/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]}),
               ("POST", "/media/image", {"prompt": "a cat"}),
               ("POST", "/sites", {"prompt": "a page about football clubs"}),
               ("POST", "/web/search", {"query": "football results"}),
               ("POST", "/genie/projects", {"prompt": "Build a quiz game"}),
               ("POST", "/media/song", {"audio_b64": "UklGRg=="}),
               ("POST", "/voice/transcribe", {"audio_b64": "x"}),
               ("POST", "/voice/speak", {"text": "hi"})]


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "fe.db"))
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    monkeypatch.setattr(b, "_send_email", lambda *a, **k: "")
    c = TestClient(b.app)

    def account(email, by):
        b._upsert_user(email, email.split("@")[0], None, "password")
        b._set_birth_year(email, by)
        return {"Authorization": "Bearer " + b._token_response(email, email.split("@")[0])["token"]}
    return b, c, account


def send(c, h, method, path, body):
    return c.request(method, path, headers=h, json=body)


def test_under_13_refused_by_every_ai_feature(srv):
    b, c, account = srv
    kid = account("kid@x.co", Y - 11)
    for method, path, body in AI_FEATURES:
        r = send(c, kid, method, path, body)
        text = r.text
        assert r.status_code == 403 and b.UNDER_13_MSG in text, (path, r.status_code, text[:200])


def test_quiet_hours_in_every_ai_feature(srv):
    b, c, account = srv
    mum = account("mum@x.co", Y - 40)
    teen = account("teen@x.co", Y - 15)
    c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"})
    c.post("/family/respond", headers=teen, json={"accept": True})
    now = time.gmtime()
    c.put("/family/controls", headers=mum, json={"teen": "teen@x.co", "controls": {
        "quiet": True, "quiet_from": f"{now.tm_hour:02d}:00", "quiet_to": f"{(now.tm_hour + 2) % 24:02d}:00", "tz": "UTC"}})
    for method, path, body in AI_FEATURES:
        if path in ("/media/song", "/voice/transcribe", "/voice/speak"):
            continue                                                            # listening/speaking: not "making"
        r = send(c, teen, method, path, body)
        assert r.status_code == 403 and "quiet time" in r.text, (path, r.status_code, r.text[:200])


def test_websites_get_teen_safety_and_the_check(srv, monkeypatch):
    b, c, account = srv
    mum = account("mum@x.co", Y - 40)
    teen = account("teen@x.co", Y - 15)
    adult = account("grown@x.co", Y - 30)
    c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"})
    c.post("/family/respond", headers=teen, json={"accept": True})
    seen, checked = [], []

    async def site_ai(messages):
        seen.append(messages)
        raise ValueError("stop here")
    monkeypatch.setattr(b, "_site_ai", site_ai)
    monkeypatch.setattr(b, "_start_safety_check", lambda t, p, words: checked.append((t, p, words)))
    c.post("/sites", headers=teen, json={"prompt": "a page about my football team"})
    assert seen[-1][1] == {"role": "system", "content": b.TEEN_SAFETY} and seen[-1][0]["content"] == b.SITE_SYSTEM
    assert checked == [("teen@x.co", "mum@x.co", "a page about my football team")]
    c.post("/sites", headers=adult, json={"prompt": "a page about my football team"})
    assert all(m["content"] != b.TEEN_SAFETY for m in seen[-1])


def test_websites_count_toward_the_teens_daily_limit(srv, monkeypatch):
    b, c, account = srv
    mum = account("mum@x.co", Y - 40)
    teen = account("teen@x.co", Y - 15)
    c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"})
    c.post("/family/respond", headers=teen, json={"accept": True})
    c.put("/family/controls", headers=mum, json={"teen": "teen@x.co", "controls": {"daily_limit": 1}})
    b._count_call("teen@x.co", "earlier-turn", "free", 1)                     # one message already today
    r = c.post("/sites", headers=dict(teen, **{"x-gink-turn": "new"}), json={"prompt": "a page about my football team"})
    assert r.status_code == 429 and "parental controls" in r.text
