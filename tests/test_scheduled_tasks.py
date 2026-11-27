"""Scheduled tasks for everyone (0.1.161): the server runs a task at its local time -- searching the web as it needs --
and the result arrives in the task's own synced chat (and by email). Session (/tasks) and API key (/v1/tasks) routes,
plan limits, the family and workspace rules, retries, and the prompt that makes chats offer schedules."""
import asyncio, datetime, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import pytest
import test_genie
from test_genie import SCRIPT, SEEN, call      # the simulated AI (genie_srv: conftest.py)
from zoneinfo import ZoneInfo

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def srv(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    return b, c, dict(h, **{"X-Gink-TZ": "Europe/Paris", "X-Gink-Locale": "fr-FR"})


def local(b, ts, tz):
    return datetime.datetime.fromtimestamp(ts, ZoneInfo(tz))


def run_due(b):
    async def go():
        n = await b._tasks_tick()
        await asyncio.gather(*[t for t in list(b._safety_tasks) if not t.done()], return_exceptions=True)
        return n
    return asyncio.run(go())


def chat_doc(c, h, chat_id):
    docs = c.post("/sync", headers=h, json={"since": 0, "push": {}}).json()["changes"]["chats"]
    return next((d for d in docs if d["id"] == chat_id), None)


def test_next_run_for_every_kind_and_daylight_saving():
    from ginkassistant.services import backend_server as b
    tz = "Europe/Paris"
    sat = datetime.datetime(2026, 11, 21, 9, 0, tzinfo=ZoneInfo(tz)).timestamp()          # a Saturday, 09:00
    t = local(b, b._task_next("daily", "08:00", tz, None, None, sat), tz)
    assert (t.day, t.hour) == (22, 8)                                                       # already past: tomorrow
    t = local(b, b._task_next("weekdays", "08:00", tz, None, None, sat), tz)
    assert (t.weekday(), t.day) == (0, 23)                                                  # the weekend is skipped
    t = local(b, b._task_next("weekly", "18:30", tz, 4, None, sat), tz)
    assert (t.weekday(), t.day, t.hour, t.minute) == (4, 27, 18, 30)                        # next Friday
    t = local(b, b._task_next("monthly", "08:00", tz, 31, None, sat), tz)
    assert (t.month, t.day) == (11, 30)                                                     # the 31st in November: the 30th
    t = local(b, b._task_next("hourly", "00:15", tz, None, None, sat), tz)
    assert (t.hour, t.minute) == (9, 15)
    assert b._task_next("once", "08:00", tz, None, "2026-11-21", sat) is None                # passed
    t = local(b, b._task_next("once", "17:00", tz, None, "2026-11-21", sat), tz)
    assert (t.day, t.hour) == (21, 17)
    before = datetime.datetime(2026, 3, 28, 12, 0, tzinfo=ZoneInfo(tz)).timestamp()      # clocks go forward on the 29th
    t = local(b, b._task_next("daily", "08:00", tz, None, None, before + 86400), tz)
    assert (t.day, t.hour, t.utcoffset()) == (30, 8, datetime.timedelta(hours=2))           # still 08:00 local


def test_times_and_schedule_fields():
    from ginkassistant.services import backend_server as b
    assert [b._task_time(x) for x in ("8", "08:05", "8am", "5:30 pm", "12am", "17h30", "25:00", "noon")] == \
        ["08:00", "08:05", "08:00", "17:30", "00:00", "17:30", "", ""]
    f = b._task_fields({"every": "every week", "day": "Friday", "at": "6pm"}, "UTC")
    assert (f["every"], f["day"], f["at"]) == ("weekly", 4, "18:00")
    assert b._task_fields({"every": "monthly", "day": "1st"}, "UTC")["day"] == 1
    assert b._task_fields({"every": "once", "date": "2030-01-02", "at": "9"}, "UTC")["date"] == "2030-01-02"
    for bad in ({"every": "yearly"}, {"at": "soon"}, {"every": "weekly", "day": "someday"}, {"every": "monthly", "day": 40},
                {"every": "once", "date": "next week"}):
        with pytest.raises(Exception) as e:
            b._task_fields(bad, "UTC")
        assert getattr(e.value, "status_code", 0) == 400, bad
    assert b._task_when({"every": "monthly", "day": 2, "at": "07:00"}) == "Every month on the 2nd at 07:00"
    assert b._task_when({"every": "weekly", "day": 0, "at": "09:00"}) == "Every Monday at 09:00"


def test_create_from_a_chat_card_runs_with_search_and_lands_in_its_chat(srv, monkeypatch):
    b, c, h = srv
    sent = []
    monkeypatch.setattr(b, "_send_email", lambda to, subject, text, html="": sent.append((to, subject, text)) or "")
    t = c.post("/tasks", headers=h, json={"title": "Morning news", "task": "Give me the three biggest news stories, with sources.",
                                          "every": "daily", "at": "08:00", "notify_email": True, "source": "blk_abc"}).json()
    assert t["timezone"] == "Europe/Paris" and t["when"] == "Every day at 08:00" and t["chat_id"] == "task-" + t["id"][4:]
    assert local(b, t["next_run"], "Europe/Paris").hour == 8 and t["enabled"] is True
    again = c.post("/tasks", headers=h, json={"task": "Give me the news", "source": "blk_abc"}).json()
    assert again["id"] == t["id"] and again["existing"] is True                      # the same card again: no second task
    doc = chat_doc(c, h, t["chat_id"])                                               # its chat is on every device at once
    assert doc["payload"]["title"] == "Morning news" and "Scheduled task: Morning news" in doc["payload"]["messages"][0]["content"]
    listing = c.get("/tasks", headers=h).json()
    assert [x["id"] for x in listing["data"]] == [t["id"]] and listing["limits"] == {"plan": "pro", "max": 25, "used": 1, "hourly": True}
    SCRIPT[:] = [{"content": "", "tool_calls": [call("web_search", query="top news today")]},
                 {"content": "A new space telescope launched; markets rose."},                   # the search's own answer
                 {"content": "## Today\n1. A new telescope launched.\n2. Markets rose."}]
    SEEN.clear()
    r = c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True}).json()
    assert r["status"] == "ok" and r["text"].startswith("## Today") and r["task"]["runs"] == 1
    system = SEEN[0]["messages"][0]["content"]
    assert "scheduled task" in system and "Morning news" in system and "(Europe/Paris)" in system and "(and by email)" in system
    assert [x["function"]["name"] for x in SEEN[0]["tools"]] == ["web_search", "read_page"]
    assert SEEN[0]["messages"][-1] == {"role": "user", "content": "Give me the three biggest news stories, with sources."}
    msgs = chat_doc(c, h, t["chat_id"])["payload"]["messages"]
    assert len(msgs) == 2 and msgs[1]["role"] == "assistant" and msgs[1]["content"].startswith("**⏰ Morning news**")
    assert "2. Markets rose." in msgs[1]["content"]
    assert sent and sent[0][0] == "ib@example.com" and sent[0][1] == "⏰ Morning news" and "Markets rose" in sent[0][2]
    got = c.get(f"/tasks/{t['id']}", headers=h).json()
    assert got["last_status"] == "ok" and got["results"][-1]["text"] == msgs[1]["content"]
    assert c.post(f"/tasks/{t['id']}/run", headers=h).status_code == 429                # it just ran
    # the next run sees the previous result (to say what's new)
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=?, last_run=0 WHERE id=?", (time.time() - 5, t["id"])))
    SCRIPT[:] = [{"content": "Nothing new since this morning."}]
    SEEN.clear()
    assert run_due(b) == 1
    assert "Markets rose." in SEEN[0]["messages"][1]["content"]
    assert local(b, c.get(f"/tasks/{t['id']}", headers=h).json()["next_run"], "Europe/Paris").hour == 8
    assert run_due(b) == 0                                                           # not due again
    assert len(chat_doc(c, h, t["chat_id"])["payload"]["messages"]) == 3


