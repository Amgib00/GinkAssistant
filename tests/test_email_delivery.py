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
    b._dispatch_otp("ada@example.com", "111222")
    out = capsys.readouterr().out
    assert "111222" in out and "verify this sender" in out                # the code still reaches the log


def test_gmail_blocked_on_render_free_plan(monkeypatch, capsys):
    monkeypatch.setenv("GMAIL_USER", "me@gmail.com"); monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh")
    def blocked(*a, **k): raise OSError(101, "Network is unreachable")
    monkeypatch.setattr(smtplib, "SMTP", blocked)
    reason = b._send_email("ada@example.com", "s", "t")
    assert "Network is unreachable" in reason and "set BREVO_API_KEY" in reason
    b._dispatch_otp("ada@example.com", "333444")                         # never crashes the sign-in
    assert "333444" in capsys.readouterr().out


def test_nothing_set_up():
    assert "no email service is set up" in b._send_email("ada@example.com", "s", "t")
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
