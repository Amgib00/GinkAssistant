"""SMS codes go through a provider that actually reaches the number: Africa's Talking doesn't cover
Senegal or Sierra Leone (its own country list), so those go through Twilio, or are refused clearly."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import httpx, pytest
from test_phone_signin import fake_post, SENT


@pytest.fixture
def srv(tmp_path, monkeypatch):
    SENT.clear()
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "GINK_SMS_PROVIDER", "GINK_SMS_MONTHLY_LIMIT",
              "AT_SENDER_ID", "AT_USERNAME", "AT_API_KEY", "GINK_AT_COUNTRIES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "r.db"))
    monkeypatch.setattr(httpx, "post", fake_post)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._phone_codes.clear(); b._code_sends.clear()
    return b, TestClient(b.app), monkeypatch


def at(mp):
    mp.setenv("AT_USERNAME", "gink"); mp.setenv("AT_API_KEY", "k")


def twilio(mp):
    mp.setenv("TWILIO_ACCOUNT_SID", "AC1"); mp.setenv("TWILIO_AUTH_TOKEN", "t"); mp.setenv("TWILIO_FROM", "+15550001111")


def send(b, c, number):
    b._code_sends.clear()
    return c.post("/auth/phone/send", json={"phone": number})


def test_both_providers_split_by_country(srv):
    b, c, mp = srv
    at(mp); twilio(mp)
    assert send(b, c, "+254 712 345 678").status_code == 200 and "africastalking" in SENT[-1]["url"]     # Kenya
    assert send(b, c, "+233 24 123 4567").status_code == 200 and "africastalking" in SENT[-1]["url"]     # Ghana
    assert send(b, c, "+221 77 123 45 67").status_code == 200 and "twilio" in SENT[-1]["url"]            # Senegal
    assert send(b, c, "+232 76 123 456").status_code == 200 and "twilio" in SENT[-1]["url"]              # Sierra Leone


def test_only_africas_talking_refuses_uncovered_countries_clearly(srv):
    b, c, mp = srv
    at(mp)
    assert c.get("/auth/phone/status").json() == {"enabled": True}
    r = send(b, c, "+221 77 123 45 67")
    assert r.status_code == 422 and "can\u2019t text codes to numbers in this country" in r.json()["detail"].replace("'", "\u2019")
    assert SENT == []                                                        # nothing paid for, nothing sent
    assert send(b, c, "+234 803 123 4567").status_code == 200               # Nigeria works


def test_forcing_and_a_longer_country_list(srv):
    b, c, mp = srv
    at(mp); twilio(mp)
    mp.setenv("GINK_SMS_PROVIDER", "twilio")
    send(b, c, "+254712345678")
    assert "twilio" in SENT[-1]["url"]                                       # forced
    mp.delenv("GINK_SMS_PROVIDER")
    mp.delenv("TWILIO_ACCOUNT_SID")
    mp.setenv("GINK_AT_COUNTRIES", "221, +254")                              # Africa's Talking added Senegal
    assert send(b, c, "+221771234567").status_code == 200 and "africastalking" in SENT[-1]["url"]
    assert send(b, c, "+233241234567").status_code == 422                    # the custom list replaces the default