def test_device_edits_are_kept_and_the_server_copy_is_newer(srv):
    b, c, h = srv
    t = c.post("/tasks", headers=h, json={"task": "Plan my week", "every": "weekly", "day": "monday", "at": "07:00"}).json()
    doc = chat_doc(c, h, t["chat_id"])
    ahead = time.time() + 600                                       # a device whose clock is ten minutes ahead
    mine = dict(doc["payload"], messages=doc["payload"]["messages"] + [{"role": "user", "content": "Add gym on Tuesday"}])
    c.post("/sync", headers=h, json={"since": 0, "push": {"chats": [{"id": t["chat_id"], "updated": ahead, "payload": mine}]}})
    SCRIPT[:] = [{"content": "Monday: ... Tuesday: gym."}]
    c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True})
    d = chat_doc(c, h, t["chat_id"])
    assert [m["role"] for m in d["payload"]["messages"]] == ["assistant", "user", "assistant"]
    assert d["updated"] > ahead                                     # newer than the device's own copy: it takes it


def test_plan_limits_and_the_rules(srv, monkeypatch):
    b, c, h = srv
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "free"})
    assert c.post("/tasks", headers=h, json={"task": "Check the weather", "every": "hourly"}).status_code == 403   # Pro
    for i in range(3):
        assert c.post("/tasks", headers=h, json={"task": f"Task {i}"}).status_code == 200
    r = c.post("/tasks", headers=h, json={"task": "One more"})
    assert r.status_code == 409 and "Gink Pro" in r.json()["detail"]
    assert c.post("/tasks", headers=h, json={"task": ""}).status_code == 400
    assert c.post("/tasks", headers=h, json={"task": "x", "timezone": "Mars/Base"}).status_code == 400
    past = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    assert c.post("/tasks", headers=h, json={"task": "x", "every": "once", "date": past}).status_code in (400, 409)
    assert c.get("/tasks").status_code == 401
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 11)
    assert c.post("/tasks", headers=h, json={"task": "x"}).status_code == 403                   # under 13


