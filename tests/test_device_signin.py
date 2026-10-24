"""Device sign-in for the CLI ("gink login"): code -> approve in the browser -> a new API key, once."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src")); sys.path.insert(0, os.path.join(HERE, "..", "cli"))
import pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "d.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    for d in (b._device_codes, b._device_by_user, b._device_starts, b._device_lookups):
        d.clear()
    c = TestClient(b.app)
    me = {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}
    return b, c, me


def test_approve_gives_a_working_key_once(srv):
    b, c, me = srv
    d = c.post("/auth/device/start", json={"client": "gink CLI on MacBook-Air"}).json()
    assert re.fullmatch(r"[BCDFGHJKLMNPQRSTVWXZ]{4}-[BCDFGHJKLMNPQRSTVWXZ]{4}", d["user_code"])
    assert d["verification_uri_complete"].endswith("/device?code=" + d["user_code"]) and d["interval"] == 5
    assert c.post("/auth/device/poll", json={"device_code": d["device_code"]}).json() == {"status": "pending"}
    assert c.post("/auth/device/lookup", json={"user_code": d["user_code"]}).status_code == 401            # must be signed in
    assert c.post("/auth/device/lookup", headers=me, json={"user_code": d["user_code"].lower().replace("-", "")}).json()["client"] \
        == "gink CLI on MacBook-Air"                                                                         # forgiving typing
    assert c.post("/auth/device/approve", headers=me, json={"user_code": d["user_code"], "approve": True}).json()["status"] == "approved"
    b._device_codes[d["device_code"]]["polled"] = 0
    got = c.post("/auth/device/poll", json={"device_code": d["device_code"]}).json()
    assert got["status"] == "approved" and got["api_key"].startswith("gink_live_") and got["email"] == "ib@example.com"
    assert c.post("/auth/device/poll", json={"device_code": d["device_code"]}).json() == {"status": "expired"}   # once
    assert c.get("/v1/models", headers={"Authorization": "Bearer " + got["api_key"]}).status_code == 200
    assert "Device sign-in approved: gink CLI on MacBook-Air" in [e["text"] for e in c.get("/account/security-history", headers=me).json()["events"]]


def test_deny_wrong_codes_and_limits(srv):
    b, c, me = srv
    d = c.post("/auth/device/start", json={}).json()
    assert c.post("/auth/device/lookup", headers=me, json={"user_code": "BCDF-GHJK"}).status_code == 404
    c.post("/auth/device/approve", headers=me, json={"user_code": d["user_code"], "approve": False})
    assert c.post("/auth/device/poll", json={"device_code": d["device_code"]}).json() == {"status": "denied"}
    d2 = c.post("/auth/device/start", json={}).json()
    c.post("/auth/device/poll", json={"device_code": d2["device_code"]})
    assert c.post("/auth/device/poll", json={"device_code": d2["device_code"]}).json() == {"status": "slow_down"}
    codes = [c.post("/auth/device/lookup", headers=me, json={"user_code": "ZZZZ-ZZZZ"}).status_code for _ in range(20)]
    assert codes[-1] == 429                                                                                  # no brute force
    starts = [c.post("/auth/device/start", json={}).status_code for _ in range(10)]
    assert starts[-1] == 429


def test_cli_device_login(srv, monkeypatch):
    """The CLI's own function, against the real server routes."""
    b, c, me = srv
    from gink_cli import main as m
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda **kw: c)                    # the CLI talks to the test server
    monkeypatch.setattr(c, "__enter__", lambda: c, raising=False)
    said = []
    def approve_then_wait(seconds):
        code = re.search(r"enter:\s+(\S+)", said[0]).group(1)
        c.post("/auth/device/approve", headers=me, json={"user_code": code, "approve": True})
        for e in b._device_codes.values():
            e["polled"] = 0
    key = m.device_login("http://testserver/v1", open_browser=False, sleep=approve_then_wait, say=said.append)
    assert key.startswith("gink_live_") and "/device" in said[0] and "Waiting" in said[1]
