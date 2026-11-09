"""Scheduled agents across the suite: hourly / daily / weekly runs at a local time, each an ordinary interaction;
API keys, the console, both SDKs and the CLI."""
import asyncio, datetime, json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest
from test_genie import SCRIPT, call      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def api(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "s")["key"]
    return b, c, {"Authorization": f"Bearer {key}"}, h


def test_next_run_times():
    from ginkassistant.services import backend_server as b
    from zoneinfo import ZoneInfo
    tz = "Asia/Tokyo"
    base = datetime.datetime(2026, 11, 9, 7, 30, tzinfo=ZoneInfo(tz)).timestamp()
    t = datetime.datetime.fromtimestamp(b._next_run("daily", "08:00", tz, base), ZoneInfo(tz))
    assert (t.day, t.hour, t.minute) == (9, 8, 0)                                  # later today, local time
    t = datetime.datetime.fromtimestamp(b._next_run("daily", "07:00", tz, base), ZoneInfo(tz))
    assert (t.day, t.hour) == (10, 7)                                              # already past: tomorrow
    t = datetime.datetime.fromtimestamp(b._next_run("hourly", "08:15", tz, base), ZoneInfo(tz))
    assert (t.hour, t.minute) == (8, 15)


def test_create_list_run_and_due(api):
    b, c, k, session = api
    s = c.post("/v1/schedules", headers=dict(k, **{"X-Gink-TZ": "Europe/Berlin"}),
               json={"input": "Update notes.md with today's news", "every": "daily", "at": "8:05"}).json()
    assert s["every"] == "daily" and s["at"] == "08:05" and s["timezone"] == "Europe/Berlin" and s["environment"].startswith("gp_")
    assert s["next_run"] > time.time()
    assert [x["id"] for x in c.get("/v1/schedules", headers=k).json()["data"]] == [s["id"]]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="notes.md", content="# News")]}, {"content": "Updated."}]
    r = c.post(f"/v1/schedules/{s['id']}/run", headers=k).json()
    assert r["interaction_id"].startswith("int_") and r["schedule"]["last_interaction_id"] == r["interaction_id"]
    for _ in range(50):
        it = c.get(f"/v1/interactions/{r['interaction_id']}", headers=k).json()
        if it["status"] != "running":
            break
        time.sleep(0.05)
    assert it["status"] == "completed" and it["environment"] == s["environment"]
    b._sched_db(lambda con: con.execute("UPDATE agent_schedules SET next_run=? WHERE id=?", (time.time() - 5, s["id"])))
    SCRIPT[:] = [{"content": "Again."}]
    assert asyncio.run(b._schedules_tick()) == 1                                   # due: started
    after = c.get("/v1/schedules", headers=k).json()["data"][0]
    assert after["next_run"] > time.time() + 3600 and after["last_interaction_id"] != r["interaction_id"]
    assert asyncio.run(b._schedules_tick()) == 0                                   # not due again


def test_pause_delete_limits_and_rules(api, monkeypatch):
    b, c, k, session = api
    s = c.post("/dev/schedules", headers=session, json={"input": "Daily summary", "every": "weekly", "at": "09:00"}).json()
    assert c.patch(f"/dev/schedules/{s['id']}", headers=session, json={"enabled": False}).json()["enabled"] is False
    b._sched_db(lambda con: con.execute("UPDATE agent_schedules SET next_run=0"))
    assert asyncio.run(b._schedules_tick()) == 0                                   # paused: never runs
    assert c.delete(f"/dev/schedules/{s['id']}", headers=session).json()["deleted"] is True
    bad = [{"input": ""}, {"input": "x", "every": "monthly"}, {"input": "x", "at": "25:00"}, {"input": "x", "timezone": "Mars/Base"}]
    for body in bad:
        assert c.post("/v1/schedules", headers=k, json=body).status_code == 400, body
    monkeypatch.setattr(b, "SCHEDULE_MAX", 1)
    assert c.post("/v1/schedules", headers=k, json={"input": "one"}).status_code == 200
    assert c.post("/v1/schedules", headers=k, json={"input": "two"}).status_code == 409
    assert c.get("/v1/schedules").status_code == 401
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 11)
    assert c.post("/dev/schedules", headers=session, json={"input": "x"}).status_code == 403    # the usual rules


def test_python_sdk_and_cli(api, monkeypatch, capsys):
    b, c, k, session = api
    from gink import Client
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    s = gink.schedules.create(input="Morning brief in brief.md", every="daily", at="07:30", timezone="America/Lima")
    assert s.timezone == "America/Lima" and [x.id for x in gink.schedules.list()] == [s.id]
    assert gink.schedules.pause(s.id).enabled is False and gink.schedules.resume(s.id).enabled is True
    gink.schedules.delete(s.id)
    assert gink.schedules.list() == []
    from gink_cli import main as m
    calls = []

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if method == "POST" and path == "/schedules":
            return R(dict(kw["json"], id="sch_1", timezone="UTC", next_run=time.time() + 60, environment="gp_9"))
        return R({"data": []})
    monkeypatch.setattr(m, "_env_call", fake)
    monkeypatch.setattr(m, "settings", lambda: ("k", "https://x/v1"))
    assert m.main(["schedule", "add", "Update", "notes", "--every", "hourly", "--at", "00:10"]) == 0
    assert calls[-1] == ("POST", "/schedules", {"input": "Update notes", "every": "hourly", "at": "00:10", "environment": "remote"})
    assert m.main(["schedule", "list"]) == 0 and "No schedules" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_schedules(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url, init.body ? JSON.parse(init.body) : null]);
  return new Response(JSON.stringify({ id: "sch_1", data: [] }), { status: 200 }); } });
await gink.schedules.create({ input: "Brief", every: "weekly", at: "06:00" });
await gink.schedules.pause("sch_1");
await gink.schedules.run("sch_1");
console.log(JSON.stringify(seen));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    seen = json.loads(r.stdout)
    assert seen[0] == ["POST", "https://x/v1/schedules", {"input": "Brief", "every": "weekly", "at": "06:00", "environment": "remote"}]
    assert seen[1] == ["PATCH", "https://x/v1/schedules/sch_1", {"enabled": False}] and seen[2][1].endswith("/sch_1/run")


def test_console_has_schedules():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "console.html"), encoding="utf-8").read()
    assert 'id="sch-add"' in page and "function loadSchedules" in page and '"/dev/schedules"' in page
