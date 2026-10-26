"""Gink Genie: AI-built multi-file projects (the AI is simulated as scripted tool calls)."""
import base64, io, json, os, sys, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

SCRIPT, SEEN = [], []


def call(name, **args):
    return {"id": f"c{len(SEEN)}{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def groq(request):
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
    body = json.loads(request.content); SEEN.append(body)
    step = SCRIPT.pop(0) if SCRIPT else {"content": "Done."}
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", **step}}]})


@pytest.fixture
def srv(tmp_path, monkeypatch):
    SCRIPT.clear(); SEEN.clear()
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "g.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "pro"})
    c = TestClient(b.app)
    yield b, c, {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}
    b._groq_models.update(ids=set(), at=0.0)                    # don't leave our simulated model list behind


def build(c, h, prompt="Build a school app with students and grades"):
    SCRIPT[:] = [
        {"content": "", "tool_calls": [call("write_file", path="index.html", content="<!doctype html><link rel=stylesheet href=styles.css><h1>School</h1><script src=js/app.js></script>"),
                                       call("write_file", path="styles.css", content="h1{color:green}"),
                                       call("write_file", path="js/app.js", content="console.log('grades')")]},
        {"content": "I built a school app: open index.html."}]
    return c.post("/genie/projects", headers=h, json={"prompt": prompt}).json()


def test_build_a_project_from_a_prompt(srv):
    b, c, h = srv
    r = build(c, h)
    assert r["result"]["reply"].startswith("I built a school app") and r["result"]["rounds"] == 2
    assert [f["path"] for f in r["files"]] == ["index.html", "js/app.js", "styles.css"]
    assert [x["action"] for x in r["result"]["changes"]] == ["created"] * 3
    assert SEEN[0]["messages"][0]["content"].startswith("You are Gink Genie") and SEEN[0]["tools"][0]["function"]["name"] == "list_files"
    assert "Request: Build a school app" in SEEN[0]["messages"][1]["content"]
    assert SEEN[1]["messages"][-1]["role"] == "tool" and SEEN[1]["messages"][-1]["content"] == "Saved js/app.js."


def test_change_many_files_and_refuse_unsafe_paths(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    SCRIPT[:] = [
        {"content": "", "tool_calls": [call("search_files", text="GRADES"), call("read_file", path="js/app.js")]},
        {"content": "", "tool_calls": [call("write_file", path="js/app.js", content="console.log('grades v2')"),
                                       call("delete_file", path="styles.css"),
                                       call("write_file", path="../../etc/passwd", content="x"),
                                       call("write_file", path="/etc/hosts", content="x"),
                                       call("write_file", path="a/../b.txt", content="x"),
                                       call("write_file", path="big.txt", content="x" * 300_001)]},
        {"content": "Updated the grades script and removed the old styles."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "update the grades and remove the styles"}).json()
    assert [(x["path"], x["action"]) for x in r["changes"]] == [("js/app.js", "changed"), ("styles.css", "deleted")]
    assert [f["path"] for f in r["files"]] == ["index.html", "js/app.js"]                 # nothing escaped the project
    tool_answers = [m["content"] for m in SEEN[-1]["messages"] if m["role"] == "tool"]
    assert "js/app.js:1: console.log('grades')" in tool_answers[0] and tool_answers[1] == "console.log('grades')"
    assert sum("isn't a valid file path" in t for t in tool_answers) == 3 and any("too large" in t for t in tool_answers)
    assert c.get(f"/genie/projects/{pid}/file", headers=h, params={"path": "js/app.js"}).json()["content"] == "console.log('grades v2')"


def test_manual_edits_privacy_zip_and_import(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    assert c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "README.md", "content": "# School"}).status_code == 200
    assert c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "../x", "content": "no"}).status_code == 422
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.get(f"/genie/projects/{pid}", headers=eve).status_code == 404
    assert c.get("/genie/projects", headers=eve).json()["projects"] == []
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/genie/projects/{pid}/zip", headers=h).content))
    assert sorted(z.namelist()) == ["README.md", "index.html", "js/app.js", "styles.css"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as up:
        up.writestr("shop/app.py", "print('shop')"); up.writestr("shop/node_modules/lib.js", "x")
        up.writestr("shop/logo.png", b"\x89PNG\x00\xff\xfe"); up.writestr("shop/.git/HEAD", "ref")
    new = c.post("/genie/projects", headers=h, json={"name": "Shop"}).json()["project"]["id"]
    r = c.post(f"/genie/projects/{new}/import", headers=h, json={"zip_b64": base64.b64encode(buf.getvalue()).decode()}).json()
    assert r["imported"] == ["app.py"] and r["skipped"][0].startswith("logo.png (logo.png isn't a PNG")   # fake picture refused


def test_sandboxed_preview(srv):
    b, c, h = srv
    proj = build(c, h)["project"]
    page = c.get(proj["preview_url"].replace("http://testserver", ""))
    csp = page.headers["content-security-policy"]
    assert page.status_code == 200 and "<h1>School</h1>" in page.text and page.headers["content-type"].startswith("text/html")
    assert csp.startswith("sandbox ") and "allow-same-origin" not in csp and "form-action 'none'" in csp
    css = c.get(proj["preview_url"].replace("http://testserver", "") + "styles.css")
    assert css.headers["content-type"].startswith("text/css")
    assert c.get("/genie/p/not-a-key/").status_code == 404
    assert c.get(proj["preview_url"].replace("http://testserver", "") + "..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_limits_and_account_deletion(srv, monkeypatch):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    monkeypatch.setattr(b, "_count_call", lambda *a: b._ai_error(429, "You've reached today's limit.", "daily_limit"))
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "more"})
    assert r.status_code == 429 and "today's limit" in r.json()["detail"]
    c.post("/account/delete", headers=h, json={"confirm": "DELETE"})
    assert b._genie_db(lambda con: con.execute("SELECT COUNT(*) FROM genie_files").fetchone()[0]) == 0


