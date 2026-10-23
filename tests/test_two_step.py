"""Two-step sign-in (TOTP): standard-correct codes, encrypted secret, every sign-in gated, recovery codes, limits."""
import base64, os, sqlite3, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "t.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._twofa_attempts.clear(); b._code_sends.clear(); b._no_account_notices.clear(); b._otp_store.clear()
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse 42"), "password")
    return b, TestClient(b.app), str(tmp_path / "t.db")


def login(c):
    return c.post("/auth/login", json={"email": "ib@example.com", "password": "correct horse 42"}).json()


def now_code(b, secret):
    return b._totp(secret.replace(" ", ""), int(time.time() // 30))


def test_rfc6238_vector():
    from ginkassistant.services import backend_server as b
    secret = base64.b32encode(b"12345678901234567890").decode()          # RFC 6238 appendix B, SHA-1
    assert b._totp(secret, 59 // 30) == "287082" and b._totp(secret, 1111111109 // 30) == "081804"


def turn_on(b, c, auth):
    setup = c.post("/account/2fa/setup", headers=auth).json()
    assert setup["uri"].startswith("otpauth://totp/Gink:") and setup["qr"].startswith("data:image/svg+xml;base64,")
    secret = setup["secret"].replace(" ", "")
    on = c.post("/account/2fa/enable", headers=auth, json={"code": b._totp(secret, int(time.time() // 30) - 1)}).json()
    assert on["enabled"] and len(on["recovery_codes"]) == 10
    return secret, on["recovery_codes"]


def test_the_whole_flow(srv):
    b, c, db = srv
    auth = {"Authorization": "Bearer " + login(c)["token"]}
    assert c.get("/account/2fa", headers=auth).json()["enabled"] is False
    secret, recovery = turn_on(b, c, auth)
    stored = sqlite3.connect(db).execute("SELECT secret FROM twofa").fetchone()[0]
    assert secret not in stored and b._unseal(stored) == secret                      # encrypted at rest

    first = login(c)
    assert first.get("twofa_required") and "token" not in first                     # password alone isn't enough
    assert c.post("/auth/2fa", json={"ticket": first["ticket"], "code": "000000"}).status_code == 401
    code = now_code(b, secret)
    ok = c.post("/auth/2fa", json={"ticket": first["ticket"], "code": code})
    assert ok.status_code == 200 and ok.json()["token"]
    again = login(c)
    assert c.post("/auth/2fa", json={"ticket": again["ticket"], "code": code}).status_code == 401   # no reuse

    spare = recovery[0].replace("-", "").upper()                                     # typed without the dash
    assert c.post("/auth/2fa", json={"ticket": again["ticket"], "code": spare}).status_code == 200
    third = login(c)
    assert c.post("/auth/2fa", json={"ticket": third["ticket"], "code": recovery[0]}).status_code == 401  # spent


def test_too_many_wrong_codes(srv):
    b, c, db = srv
    turn_on(b, c, {"Authorization": "Bearer " + login(c)["token"]})
    t = login(c)["ticket"]
    for _ in range(5):
        assert c.post("/auth/2fa", json={"ticket": t, "code": "123456"}).status_code == 401
    assert c.post("/auth/2fa", json={"ticket": t, "code": "123456"}).status_code == 429


def test_reset_and_social_sign_in_are_gated_too(srv, monkeypatch):
    b, c, db = srv
    turn_on(b, c, {"Authorization": "Bearer " + login(c)["token"]})
    assert "token" not in b._login_response("ib@example.com", "Ibrahim")             # Google/GitHub/... path
    monkeypatch.setattr(b, "_send_code_email", lambda *a, **k: None)
    c.post("/auth/forgot", json={"email": "ib@example.com"})
    code = b._reset_codes["ib@example.com"]["code"]
    r = c.post("/auth/reset", json={"email": "ib@example.com", "code": code, "password": "brand new pass 42"}).json()
    assert r.get("twofa_required") and "token" not in r                              # a reset can't skip it


def test_turning_it_off_needs_a_code(srv):
    b, c, db = srv
    auth = {"Authorization": "Bearer " + login(c)["token"]}
    secret, _ = turn_on(b, c, auth)
    assert c.post("/account/2fa/disable", headers=auth, json={"code": "000000"}).status_code == 401
    assert c.post("/account/2fa/disable", headers=auth, json={"code": now_code(b, secret)}).json() == {"enabled": False}
    assert "token" in login(c)


def test_app_sign_in_screen_asks_for_the_code(tmp_path, monkeypatch):
    """The app's sign-in logic against a real server: password -> code step -> signed in; same via Google."""
    import asyncio, threading, types, uvicorn
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "app.db"))
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui.login_screen import LoginController
    b._twofa_attempts.clear()
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse 42"), "password")
    server = uvicorn.Server(uvicorn.Config(b.app, port=8811, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(1.5)
    try:
        from fastapi.testclient import TestClient
        c = TestClient(b.app)
        secret, _ = turn_on(b, c, {"Authorization": "Bearer " + login(c)["token"]})
        ctl = LoginController.__new__(LoginController)
        ctl.app = types.SimpleNamespace(state=types.SimpleNamespace(base_url="http://127.0.0.1:8811"))
        ctl.pending, ctl.oauth, ctl.token = {"email": "", "mode": "", "remember": True}, {"state": None, "provider": None}, object()
        ctl.app._login_screen_token = ctl.token
        calls, done = [], []
        async def call(fn, *args): calls.append((fn,) + args)
        ctl.call, ctl.finish = call, lambda session, remember: done.append(session)

        asyncio.run(ctl.handle({"type": "login", "value": {"email": "ib@example.com", "password": "correct horse 42", "remember": True}}))
        assert ("show", "twofa", {"email": "ib@example.com"}) in calls and not done        # the code step, no session yet
        asyncio.run(ctl.handle({"type": "twofa", "value": {"code": "000000"}}))
        assert calls[-1][0] == "error" and not done                                          # wrong code: message
        asyncio.run(ctl.handle({"type": "twofa", "value": {"code": now_code(b, secret)}}))
        assert done and done[0].token and done[0].email == "ib@example.com"                 # signed in

        # Google / GitHub path: the real start_oauth (server registers the sign-in, then the app polls)
        import ginkassistant.ui.login_screen as ls
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "gink-id"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
        monkeypatch.setattr(ls, "_open_in_browser", lambda app, url: True)
        calls.clear(); done.clear()

        async def google():
            task = asyncio.create_task(ctl.start_oauth("google"))
            for _ in range(40):                                   # wait for the app to register the sign-in
                await asyncio.sleep(0.1)
                pending = [st for st, e in b._oauth_states.items() if e["result"] is None]
                if pending:
                    break
            with b._otp_lock:                                     # Google said yes, on the server
                b._oauth_states[pending[-1]]["result"] = b._login_response("ib@example.com", "Ibrahim")
            await asyncio.wait_for(task, timeout=10)
        asyncio.run(google())
        assert ("show", "twofa", {"email": "ib@example.com"}) in calls and not done          # code step, not signed in
    finally:
        server.should_exit = True


def test_email_code_sign_in_is_gated_and_has_a_session(srv, monkeypatch):
    """/verify-otp used to issue a bare token: no session, and no two-step verification."""
    b, c, db = srv
    monkeypatch.setattr(b, "_dispatch_otp", lambda email, otp: None)
    def code_login():
        c.post("/send-otp", params={"email": "ib@example.com"})
        otp = b._otp_store["ib@example.com"]["otp"] if "otp" in b._otp_store["ib@example.com"] else b._otp_store["ib@example.com"]["code"]
        return c.post("/verify-otp", params={"email": "ib@example.com", "otp": otp}).json()
    plain = code_login()
    auth = {"Authorization": "Bearer " + plain["token"]}
    assert len(c.get("/account/sessions", headers=auth).json()["sessions"]) == 1     # a real session now
    turn_on(b, c, auth)
    b._otp_store.clear(); b._code_sends.clear()                                        # as if the cooldown passed
    gated = code_login()
    assert gated.get("twofa_required") and "token" not in gated                       # code alone isn't enough


def test_email_codes_only_for_existing_accounts(srv, monkeypatch):
    """An unknown email used to get a working account-less ("ghost") sign-in."""
    b, c, db = srv
    notes = []
    monkeypatch.setattr(b, "_send_email", lambda to, subject, text, html="": notes.append((to, subject)) or "")
    monkeypatch.setattr(b, "_dispatch_otp", lambda email, otp: None)
    b._no_account_notices.clear()
    known = c.post("/send-otp", params={"email": "ib@example.com"})
    stranger = c.post("/send-otp", params={"email": "nobody@example.com"})
    assert known.status_code == stranger.status_code == 200 and known.json() == stranger.json()   # can't tell apart
    assert "nobody@example.com" not in b._otp_store and notes == [("nobody@example.com", "Gink - no account for this email")]
    c.post("/send-otp", params={"email": "nobody@example.com"})
    assert len(notes) == 1                                                            # no spamming
    assert c.post("/verify-otp", params={"email": "nobody@example.com", "otp": "123456"}).status_code == 401
    code = b._otp_store["ib@example.com"]["otp"]
    assert len(code) == 6 and code.isdigit()


def test_code_emails_are_limited(srv, monkeypatch):
    """Sign-up / reset / email sign-in used to send a code on every request (inbox flooding)."""
    b, c, db = srv
    monkeypatch.setattr(b, "_send_code_email", lambda *a, **k: None)
    monkeypatch.setattr(b, "_dispatch_otp", lambda *a, **k: None)
    monkeypatch.setattr(b, "_send_email", lambda *a, **k: "")
    b._code_sends.clear(); b._otp_store.clear(); b._no_account_notices.clear()
    first = c.post("/auth/forgot", json={"email": "ib@example.com"})
    again = c.post("/auth/forgot", json={"email": "ib@example.com"})
    assert first.status_code == 200 and again.status_code == 429 and "Wait" in again.json()["detail"]
    for _ in range(5):                                                                 # pretend the cooldowns passed
        b._code_sends[("reset", "ib@example.com")] = [t - 31 for t in b._code_sends[("reset", "ib@example.com")]]
        assert c.post("/auth/forgot", json={"email": "ib@example.com"}).status_code == 200
    b._code_sends[("reset", "ib@example.com")] = [t - 31 for t in b._code_sends[("reset", "ib@example.com")]]
    seventh = c.post("/auth/forgot", json={"email": "ib@example.com"})
    assert seventh.status_code == 429 and "last hour" in seventh.json()["detail"]
    # an unknown email is treated exactly the same (the limit can't reveal who has an account)
    assert [c.post("/auth/forgot", json={"email": "ghost@example.com"}).status_code for _ in range(2)] == [200, 429]
    assert [c.post("/send-otp", params={"email": "ghost@example.com"}).status_code for _ in range(2)] == [200, 429]
    assert [c.post("/auth/register", json={"name": "N", "email": "new@example.com", "password": "abc12345!"}).status_code
            for _ in range(2)] == [200, 429]
