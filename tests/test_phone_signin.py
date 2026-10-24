"""Phone sign-in (openspec/changes/add-phone-signin) with the SMS providers simulated."""
import os, re, sys, time, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

SENT = []


def fake_post(url, data=None, headers=None, auth=None, timeout=None, **kw):
    SENT.append({"url": url, "data": dict(data or {}), "headers": dict(headers or {}), "auth": auth})
    if "africastalking" in url:
        return httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"status": "Success", "number": data["to"]}]}})
    return httpx.Response(201, json={"sid": "SM1"})


@pytest.fixture
def srv(tmp_path, monkeypatch):
    SENT.clear()
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "GINK_SMS_PROVIDER", "GINK_SMS_MONTHLY_LIMIT", "AT_SENDER_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("AT_USERNAME", "gink"); monkeypatch.setenv("AT_API_KEY", "at-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._phone_codes.clear(); b._code_sends.clear()
    return b, TestClient(b.app)


def last_code():
    text = SENT[-1]["data"].get("message") or SENT[-1]["data"].get("Body")
    return re.search(r"\b(\d{6})\b", text).group(1)


def again(b):
    b._code_sends.clear()                                         # as if the 30-second cooldown passed


def test_status_and_provider_requests(srv, monkeypatch):
    b, c = srv
    assert c.get("/auth/phone/status").json() == {"enabled": True}
    c.post("/auth/phone/send", json={"phone": "+221 77 123 45 67"})
    at = SENT[-1]
    assert at["url"] == "https://api.africastalking.com/version1/messaging" and at["headers"]["apiKey"] == "at-key"
    assert at["data"]["to"] == "+221771234567" and at["data"]["username"] == "gink" and "Never share it" in at["data"]["message"]
    monkeypatch.setenv("AT_USERNAME", "sandbox"); again(b)
    c.post("/auth/phone/send", json={"phone": "+221771234567"})
    assert SENT[-1]["url"].startswith("https://api.sandbox.africastalking.com/")       # Africa's Talking's free sandbox
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC1"); monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_FROM", "+15550001111"); monkeypatch.setenv("GINK_SMS_PROVIDER", "twilio"); again(b)
    c.post("/auth/phone/send", json={"phone": "+221771234567"})
    tw = SENT[-1]
    assert tw["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json" and tw["auth"] == ("AC1", "tok")
    assert tw["data"]["To"] == "+221771234567" and tw["data"]["From"] == "+15550001111"
    for k in ("AT_USERNAME", "AT_API_KEY", "TWILIO_ACCOUNT_SID"):
        monkeypatch.delenv(k)
    assert c.get("/auth/phone/status").json() == {"enabled": False}
    assert c.post("/auth/phone/send", json={"phone": "+221771234567"}).status_code == 503


def test_sign_up_then_sign_in(srv):
    b, c = srv
    c.post("/auth/phone/send", json={"phone": "+221771234567"})
    code = last_code()
    assert c.post("/auth/phone/verify", json={"phone": "+221771234567", "code": code}).json() == {"need_name": True}
    r = c.post("/auth/phone/verify", json={"phone": "+221771234567", "code": code, "name": "Awa Diop"}).json()
    assert r["token"] and r["email"] == "221771234567@phone.gink.invalid"
    assert b._get_user(r["email"])["name"] == "Awa Diop"
    assert b._send_email(r["email"], "x", "y") != ""                               # never emailed
    again(b); c.post("/auth/phone/send", json={"phone": "+221771234567"})
    r2 = c.post("/auth/phone/verify", json={"phone": "+221771234567", "code": last_code()}).json()
    assert r2["token"] and r2["email"] == r["email"]                                 # same account, no name asked
    me = {"Authorization": "Bearer " + r2["token"]}
    assert c.delete("/account/phone", headers=me).status_code == 409                 # its only way in


def test_numbers_codes_and_limits(srv, monkeypatch):
    b, c = srv
    for good in ("+221 77 123 45 67", "00221771234567", "+44 7700 900123"):
        again(b); assert c.post("/auth/phone/send", json={"phone": good}).status_code == 200, good
    for bad in ("77 123 45 67", "+0123", "+1"):
        assert c.post("/auth/phone/send", json={"phone": bad}).status_code == 422, bad
    again(b); c.post("/auth/phone/send", json={"phone": "+221770000001"})
    assert c.post("/auth/phone/send", json={"phone": "+221770000001"}).status_code == 429   # cooldown per number
    for _ in range(5):
        r = c.post("/auth/phone/verify", json={"phone": "+221770000001", "code": "000000", "name": "X"})
    assert r.status_code == 401
    r = c.post("/auth/phone/verify", json={"phone": "+221770000001", "code": "000000", "name": "X"})
    assert "Too many wrong codes" in r.json()["detail"]
    monkeypatch.setenv("GINK_SMS_MONTHLY_LIMIT", str(b._sms_sent_this_month())); again(b)
    r = c.post("/auth/phone/send", json={"phone": "+221770000002"})
    assert r.status_code == 503 and "paused for the rest of this month" in r.json()["detail"]


def test_add_phone_to_email_account_and_two_step(srv):
    b, c = srv
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse 42"), "password")
    me = {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}
    c.post("/account/phone/send", headers=me, json={"phone": "+23276123456"})
    assert c.post("/account/phone/verify", headers=me, json={"phone": "+23276123456", "code": last_code()}).json() == {"phone": "+23276123456"}
    assert c.get("/account/phone", headers=me).json()["phone"] == "+23276123456"
    b._upsert_user("eve@example.com", "Eve", b._hash_password("another pass 42"), "password")
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    again(b)
    assert c.post("/account/phone/send", headers=eve, json={"phone": "+23276123456"}).status_code == 409   # taken
    secret = c.post("/account/2fa/setup", headers=me).json()["secret"].replace(" ", "")
    c.post("/account/2fa/enable", headers=me, json={"code": b._totp(secret, int(time.time() // 30) - 1)})
    again(b); c.post("/auth/phone/send", json={"phone": "+23276123456"})
    r = c.post("/auth/phone/verify", json={"phone": "+23276123456", "code": last_code()}).json()
    assert r.get("twofa_required") and "token" not in r                              # still two-step
    assert "Phone number added: +232\u202656" in [e["text"] for e in c.get("/account/security-history", headers=me).json()["events"]]
    c.post("/account/delete", headers=me, json={"confirm": "DELETE"})
    assert b._account_for_phone("+23276123456") is None


def test_owner_dashboard_shows_sms_use(srv, monkeypatch):
    b, c = srv
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 40); b._admin_failures.clear()
    c.post("/auth/phone/send", json={"phone": "+221771234567"})
    s = c.get("/admin/stats", headers={"x-admin-key": "k" * 40}).json()["services"]
    assert s["sms"] and s["sms_provider"] == "africastalking" and s["sms_month"] == 1 and s["sms_limit"] == 500