def test_pause_resume_change_delete_and_once(srv):
    b, c, h = srv
    t = c.post("/tasks", headers=h, json={"task": "Water the plants", "every": "daily", "at": "19:00"}).json()
    p = c.patch(f"/tasks/{t['id']}", headers=h, json={"enabled": False}).json()
    assert p["enabled"] is False and p["next_run"] is None
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=0"))
    assert run_due(b) == 0                                                           # paused: never runs
    p = c.patch(f"/tasks/{t['id']}", headers=h, json={"enabled": True, "every": "weekly", "day": "friday", "at": "18:00"}).json()
    assert p["enabled"] and p["when"] == "Every Friday at 18:00" and local(b, p["next_run"], "Europe/Paris").weekday() == 4
    chat = p["chat_id"]
    assert c.delete(f"/tasks/{t['id']}", headers=h).json()["deleted"] is True
    assert c.get(f"/tasks/{t['id']}", headers=h).status_code == 404
    assert chat_doc(c, h, chat) is not None                                          # its chat and results stay
    tomorrow = (datetime.datetime.now(ZoneInfo("Europe/Paris")) + datetime.timedelta(days=1)).date().isoformat()
    o = c.post("/tasks", headers=h, json={"task": "Remind me to call Sam", "every": "once", "date": tomorrow, "at": "17:00"}).json()
    assert o["when"].startswith("Once, ") and o["date"] == tomorrow
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=? WHERE id=?", (time.time() - 1, o["id"])))
    SCRIPT[:] = [{"content": "Time to call Sam!"}]
    assert run_due(b) == 1
    done = c.get(f"/tasks/{o['id']}", headers=h).json()
    assert done["enabled"] is False and done["next_run"] is None and done["runs"] == 1        # a one-time task ends


def test_busy_ai_retries_once_and_daily_limit_skips(srv, monkeypatch):
    b, c, h = srv
    t = c.post("/tasks", headers=h, json={"task": "Summarise AI news", "every": "weekly", "at": "08:00"}).json()
    import httpx
    monkeypatch.setattr(test_genie, "groq", lambda request: httpx.Response(503, json={"error": {"message": "busy"}}))
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=? WHERE id=?", (time.time() - 1, t["id"])))
    assert run_due(b) == 1
    x = c.get(f"/tasks/{t['id']}", headers=h).json()
    assert x["last_status"] == "retrying" and 500 < x["next_run"] - time.time() < 700          # once more in 10 minutes
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=? WHERE id=?", (time.time() - 1, t["id"])))
    assert run_due(b) == 1
    x = c.get(f"/tasks/{t['id']}", headers=h).json()
    # then its normal time -- the same as when it was made (before 08:00 that's later today, so no "> a day")
    assert x["last_status"] == "failed" and x["next_run"] - time.time() > 700 and abs(x["next_run"] - t["next_run"]) < 5
    monkeypatch.setattr(b, "_count_call", lambda *a, **k: b._ai_error(429, "You've used today's 30 free messages.", "daily_limit"))
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET next_run=? WHERE id=?", (time.time() - 1, t["id"])))
    assert run_due(b) == 1
    x = c.get(f"/tasks/{t['id']}", headers=h).json()
    assert x["last_status"] == "skipped" and "30 free messages" in x["last_note"]


