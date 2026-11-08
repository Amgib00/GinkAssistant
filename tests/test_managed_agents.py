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
