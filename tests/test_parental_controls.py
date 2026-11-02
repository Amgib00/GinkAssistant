"""Age (13+, birth year at sign-up) and parental controls: linking, server-enforced controls, stricter
safety for teens, and safety notices that never include what was said."""
import asyncio, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from fastapi import HTTPException

Y = time.gmtime().tm_year


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "family.db"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._safety_seen.clear()
    mails = []
    monkeypatch.setattr(b, "_send_email", lambda to, subject, text, html="": mails.append((to, subject, text)) or "")
    c = TestClient(b.app)

    def account(email, name, birth_year=None):
        b._upsert_user(email, name, None, "password")
        if birth_year:
            b._set_birth_year(email, birth_year)
        return {"Authorization": "Bearer " + b._token_response(email, name)["token"]}
    return b, c, account, mails


def linked(b, c, account, controls=None):
    mum = account("mum@x.co", "Aminata", Y - 40)
    teen = account("teen@x.co", "Moussa", Y - 15)
    assert c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"}).json()["status"] == "pending"
    assert c.post("/family/respond", headers=teen, json={"accept": True}).json() == {"status": "active"}
    if controls:
        assert c.put("/family/controls", headers=mum, json={"teen": "teen@x.co", "controls": controls}).status_code == 200
    return mum, teen


# ---------------------------------------------------------------- age
def test_sign_up_asks_birth_year_and_refuses_under_13(srv, monkeypatch):
    b, c, account, mails = srv
    r = c.post("/auth/register", json={"email": "kid@x.co", "name": "K", "password": "gink2026!", "birth_year": Y - 10})
    assert r.status_code == 403 and r.json()["detail"] == b.UNDER_13_MSG
    assert "kid@x.co" not in b._pending_signups and mails == []                     # nothing kept, nothing sent
    monkeypatch.setattr(b, "_send_code_email", lambda *a: True)
    assert c.post("/auth/register", json={"email": "t@x.co", "name": "T", "password": "gink2026!",
                                          "birth_year": Y - 14}).status_code == 200
    code = b._pending_signups["t@x.co"]["code"]
    assert c.post("/auth/register/verify", json={"email": "t@x.co", "code": code}).status_code == 200
    assert b._age("t@x.co") == 14
    assert c.post("/auth/register", json={"email": "old@x.co", "password": "gink2026!"}).status_code == 200  # older apps