def test_no_web_tools_when_search_is_off(srv):
    b, c, h = srv
    b._prefs_db(lambda con: con.execute("INSERT OR REPLACE INTO account_preferences (email, data, updated) VALUES (?, ?, ?)",
                                        ("ib@example.com", json.dumps({"web_search": False}), time.time())))
    t = c.post("/tasks", headers=h, json={"task": "A joke for the morning"}).json()
    SCRIPT[:] = [{"content": "Why did the scarecrow win an award?"}]
    SEEN.clear()
    assert c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True}).json()["status"] == "ok"
    assert "tools" not in SEEN[0]


def test_api_key_routes_and_openapi(srv):
    b, c, h = srv
    key = b._create_api_key("ib@example.com", "k")["key"]
    k = {"Authorization": f"Bearer {key}", "X-Gink-TZ": "America/Lima"}
    t = c.post("/v1/tasks", headers=k, json={"task": "Weekly AI digest", "every": "weekly", "day": 0, "at": "09:00"}).json()
    assert t["timezone"] == "America/Lima" and t["when"] == "Every Monday at 09:00"
    assert [x["id"] for x in c.get("/v1/tasks", headers=k).json()["data"]] == [t["id"]]
    assert c.get("/tasks", headers=h).json()["data"][0]["id"] == t["id"]               # the same account's tasks
    spec = c.get("/v1/openapi.json").json()
    assert "/tasks" in spec["paths"] and "/tasks/{task_id}/run" in spec["paths"] and "Task" in spec["components"]["schemas"]
    props = spec["paths"]["/chat/completions"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert "gink_tasks" in props


def test_schedule_prompt_is_the_same_everywhere_and_in_the_system_prompts():
    from ginkassistant.services import backend_server as b, groq_worker as g
    assert b.SCHEDULE_PROMPT == g.SCHEDULE_PROMPT and g.SCHEDULE_PROMPT in g.DEFAULT_SYSTEM_PROMPT
    js = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    line = next(x for x in js.splitlines() if x.strip().startswith("var SCHEDULE_PROMPT = "))
    assert json.loads(line.split("= ", 1)[1].rstrip(";")) == g.SCHEDULE_PROMPT
    assert '" " + SCHEDULE_PROMPT' in js
    assert "```schedule" not in g.SCHEDULE_PROMPT and "language schedule" in g.SCHEDULE_PROMPT


def test_developer_flag_adds_the_schedule_prompt(srv):
    b, c, h = srv
    key = b._create_api_key("ib@example.com", "k")["key"]
    SEEN.clear()
    SCRIPT[:] = [{"content": "Done."}]
    c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
           json={"messages": [{"role": "user", "content": "every day at 7 tell me a quote"}], "gink_tasks": True, "gink_web": False})
    assert any(m["role"] == "system" and m["content"] == b.SCHEDULE_PROMPT for m in SEEN[-1]["messages"])


