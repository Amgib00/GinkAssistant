"""Signed-in devices, signing out a device / all others / this one, HSTS, and the ID-token issuer check."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, jwt, pytest

CHROME_ANDROID = "Mozilla/5.0 (Linux; Android 12; TECNO BF6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse 42"), "password")
    return b, TestClient(b.app)


def login(c, **headers):
    r = c.post("/auth/login", json={"email": "ib@example.com", "password": "correct horse 42"}, headers=headers)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_devices_listed_and_signed_out_one_by_one(srv):
    b, c = srv
    mac = login(c, **{"X-Gink-Device": "Gink for Mac"})
    phone = login(c, **{"User-Agent": CHROME_ANDROID})
    listed = c.get("/account/sessions", headers=mac).json()["sessions"]
    assert sorted(s["device"] for s in listed) == ["Chrome on Android", "Gink for Mac"]
    assert [s["device"] for s in listed if s["current"]] == ["Gink for Mac"]
    phone_id = next(s["id"] for s in listed if s["device"] == "Chrome on Android")
    assert c.delete(f"/account/sessions/{phone_id}", headers=mac).status_code == 200
    r = c.get("/account/sessions", headers=phone)
    assert r.status_code == 401 and "signed out on this device" in r.json()["detail"]      # refused at once
    assert c.get("/account/sessions", headers=mac).status_code == 200                      # the others keep working


def test_sign_out_all_others_including_old_tokens(srv):
    b, c = srv
    mine, other = login(c), login(c)
    legacy = {"Authorization": "Bearer " + jwt.encode({"sub": "ib@example.com", "iat": time.time() - 60, "exp": time.time() + 3600,
                                                       "iss": "gink_assistant"}, b._get_secret_key(), algorithm=b.ALGORITHM)}
    assert c.get("/account/sessions", headers=legacy).status_code == 200                   # works before
    assert c.post("/account/sessions/sign-out-others", headers=mine).status_code == 200
    assert c.get("/account/sessions", headers=other).status_code == 401
    assert c.get("/account/sessions", headers=legacy).status_code == 401
    assert len(c.get("/account/sessions", headers=mine).json()["sessions"]) == 1


def test_logout_really_ends_the_session(srv):
    b, c = srv
    me = login(c)
    assert c.post("/auth/logout", headers=me).json() == {"ok": True}
    assert c.get("/account/sessions", headers=me).status_code == 401
    assert c.post("/auth/logout", headers=me).json() == {"ok": True}                       # twice is harmless


def test_another_account_cannot_sign_out_my_device(srv):
    b, c = srv
    me = login(c)
    my_id = c.get("/account/sessions", headers=me).json()["sessions"][0]["id"]
    b._upsert_user("eve@example.com", "Eve", b._hash_password("another pass 42"), "password")
    eve = {"Authorization": "Bearer " + c.post("/auth/login", json={"email": "eve@example.com", "password": "another pass 42"}).json()["token"]}
    c.delete(f"/account/sessions/{my_id}", headers=eve)
    assert c.get("/account/sessions", headers=me).status_code == 200


def test_security_headers(srv):
    b, c = srv
    r = c.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["Strict-Transport-Security"].startswith("max-age=31536000")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Referrer-Policy"] == "no-referrer"


def test_id_token_from_an_unexpected_issuer_is_refused(srv, monkeypatch):
    b, c = srv
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "gink-id"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"id_token": "x", "access_token": "y"}))
    good = {"aud": "gink-id", "exp": time.time() + 60, "email": "ib@example.com", "email_verified": True, "iss": "https://accounts.google.com"}
    monkeypatch.setattr(b, "_unverified_claims", lambda t: dict(good))
    assert b._identity_from_code("google", "code", "https://x/cb")[0] == "ib@example.com"
    monkeypatch.setattr(b, "_unverified_claims", lambda t: {**good, "iss": "https://accounts.google.com.evil.example"})
    with pytest.raises(ValueError, match="unexpected issuer"):
        b._identity_from_code("google", "code", "https://x/cb")