def test_age_once_and_under_13_blocked_everywhere(srv):
    b, c, account, _ = srv
    h = account("g@x.co", "G")                                                     # e.g. a Google sign-up
    assert c.get("/account/age", headers=h).json()["needed"] is True
    assert c.post("/account/age", headers=h, json={"birth_year": Y - 9}).status_code == 403
    assert b._birth_year("g@x.co") is None                                         # not stored
    assert c.post("/account/age", headers=h, json={"birth_year": Y - 30}).json()["needed"] is False
    assert c.post("/account/age", headers=h, json={"birth_year": Y - 15}).status_code == 409   # can't switch to dodge controls
    kid = account("kid@x.co", "K", Y - 11)                                         # (an older account, say)
    r = c.post("/ai/openai/v1/chat/completions", headers=kid, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "under_13"
    assert c.post("/media/image", headers=kid, json={"prompt": "a cat"}).status_code == 403


# ---------------------------------------------------------------- linking
def test_linking_rules_and_privacy(srv):
    b, c, account, mails = srv
    nobody = account("x@x.co", "X")
    account("teen@x.co", "Moussa", Y - 15)
    account("adult@x.co", "Ad", Y - 30)
    assert "birth year" in c.post("/family/invite", headers=nobody, json={"teen": "teen@x.co"}).json()["detail"]
    teen2 = account("teen2@x.co", "Fatou", Y - 16)
    assert c.post("/family/invite", headers=teen2, json={"teen": "teen@x.co"}).status_code == 403   # teens can't be parents
    mum = account("mum@x.co", "Aminata", Y - 40)
    assert c.post("/family/invite", headers=mum, json={"teen": "adult@x.co"}).status_code == 422
    assert c.post("/family/invite", headers=mum, json={"teen": "nobody@x.co"}).status_code == 404
    c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"})
    assert mails[-1][0] == "teen@x.co" and "accept or decline" in mails[-1][2]
    teen = {"Authorization": "Bearer " + b._token_response("teen@x.co", "Moussa")["token"]}
    assert b._family_rules("teen@x.co")["controls"] is None                        # pending: nothing applies yet
    assert c.get("/family", headers=teen).json()["parent"]["status"] == "pending"
    c.post("/family/respond", headers=teen, json={"accept": True})
    dad = account("dad@x.co", "Ibou", Y - 45)
    assert c.post("/family/invite", headers=dad, json={"teen": "teen@x.co"}).status_code == 409    # one parent
    view = c.get("/family", headers=mum).json()
    t = view["teens"][0]
    assert t["label"] == "teen@x.co" and t["status"] == "active" and t["controls"]["images"] is True
    assert t["messages_today"] == 0 and "chat" not in str(view).lower()             # usage totals, no chats


def test_teen_unlinks_and_parent_is_told(srv):
    b, c, account, mails = srv
    mum, teen = linked(b, c, account)
    assert c.post("/family/unlink", headers=teen, json={}).json() == {"status": "unlinked"}
    assert b._family_rules("teen@x.co")["controls"] is None
    assert mails[-1][0] == "mum@x.co" and "unlinked" in mails[-1][1]
    assert c.get("/family", headers=mum).json()["notices"][0]["kind"] == "unlinked"


def test_parent_can_unlink_and_decline_works(srv):
    b, c, account, _ = srv
    mum, teen = linked(b, c, account)
    assert c.post("/family/unlink", headers=mum, json={"teen": "teen@x.co"}).status_code == 200
    c.post("/family/invite", headers=mum, json={"teen": "teen@x.co"})
    assert c.post("/family/respond", headers=teen, json={"accept": False}).json() == {"status": "declined"}
    assert b._link_of("teen@x.co") is None


# ---------------------------------------------------------------- controls, enforced by the server
def test_features_turned_off(srv):
    b, c, account, _ = srv
    mum, teen = linked(b, c, account, {"images": False, "voice": False, "websites": False, "apps": False, "web": False})
    r = c.post("/media/image", headers=teen, json={"prompt": "a cat"})
    assert r.status_code == 403 and "Making images is turned off" in r.json()["error"]["message"]
    assert c.post("/voice/speak", headers=teen, json={"text": "hi"}).status_code == 403
    assert c.post("/voice/transcribe", headers=teen, json={"audio_b64": "x"}).status_code == 403
    assert "Making websites" in c.post("/sites", headers=teen, json={"prompt": "a page about football"}).json()["detail"]
    assert c.post("/connected/google/begin", headers=teen, json={}).status_code == 403
    r = c.post("/ai/openai/v1/chat/completions", headers=teen,
               json={"messages": [{"role": "user", "content": "news"}], "gink_web": True})
    assert r.status_code == 403 and "Web search is turned off" in r.json()["error"]["message"]


def test_quiet_hours(srv):
    b, c, account, _ = srv
    now = time.gmtime()
    start = f"{now.tm_hour:02d}:00"
    end = f"{(now.tm_hour + 2) % 24:02d}:00"
    mum, teen = linked(b, c, account, {"quiet": True, "quiet_from": start, "quiet_to": end, "tz": "UTC"})
    r = c.post("/ai/openai/v1/chat/completions", headers=teen, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "quiet_hours" and end in r.json()["error"]["message"]
    from datetime import datetime, timezone
    q = {"quiet": True, "quiet_from": "21:30", "quiet_to": "06:30", "tz": "Africa/Dakar"}
    assert b._quiet_until(q, datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc)) == "06:30"     # across midnight
    assert b._quiet_until(q, datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)) == ""
    assert b._quiet_until(dict(q, quiet=False), datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc)) == ""


def test_daily_limit(srv):
    b, c, account, _ = srv
    linked(b, c, account, {"daily_limit": 2})
    assert b._count_call("teen@x.co", "t1", "free", 2) is None
    assert b._count_call("teen@x.co", "t2", "free", 2) is None
    assert b._count_call("teen@x.co", "t2", "free", 2) is None                     # same message, more steps
    r = b._count_call("teen@x.co", "t3", "free", 2)
    assert r.status_code == 429 and b"parental controls" in r.body