def test_python_sdk_tasks_and_answer_helpers(srv):
    b, c, h = srv
    sys.path.insert(0, os.path.join(ROOT, "cli"))
    from gink import Client, artifacts, schedules_in
    key = b._create_api_key("ib@example.com", "k")["key"]
    gink = Client(api_key=key, base_url="http://testserver/v1", http=c)
    t = gink.tasks.create("Give me a quote to start the day", every="weekdays", at="7am", timezone="Asia/Tokyo",
                          title="Morning quote")
    assert t.when == "Weekdays at 07:00" and t.timezone == "Asia/Tokyo" and [x.id for x in gink.tasks.list()] == [t.id]
    SCRIPT[:] = [{"content": "\u201cWell begun is half done.\u201d"}]
    r = gink.tasks.run(t.id)
    assert r.status == "ok" and "half done" in r.text
    assert gink.tasks.get(t.id).results[-1]["text"].endswith("half done.\u201d")
    assert gink.tasks.pause(t.id).enabled is False and gink.tasks.resume(t.id).enabled is True
    assert gink.tasks.update(t.id, every="monthly", day=15).when == "Every month on the 15th at 07:00"
    gink.tasks.delete(t.id)
    assert gink.tasks.list() == []
    text = ('Here it is.\n\n```html title="Pomodoro timer"\n<!doctype html><p>25:00</p>\n```\n\nDarker:\n\n'
            '```html title="Pomodoro timer"\n<!doctype html><p style="color:#fff">25:00</p>\n```\n\n```bash\nls\n```\n\n'
            '```python title="invoice.py"\nprint("invoice")\n```\n\nI\'ll do it every morning.\n\n```schedule\n'
            '{"title": "News", "task": "Top news", "every": "daily", "at": "08:00"}\n```')
    arts = artifacts(text)
    assert [(a["title"], a["kind"], a["filename"], a["version"]) for a in arts] == [
        ("Pomodoro timer", "page", "pomodoro-timer.html", 1), ("Pomodoro timer", "page", "pomodoro-timer.html", 2),
        ("invoice.py", "code", "invoice.py", 1)]
    assert schedules_in(text) == [{"title": "News", "task": "Top news", "every": "daily", "at": "08:00"}]
    made = gink.tasks.create(**schedules_in(text)[0])
    assert made.title == "News" and made.every == "daily"


def test_cli_tasks_artifacts_and_auto(monkeypatch, capsys, tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "cli"))
    from gink_cli import main as m
    calls, sent = [], []

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if method == "POST" and path == "/tasks":
            return R(dict(kw["json"], id="tsk_1", title=kw["json"].get("title") or "Top news", when="Every day at 08:00",
                          timezone="UTC", next_run=time.time() + 60))
        if path == "/tasks/tsk_1/run":
            return R({"status": "ok", "text": "Today: three stories."})
        return R({"data": [], "limits": {"max": 3, "used": 0}})
    monkeypatch.setattr(m, "_env_call", fake)
    monkeypatch.setattr(m, "settings", lambda: ("k", "https://x/v1"))
    assert m.main(["tasks", "add", "Top", "news", "--every", "weekly", "--day", "friday", "--at", "18:00", "--email"]) == 0
    assert calls[-1] == ("POST", "/tasks", {"task": "Top news", "every": "weekly", "at": "18:00", "day": "friday", "notify_email": True})
    assert m.main(["tasks"]) == 0 and "No scheduled tasks" in capsys.readouterr().out
    assert m.main(["tasks", "run", "tsk_1"]) == 0 and "three stories" in capsys.readouterr().out
    answer = ('Your timer:\n\n```html title="Pomodoro timer"\n<!doctype html><p>25:00</p>\n```\n\n'
              '```schedule\n{"title": "News", "task": "Top news", "every": "daily", "at": "08:00"}\n```')
    monkeypatch.setattr(m, "stream_answer", lambda key, base, messages, model="", out=None, extra=None: sent.append(extra) or answer)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", None)
    assert m.main(["--save-artifacts", "out", "--schedule", "make", "a", "timer"]) == 0
    assert sent[-1] == {"gink_web": "auto", "gink_code": True, "gink_artifacts": True, "gink_tasks": True}
    assert open(tmp_path / "out" / "pomodoro-timer.html").read() == "<!doctype html><p>25:00</p>\n"
    assert calls[-1] == ("POST", "/tasks", {"title": "News", "task": "Top news", "every": "daily", "at": "08:00"})
    assert m.main(["--no-auto", "hello"]) == 0 and sent[-1] is None


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="needs Node")
def test_js_sdk_tasks_and_answer_helpers(tmp_path):
    import subprocess
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink, artifacts, schedulesIn } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url, init.body ? JSON.parse(init.body) : null]);
  return new Response(JSON.stringify({ id: "tsk_1", data: [] }), { status: 200 }); } });