def test_runner_page_and_files_for_running(srv):
    b, c, h = srv
    page = c.get("/genie/runner")
    csp = page.headers["content-security-policy"]
    assert "frame-ancestors http://testserver" in csp and "https://cdn.jsdelivr.net" in csp and "'wasm-unsafe-eval'" in csp
    assert "default-src 'none'" in csp and "form-action 'none'" in csp and "x-frame-options" not in page.headers
    assert "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/" in page.text                 # pinned, never "latest"
    assert "http://testserver/test-copy/" in c.get("/genie/runner", params={"pyodide": "/test-copy/"}).text
    assert "evil.example" not in c.get("/genie/runner", params={"pyodide": "https://evil.example/"}).text   # only same-site paths
    pid = build(c, h)["project"]["id"]
    files = c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]
    assert set(files) == {"index.html", "styles.css", "js/app.js"} and files["styles.css"] == "h1{color:green}"
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.get(f"/genie/projects/{pid}/all", headers=eve).status_code == 404
    assert "no input()" in b.GENIE_SYSTEM and "test_*.py" in b.GENIE_SYSTEM


def test_commands_pause_for_the_browser_and_steps_are_recorded(srv):
    b, c, h = srv
    pid = c.post("/genie/projects", headers=h, json={"name": "Grades"}).json()["project"]["id"]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="main.py", content="print('Average:', 15)"),
                                                call("run_command", command="python main.py"),
                                                call("read_file", path="main.py")]},
                 {"content": "It works: the average is 15."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "write and run it"}).json()
    assert r["pending"]["command"] == "python main.py" and "reply" not in r
    assert [s["kind"] for s in r["steps"]] == ["write", "command"] and r["steps"][0]["title"] == "Created main.py"
    assert r["steps"][1]["output"] is None                                            # waiting for the browser
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.post(f"/genie/projects/{pid}/ask/continue", headers=eve, json={"run_id": r["pending"]["run_id"]}).status_code == 404
    done = c.post(f"/genie/projects/{pid}/ask/continue", headers=h,
                  json={"run_id": r["pending"]["run_id"], "output": "Average: 15\n", "exit_code": 0}).json()
    assert done["reply"] == "It works: the average is 15."
    assert [s["kind"] for s in done["steps"]] == ["write", "command", "read"]          # the queued read ran after the command
    assert done["steps"][1]["output"] == "Average: 15\n" and done["steps"][1]["exit_code"] == 0
    assert any(m["role"] == "tool" and m["content"].startswith("exit code: 0\nAverage: 15") for m in SEEN[-1]["messages"])
    assert any(t["function"]["name"] == "run_command" for t in SEEN[-1]["tools"])
    again = c.post(f"/genie/projects/{pid}/ask/continue", headers=h, json={"run_id": r["pending"]["run_id"], "output": "x"})
    assert again.status_code == 404                                                     # a run continues only once


