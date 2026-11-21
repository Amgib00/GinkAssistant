"""The stronger, automatic agent (0.1.159): it plans first (shown live), works through up to 30 rounds (managed agents:
up to 60 steps), is told to carry on when it stops with steps of its plan open, and has apps, editors and text files as
tools (find, open, close apps; open a project in an IDE; read, write and edit files with a backup first). Long agent
turns count one message per 10 calls."""
import asyncio, json, os, shutil, sys, types
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from ginkassistant.services.actions import agent as ag
from test_genie import SCRIPT, SEEN, call as gcall          # the simulated AI (genie_srv: conftest.py)


def call(i, name, **args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def make(script):
    executed, seen = [], []

    async def execute(name, args):
        executed.append((name, args))
        return {"ok": True, "message": f"{name} done"}
    runner = types.SimpleNamespace(execute=execute, memory=None, live=types.SimpleNamespace(city_fn=lambda: ""),
                                   use_memory=False, reply_language_note=lambda: "", profile_note=lambda: "")
    a = ag.TaskAgent(runner, api_key="test")

    async def chat(messages, use_tools=True):
        seen.append([dict(m) for m in messages])
        return script.pop(0) if script else {"content": "All done."}
    a._chat = chat
    return a, executed, seen


def test_plans_first_shows_it_and_finishes_by_itself():
    plan = [{"title": "Open the project in VS Code", "status": "doing"}, {"title": "Fix the title", "status": "todo"}]
    script = [{"content": "", "tool_calls": [call(1, "update_plan", steps=plan), call(2, "open_in_editor", path="site", editor="vs code")]},
              {"content": "I opened it."},                                          # stops with a step still open...
              {"content": "", "tool_calls": [call(3, "edit_text_file", which="site/index.html", find="Old", replace="New"),
                                             call(4, "update_plan", steps=[dict(p, status="done") for p in plan])]},
              {"content": "Opened the project and fixed the title."}]
    a, executed, seen = make(script)
    plans, steps = [], []

    async def on_plan(p): plans.append(p)

    async def on_step(i, label, state): steps.append((label, state))
    r = asyncio.run(a.run("Open my site project and fix its title", on_plan=on_plan, on_step=on_step,
                          confirm=lambda *x: asyncio.sleep(0, True)))
    assert [n for n, _ in executed] == ["open_in_editor", "edit_text_file"]          # the plan isn't a device action
    assert plans[0][0] == {"title": "Open the project in VS Code", "status": "doing"} and plans[-1][1]["status"] == "done"
    nudge = seen[2][-1]
    assert nudge["role"] == "user" and "Keep going" in nudge["content"] and "Fix the title" in nudge["content"]
    assert r.text == "Opened the project and fixed the title."
    assert ("Open site in vs code", "done") in steps and ("Change index.html", "done") in steps
    assert ag.MAX_ROUNDS == 30 and "quit_app" not in ag.ASK_IN_CHAIN and "lock_screen" in ag.ASK_IN_CHAIN


def test_the_nudge_happens_at_most_twice():
    script = [{"content": "", "tool_calls": [call(1, "update_plan", steps=["A", "B"])]}, {"content": "1"}, {"content": "2"},
              {"content": "I couldn't do B: it needs your password."}]
    a, executed, seen = make(script)
    r = asyncio.run(a.run("Do A and B"))
    assert r.text == "I couldn't do B: it needs your password." and len(seen) == 4


def test_agent_turns_send_the_agent_header():
    import httpx
    sent = []

    def handler(request):
        sent.append(dict(request.headers))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    runner = types.SimpleNamespace(execute=None, memory=None, live=types.SimpleNamespace(city_fn=lambda: ""),
                                   use_memory=False, reply_language_note=lambda: "", profile_note=lambda: "",
                                   disabled_tools=set())
    a = ag.TaskAgent(runner, api_key="k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    asyncio.run(a.run("Plan my week and save it as tasks"))
    assert sent[0]["x-gink-agent"] == "1" and sent[0]["x-gink-turn"]
    tools = json.loads(json.dumps(ag.PLAN_SPEC))
    assert tools["function"]["name"] == "update_plan"


def test_computer_tools_for_apps_editors_and_files(tmp_path, monkeypatch):
    from ginkassistant.services.actions import computer as c, tools
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path), 1) if p.startswith("~") else p)
    pc = c.ComputerControl(files_dir=str(tmp_path / "gink-files"))
    made = pc.write_text_file("~/Projects/site/index.html", "<h1>Old</h1>\n")
    assert made["ok"] and os.path.isfile(tmp_path / "Projects" / "site" / "index.html")
    assert not pc.write_text_file("~/Projects/site/index.html", "x")["ok"]                 # never overwritten silently
    edit = pc.edit_text_file("~/Projects/site/index.html", "Old", "New")
    assert edit["ok"] and open(edit["backup"]).read() == "<h1>Old</h1>\n"                # the old version is kept
    assert "<h1>New</h1>" in pc.read_text_file("~/Projects/site/index.html")["message"]
    assert not pc.edit_text_file("~/Projects/site/index.html", "Missing", "x")["ok"]
    assert "home folder" in pc.write_text_file("/etc/gink-test", "x")["message"]
    assert "hidden or system" in pc.write_text_file("~/.ssh/config", "x")["message"]
    names = {t["function"]["name"] for t in tools.TOOL_SPECS}
    assert {"find_app", "running_apps", "open_in_editor", "read_text_file", "write_text_file", "edit_text_file"} <= names
    for n in names:                                                                  # every tool can run
        assert hasattr(tools.ToolRunner, "_t_" + n), n
    assert "vs code" in c.EDITOR_ALIASES and "visual studio code" in c.EDITORS