await gink.tasks.create({ task: "Brief", every: "weekly", day: "monday", at: "06:00", notify_email: true });
await gink.tasks.pause("tsk_1"); await gink.tasks.run("tsk_1"); await gink.tasks.get("tsk_1", { results: 2 });
const text = "```html title=\\"Timer\\"\\n<p>1</p>\\n```\\n\\n```schedule\\n{\\"task\\": \\"Top news\\", \\"every\\": \\"daily\\", \\"at\\": \\"08:00\\"}\\n```";
console.log(JSON.stringify({ seen, arts: artifacts(text), offers: schedulesIn(text) }));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["seen"][0] == ["POST", "https://x/v1/tasks", {"task": "Brief", "every": "weekly", "at": "06:00", "day": "monday", "notify_email": True}]
    assert out["seen"][1] == ["PATCH", "https://x/v1/tasks/tsk_1", {"enabled": False}]
    assert out["seen"][2] == ["POST", "https://x/v1/tasks/tsk_1/run", {"wait": True}] and out["seen"][3][1].endswith("/tsk_1?results=2")
    assert out["arts"] == [{"title": "Timer", "language": "html", "kind": "page", "content": "<p>1</p>", "filename": "timer.html", "version": 1}]
    assert out["offers"] == [{"task": "Top news", "every": "daily", "at": "08:00"}]
    d_ts = open(os.path.join(ROOT, "sdk", "js", "index.d.ts"), encoding="utf-8").read()
    assert "export declare function artifacts(" in d_ts and "export declare function schedulesIn(" in d_ts and "tasks: {" in d_ts


def test_scheduled_agents_can_run_on_weekdays_too(srv):
    b, c, h = srv
    tz = "Europe/Paris"
    sat = datetime.datetime(2026, 11, 21, 9, 0, tzinfo=ZoneInfo(tz)).timestamp()
    assert local(b, b._next_run("weekdays", "08:00", tz, sat), tz).weekday() == 0
    s = c.post("/dev/schedules", headers=h, json={"input": "Update news.md", "every": "weekdays", "at": "07:30"}).json()
    assert s["every"] == "weekdays" and local(b, s["next_run"], "Europe/Paris").weekday() < 5
    for page in ("genie.html", "console.html"):
        html = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", page), encoding="utf-8").read()
        assert '<option value="weekdays">Weekdays</option>' in html, page


def test_new_results_arriving_by_sync_are_noticed(tmp_path):
    from ginkassistant.services.history import HistoryStore
    h = HistoryStore.__new__(HistoryStore)
    h.db_path = tmp_path / "h.db"
    h._init_db()
    intro = {"role": "assistant", "content": "**⏰ Scheduled task: News**"}
    h.apply_remote([{"id": "task-1", "updated": 10, "payload": {"title": "News", "messages": [intro]}}])
    assert h.pop_task_news() == []                                  # just made: nothing to tell yet
    result = {"role": "assistant", "content": "**⏰ News** · Monday\n\nThree stories."}
    h.apply_remote([{"id": "task-1", "updated": 20, "payload": {"title": "News", "messages": [intro, result]}},
                    {"id": "session-x", "updated": 20, "payload": {"messages": [result, result]}}])
    assert h.pop_task_news() == [{"id": "task-1", "title": "News", "text": result["content"]}]   # only task chats
    assert h.pop_task_news() == []