def _png(size=(4, 4)):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", size, (63, 125, 18)).save(buf, "PNG"); return buf.getvalue()


def test_pictures_in_projects(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    png = _png()
    r = c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "images/logo.png", "content_b64": base64.b64encode(png).decode()})
    assert r.status_code == 200
    logo = [f for f in r.json()["files"] if f["path"] == "images/logo.png"][0]
    assert logo["picture"] is True and logo["size"] == len(png)                                  # the real size
    got = c.get(f"/genie/projects/{pid}/file", headers=h, params={"path": "images/logo.png"}).json()
    assert got["picture"] and base64.b64decode(got["content_b64"]) == png and got["mime"] == "image/png"
    url = c.get(f"/genie/projects/{pid}", headers=h).json()["project"]["preview_url"].replace("http://testserver", "")
    shown = c.get(url + "images/logo.png")
    assert shown.content == png and shown.headers["content-type"] == "image/png"                 # the preview serves the picture
    assert "images/logo.png" not in c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]   # the runner: text only
    assert "picture" in b._genie_tool(pid, "list_files", {}, [])
    assert "is a picture" in b._genie_tool(pid, "read_file", {"path": "images/logo.png"}, [])
    assert "pictures can be added, not written" in b._genie_tool(pid, "write_file", {"path": "images/logo.png", "content": "x"}, [])
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/genie/projects/{pid}/zip", headers=h).content))
    assert z.read("images/logo.png") == png                                                      # exact bytes
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as up:
        up.writestr("site/photo.png", png); up.writestr("site/index.html", "<img src=photo.png>")
    new = c.post("/genie/projects", headers=h, json={"name": "Site"}).json()["project"]["id"]
    imp = c.post(f"/genie/projects/{new}/import", headers=h, json={"zip_b64": base64.b64encode(buf.getvalue()).decode()}).json()
    assert sorted(imp["imported"]) == ["index.html", "photo.png"] and imp["skipped"] == []
    for bad in ({"path": "fake.png", "content_b64": base64.b64encode(b"not a picture").decode()},
                {"path": "big.png", "content_b64": base64.b64encode(png + b"0" * 1_000_001).decode()},
                {"path": "notes.txt", "content": "a\x00b"},
                {"path": "logo2.png", "content": "<svg>"}):
        assert c.put(f"/genie/projects/{pid}/file", headers=h, json=bad).status_code == 422, bad["path"]


def test_genie_remembers_the_conversation(srv):
    b, c, h = srv
    pid = build(c, h, "Build a shop website")["project"]["id"]                    # exchange 1 (writes 3 files)
    SCRIPT[:] = [{"content": "", "tool_calls": [call("run_command", command="ls")]}, {"content": "Made the buttons green."}]
    paused = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "make the buttons green"}).json()
    assert len(c.get(f"/genie/projects/{pid}/chat", headers=h).json()["messages"]) == 2      # saved only when finished
    c.post(f"/genie/projects/{pid}/ask/continue", headers=h, json={"run_id": paused["pending"]["run_id"], "output": "index.html", "exit_code": 0})
    msgs = SEEN[-2]["messages"]                                                    # what the AI saw for request 2
    assert [m["role"] for m in msgs[:4]] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == "Build a shop website" and msgs[2]["content"].startswith("I built a school app")
    assert "Request: make the buttons green" in msgs[3]["content"]
    chat = c.get(f"/genie/projects/{pid}/chat", headers=h).json()["messages"]
    assert [(m["role"], m["text"]) for m in chat] == [("user", "Build a shop website"), ("genie", "I built a school app: open index.html."),
                                                      ("user", "make the buttons green"), ("genie", "Made the buttons green.")]
    assert [s["kind"] for s in chat[1]["steps"]] == ["write"] * 3 and chat[3]["steps"][0]["output"] == "index.html"
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.get(f"/genie/projects/{pid}/chat", headers=eve).status_code == 404
    c.delete(f"/genie/projects/{pid}", headers=h)
    assert b._genie_db(lambda con: con.execute("SELECT COUNT(*) FROM genie_chat").fetchone()[0]) == 0


