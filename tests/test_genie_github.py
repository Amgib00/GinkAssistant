"""Gink Genie -> GitHub: connect (repo permission), push projects as commits, revoke. GitHub is simulated."""
import json, os, sqlite3, sys, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

GH = {}


def github(request):
    path, method = request.url.path, request.method
    GH.setdefault("calls", []).append((method, path))
    auth = request.headers.get("authorization", "")
    if path == "/login/oauth/access_token":
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        GH["redirect_uri"] = form.get("redirect_uri")
        return httpx.Response(200, json={"access_token": "gho_SECRET_TOKEN", "scope": "repo"})
    if GH.get("expired") and auth:
        return httpx.Response(401, json={"message": "Bad credentials"})
    if path == "/user":
        return httpx.Response(200, json={"login": "Amgib00"})
    repo = "/repos/Amgib00/school-app"
    if path == repo and method == "GET":
        return httpx.Response(200, json=GH["repo"]) if GH.get("repo") else httpx.Response(404, json={"message": "Not Found"})
    if path == "/user/repos" and method == "POST":
        body = json.loads(request.content); GH["created"] = body
        GH["repo"] = {"html_url": "https://github.com/Amgib00/school-app", "default_branch": "main"}; GH["head"] = "init0"
        return httpx.Response(201, json=GH["repo"])
    if path == repo + "/git/ref/heads/main":
        return httpx.Response(200, json={"object": {"sha": GH["head"]}})
    if path == repo + "/git/blobs":
        GH.setdefault("blobs", []).append(json.loads(request.content)); return httpx.Response(201, json={"sha": f"blob{len(GH['blobs'])}"})
    if path == repo + "/git/trees":
        GH["tree"] = json.loads(request.content)["tree"]; return httpx.Response(201, json={"sha": f"tree{len(GH['tree'])}"})
    if path == repo + "/git/commits":
        body = json.loads(request.content); GH.setdefault("commits", []).append(body)
        return httpx.Response(201, json={"sha": f"commit{len(GH['commits'])}"})
    if path == repo + "/git/refs/heads/main" and method == "PATCH":
        GH["head"] = json.loads(request.content)["sha"]; return httpx.Response(200, json={})
    return httpx.Response(404, json={"message": "unexpected " + path})


@pytest.fixture
def srv(tmp_path, monkeypatch):
    GH.clear()
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "gh.db"))
    monkeypatch.setenv("GITHUB_CLIENT_ID", "ghid"); monkeypatch.setenv("GITHUB_CLIENT_SECRET", "ghsecret")
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(github); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    def sync_request(method, url, json=None, auth=None, headers=None, timeout=None, **kw):
        GH.setdefault("revoked", []).append((url, json, auth)); return httpx.Response(204)
    monkeypatch.setattr(httpx, "request", sync_request)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: GH.setdefault("google", []).append((url, kw.get("data"))) or httpx.Response(200))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._gh_states.clear()
    c = TestClient(b.app)
    return b, c, {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}, str(tmp_path / "gh.db")


def connect(b, c, h):
    url = c.post("/genie/github/begin", headers=h).json()["url"]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    page = c.get("/auth/github/callback/connect", params={"code": "abc", "state": q["state"]})
    return q, page


def project(c, h):
    pid = c.post("/genie/projects", headers=h, json={"name": "School app"}).json()["project"]["id"]
    for path, content in {"index.html": "<h1>School</h1>", "js/app.js": "console.log(1)", "old.txt": "remove me"}.items():
        c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": path, "content": content})
    return pid


def test_connect_push_and_push_again(srv):
    b, c, h, db = srv
    assert c.get("/genie/github", headers=h).json() == {"configured": True, "connected": False, "login": ""}
    q, page = connect(b, c, h)
    assert q["scope"] == "repo" and q["redirect_uri"] == "http://testserver/auth/github/callback/connect"   # under the sign-in callback
    assert page.status_code == 200 and "Connected as Amgib00" in page.text and GH["redirect_uri"] == q["redirect_uri"]
    assert c.get("/genie/github", headers=h).json()["login"] == "Amgib00"
    assert "gho_SECRET_TOKEN" not in str(sqlite3.connect(db).execute("SELECT * FROM connections").fetchall())   # encrypted
    pid = project(c, h)
    r = c.post(f"/genie/projects/{pid}/github", headers=h, json={"repo": "school-app", "private": True, "message": "First version"}).json()
    assert r["repo"] == "Amgib00/school-app" and r["files"] == 3 and r["commit_url"].endswith("/commit/commit1")
    assert GH["created"]["private"] is True and GH["created"]["auto_init"] is True
    assert sorted(t["path"] for t in GH["tree"]) == ["index.html", "js/app.js", "old.txt"] and GH["commits"][0]["parents"] == ["init0"]
    c.delete(f"/genie/projects/{pid}/file", headers=h, params={"path": "old.txt"})
    r2 = c.post(f"/genie/projects/{pid}/github", headers=h, json={"repo": "school-app"}).json()
    assert GH["commits"][1]["parents"] == ["commit1"] and GH["head"] == "commit2"                # on top of the first
    assert sorted(t["path"] for t in GH["tree"]) == ["index.html", "js/app.js"]                     # deleted file is gone
    assert GH["calls"].count(("POST", "/user/repos")) == 1                                        # created once, then reused


def test_expired_disconnect_and_account_deletion(srv):
    b, c, h, db = srv
    connect(b, c, h)
    pid = project(c, h)
    assert c.post(f"/genie/projects/{pid}/github", headers={"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]},
                  json={"repo": "x"}).status_code == 404                                           # not her project
    GH["expired"] = True
    r = c.post(f"/genie/projects/{pid}/github", headers=h, json={"repo": "school-app"})
    assert r.status_code == 409 and "Connect GitHub again" in r.json()["detail"]
    assert c.get("/genie/github", headers=h).json()["connected"] is False                           # forgotten
    GH["expired"] = False; connect(b, c, h)
    assert c.delete("/genie/github", headers=h).json() == {"ok": True}
    url, body, auth = GH["revoked"][-1]
    assert url == "https://api.github.com/applications/ghid/token" and body == {"access_token": "gho_SECRET_TOKEN"} and auth == ("ghid", "ghsecret")
    connect(b, c, h)
    assert c.post("/account/delete", headers=h, json={"confirm": "DELETE"}).status_code == 200
    assert GH["revoked"][-1][1] == {"access_token": "gho_SECRET_TOKEN"}                             # revoked at GitHub
    assert not any("gho_SECRET_TOKEN" in str(d) for _, d in GH.get("google", []))                   # never sent to Google


def test_pictures_go_to_github_as_blobs(srv):
    import base64 as b64
    b, c, h, db = srv
    connect(b, c, h)
    pid = project(c, h)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    c.put(f"/genie/projects/{pid}/file", headers=h, json={"path": "logo.png", "content_b64": b64.b64encode(png).decode()})
    c.post(f"/genie/projects/{pid}/github", headers=h, json={"repo": "school-app"})
    assert GH["blobs"] == [{"content": b64.b64encode(png).decode(), "encoding": "base64"}]
    entry = [t for t in GH["tree"] if t["path"] == "logo.png"][0]
    assert entry["sha"] == "blob1" and "content" not in entry                                   # referenced, not inlined
    assert all("content" in t for t in GH["tree"] if t["path"] != "logo.png")
