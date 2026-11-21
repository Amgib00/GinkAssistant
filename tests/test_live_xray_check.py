"""0.1.150 across the suite: Live camera (ask again and again about what the camera sees), X-ray / exploded /
cutaway looks (illustrations, never scans), and Genie's whole-project Check & fix (page, API, SDKs, CLI)."""
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---- Live camera
def test_live_camera_in_the_page():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert "function openLive(" in html and "ginkEmit('live_ask'" in html and "t.stop()" in html
    assert "cameraFallback()" in html and "window.liveDone" in html and "setTimeout(window.liveDone, 0)" in html
    assert "LIVE.hands && LIVE.listen" in html                       # hands-free: listens again after each answer
    assert "|| (screen ? 'What\u2019s on my screen?' : 'What\u2019s this?')" in html   # nothing typed: a short question


def test_live_camera_apps_and_web_app():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert 'kind == "live_ask"' in main and "load_data_url(value[\"data\"]" in main
    bridge = read("webapp", "bridge.js")
    assert "live_ask: function (v)" in bridge and "window.liveDone" in bridge


# ---- X-ray vision: picked from the words, no cards
def test_xray_looks_are_automatic():
    from ginkassistant.services import image_ideas as ii
    assert not {"xray", "exploded", "cutaway"} & {i[0] for i in ii.IDEAS}             # not among Media Studio's cards
    assert ii.auto_look("an x-ray of my camera")[0] == "xray" and "my camera" in ii.auto_look("an x-ray of my camera")[1]
    assert ii.auto_look("exploded view of a drone")[0] == "exploded"
    assert ii.auto_look("a cutaway of a submarine")[0] == "cutaway"
    assert ii.auto_look("a cat on a sofa") is None
    for body in ("x-ray of my chest", "an x-ray of a hand", "x-ray of me", "a cutaway of a patient's knee"):
        assert ii.auto_look(body) is None, body                                         # never a fake medical image
    assert "not a real medical image" in ii.medical_prompt("x-ray of my chest")
    assert ii.medical_prompt("a cat on a sofa") == "a cat on a sofa"


def test_xray_looks_on_the_server(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    k = {"Authorization": "Bearer " + b._create_api_key("ib@example.com", "s")["key"]}
    cat = c.get("/v1/images/ideas", headers=k).json()
    assert {"xray", "exploded", "cutaway"} == {i["id"] for i in cat["looks"]}            # developers can still name them
    assert not {"xray", "exploded", "cutaway"} & {i["id"] for i in cat["ideas"]}
    src = read("src", "ginkassistant", "services", "backend_server.py")
    assert "ideas.auto_look(prompt)" in src and "ideas.medical_prompt(prompt)" in src


# ---- Whole-project check
@pytest.fixture
def proj(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "Site"}).json()["project"]["id"]
    b._genie_write(pid, "index.html", '<link rel="stylesheet" href="style.css"><script src="app.js"></script>')
    b._genie_write(pid, "app.js", "console.log(1)")
    b._genie_write(pid, "data.json", '{"a": 1,}')
    b._genie_write(pid, "tool.py", "def f(:\n  pass\n")
    b._genie_write(pid, "ok.py", "x = 1\n")
    return b, c, h, pid


def test_genie_check_finds_everything(proj):
    b, c, h, pid = proj
    j = c.get(f"/genie/projects/{pid}/check", headers=h).json()
    assert j["ok"] is False and j["files"] == 5
    assert any(p.startswith("style.css") for p in j["missing"])
    assert any(p.startswith("data.json") for p in j["broken"]) and any(p.startswith("tool.py") for p in j["broken"])
    assert not any("ok.py" in p for p in j["problems"]) and "style.css" in j["fix_request"]
    b._genie_write(pid, "style.css", "body{}")
    b._genie_write(pid, "data.json", '{"a": 1}')
    b._genie_write(pid, "tool.py", "def f():\n  pass\n")
    j = c.get(f"/genie/projects/{pid}/check", headers=h).json()
    assert j["ok"] is True and j["problems"] == [] and j["fix_request"] == ""


def test_genie_checks_by_itself():
    page = read("src", "ginkassistant", "services", "web_app", "genie.html")
    assert "checkall-btn" not in page and "function quietCheck(" in page and "quietCheck(id)" in page
    src = read("src", "ginkassistant", "services", "backend_server.py")
    assert '_genie_project_check(state["pid"])["broken"]' in src                        # every request: the whole project


def test_genie_fixes_problems_anywhere_by_itself(genie_srv):
    """A request that only touches one file still gets the whole project fixed before Genie answers."""
    from test_genie import SCRIPT, call
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "Site"}).json()["project"]["id"]
    b._genie_write(pid, "index.html", "<h1>Hi</h1>")
    b._genie_write(pid, "old.json", '{"a": 1,}')                                       # broken before the request
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html", content="<h1>Hello</h1>")]},
                 {"content": "Done."},
                 {"content": "", "tool_calls": [call("write_file", path="old.json", content='{"a": 1}')]},
                 {"content": "Fixed old.json too."}]
    j = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "Say hello"}).json()
    assert any(s.get("kind") == "check" and "old.json" in s.get("output", "") for s in j["steps"])
    assert c.get(f"/genie/projects/{pid}/check", headers=h).json()["ok"] is True


def test_api_sdk_cli_check(proj, monkeypatch, capsys):
    b, c, h, pid = proj
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    k = {"Authorization": "Bearer " + b._create_api_key("ib@example.com", "s")["key"]}
    j = c.get(f"/v1/environments/{pid}/check", headers=k).json()
    assert j["object"] == "check" and len(j["problems"]) == 3
    assert c.get("/v1/environments/nope/check", headers=k).status_code == 404
    from gink import Client
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    r = gink.environments.get(pid).check()
    assert r.ok is False and len(r.problems) == 3 and r.fix_request
    from gink_cli import main as cli

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    monkeypatch.setattr(cli, "_env_call", lambda key, base, method, path, **kw: R(j))
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["env", "check", pid]) == 1
    out = capsys.readouterr().out
    assert "3 problems" in out and f"gink env check {pid} --fix" in out


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_check(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url]);
  return new Response(JSON.stringify({ id: "gp_1", files: [], ok: true, problems: [] }), { status: 200 }); } });
const env = await gink.environments.get("gp_1");
const r = await env.check();
console.log(JSON.stringify([seen, r.ok]));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    seen, ok = json.loads(r.stdout)
    assert seen[1] == ["GET", "https://x/v1/environments/gp_1/check"] and ok is True
    assert "check(): Promise<" in read("sdk", "js", "index.d.ts")