def test_undo_puts_the_project_back(srv):
    b, c, h = srv
    first = build(c, h)                                                              # request 1: 3 files
    pid, cp1 = first["project"]["id"], first["result"]["checkpoint"]
    before = c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="js/app.js", content="changed()"),
                                                call("delete_file", path="styles.css"), call("write_file", path="new.txt", content="new")]},
                 {"content": "Changed things."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "change things"}).json()
    assert set(c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]) == {"index.html", "js/app.js", "new.txt"}
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.post(f"/genie/projects/{pid}/undo", headers=eve, json={"checkpoint": r["checkpoint"]}).status_code == 404
    assert c.post(f"/genie/projects/{pid}/undo", headers=h, json={"checkpoint": r["checkpoint"]}).json()["ok"]
    assert c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"] == before          # exactly as before
    chat = c.get(f"/genie/projects/{pid}/chat", headers=h).json()["messages"]
    assert chat[-1]["text"].startswith("Undid the changes from: \u201cchange things\u201d") and chat[1]["checkpoint"] == cp1
    c.post(f"/genie/projects/{pid}/undo", headers=h, json={"checkpoint": cp1})
    assert c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"] == {}             # before request 1: empty
    for i in range(5):
        SCRIPT[:] = [{"content": f"Answer {i}."}]
        c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": f"request {i}"})
    old = c.post(f"/genie/projects/{pid}/undo", headers=h, json={"checkpoint": cp1})
    assert old.status_code == 404 and "too old" in old.json()["detail"]
    assert c.post(f"/genie/projects/{pid}/undo", headers=h, json={"checkpoint": "nonsense"}).status_code == 404
    c.delete(f"/genie/projects/{pid}", headers=h)
    assert b._genie_db(lambda con: con.execute("SELECT COUNT(*) FROM genie_snapshots").fetchone()[0]) == 0


def test_updates_show_a_diff(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]                                              # js/app.js = console.log('grades')
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="js/app.js", content="console.log('grades v2')\nconsole.log('more')"),
                                                call("write_file", path="new.js", content="x()")]},
                 {"content": "Updated."}]
    steps = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "update"}).json()["steps"]
    upd, new = steps
    assert upd["title"] == "Updated js/app.js (+2 \u22121)" and upd["diff"] is True
    assert "-console.log('grades')" in upd["detail"] and "+console.log('grades v2')" in upd["detail"] and "+++" not in upd["detail"]
    assert new["title"] == "Created new.js" and new["detail"] == "x()" and "diff" not in new


def test_live_progress_is_private(srv):
    b, c, h = srv
    pid = c.post("/genie/projects", headers=h, json={"name": "Live"}).json()["project"]["id"]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="a.txt", content="a")]}, {"content": "Done."}]
    c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "go", "progress": "abc123"})
    got = c.get(f"/genie/projects/{pid}/progress", headers=h, params={"id": "abc123"}).json()
    assert [s["title"] for s in got["steps"]] == ["Created a.txt"] and got["rounds"] == 2
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.get(f"/genie/projects/{pid}/progress", headers=eve, params={"id": "abc123"}).json()["steps"] == []
    assert c.get("/genie/projects/other/progress", headers=h, params={"id": "abc123"}).json()["steps"] == []


def test_stop_a_request(srv):
    b, c, h = srv
    pid = c.post("/genie/projects", headers=h, json={"name": "Stop"}).json()["project"]["id"]
    assert c.post(f"/genie/projects/{pid}/stop", headers=h, json={"progress": "p1"}).json() == {"stopping": True}
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="a.txt", content="a")]}, {"content": "Done."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "go", "progress": "p1"}).json()
    assert r["stopped"] and r["reply"] == b.GENIE_STOPPED and r["rounds"] == 0 and "p1" not in b._genie_stops
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="b.txt", content="b"), call("run_command", command="ls")]}]
    paused = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "again", "progress": "p2"}).json()
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.post(f"/genie/projects/{pid}/stop", headers=eve, json={"progress": "p2"}).status_code == 404
    s = c.post(f"/genie/projects/{pid}/stop", headers=h, json={"progress": "p2"}).json()
    assert s["stopped"] and [x["kind"] for x in s["steps"]] == ["write", "command"] and s["steps"][1]["output"] is None
    assert c.post(f"/genie/projects/{pid}/ask/continue", headers=h, json={"run_id": paused["pending"]["run_id"], "output": "x"}).status_code == 404
    chat = c.get(f"/genie/projects/{pid}/chat", headers=h).json()["messages"]
    assert [m["text"] for m in chat if m["role"] == "genie"] == [b.GENIE_STOPPED, b.GENIE_STOPPED]


