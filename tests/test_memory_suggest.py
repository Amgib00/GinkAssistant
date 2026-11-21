"""Automatic memory across the suite: lasting facts are remembered by themselves (with Undo), never health, never in a
healthcare workspace; a single fact said again replaces the old one; the same memories for the web app (signed in),
the API, both SDKs and the CLI."""
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_rules_offer_lasting_facts_only():
    from ginkassistant.services import memory_rules as r
    assert r.suggest("Hi! I live in Nairobi. What's the weather?") == "I live in Nairobi"
    assert r.suggest("By the way, my sister is called Awa") == "My sister is called Awa"
    assert r.suggest("I'm a nurse") == "I'm a nurse" and r.suggest("I'm vegan") == "I'm vegan"
    for health in ("I'm allergic to peanuts", "I'm diabetic", "My sister has cancer", "I take insulin every day",
                   "My blood type is O+", "I'm pregnant"):
        assert r.suggest(health) is None, health                                         # never health, about anyone
    for no in ("Where do I live?", "I think I live too far", "If I live in Lagos what changes?", "Write a poem", "thanks"):
        assert r.suggest(no) is None, no
    assert r.suggest("I live in Nairobi", known=["I live in Nairobi"]) is None          # already known
    assert r.subject("I live in Lima") == r.subject("I live in Oslo")                   # one city at a time


@pytest.fixture
def srv(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "s")["key"]
    return b, c, h, {"Authorization": f"Bearer {key}"}


def test_web_app_remembers_by_itself_with_undo(srv):
    b, c, h, k = srv
    j = c.post("/memory/auto", headers=h, json={"text": "I live in Lima. Any tips?"}).json()
    assert j["saved"]["text"] == "I live in Lima" and j["saved"]["replaced"] is None
    m2 = c.post("/memory/auto", headers=h, json={"text": "I live in Oslo"}).json()["saved"]
    assert m2["replaced"] == "I live in Lima"
    assert [x["text"] for x in c.get("/v1/memories", headers=k).json()["data"]] == ["I live in Oslo"]
    # Undo = the old fact takes its place back
    back = c.post("/memory/remember", headers=h, json={"text": m2["replaced"]}).json()
    assert back["replaced"] == "I live in Oslo"
    new = c.post("/memory/auto", headers=h, json={"text": "I'm a teacher"}).json()["saved"]
    assert c.post("/memory/forget", headers=h, json={"id": new["id"]}).json()["deleted"] is True
    assert [x["text"] for x in c.get("/v1/memories", headers=k).json()["data"]] == ["I live in Lima"]
    assert c.post("/memory/auto", headers=h, json={"text": "I'm allergic to penicillin"}).json()["saved"] is None
    assert c.post("/memory/auto", json={"text": "x"}).status_code == 401


def test_never_in_a_healthcare_workspace(srv):
    b, c, h, k = srv
    import time
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 35)               # adults create workspaces
    assert c.post("/org", headers=h, json={"name": "City Hospital", "healthcare": True}).status_code == 200
    assert b._org_rules("ib@example.com")["healthcare"] is True
    assert c.post("/memory/auto", headers=h, json={"text": "I live in Lima"}).json()["saved"] is None
    assert c.post("/v1/memories/suggest", headers=k, json={"text": "I live in Lima"}).json()["fact"] is None
    assert c.get("/v1/memories", headers=k).json()["data"] == []


def test_api_add_list_forget(srv):
    b, c, h, k = srv
    m = c.post("/v1/memories", headers=k, json={"text": "I prefer short answers"}).json()
    assert m["object"] == "memory" and m["id"]
    assert c.post("/v1/memories", headers=k, json={"text": " "}).json()["error"]["code"] == "invalid_memory"
    assert c.post("/v1/memories/suggest", headers=k, json={"text": "My name is Ibrahim"}).json()["fact"]
    assert c.delete(f"/v1/memories/{m['id']}", headers=k).json()["deleted"] is True
    assert c.delete(f"/v1/memories/{m['id']}", headers=k).status_code == 404
    assert c.get("/v1/memories", headers=k).json()["data"] == []


def test_python_sdk_and_cli(srv, monkeypatch, capsys):
    b, c, h, k = srv
    from gink import Client
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    m = gink.memories.add("I work as a nurse")
    assert [x.text for x in gink.memories.list()] == ["I work as a nurse"]
    gink.memories.forget(m.id)
    assert gink.memories.list() == [] and gink.memories.suggest("I live in Accra") == "I live in Accra"
    from gink_cli import main as cli
    calls = []

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw.get("json")))
        return R({"id": "m1", "text": "I live in Accra", "replaced": "I live in Lima"} if method == "POST" else {"data": []})
    monkeypatch.setattr(cli, "_env_call", fake)
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["remember", "I", "live", "in", "Accra"]) == 0 and "Updated" in capsys.readouterr().out
    assert calls[-1] == ("POST", "/memories", {"text": "I live in Accra"})
    assert cli.main(["memories"]) == 0 and "Nothing yet" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_memories(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url, init.body ? JSON.parse(init.body) : null]);
  return new Response(JSON.stringify({ id: "m1", data: [], fact: "I live in Accra" }), { status: 200 }); } });
await gink.memories.add("I live in Accra");
const f = await gink.memories.suggest("I live in Accra");
await gink.memories.forget("m1");
console.log(JSON.stringify([seen, f]));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    seen, fact = json.loads(r.stdout)
    assert seen[0] == ["POST", "https://x/v1/memories", {"text": "I live in Accra"}] and fact == "I live in Accra"
    assert seen[2][0] == "DELETE" and seen[2][1].endswith("/memories/m1")
    assert "memories:" in read("sdk", "js", "index.d.ts")


def test_page_apps_and_web_wiring():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert "memorySuggestion" not in html and "Remember this?" not in html                   # no button to press
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "async def auto_remember(" in main and '"memory_undo"' in main and "in_healthcare_workspace()" in main
    assert "is_temporary(current_session" in main
    bridge = read("webapp", "bridge.js")
    assert '"/memory/auto"' in bridge and "memory_undo: function" in bridge and "!s.temporary" in bridge
    assert "memory_rules.py ./memory_rules.py" in read("deploy", "Dockerfile")
    assert "Generate memory from chats" in read("src", "ginkassistant", "ui", "settings_page.py")
