"""Phone sign-in in the apps' sign-in screen (the web page had it; the apps didn't): number -> SMS code
-> a name for a new number -> signed in; next time straight in. Real server, SMS simulated."""
import asyncio
import os
import re
import sys
import threading
import time
import types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx

SENT = []


def fake_post(url, data=None, headers=None, auth=None, timeout=None, **kw):
    SENT.append(dict(data or {}))
    return httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"status": "Success"}]}})


def code():
    return re.search(r"\b(\d{6})\b", SENT[-1]["message"]).group(1)


def test_account_label():
    from ginkassistant.services.api_client import account_label
    assert account_label("221771234567@phone.gink.invalid") == "+221771234567"
    assert account_label("ib@example.com") == "ib@example.com" and account_label("") == ""


def test_app_signs_in_with_a_phone_number(tmp_path, monkeypatch):
    import uvicorn
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "GINK_SMS_PROVIDER", "GINK_SMS_MONTHLY_LIMIT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "phone.db"))
    monkeypatch.setenv("AT_USERNAME", "gink"); monkeypatch.setenv("AT_API_KEY", "at-key")
    monkeypatch.setattr(httpx, "post", fake_post)                        # the server's SMS call
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui.login_screen import LoginController
    b._phone_codes.clear(); b._code_sends.clear()
    server = uvicorn.Server(uvicorn.Config(b.app, port=8813, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(1.5)
    try:
        ctl = LoginController.__new__(LoginController)
        ctl.app = types.SimpleNamespace(state=types.SimpleNamespace(base_url="http://127.0.0.1:8813"))
        ctl.pending, ctl.oauth, ctl.token = {"email": "", "mode": "", "remember": True}, {"state": None, "provider": None}, object()
        ctl.app._login_screen_token = ctl.token
        calls, done = [], []
        async def call(fn, *args): calls.append((fn,) + args)
        ctl.call, ctl.finish = call, lambda session, remember: done.append((session, remember))
        import ginkassistant.ui.login_screen as ls
        monkeypatch.setattr(ls.server_config, "saved_url", lambda app: "")
        run = lambda ev: asyncio.run(ctl.handle(ev))

        run({"type": "ready"})
        assert ("setPhoneEnabled", True) in calls                                    # the button shows
        run({"type": "phone_send", "value": {"phone": "+234 803 123 4567", "remember": False}})
        assert SENT[-1]["to"] == "+2348031234567"
        assert calls[-1] == ("show", "verify", {"email": "+234 803 123 4567", "phone": True})
        run({"type": "verify", "value": {"code": "000000" if code() != "000000" else "111111"}})
        assert calls[-1][0] == "error" and "isn\u2019t right" in calls[-1][1].replace("'", "\u2019") and not done
        run({"type": "verify", "value": {"code": code()}})
        assert calls[-1] == ("show", "name") and not done                            # a new number: a name first
        run({"type": "phone_name", "value": {"name": "Awa Diop"}})
        session, remember = done[-1]
        assert session.email == "2348031234567@phone.gink.invalid" and session.name == "Awa Diop" and remember is False

        b._code_sends.clear()                                                     # as if the cooldown passed
        done.clear(); calls.clear()
        run({"type": "phone_send", "value": {"phone": "+2348031234567", "remember": True}})
        run({"type": "verify", "value": {"code": code()}})
        assert done and done[-1][0].email == "2348031234567@phone.gink.invalid"      # known number: straight in
        assert ("show", "name") not in calls

        b._code_sends.clear(); calls.clear()                                      # resend in phone mode texts again
        before = len(SENT)
        run({"type": "phone_send", "value": {"phone": "+2348031234567"}})
        b._code_sends.clear()
        run({"type": "resend"})
        assert len(SENT) == before + 2 and ("info", "New code sent.") in calls
    finally:
        server.should_exit = True


def test_phone_button_hidden_when_the_server_has_no_sms(monkeypatch):
    from ginkassistant.services.api_client import ApiClient

    async def go():
        api = ApiClient("http://127.0.0.1:1")                                       # nothing listens there
        return await api.phone_signin_enabled()
    assert asyncio.run(go()) is False