# ---------------------------------------------------------------- managed agents (API, console, CLI, SDKs)
@pytest.fixture
def api(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "test")["key"]
    return b, c, {"Authorization": f"Bearer {key}"}


def test_managed_agent_plans_carries_on_and_reads_pages(api, monkeypatch):
    b, c, k = api
    asked = []

    async def search(email, query):
        asked.append(query)
        return {"answer": "The page lists 3 prices.", "sources": []}
    monkeypatch.setattr(b, "_search_core", search)
    SCRIPT[:] = [{"content": "", "tool_calls": [gcall("update_plan", steps=[{"title": "Read the page"}, {"title": "Write prices.md"}])]},
                 {"content": "", "tool_calls": [gcall("read_page", url="https://example.org/prices")]},
                 {"content": "I read it."},                                          # stops early: told to carry on
                 {"content": "", "tool_calls": [gcall("write_file", path="prices.md", content="3 prices"),
                                                gcall("update_plan", steps=[{"title": "Read the page", "status": "done"},
                                                                            {"title": "Write prices.md", "status": "done"}])]},
                 {"content": "Wrote prices.md from the page."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "Put the prices from example.org/prices in prices.md"}).json()
    assert it["status"] == "completed" and it["output_text"] == "Wrote prices.md from the page."
    assert it["plan"] == [{"title": "Read the page", "status": "done"}, {"title": "Write prices.md", "status": "done"}]
    assert [s["tool"] for s in it["steps"]] == ["plan", "read_page", "write_file", "plan"]
    assert "https://example.org/prices" in asked[0] and it["files_changed"] == ["prices.md"]
    names = [t["function"]["name"] for t in SEEN[0]["tools"]]
    assert names[0] == "update_plan" and "read_page" in names and "run_command" not in names
    assert "Keep going" in SEEN[3]["messages"][-1]["content"]
    assert b.AGENT_DEFAULT_STEPS == 30 and b.AGENT_MAX_STEPS == 60
    bad = c.post("/v1/interactions", headers=k, json={"input": "x", "max_steps": "lots"}).json()
    assert "1 to 60" in bad["error"]["message"]
    SCRIPT[:] = [{"content": "", "tool_calls": [gcall("read_page", url="file:///etc/passwd")]}, {"content": "Can't."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "read it"}).json()
    assert "full http" in it["steps"][0]["result"] and len(asked) == 1               # never a local file


def test_long_agent_turns_count_one_message_per_ten_calls(api):
    b, c, k = api
    day = b._today()

    def used():
        with b._db_lock:
            con = b._usage_db()
            try:
                row = con.execute("SELECT messages, calls FROM ai_usage WHERE email=? AND day=?", ("ib@example.com", day)).fetchone()
            finally:
                con.close()
        return tuple(row) if row else (0, 0)
    before = used()
    for _ in range(25):
        assert b._count_call("ib@example.com", "turn-agent", "pro", cap=40) is None
    assert used()[0] - before[0] == 3                                                # 25 calls = 3 messages
    for _ in range(10):
        assert b._count_call("ib@example.com", "turn-chat", "pro") is None
    blocked = b._count_call("ib@example.com", "turn-chat", "pro")
    assert blocked is not None and json.loads(bytes(blocked.body))["error"]["code"] == "turn_limit"
    assert used()[0] - before[0] == 4                                                # an ordinary turn: still one


def test_clients_default_to_thirty_steps():
    root = os.path.join(os.path.dirname(__file__), "..")
    read = lambda *p: open(os.path.join(root, *p), encoding="utf-8").read()
    assert 'add_argument("--max-steps", type=int, default=30' in read("cli", "gink_cli", "main.py")
    assert "max_steps: int = 30" in read("cli", "gink", "client.py")
    assert "params.max_steps ?? 30" in read("sdk", "js", "index.js") and "1-60, default 30" in read("sdk", "js", "index.d.ts")
    assert 'st.tool === "plan"' in read("src", "ginkassistant", "services", "web_app", "console.html")
    assert "window.agentPlan" in read("src", "ginkassistant", "ui", "agent_ui.py")
    assert "on_plan=agent_plan" in read("src", "ginkassistant", "ui", "main_screen.py")
    if shutil.which("node"):
        pass
