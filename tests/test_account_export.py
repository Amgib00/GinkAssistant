"""Download my data: everything the server keeps for an account, as a ZIP -- never passwords, keys or tokens; Genie
projects as real files; available from Settings (apps + web), the API, both SDKs and the CLI."""
import io, json, os, sys, zipfile
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
from test_genie import SCRIPT, call      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_export_has_everything_but_secrets(genie_srv, monkeypatch):
    b, c, h = genie_srv
    b._export_last.clear()
    b._upsert_user("ib@example.com", "Ibrahim", b._hash_password("correct horse battery"), "password")
    key = b._create_api_key("ib@example.com", "mine")["key"]
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html", content="<h1>Hello</h1>")]}, {"content": "Built."}]
    pid = c.post("/genie/projects", headers=h, json={"prompt": "Build a hello page"}).json()["project"]["id"]
    c.post("/dev/schedules", headers=h, json={"input": "Morning news", "environment": pid})
    r = c.get("/account/export.zip", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "README.txt" in names and "data/users.json" in names and "data/agent_schedules.json" in names
    assert any(n.endswith(f"({pid})/index.html") for n in names)                   # the project as real files
    assert z.read(next(n for n in names if n.endswith("/index.html"))) == b"<h1>Hello</h1>"
    everything = b"".join(z.read(n) for n in names)
    assert key.encode() not in everything and b"correct horse battery" not in everything
    users = json.loads(z.read("data/users.json"))
    assert users[0]["email"] == "ib@example.com" and "pw_hash" not in users[0]
    keys = json.loads(z.read("data/api_keys.json")) if "data/api_keys.json" in names else []
    assert all(not any(s in k for s in ("hash", "secret", "token")) for row in keys for k in row)
    assert c.get("/account/export.zip", headers=h).status_code == 429                # not again for 10 minutes
    assert c.get("/account/export.zip").status_code == 401


def test_export_from_the_api_sdk_and_cli(genie_srv, monkeypatch, tmp_path):
    b, c, h = genie_srv
    b._export_last.clear()
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "sdk")["key"]
    from gink import Client
    data = Client(api_key=key, base_url="http://testserver/v1", http=c).export_account()
    assert zipfile.ZipFile(io.BytesIO(data)).read("README.txt").startswith(b"Everything Gink")
    from gink_cli import main as m

    class R:
        content = b"PK-zip"
    monkeypatch.setattr(m, "_env_call", lambda key, base, method, path, **kw: R() if path == "/account/export.zip" else None)
    monkeypatch.setattr(m, "settings", lambda: ("k", "https://x/v1"))
    out = tmp_path / "mine.zip"
    assert m.main(["export", str(out)]) == 0 and out.read_bytes() == b"PK-zip"


def test_settings_and_js_pieces():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    ctl = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_controller.py"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "sdk", "js", "index.js"), encoding="utf-8").read()
    assert "action: 'export_server'" in page and 'name === "export_server"' in bridge and "_a_export_server" in ctl
    assert "exportAccount()" in js


def test_deleting_an_account_leaves_nothing_behind(genie_srv):
    """The other half of the export: after deleting an account, no table (today's or one added later) still names
    it -- except anonymised payments, the deletion marker and workspaces that belong to their members."""
    b, c, h = genie_srv
    email = "ib@example.com"
    b._upsert_user(email, "Ibrahim", b._hash_password("correct horse battery"), "password")
    SCRIPT[:] = [{"content": "Done."}]
    c.post("/genie/projects", headers=h, json={"prompt": "Build a page"})
    c.post("/dev/schedules", headers=h, json={"input": "Morning news"})
    # a row for this account in EVERY table that names accounts (so a table added later is covered too)
    with b._db_lock:
        con = b._db()
        try:
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                info = con.execute(f"PRAGMA table_info({t})").fetchall()
                col = next((r[1] for r in info if r[1] in ("email", "owner", "teen", "parent")), None)
                if not col or t in b.ACCOUNT_DELETE_KEEP:
                    continue
                vals = {r[1]: (email if r[1] in ("email", "owner", "teen", "parent") else ("x" + t if r[5] else (0 if "INT" in (r[2] or "").upper() or "REAL" in (r[2] or "").upper() else "x")))
                        for r in info if r[3] or r[5] or r[1] in ("email", "owner", "teen", "parent")}
                try:
                    con.execute(f"INSERT INTO {t} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", list(vals.values()))
                except Exception:
                    pass                                            # a unique row already exists: fine
            con.commit()
        finally:
            con.close()
    r = c.post("/account/delete", headers=h, json={"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    left = []
    with b._db_lock:
        con = b._db()
        try:
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                if t in b.ACCOUNT_DELETE_KEEP:
                    continue
                for (col,) in [(r[1],) for r in con.execute(f"PRAGMA table_info({t})").fetchall() if r[1] in ("email", "owner", "teen", "parent")]:
                    if con.execute(f"SELECT COUNT(*) FROM {t} WHERE {col}=?", (email,)).fetchone()[0]:
                        left.append(f"{t}.{col}")
        finally:
            con.close()
    assert left == [], left