def test_plan_mode_looks_but_never_touches(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    before = c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("read_file", path="index.html"), call("write_file", path="hack.txt", content="x"),
                                                call("run_command", command="ls")]},
                 {"content": "1. Add a cart page\n2. Link it from index.html"}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "add a cart", "mode": "plan"}).json()
    assert r["plan"] is True and r["reply"].startswith("1. Add a cart page") and "pending" not in r
    assert c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"] == before                # nothing changed
    names = [t["function"]["name"] for t in SEEN[-2]["tools"]]
    assert sorted(names) == ["list_files", "read_file", "search_files"]                           # only looking tools
    assert "PLAN MODE" in SEEN[-2]["messages"][-1]["content"] or any("PLAN MODE" in m.get("content", "") for m in SEEN[-2]["messages"])
    refused = [m["content"] for m in SEEN[-1]["messages"] if m["role"] == "tool"]
    assert refused.count("Not allowed in plan mode: reply with your plan instead.") == 2
    assert c.get(f"/genie/projects/{pid}/chat", headers=h).json()["messages"][-1]["plan"] is True
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="cart.html", content="<h1>Cart</h1>")]}, {"content": "Built it."}]
    done = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "Go ahead and build the plan above.", "mode": "auto"}).json()
    assert done["plan"] is False and "cart.html" in c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]
    assert any(m["role"] == "assistant" and m["content"].startswith("1. Add a cart page") for m in SEEN[-2]["messages"])   # it remembers the plan


def test_rename_and_duplicate(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]
    png = _png()
    c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "logo.png", "content_b64": base64.b64encode(png).decode()})
    assert c.patch(f"/genie/projects/{pid}", headers=h, json={"name": "  My   School  "}).json()["project"]["name"] == "My School"
    assert c.patch(f"/genie/projects/{pid}", headers=h, json={"name": "   "}).status_code == 422
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert c.patch(f"/genie/projects/{pid}", headers=eve, json={"name": "mine"}).status_code == 404
    assert c.post(f"/genie/projects/{pid}/duplicate", headers=eve).status_code == 404
    copy = c.post(f"/genie/projects/{pid}/duplicate", headers=h).json()
    cid = copy["project"]["id"]
    assert copy["project"]["name"] == "My School (copy)" and cid != pid
    assert c.get(f"/genie/projects/{cid}/all", headers=h).json() == c.get(f"/genie/projects/{pid}/all", headers=h).json()
    got = c.get(f"/genie/projects/{cid}/file", headers=h, params={"path": "logo.png"}).json()
    assert base64.b64decode(got["content_b64"]) == png                                             # pictures copied exactly
    assert c.get(f"/genie/projects/{cid}/chat", headers=h).json()["messages"] == []               # fresh conversation
    c.put(f"/genie/projects/{cid}/file", headers=h, json={"path": "index.html", "content": "changed"})
    assert c.get(f"/genie/projects/{pid}/file", headers=h, params={"path": "index.html"}).json()["content"] != "changed"   # original untouched
    assert copy["project"]["preview_url"] != c.get(f"/genie/projects/{pid}", headers=h).json()["project"]["preview_url"]


def test_rename_and_move_files(srv):
    b, c, h = srv
    pid = build(c, h)["project"]["id"]                                              # index.html, styles.css, js/app.js
    mv = lambda a, z, hh=h: c.patch(f"/genie/projects/{pid}/file", headers=hh, json={"path": a, "new_path": z})
    r = mv("styles.css", "css/main.css")
    assert r.status_code == 200 and r.json()["path"] == "css/main.css"
    assert set(c.get(f"/genie/projects/{pid}/all", headers=h).json()["files"]) == {"index.html", "js/app.js", "css/main.css"}
    assert c.get(f"/genie/projects/{pid}/file", headers=h, params={"path": "css/main.css"}).json()["content"] == "h1{color:green}"
    assert mv("index.html", "js/app.js").status_code == 409                       # never overwrites
    assert mv("nope.txt", "x.txt").status_code == 404 and mv("index.html", "../x").status_code == 422
    c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "logo.png", "content_b64": base64.b64encode(_png()).decode()})
    assert mv("logo.png", "images/logo.png").status_code == 200
    assert mv("images/logo.png", "logo.txt").status_code == 422 and mv("index.html", "index.png").status_code == 422
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    assert mv("index.html", "home.html", eve).status_code == 404
