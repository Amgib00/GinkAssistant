"""Managed agents in the Gink API: one call runs Gink's agent in a persistent environment (a Genie project);
files stay between interactions; it can continue, run in the background, be cancelled; all under the usual
limits and rules."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import pytest
from test_genie import SCRIPT, SEEN, call      # the simulated AI (genie_srv: conftest.py)


@pytest.fixture
def api(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "test")["key"]
    return b, c, {"Authorization": f"Bearer {key}"}


def test_one_call_runs_the_agent_in_a_new_environment(api):
    b, c, k = api
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="report.md", content="# Solar\nGrowth was strong.")]},
                 {"content": "I wrote report.md with a short summary."}]
    r = c.post("/v1/interactions", headers=k, json={"agent": "gink-agent", "input": "Write a short report on solar growth",
                                                     "environment": "remote"})
    assert r.status_code == 200, r.text
    it = r.json()
    assert it["status"] == "completed" and it["output_text"] == "I wrote report.md with a short summary."
    assert it["files_changed"] == ["report.md"] and it["environment"].startswith("gp_")
    assert SEEN[0]["messages"][0]["content"] == b.AGENT_SYSTEM
    assert "run_command" not in [t["function"]["name"] for t in SEEN[0]["tools"]]          # no code runs on the server
    env = c.get(f"/v1/environments/{it['environment']}", headers=k).json()
    assert [f["path"] for f in env["files"]] == ["report.md"]
    assert c.get(f"/v1/environments/{it['environment']}/files/report.md", headers=k).text.startswith("# Solar")


def test_environments_persist_and_interactions_continue(api):
    b, c, k = api
    env = c.post("/v1/environments", headers=k, json={"name": "notes"}).json()["id"]
    assert c.put(f"/v1/environments/{env}/files/data.csv", headers=k, content=b"country,share\nSenegal,12\n").status_code == 200
    SCRIPT[:] = [{"content": "", "tool_calls": [call("read_file", path="data.csv")]}, {"content": "Senegal: 12%."}]
    first = c.post("/v1/interactions", headers=k, json={"input": "What share does Senegal have?", "environment": env}).json()
    assert first["output_text"] == "Senegal: 12%." and first["environment"] == env
    assert "Senegal,12" in json.dumps(SEEN[1]["messages"])                                 # it read the uploaded file
    SCRIPT[:] = [{"content": "And it was 9% before."}]
    second = c.post("/v1/interactions", headers=k, json={"input": "And before?", "previous_interaction_id": first["id"]}).json()
    assert second["environment"] == env and second["previous_interaction_id"] == first["id"]
    sent = json.dumps(SEEN[-1]["messages"])
    assert "What share does Senegal have?" in sent and "Senegal: 12%." in sent              # remembers the conversation
    assert c.get(f"/v1/interactions/{first['id']}", headers=k).json()["status"] == "completed"


def test_web_search_tool(api, monkeypatch):
    b, c, k = api
    async def search(email, query): return {"answer": "Solar grew 30% in 2025.", "sources": [{"title": "IEA", "url": "https://iea.org/x"}]}
    monkeypatch.setattr(b, "_search_core", search)
    SCRIPT[:] = [{"content": "", "tool_calls": [call("web_search", query="solar growth 2025")]}, {"content": "It grew 30%."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "How fast did solar grow?"}).json()
    assert it["steps"][0]["tool"] == "web_search" and "30%" in it["steps"][0]["result"]
    SCRIPT[:] = [{"content": "Done"}]
    c.post("/v1/interactions", headers=k, json={"input": "x", "tools": ["files"]})
    assert [t["function"]["name"] for t in SEEN[-1]["tools"]].count("web_search") == 0       # tools can be chosen


def test_steps_are_capped_and_continuable(api):
    b, c, k = api
    SCRIPT[:] = [{"content": "", "tool_calls": [call("list_files")]}] * 5
    it = c.post("/v1/interactions", headers=k, json={"input": "Look around", "max_steps": 2}).json()
    assert it["status"] == "incomplete" and "previous_interaction_id" in it["error"]["message"] and len(it["steps"]) == 2


def test_errors_and_rules(api, monkeypatch):
    b, c, k = api
    assert c.post("/v1/interactions", json={"input": "x"}).status_code == 401                # an API key is needed
    assert c.post("/v1/interactions", headers=k, json={"input": ""}).status_code == 400
    assert c.post("/v1/interactions", headers=k, json={"input": "x", "agent": "other"}).status_code == 400
    assert c.post("/v1/interactions", headers=k, json={"input": "x", "environment": "gp_nope"}).status_code == 404
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 11)
    r = c.post("/v1/interactions", headers=k, json={"input": "x"})
    assert r.status_code == 403 and b.UNDER_13_MSG in r.text                                # the usual rules apply


def test_background_and_restart(api):
    b, c, k = api
    SCRIPT[:] = [{"content": "Background done."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "Take your time", "background": True}).json()
    assert it["status"] in ("running", "completed")
    for _ in range(50):
        it = c.get(f"/v1/interactions/{it['id']}", headers=k).json()
        if it["status"] != "running":
            break
        time.sleep(0.05)
    assert it["status"] == "completed" and it["output_text"] == "Background done."
    b._agent_db(lambda con: con.execute("UPDATE agent_interactions SET status='running' WHERE id=?", (it["id"],)))
    b._agents_after_restart()
    assert c.get(f"/v1/interactions/{it['id']}", headers=k).json()["status"] == "failed"


def test_environments_list_and_delete(api):
    b, c, k = api
    e = c.post("/v1/environments", headers=k, json={"name": "tmp"}).json()["id"]
    assert e in [x["id"] for x in c.get("/v1/environments", headers=k).json()["data"]]
    assert c.delete(f"/v1/environments/{e}", headers=k).json()["deleted"] is True
    assert c.get(f"/v1/environments/{e}", headers=k).status_code == 404


def test_the_guide_page(api):
    b, c, k = api
    r = c.get("/developers/agents")
    assert r.status_code == 200 and "Managed agents" in r.text and "/v1/interactions" in r.text
    assert "previous_interaction_id" in r.text and "doesn&rsquo;t run code" in r.text


def test_cli_agent_shows_steps_and_the_answer(monkeypatch, capsys):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
    from gink_cli import main as m
    polls = [{"id": "int_1", "status": "running", "steps": [{"tool": "web_search", "query": "solar"}], "environment": "gp_1"},
             {"id": "int_1", "status": "completed", "steps": [{"tool": "web_search", "query": "solar"},
              {"tool": "write_file", "path": "report.md", "changed": True}], "output_text": "Done: report.md",
              "files_changed": ["report.md"], "environment": "gp_1"}]
    sent = {}

    class R:
        def __init__(self, j): self.status_code, self._j = 200, j
        def json(self): return self._j

    class C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json): sent.update(url=url, body=json); return R({"id": "int_1", "status": "running", "steps": []})
        def get(self, url): return R(polls.pop(0))
    monkeypatch.setattr(m, "_client", lambda key, t: C())
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    monkeypatch.setattr(m, "settings", lambda: ("gink_test", "https://x/v1"))
    assert m.main(["agent", "Write a solar report"]) == 0
    out = capsys.readouterr()
    assert sent["url"] == "https://x/v1/interactions" and sent["body"]["environment"] == "remote" and sent["body"]["background"]
    assert "Done: report.md" in out.out and "web_search solar" in out.err and "write_file report.md" in out.err
    assert "gink agent --continue int_1" in out.err


def test_live_information_for_agents(api, monkeypatch):
    b, c, k = api
    async def facts(text): return ["Weather in Dakar now: 29°C, sunny."] if "weather" in text.lower() else []
    monkeypatch.setattr(b, "_live_facts", facts)
    SCRIPT[:] = [{"content": "It's 29°C and sunny in Dakar."}]
    c.post("/v1/interactions", headers=k, json={"input": "What's the weather in Dakar right now?"})
    system = " ".join(m["content"] for m in SEEN[-1]["messages"] if m["role"] == "system")
    assert "Current date and time:" in system and "29°C, sunny" in system and "Live data fetched just now" in system


def test_streaming_steps_live(api, monkeypatch):
    b, c, k = api
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="a.txt", content="hi")]}, {"content": "Wrote a.txt."}]
    with c.stream("POST", "/v1/interactions", headers=k, json={"input": "Write a.txt", "stream": True}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = [l[7:] for l in text.splitlines() if l.startswith("event: ")]
    assert events[0] in ("status", "step") and "step" in events and events[-1] == "done"
    done = json.loads([l for l in text.splitlines() if l.startswith("data: ")][-1][6:])
    assert done["status"] == "completed" and done["files_changed"] == ["a.txt"]


def test_agent_work_shows_in_genie(api, genie_srv):
    b, c, k = api
    _b, _c, session = genie_srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="notes.md", content="# Notes")]}, {"content": "Saved notes.md."}]
    env = c.post("/v1/interactions", headers=k, json={"input": "Start my notes"}).json()["environment"]
    chat = c.get(f"/genie/projects/{env}/chat", headers=session).json()
    text = json.dumps(chat)
    assert "[API agent] Start my notes" in text and "Saved notes.md." in text and "Wrote notes.md" in text


def test_genie_searches_the_web_and_knows_the_date(genie_srv, monkeypatch):
    b, c, h = genie_srv
    async def search(email, query): return {"answer": "Python 3.14 is the latest.", "sources": [{"title": "python.org", "url": "https://python.org"}]}
    monkeypatch.setattr(b, "_search_core", search)
    SCRIPT[:] = [{"content": "", "tool_calls": [call("web_search", query="latest python version")]},
                 {"content": "", "tool_calls": [call("write_file", path="README.md", content="Needs Python 3.14")]},
                 {"content": "Done."}]
    r = c.post("/genie/projects", headers=h, json={"prompt": "Write a README with the latest Python version"}).json()
    assert "Current date and time:" in SEEN[0]["messages"][0]["content"]
    assert "web_search" in [t["function"]["name"] for t in SEEN[0]["tools"]]
    steps = r["result"]["steps"]
    assert steps[0]["kind"] == "search" and "latest python version" in steps[0]["title"]
    assert "Python 3.14 is the latest" in json.dumps(SEEN[1]["messages"])                # the result went back to the AI


def test_cli_env_commands(monkeypatch, tmp_path, capsys):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
    from gink_cli import main as m
    calls = []

    class R:
        def __init__(self, j=None, content=b""): self.status_code, self._j, self.content = 200, j, content
        def json(self): return self._j

    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw.get("content")))
        if path == "/environments" and method == "GET":
            return R({"data": [{"id": "gp_1", "name": "notes", "files": [{"path": "a.md", "size": 3}]}]})
        if path == "/environments" and method == "POST":
            return R({"id": "gp_2"})
        if path == "/environments/gp_1" and method == "GET":
            return R({"files": [{"path": "a.md", "size": 3}, {"path": "../../escape.txt", "size": 1}]})
        if path.startswith("/environments/gp_1/files/"):
            return R(content=b"hey")
        return R({})
    monkeypatch.setattr(m, "_env_call", fake)
    monkeypatch.setattr(m, "settings", lambda: ("gink_test", "https://x/v1"))
    assert m.main(["env", "list"]) == 0 and "gp_1  notes  (1 files)" in capsys.readouterr().out
    assert m.main(["env", "new", "My", "notes"]) == 0 and capsys.readouterr().out.strip() == "gp_2"
    out_dir = tmp_path / "pulled"
    assert m.main(["env", "pull", "gp_1", str(out_dir)]) == 0
    assert (out_dir / "a.md").read_bytes() == b"hey" and not (tmp_path / "escape.txt").exists()   # stays in the folder
    src = tmp_path / "src"; (src / "sub").mkdir(parents=True); (src / "sub" / "x.py").write_text("print(1)")
    (src / ".git").mkdir(); (src / ".git" / "HEAD").write_text("ref")
    assert m.main(["env", "push", "gp_1", str(src)]) == 0
    assert ("PUT", "/environments/gp_1/files/sub/x.py", b"print(1)") in calls
    assert not any(".git" in c[1] for c in calls)


def test_console_endpoints(api, genie_srv):
    b, c, k = api
    _b, _c, session = genie_srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="x.md", content="x")]}, {"content": "Done from the console."}]
    it = c.post("/dev/interactions", headers=session, json={"input": "Write x.md", "environment": "remote"}).json()
    assert it["status"] == "completed" and it["output_text"] == "Done from the console."
    runs = c.get("/dev/interactions", headers=session).json()["data"]
    assert runs[0]["id"] == it["id"] and runs[0]["via"] == "console" and runs[0]["input"] == "Write x.md"
    assert c.get(f"/dev/interactions/{it['id']}", headers=session).json()["input"] == "Write x.md"
    envs = c.get("/dev/environments", headers=session).json()["data"]
    assert any(e["id"] == it["environment"] for e in envs)
    assert c.get("/dev/interactions").status_code == 401                                   # signed in only


def test_console_page_and_genie_links():
    root = os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "web_app")
    console = open(os.path.join(root, "console.html"), encoding="utf-8").read()
    genie = open(os.path.join(root, "genie.html"), encoding="utf-8").read()
    assert 'data-v="agents"' in console and 'data-view="agents"' in console and "agents: function () { return Promise.all([loadAgents(), loadSchedules()]); }" in console
    assert "stream: true" in console and '"/genie#" + it.environment' in console
    assert "/^#(gp_[a-f0-9]+)$/.exec(location.hash)" in genie                       # /genie#gp_... opens that project


def test_at_most_a_few_runs_at_once(api, monkeypatch):
    """One account (or a buggy script) can't start hundreds of agent runs: GINK_AGENT_CONCURRENT (default 3)."""
    b, c, k = api
    monkeypatch.setattr(b, "AGENT_CONCURRENT_MAX", 2)
    for i in range(2):
        b._agent_db(lambda con: con.execute("INSERT INTO agent_interactions (id, email, status, created) VALUES (?, ?, 'running', ?)",
                                            (f"int_busy{i}", "ib@example.com", time.time())))
    r = c.post("/v1/interactions", headers=k, json={"input": "one more"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_running"
    s = c.post("/v1/schedules", headers=k, json={"input": "brief"}).json()
    before = time.time()
    out = c.post(f"/v1/schedules/{s['id']}/run", headers=k).json()
    assert out["interaction_id"] is None
    nxt = c.get("/v1/schedules", headers=k).json()["data"][0]["next_run"]
    assert before + 250 < nxt < before + 400                                       # busy: tried again in ~5 minutes
    b._agent_db(lambda con: con.execute("UPDATE agent_interactions SET status='completed' WHERE id LIKE 'int_busy%'"))
    SCRIPT[:] = [{"content": "ok"}]
    assert c.post("/v1/interactions", headers=k, json={"input": "now it fits"}).json()["status"] == "completed"
