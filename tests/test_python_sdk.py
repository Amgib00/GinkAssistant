"""The Gink Python SDK (cli/gink, shipped in gink-ai): managed agents, live events, environments, chat --
against the real server (with the simulated AI)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest
from test_genie import SCRIPT, call      # the simulated AI (genie_srv: conftest.py)
from gink import Client, GinkAPIError


@pytest.fixture
def client(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "sdk")["key"]
    return b, Client(api_key=key, base_url="http://testserver/v1", http=c)


def test_agent_in_one_call(client):
    b, gink = client
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="report.md", content="# Report")]}, {"content": "Wrote report.md."}]
    it = gink.interactions.create(input="Write a report", environment="remote")
    assert it.status == "completed" and it.output_text == "Wrote report.md." and it.files_changed == ["report.md"]
    env = gink.environments.get(it.environment)
    assert [f["path"] for f in env.files] == ["report.md"] and env.download("report.md") == b"# Report"
    SCRIPT[:] = [{"content": "Still here."}]
    again = gink.interactions.create(input="Anything else?", previous_interaction_id=it.id)
    assert again.environment == it.environment and again.previous_interaction_id == it.id


def test_live_events(client):
    b, gink = client
    SCRIPT[:] = [{"content": "", "tool_calls": [call("list_files")]}, {"content": "Nothing yet."}]
    events = list(gink.interactions.create(input="Look around", stream=True))
    kinds = [e.type for e in events]
    assert "step" in kinds and kinds[-1] == "done" and events[-1].data.output_text == "Nothing yet."
    assert [e.data.tool for e in events if e.type == "step"] == ["list_files"]


def test_environments(client):
    b, gink = client
    env = gink.environments.create(name="data")
    env.upload("data.csv", "country,share\nSenegal,12\n")
    assert env.download("data.csv").startswith(b"country") and any(e.id == env.id for e in gink.environments.list())
    env.delete()
    with pytest.raises(GinkAPIError) as e:
        gink.environments.get(env.id)
    assert e.value.status == 404


def test_errors_are_clear(client, monkeypatch):
    b, gink = client
    bad = Client(api_key="gink_wrong", base_url="http://testserver/v1", http=gink._http)
    with pytest.raises(GinkAPIError) as e:
        bad.interactions.create(input="x")
    assert e.value.status == 401 and e.value.code == "invalid_api_key"
    monkeypatch.delenv("GINK_API_KEY", raising=False)
    monkeypatch.setattr("gink.client._saved_key", lambda: "")
    with pytest.raises(GinkAPIError):
        Client()


def test_versions_match():
    import tomllib, gink, gink_cli
    with open(os.path.join(os.path.dirname(__file__), "..", "cli", "pyproject.toml"), "rb") as f:
        proj = tomllib.load(f)["project"]
    assert proj["version"] == gink.__version__ == gink_cli.__version__


def test_chat_with_live_information(client, monkeypatch):
    b, gink = client
    from test_genie import SEEN
    SCRIPT[:] = [{"content": "It's 29°C in Dakar."}]
    assert gink.chat("What's the weather in Dakar right now?") == "It's 29°C in Dakar."
    system = " ".join(m["content"] for m in SEEN[-1]["messages"] if m["role"] == "system")
    assert "Current date and time:" in system                                  # Gink adds live information
