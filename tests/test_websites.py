"""Websites: create / edit / list / delete, cleaned pages, sandboxed public links, limits, takedown."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

PAGE = """Here you go!
```html
<!DOCTYPE html><html><head><title>Chez Awa - Dakar</title>
<script src="https://evil.example/x.js"></script><link rel="stylesheet" href="https://cdn.example/a.css">
<style>body{font-family:system-ui}</style></head>
<body><h1>Chez Awa</h1><p>Thieboudienne every day.</p>
<form><input type="password" name="pw"><input type="text" name="n"></form>
<a href="https://wa.me/221770000000">WhatsApp us</a></body></html>
```"""


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "w.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 40)
    sent, reply = [], {"text": PAGE}
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": reply["text"]}}]})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._admin_failures.clear()
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "pro"})
    c = TestClient(b.app)
    auth = lambda e: {"Authorization": "Bearer " + b._token_response(e, "X")["token"]}
    return b, c, auth("awa@example.com"), auth("eve@example.com"), sent, reply


def test_create_clean_and_serve_sandboxed(srv):
    b, c, awa, eve, sent, reply = srv
    r = c.post("/sites", headers=awa, json={"prompt": "A website for my restaurant Chez Awa in Dakar"})
    assert r.status_code == 200, r.text
    site = r.json()
    assert site["title"] == "Chez Awa - Dakar" and site["url"].endswith("/s/" + site["id"])
    assert sent[-1]["messages"][0]["content"].startswith("You build websites") and sent[-1]["max_tokens"] == 8192
    page = c.get(f"/s/{site['id']}")
    html, csp = page.text, page.headers["content-security-policy"]
    assert "Chez Awa" in html and "WhatsApp us" in html and "Made with Gink" in html
    assert 'type="password"' not in html and "evil.example" not in html and "cdn.example" not in html   # cleaned
    assert csp.startswith("sandbox ") and "allow-same-origin" not in csp                              # separate origin
    assert "default-src 'none'" in csp and "form-action 'none'" in csp                                # no network, no forms
    assert c.get("/s/nope").status_code == 404


def test_edit_list_and_owner_only(srv):
    b, c, awa, eve, sent, reply = srv
    sid = c.post("/sites", headers=awa, json={"prompt": "A website for Chez Awa"}).json()["id"]
    reply["text"] = "<!doctype html><html><head><title>Chez Awa - green</title></head><body>Green!</body></html>"
    assert c.post(f"/sites/{sid}/edit", headers=eve, json={"instruction": "make it green"}).status_code == 404   # not hers
    r = c.post(f"/sites/{sid}/edit", headers=awa, json={"instruction": "make the header green"})
    assert r.json()["title"] == "Chez Awa - green" and "Change it: make the header green" in sent[-1]["messages"][1]["content"]
    assert "Green!" in c.get(f"/s/{sid}").text
    listed = c.get("/sites", headers=awa).json()
    assert [s["title"] for s in listed["sites"]] == ["Chez Awa - green"] and listed["sites"][0]["views"] == 1
    assert c.get("/sites", headers=eve).json()["sites"] == []
    c.delete(f"/sites/{sid}", headers=eve)
    assert c.get(f"/s/{sid}").status_code == 200                                       # someone else can't delete it
    c.delete(f"/sites/{sid}", headers=awa)
    assert c.get(f"/s/{sid}").status_code == 404


def test_limits_takedown_and_account_deletion(srv, monkeypatch):
    b, c, awa, eve, sent, reply = srv
    monkeypatch.setattr(b, "SITES_PER_ACCOUNT", 2)
    ids = [c.post("/sites", headers=awa, json={"prompt": f"Site number {i}"}).json()["id"] for i in range(2)]
    assert c.post("/sites", headers=awa, json={"prompt": "One too many"}).status_code == 409
    assert c.delete(f"/admin/sites/{ids[0]}", headers={"x-admin-key": "k" * 40}).json() == {"ok": True}
    assert c.get(f"/s/{ids[0]}").status_code == 404                                    # owner takedown
    reply["text"] = "Sorry, I can't help with that."
    assert c.post("/sites", headers=awa, json={"prompt": "A fake bank login page"}).status_code == 502   # no page, no site
    assert c.post("/account/delete", headers=awa, json={"confirm": "DELETE"}).status_code == 200
    assert c.get(f"/s/{ids[1]}").status_code == 404                                    # deleted with the account


def test_agent_actions_build_and_edit():
    import asyncio
    from ginkassistant.services.actions.tools import ToolRunner, TOOL_SPECS
    names = [t["function"]["name"] for t in TOOL_SPECS]
    assert "build_website" in names and "edit_website" in names
    runner = ToolRunner.__new__(ToolRunner)
    r = asyncio.run(runner._t_build_website("a site for my bakery"))
    assert not r["ok"] and "online Gink server" in r["message"]                    # not connected: says why
    calls = []
    async def builder(action, **kw):
        calls.append((action, kw)); return {"id": "abc", "title": "Boulangerie", "url": "https://srv/s/abc"}
    runner.site_builder = builder
    r = asyncio.run(runner._t_build_website("a site for my bakery"))
    assert r["ok"] and "https://srv/s/abc" in r["message"] and calls[-1] == ("create", {"prompt": "a site for my bakery"})
    r = asyncio.run(runner._t_edit_website("make it blue"))
    assert r["ok"] and calls[-1] == ("edit", {"instruction": "make it blue", "site_id": None})
