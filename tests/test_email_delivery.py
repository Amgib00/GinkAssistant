"""Email: Brevo's HTTPS API (works on Render's free plan), Gmail SMTP, clear reasons, owner test email."""
import json, os, smtplib, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest
from ginkassistant.services import backend_server as b


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("BREVO_API_KEY", "EMAIL_FROM", "GMAIL_USER", "GMAIL_APP_PASSWORD", "GMAIL_PASSWORD", "GMAIL_PASS"):
        monkeypatch.delenv(k, raising=False)


def brevo(monkeypatch, status=201, reply=None):
    sent = []
    def post(url, json=None, headers=None, timeout=None):
        sent.append({"url": url, "json": json, "headers": headers})
        return httpx.Response(status, json=reply or {"messageId": "<1@brevo>"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test"); monkeypatch.setenv("EMAIL_FROM", "gink@example.com")
    return sent


def test_brevo_sends_the_code(monkeypatch, capsys):
    sent = brevo(monkeypatch)
    b._send_code_email("ada@example.com", "482913", "Verify your email", "Welcome to Gink!")
    m = sent[0]
    assert m["url"] == "https://api.brevo.com/v3/smtp/email" and m["headers"]["api-key"] == "xkeysib-test"
    assert m["json"]["to"] == [{"email": "ada@example.com"}] and m["json"]["sender"]["email"] == "gink@example.com"
    assert "482913" in m["json"]["textContent"] and "482913" in m["json"]["htmlContent"]
    assert "482913" not in capsys.readouterr().out                     # not printed when it was emailed


def test_brevo_refusal_is_explained(monkeypatch, capsys):
    brevo(monkeypatch, status=400, reply={"code": "invalid_parameter", "message": "sender email is invalid"})
    reason = b._send_email("ada@example.com", "s", "t")
    assert "400" in reason and "verify this sender address in Brevo" in reason
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:                              # a configured service that fails: say so
        b._dispatch_otp("ada@example.com", "111222")
    out = capsys.readouterr().out
    assert e.value.status_code == 503 and "verify this sender" in out and "111222" not in out   # never the code in logs


def test_gmail_blocked_on_render_free_plan(monkeypatch, capsys):
    monkeypatch.setenv("GMAIL_USER", "me@gmail.com"); monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh")
    def blocked(*a, **k): raise OSError(101, "Network is unreachable")
    monkeypatch.setattr(smtplib, "SMTP", blocked)
    reason = b._send_email("ada@example.com", "s", "t")
    assert "Network is unreachable" in reason and "set BREVO_API_KEY" in reason
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):                                    # a clear message instead of a silent failure
        b._dispatch_otp("ada@example.com", "333444")
    assert "333444" not in capsys.readouterr().out


def test_nothing_set_up(capsys):
    assert "no email service is set up" in b._send_email("ada@example.com", "s", "t")
    b._dispatch_otp("ada@example.com", "555666")                          # setting up: the owner's log has the code
    assert "555666" in capsys.readouterr().out
    assert b._email_status() == ""


def test_owner_test_email(monkeypatch, tmp_path):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "e.db")); monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 40)
    from fastapi.testclient import TestClient
    b._admin_failures.clear()
    c = TestClient(b.app)
    sent = brevo(monkeypatch)
    r = c.post("/admin/test-email", json={"to": "me@example.com"}, headers={"x-admin-key": "k" * 40}).json()
    assert r == {"sent": True, "service": "brevo", "reason": ""} and sent[0]["json"]["to"] == [{"email": "me@example.com"}]
    assert c.post("/admin/test-email", json={"to": "me@example.com"}).status_code == 403


def test_failed_emails_are_never_reported_as_sent(tmp_path, monkeypatch):
    """Codes used to be "sent" when the email service refused them: people waited for nothing.
    Now sign-up and sign-in say so (and can retry at once); reset stays neutral (no account probing);
    the owner sees the reason on the dashboard, without the code."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "e.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._health.update(problems=[])
    monkeypatch.setattr(b, "_send_email", lambda *a, **k: "Brevo refused: sender not verified")
    c = TestClient(b.app)
    r = c.post("/auth/register", json={"email": "new@example.com", "password": "correct horse 42", "name": "N"})
    assert r.status_code == 503 and "couldn\u2019t send your code" in r.json()["detail"]
    assert "new@example.com" not in b._pending_signups
    p = b._health["problems"][0]
    assert p["kind"] == "Email not sent" and "sender not verified" in p["reason"] and "@example.com" in p["reason"]
    assert "new@example.com" not in p["reason"]                                    # only the domain
    r = c.post("/send-otp", params={"email": "someone@example.com"})
    assert r.status_code == 503 and "someone@example.com" not in b._otp_store         # can try again at once
    b._upsert_user("real@example.com", "R", b._hash_password("correct horse 42"), "password")
    r = c.post("/auth/forgot", json={"email": "real@example.com"})
    assert r.status_code == 200 and r.json() == {"status": "code_sent"}            # neutral: no account probing
    assert any("reset your password code" in x["reason"] for x in b._health["problems"])
    b._health.update(problems=[])
