import asyncio, json, os, sys, tempfile
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx
from ginkassistant.services.actions import (TaskStore, ToolRunner, TaskAgent, ReminderScheduler,
                                            DeviceActions, ActionResult, looks_like_action)
from ginkassistant.services.actions import quick_parse

NOW = datetime(2026, 10, 9, 22, 15)


class FakeDevice(DeviceActions):
    """Records calls instead of touching the OS."""
    def __init__(self, platform="linux", system_ok=True):
        super().__init__(tempfile.mkdtemp()); self.platform = platform; self.calls = []; self.ok = system_ok
    def set_alarm(self, h, m, label="", date=None, repeat_days=None, item_id=0):
        self.calls.append(("alarm", h, m)); return ActionResult(self.ok, "sys", by_system=self.ok)
    def set_timer(self, s, label=""):
        self.calls.append(("timer", s)); return ActionResult(False, "no system timer")
    def open_app(self, n):
        self.calls.append(("app", n)); return ActionResult(True, f"Opened {n}.")


def store():
    return TaskStore(os.path.join(tempfile.mkdtemp(), "t.db"))


def test_quick_parse():
    P = lambda t: quick_parse.parse(t, NOW)
    assert P("wake me up at 6:30") == ("set_alarm", {"time": "06:30", "label": "Wake up"})
    assert P("Set an alarm for 7am tomorrow")[1]["time"] == "07:00"
    assert P("Set an alarm for 7am tomorrow")[1]["date"] == "2026-10-10"
    assert P("alarm at 9.15 pm")[1]["time"] == "21:15"
    assert P("set a timer for 10 minutes") == ("set_timer", {"seconds": 600, "label": "Timer"})
    assert P("1 hour 30 minutes timer")[1]["seconds"] == 5400
    r = P("remind me to call mom at 5pm")
    assert r == ("add_reminder", {"text": "Call mom", "when": "2026-10-10 17:00"}), r
    r = P("remind me in 20 minutes to stretch")
    assert r[1]["when"] == "2026-10-09 22:35" and r[1]["text"] == "Stretch", r
    assert P("open whatsapp") == ("open_app", {"name": "whatsapp"})
    assert P("show my alarms") == ("list_items", {"kind": "alarm"})
    assert P("add buy milk to my list") == ("add_task", {"title": "Buy milk"})
    assert P("call +221 77 123 45 67")[0] == "make_call"
    assert P("what's the meaning of life") is None
    assert looks_like_action("remind me later") and not looks_like_action("tell me a joke")


def run(c): return asyncio.get_event_loop().run_until_complete(c) if False else asyncio.run(c)


def test_tools_and_store():
    s = store(); dev = FakeDevice(); r = ToolRunner(s, dev)
    res = run(r.execute("set_alarm", {"time": "6:30"}))
    assert res["ok"] and res["by_system"] and dev.calls[0] == ("alarm", 6, 30)
    assert s.get(res["id"]).system_scheduled
    res = run(r.execute("add_task", {"title": "Exam prep", "steps": ["Collect notes", "Past papers", ""]}))
    assert res["steps"] == ["Collect notes", "Past papers"]
    lst = run(r.execute("list_items", {"kind": "task"}))
    assert lst["items"][0]["steps"][1]["title"] == "Past papers"
    run(r.execute("complete_item", {"id": res["id"]}))
    assert all(c.done for c in s.children(res["id"]))
    t = run(r.execute("set_timer", {"seconds": 90}))
    assert t["ok"] and "1m 30s" in t["message"]
    bad = run(r.execute("set_alarm", {"time": "25:99"}))
    assert not bad["ok"]
    bad = run(r.execute("nope", {}))
    assert not bad["ok"]
    bad = run(r.execute("set_alarm", {"tim": "1"}))
    assert not bad["ok"] and "Bad arguments" in bad["message"]
    # iOS: no system alarm -> in-app, honest message
    s2 = store(); r2 = ToolRunner(s2, FakeDevice("ios", system_ok=False))
    res = run(r2.execute("set_alarm", {"time": "07:00"}))
    assert res["ok"] and not res["by_system"] and "keep Gink open" in res["message"]