def test_controls_are_checked(srv):
    b, c, account, _ = srv
    mum, teen = linked(b, c, account)
    bad = {"quiet_from": "25:00"}
    assert c.put("/family/controls", headers=mum, json={"teen": "teen@x.co", "controls": bad}).status_code == 422
    assert c.put("/family/controls", headers=mum, json={"teen": "teen@x.co", "controls": {"tz": "Mars/Base"}}).status_code == 422
    assert c.put("/family/controls", headers=teen, json={"teen": "teen@x.co", "controls": {"images": True}}).status_code == 404


def test_every_teen_gets_stricter_safety(srv, monkeypatch):
    b, c, account, _ = srv
    teen = account("solo@x.co", "Awa", Y - 14)                                      # not linked: still a teen
    adult = account("grown@x.co", "Ad", Y - 30)
    seen = {}

    def stop(body, cap):
        seen["messages"] = body["messages"]
        raise HTTPException(status_code=418, detail="stop")
    monkeypatch.setattr(b, "_fit_reasoning", stop)
    async def same(model, images=False): return model
    monkeypatch.setattr(b, "_current_model", same)
    c.post("/ai/openai/v1/chat/completions", headers=teen, json={"messages": [{"role": "user", "content": "hi"}]})
    assert seen["messages"][0] == {"role": "system", "content": b.TEEN_SAFETY}
    c.post("/ai/openai/v1/chat/completions", headers=adult, json={"messages": [{"role": "user", "content": "hi"}]})
    assert all(m.get("content") != b.TEEN_SAFETY for m in seen["messages"])


# ---------------------------------------------------------------- safety notices
def test_safety_notice_without_the_words(srv, monkeypatch):
    b, c, account, mails = srv
    mum, teen = linked(b, c, account)
    kinds = iter(["self_harm", "self_harm", "abuse_at_home", "none"])
    async def classify(text): return next(kinds)
    monkeypatch.setattr(b, "_classify_risk", classify)
    secret = "I want to end it all tonight, nobody would care"
    asyncio.run(b._safety_check("teen@x.co", "mum@x.co", secret))
    to, subject, text = mails[-1]
    assert to == "mum@x.co" and "safety notice" in subject.lower() and "hurting themselves" in text
    assert secret not in text and "end it all" not in text and "chats stay private" in text
    asyncio.run(b._safety_check("teen@x.co", "mum@x.co", secret))                   # same message: not again
    asyncio.run(b._safety_check("teen@x.co", "mum@x.co", "another sad message"))    # same kind today: one notice
    asyncio.run(b._safety_check("teen@x.co", "mum@x.co", "my dad hits me"))         # harm at home: never the parent
    notices = c.get("/family", headers=mum).json()["notices"]
    assert [n["kind"] for n in notices] == ["self_harm"] and secret not in str(notices)
    mine = c.get("/family", headers=teen).json()["notices_about_me"]
    assert [n["kind"] for n in mine] == ["self_harm"]                              # the teen can see it was sent


def test_no_safety_checks_without_a_parent(srv, monkeypatch):
    b, c, account, mails = srv
    called = []
    async def classify(text): called.append(text); return "self_harm"
    monkeypatch.setattr(b, "_classify_risk", classify)
    asyncio.run(b._safety_check("solo@x.co", "", "anything"))
    assert called == [] and mails == []


def test_classifier_request(srv, monkeypatch):
    b, *_ = srv
    import httpx
    sent = {}

    class Client:
        def __init__(self, timeout=None): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.update(url=url, body=json)
            return httpx.Response(200, json={"choices": [{"message": {"content": 'Sure.\n{"category": "harm_from_adult"}'}}]})
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.delenv("GINK_SAFETY_MODEL", raising=False)
    assert asyncio.run(b._classify_risk("a man online wants me to send photos and keep it secret")) == "harm_from_adult"
    assert sent["body"]["temperature"] == 0 and sent["body"]["model"] == "openai/gpt-oss-20b"   # not a retired model
    assert sent["body"]["reasoning_effort"] == "low" and sent["body"]["max_tokens"] >= 300           # room after reasoning
    assert sent["body"]["messages"][0]["content"] == b.SAFETY_PROMPT
    assert sent["body"]["model"] not in b.RETIRED_MODELS


def test_deleting_an_account_removes_family_data(srv):
    b, c, account, _ = srv
    mum, teen = linked(b, c, account, {"images": False})
    assert c.post("/account/delete", headers=teen, json={"confirm": "DELETE"}).status_code == 200
    assert b._link_of("teen@x.co") is None and b._birth_year("teen@x.co") is None
    assert c.get("/family", headers=mum).json()["teens"] == []
