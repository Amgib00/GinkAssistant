"""Gink Genie review fixes: age and parental controls apply in Genie too; when the AI stops answering
partway, the changes made so far are kept and reported; version history doesn't fill the disk; a
refused new project doesn't leave an empty one behind."""
import json
import os
import sys
import time
sys.path.insert(0, os.path.dirname(__file__))
import httpx
from test_genie import SEEN, call, build      # the simulated AI (genie_srv: conftest.py)

Y = time.gmtime().tm_year


def teen_setup(b, c, h, controls=None):
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    b._set_birth_year("ib@example.com", Y - 15)
    b._upsert_user("mum@x.co", "Aminata", None, "password")
    b._set_birth_year("mum@x.co", Y - 40)
    mum = {"Authorization": "Bearer " + b._token_response("mum@x.co", "Aminata")["token"]}
    c.post("/family/invite", headers=mum, json={"teen": "ib@example.com"})
    c.post("/family/respond", headers=h, json={"accept": True})
    if controls:
        assert c.put("/family/controls", headers=mum, json={"teen": "ib@example.com", "controls": controls}).status_code == 200
    return mum


def test_parent_can_switch_genie_off(genie_srv):
    b, c, h = genie_srv
    teen_setup(b, c, h, {"genie": False})
    r = c.post("/genie/projects", headers=h, json={"prompt": "Build a quiz game"})
    assert r.status_code == 403 and "Gink Genie is turned off" in r.json()["detail"]
    assert c.get("/genie/projects", headers=h).json()["projects"] == []         # nothing half-made


def test_quiet_hours_and_daily_limit_in_genie(genie_srv):
    b, c, h = genie_srv
    now = time.gmtime()
    mum = teen_setup(b, c, h, {"quiet": True, "quiet_from": f"{now.tm_hour:02d}:00",
                               "quiet_to": f"{(now.tm_hour + 2) % 24:02d}:00", "tz": "UTC"})
    r = c.post("/genie/projects", headers=h, json={"prompt": "Build a quiz game"})
    assert r.status_code == 403 and "quiet time" in r.json()["detail"]
    c.put("/family/controls", headers=mum, json={"teen": "ib@example.com", "controls": {"quiet": False, "daily_limit": 1}})
    assert "result" in build(c, h)                                              # message 1 of 1
    pid = c.get("/genie/projects", headers=h).json()["projects"][0]["id"]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "Add a score"})
    assert r.status_code == 429 and "parental controls" in r.json()["detail"]


def test_teens_get_stricter_safety_and_notices_in_genie(genie_srv, monkeypatch):
    b, c, h = genie_srv
    teen_setup(b, c, h)
    checked = []
    monkeypatch.setattr(b, "_start_safety_check", lambda teen, parent, text: checked.append((teen, parent, text)))
    build(c, h, "Build a diary app")
    assert any(m.get("content") == b.TEEN_SAFETY for m in SEEN[0]["messages"])
    assert checked == [("ib@example.com", "mum@x.co", "Build a diary app")]


def test_adults_unchanged(genie_srv):
    b, c, h = genie_srv
    build(c, h)
    assert not any(m.get("content") == b.TEEN_SAFETY for m in SEEN[0]["messages"])


def test_under_13_blocked(genie_srv):
    b, c, h = genie_srv
    b._set_birth_year("ib@example.com", Y - 11)
    r = c.post("/genie/projects", headers=h, json={"prompt": "Build a game"})
    assert r.status_code == 403 and r.json()["detail"] == b.UNDER_13_MSG


def test_ai_stops_partway_changes_kept_and_reported(genie_srv, monkeypatch):
    b, c, h = genie_srv
    from httpx import _client
    real = _client.AsyncClient                                  # the real one (the fixture's mock would override us)
    state = {"n": 0}

    def flaky(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
                call("write_file", path="index.html", content="<h1>Half</h1>")]}}]})
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(flaky); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    r = c.post("/genie/projects", headers=h, json={"prompt": "Build a page"}).json()
    assert r["result"]["failed"] is True and "busy right now" in r["result"]["reply"]
    assert "changes so far are kept" in r["result"]["reply"] and [f["path"] for f in r["files"]] == ["index.html"]
    pid = r["project"]["id"]
    chat = c.get(f"/genie/projects/{pid}/chat", headers=h).json()
    assert "busy right now" in json.dumps(chat)                                 # the request isn't lost from the chat
    state["n"] = 1                                                               # nothing changed this time: an error
    r2 = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "Add a footer"})
    assert r2.status_code == 502 and "busy right now" in r2.json()["detail"]


def test_version_history_without_duplicates_and_within_budget(genie_srv, monkeypatch):
    b, c, h = genie_srv
    pid = build(c, h)["project"]["id"]
    count = lambda: b._genie_db(lambda con: con.execute("SELECT COUNT(*) FROM genie_snapshots WHERE project_id=?", (pid,)).fetchone()[0])
    before = count()
    a = b._genie_checkpoint(pid, "a question")
    assert count() == before + 1
    assert b._genie_checkpoint(pid, "another question") == a and count() == before + 1      # unchanged: no copy
    monkeypatch.setattr(b, "GENIE_SNAPSHOT_BYTES", 5000)
    for i in range(6):
        b._genie_write(pid, f"notes{i}.txt", "x" * 1500)
        b._genie_checkpoint(pid, f"step {i}")
    sizes = b._genie_db(lambda con: con.execute("SELECT length(files) FROM genie_snapshots WHERE project_id=?", (pid,)).fetchall())
    assert sum(s for (s,) in sizes) <= 5000 or len(sizes) == 1                  # within budget (the newest always kept)
    assert len(sizes) >= 1