def test_every_part_of_the_suite_has_the_task_pieces():
    def read(*parts):
        return open(os.path.join(ROOT, *parts), encoding="utf-8").read()
    extras = read("src", "ginkassistant", "ui", "chat_extras.py")
    for part in ("window.upgradeSchedules = function (root, isNew)", "ginkEmit('task_create'", "window.setTasks = function",
                 "window.taskResult = function", "ginkEmit('tasks_load', null)", ".tskcard .tsk-a button.primary"):
        assert part in extras, part
    page = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "upgradeSchedules(el, !LOADING_CHAT)" in page and "(?:map|ask|schedule)" in page
    assert "async def set_tasks(self" in page and "async def task_result(self" in page
    bridge = read("webapp", "bridge.js")
    for part in ("tasks_load: function", "task_create: function", "task_action: function", "task_open: function",
                 "function taskNews(n)", 'name === "tsk_add"', 'api("/tasks")', "Notification.requestPermission()"):
        assert part in bridge, part
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert 'kind in ("task_create", "task_action", "task_open", "tasks_load")' in main and "brain.history.pop_task_news()" in main
    ctl = read("src", "ginkassistant", "ui", "settings_controller.py")
    for name in ("_a_tsk_add", "_a_tsk_pause", "_a_tsk_resume", "_a_tsk_run", "_a_tsk_delete", "_a_tsk_open"):
        assert f"async def {name}(" in ctl, name
    settings = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "scheduleSections(info.tasks, info.tasks_error, info.schedules, info.tasks_limits)" in settings
    assert "name === 'tsk_add'" in settings and "data-tsk-for" in settings
    from ginkassistant.services.actions.tools import TOOL_SPECS, ToolRunner
    from ginkassistant.services.actions import agent
    assert "schedule_task" in [t["function"]["name"] for t in TOOL_SPECS] and hasattr(ToolRunner, "_t_schedule_task")
    text = agent._with_schedules("Done.", [{"tool": "schedule_task", "result": {"ok": True},
                                            "args": {"title": "Water", "task": "Remind me to drink water", "every": "daily", "at": "09:00"}}])
    assert text.startswith("Done.\n\n```schedule\n") and '"title": "Water"' in text and text.endswith("\n```")
    from ginkassistant.services.actions import quick_parse
    assert quick_parse.parse("remind me to drink water every day at 9") is None          # a repeat: a scheduled task
    assert quick_parse.parse("remind me to call mom at 5pm")[0] == "add_reminder"


def test_a_run_with_no_searches_left_still_answers(srv, monkeypatch):
    b, c, h = srv
    t = c.post("/tasks", headers=h, json={"task": "Find three new films this week"}).json()
    monkeypatch.setattr(b, "_count_search", lambda *a, **k: b._ai_error(429, "used up", "daily_limit"))
    SCRIPT[:] = [{"content": "", "tool_calls": [call("web_search", query="films"), call("web_search", query="cinema")]},
                 {"content": "I couldn't search today, but here are three recent films I know of."}]
    SEEN.clear()
    r = c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True}).json()
    assert r["status"] == "ok" and "couldn't search" in r["text"]
    last = SEEN[-1]                     # then: the answer, with no tools at all (tool_choice "none" still slipped, 0.1.162)
    assert "tools" not in last and "tool_choice" not in last and not any(m["role"] == "tool" for m in last["messages"])
    said = [m["content"] for m in last["messages"] if m["role"] == "user"]
    assert sum("isn't available" in t for t in said) == 2                                  # both calls answered, as text
    assert any(m["role"] == "system" and m["content"] == b.PLAIN_TEXT_NOTE for m in last["messages"])


def test_runs_know_the_person_unless_memory_is_off(srv):
    b, c, h = srv
    now = time.time()
    c.post("/sync", headers=h, json={"since": 0, "push": {
        "profile": [{"id": "me", "updated": now, "payload": {"nickname": "Ibi", "work": "builds apps"}}],
        "memories": [{"id": "m1", "updated": now, "payload": {"text": "Lives in Lagos", "created": int(now)}}]}})
    t = c.post("/tasks", headers=h, json={"task": "Tell me tomorrow's weather where I live"}).json()
    SCRIPT[:] = [{"content": "Sunny, 31°C."}]
    SEEN.clear()
    c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True})
    note = SEEN[0]["messages"][1]["content"]
    assert "Call the person Ibi." in note and "- Lives in Lagos" in note and "Their work: builds apps." in note
    b._prefs_db(lambda con: con.execute("INSERT OR REPLACE INTO account_preferences (email, data, updated) VALUES (?, ?, ?)",
                                        ("ib@example.com", json.dumps({"use_memory": False}), time.time())))
    b._task_db(lambda con: con.execute("UPDATE chat_tasks SET last_run=0"))
    SCRIPT[:] = [{"content": "Sunny."}]
    SEEN.clear()
    c.post(f"/tasks/{t['id']}/run", headers=h, json={"wait": True})
    assert "Lives in Lagos" not in SEEN[0]["messages"][1]["content"]                     # memory off: not used