def test_scheduler_fires_only_in_app_items():
    s = store(); fired = []
    past = datetime.now() - timedelta(seconds=5)
    a = s.add("reminder", "in-app", due=past)
    b = s.add("alarm", "os-handled", due=past, system_scheduled=True)
    s.add("reminder", "future", due=datetime.now() + timedelta(hours=1))
    async def on_due(item): fired.append(item.title)
    sch = ReminderScheduler(s, on_due)
    import ginkassistant.services.actions.scheduler as mod
    notes = []; mod.notify = lambda *a, **k: notes.append(a[0]) or True
    run(sch.tick()); run(sch.tick())
    assert sorted(fired) == ["in-app", "os-handled"], fired     # UI hears about both, once each
    assert notes == ["in-app"], notes                            # but only in-app one rings


def test_agent_loop_with_fake_groq():
    calls = {"n": 0}
    def handler(req):
        body = json.loads(req.content); calls["n"] += 1
        assert req.headers["authorization"] == "Bearer k"
        if calls["n"] == 1:
            assert body["tools"] and "Current local date" in body["messages"][0]["content"]
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "add_task",
                "arguments": json.dumps({"title": "Move flat", "steps": ["Book van", "Pack books"]})}}]}}]})
        tool_msg = body["messages"][-1]
        assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["ok"]
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant",
                                                                  "content": "Plan saved with 2 steps."}}]})
    async def go():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        s = store(); agent = TaskAgent(ToolRunner(s, FakeDevice()), api_key="k", http_client=client)
        rep = await agent.run("help me plan moving flat next week")
        return rep, s
    rep, s = run(go())
    assert rep.text == "Plan saved with 2 steps." and rep.actions[0]["tool"] == "add_task"
    assert [c.title for c in s.children(rep.actions[0]["result"]["id"])] == ["Book van", "Pack books"]


def test_agent_offline_and_failure_fallback():
    s = store(); dev = FakeDevice()
    rep = run(TaskAgent(ToolRunner(s, dev), api_key="").run("wake me up at 6:30"))
    assert not rep.used_ai and dev.calls == [("alarm", 6, 30)]
    rep = run(TaskAgent(ToolRunner(s, dev), api_key="").run("plan my week"))
    assert "GROQ_API_KEY" in rep.text
    # Groq down -> reminder still gets set via the offline parser
    def boom(req): return httpx.Response(500, text="down")
    async def go():
        a = TaskAgent(ToolRunner(s, dev), api_key="k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
        return await a.run("remind me to drink water in 30 minutes")
    rep = run(go())
    assert rep.actions and rep.actions[0]["tool"] == "add_reminder" and rep.actions[0]["result"]["ok"], rep


def test_web_search_parsing():
    def handler(req):
        if "duckduckgo" in str(req.url):
            return httpx.Response(200, json={"AbstractText": "Dakar is the capital of Senegal.",
                                             "AbstractSource": "Wikipedia", "AbstractURL": "https://x"})
        return httpx.Response(200, json={"query": {"search": [{"title": "Dakar", "snippet": "<b>Dakar</b> city"}]}})
    async def go():
        r = ToolRunner(store(), FakeDevice(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        return await r.execute("web_search", {"query": "Dakar"})
    res = run(go())
    assert res["ok"] and res["results"][1]["text"] == "Dakar city"


def test_ics_and_platform_helpers():
    from ginkassistant.services.actions.device import _ics, _android_days, _dur
    ics = _ics("Dentist, checkup", datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 10), "Pikine", "")
    assert "SUMMARY:Dentist\\, checkup" in ics and "DTSTART:20261012T090000" in ics
    assert _android_days(["mon", "Friday", "mon"]) == [2, 6]
    assert _dur(3725) == "1h 2m 5s"
    nxt = DeviceActions.next_occurrence(6, 30, NOW)
    assert nxt == datetime(2026, 10, 10, 6, 30)
