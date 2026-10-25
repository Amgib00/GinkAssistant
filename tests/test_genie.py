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
    assert r["imported"] == ["app.py"] and r["skipped"] == ["logo.png (not a text file)"]   # top folder unwrapped


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