def test_the_apps_settings_manage_tasks(tmp_path, monkeypatch):
    import toga
    from ginkassistant.ui import settings_controller as scm
    app = toga.App("t", "org.t")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    from ginkassistant.services.actions import DeviceActions, ReminderScheduler, TaskStore, ToolRunner
    from ginkassistant.services.memory import MemoryStore
    app.task_store = TaskStore(str(tmp_path / "t.db")); app.memory = MemoryStore(str(tmp_path / "m.db"))
    app.task_runner = ToolRunner(app.task_store, DeviceActions(str(tmp_path)), memory=app.memory)
    app.task_scheduler = ReminderScheduler(app.task_store)
    app.state = type("St", (), {"base_url": "http://t"})()
    app.session_token = "tok"
    calls, tasks = [], [{"id": "tsk_1", "title": "News", "when": "Every day at 08:00", "enabled": True, "chat_id": "task-1"}]

    class Api:
        def __init__(self, base): pass
        async def app_info(self): return {}
        async def tasks(self, token): calls.append(("list",)); return {"data": tasks, "limits": {"max": 3, "used": 1}}
        async def schedules(self, token): return {"data": []}
        async def task_create(self, token, body): calls.append(("create", body)); return dict(body, id="tsk_2")
        async def task_update(self, token, tid, body): calls.append(("update", tid, body)); return {}
        async def task_run(self, token, tid): calls.append(("run", tid)); return {}
        async def task_delete(self, token, tid): calls.append(("delete", tid)); return {}
    monkeypatch.setattr(scm, "ApiClient", Api)

    class Web:
        def __init__(self): self.calls = []
        async def set_settings_state(self, st): self.calls.append(("state", st))
        async def settings_toast(self, t, k="ok"): self.calls.append(("toast", t, k))
        async def close_settings(self): self.calls.append(("close",))
        def __getattr__(self, name):
            async def anything(*a, **k): self.calls.append((name, a))
            return anything
    class Brain:
        preferred_model = ""; memory_provider = None; reply_language_note = None; history = None
    web, shown, opened, ran = Web(), [], [], []
    ctl = scm.SettingsController(app, web, Brain(), {"value": "Female (Jenny)"}, type("A", (), {"voice_key": None})(),
                                 email="ib@x.co", display_name="Ibrahim", models_fn=lambda: [], push_models=None,
                                 open_pro=lambda: None, on_log_out=lambda: None, refresh_sidebar=lambda: None,
                                 clear_all_chats=lambda: 0, brief_now=None, sync_fn=None, open_url=None)

    async def on_tasks(lst): shown.append(lst)

    async def on_open(chat): opened.append(chat)
    ctl.on_tasks, ctl.on_open_chat, ctl.on_task_ran = on_tasks, on_open, lambda: ran.append(1)
    run = asyncio.run
    run(ctl.refresh("schedules"))
    info = [c[1]["info"] for c in web.calls if c[0] == "state" and "tasks" in c[1].get("info", {})][-1]
    assert info["tasks"] == tasks and info["tasks_limits"]["max"] == 3 and shown[-1] == tasks       # the cards too
    run(ctl.on_action("tsk_add", json.dumps({"task": "Top news", "every": "weekly", "day": 4, "at": "18:00", "notify_email": True})))
    assert ("create", {"task": "Top news", "every": "weekly", "at": "18:00", "day": 4, "notify_email": True}) in calls
    run(ctl.on_action("tsk_add", json.dumps({"task": "  "})))
    assert web.calls[-1] == ("toast", "Write the task first.", "err")
    run(ctl.on_action("tsk_pause", "tsk_1")); run(ctl.on_action("tsk_resume", "tsk_1"))
    assert ("update", "tsk_1", {"enabled": False}) in calls and ("update", "tsk_1", {"enabled": True}) in calls
    run(ctl.on_action("tsk_run", "tsk_1"))
    assert ("run", "tsk_1") in calls and ran == [1]
    run(ctl.on_action("tsk_delete", "tsk_1"))
    assert ("delete", "tsk_1") in calls
    run(ctl.on_action("tsk_open", "task-1"))
    assert ("close",) in web.calls and opened == ["task-1"]
    app.session_token = None
    run(ctl.refresh("schedules"))
    info = [c[1]["info"] for c in web.calls if c[0] == "state"][-1]
    assert info.get("tasks_error") == "Sign in to Gink to schedule tasks."
