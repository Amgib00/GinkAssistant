"""Help improve Gink (Settings > Privacy): Genie sessions become training data only for adults who
switched it on; keys and private files are removed; they can stop and delete; only the owner exports."""
import json
import os
import sys
import time
sys.path.insert(0, os.path.dirname(__file__))
from test_genie import SCRIPT, call, build      # the simulated AI (genie_srv: conftest.py)

Y = time.gmtime().tm_year


def stored(b):
    return b._training_db(lambda con: [json.loads(r) for (r,) in con.execute("SELECT record FROM genie_training").fetchall()])


def test_off_by_default_and_adults_only(genie_srv):
    b, c, h = genie_srv
    t = c.get("/account/training", headers=h).json()
    assert t["genie"] is False and t["can"] is False and "birth year" in t["why"]
    assert c.put("/account/training", headers=h, json={"genie": True}).status_code == 403
    b._upsert_user("ib@example.com", "Ib", None, "password")
    b._set_birth_year("ib@example.com", Y - 16)
    r = c.put("/account/training", headers=h, json={"genie": True})
    assert r.status_code == 403 and "adults" in r.json()["detail"]                # never teens
    build(c, h)
    assert stored(b) == []


def test_shared_sessions_are_scrubbed(genie_srv):
    b, c, h = genie_srv
    b._set_birth_year("ib@example.com", Y - 30)
    assert c.put("/account/training", headers=h, json={"genie": True}).json()["genie"] is True
    key = "gsk_" + "A" * 40
    SCRIPT[:] = [{"content": "", "tool_calls": [
        call("write_file", path="index.html", content="<h1>Hi</h1>"),
        call("write_file", path=".env", content=f"GROQ_API_KEY={key}"),
        call("write_file", path="app.js", content=f"const k = '{key}';")]},
        {"content": "Built it."}]
    r = c.post("/genie/projects", headers=h, json={"prompt": f"Build a page, my key is {key}"})
    assert r.status_code == 200
    rec = stored(b)
    assert len(rec) == 1
    text = json.dumps(rec[0])
    assert key not in text and "[REMOVED]" in text                                 # in the request and in code
    assert "[not shared: a private file]" in text and "GROQ_API_KEY=" not in text  # .env left out
    assert "<h1>Hi</h1>" in text and rec[0]["messages"][-1] == {"role": "assistant", "content": "Built it."}
    assert c.get("/account/training", headers=h).json()["shared"] == 1


def test_stop_keeps_delete_removes(genie_srv):
    b, c, h = genie_srv
    b._set_birth_year("ib@example.com", Y - 30)
    c.put("/account/training", headers=h, json={"genie": True})
    build(c, h)
    c.put("/account/training", headers=h, json={"genie": False})
    assert len(stored(b)) == 1
    build(c, h, "Build another")
    assert len(stored(b)) == 1                                                     # stopped: nothing new
    c.put("/account/training", headers=h, json={"genie": False, "delete": True})
    assert stored(b) == []


def test_limits(genie_srv, monkeypatch):
    b, c, h = genie_srv
    b._set_birth_year("ib@example.com", Y - 30)
    c.put("/account/training", headers=h, json={"genie": True})
    monkeypatch.setattr(b, "TRAINING_PERSON_MAX", 10)
    build(c, h)
    assert stored(b) == []


def test_owner_export_and_account_deletion(genie_srv, monkeypatch):
    b, c, h = genie_srv
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 32)
    b._admin_failures.clear()
    b._set_birth_year("ib@example.com", Y - 30)
    c.put("/account/training", headers=h, json={"genie": True})
    build(c, h)
    assert c.get("/admin/training/genie.jsonl").status_code == 403
    r = c.get("/admin/training/genie.jsonl", headers={"x-admin-key": "k" * 32})
    lines = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert len(lines) == 1 and set(lines[0]) == {"messages", "tools"} and lines[0]["tools"] == b.GENIE_TOOLS
    assert "ib@example.com" not in r.text                                          # no account in the data
    b._upsert_user("ib@example.com", "Ib", None, "password")
    assert c.post("/account/delete", headers=h, json={"confirm": "DELETE"}).status_code == 200
    assert stored(b) == []


def test_settings_pieces():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    bridge = open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()
    ctl = open(os.path.join(root, "src", "ginkassistant", "ui", "settings_controller.py"), encoding="utf-8").read()
    assert "Help improve Gink" in page and "Adults only" in page
    for a in ("training_on", "training_off", "training_delete"):
        assert f'name === "{a}"' in bridge and f"_a_{a}" in ctl
