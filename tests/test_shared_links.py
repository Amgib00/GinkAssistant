"""Shared chat links: a read-only snapshot at /c/<id>, safe to show to anyone."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    tok = lambda e: {"Authorization": "Bearer " + b._token_response(e, "X")["token"]}
    return b, c, tok("ib@example.com"), tok("eve@example.com")


CHAT = [{"role": "system", "content": "SECRET INSTRUCTIONS"},
        {"role": "user", "content": "Plan a trip to Saint-Louis <script>alert(1)</script>"},
        {"role": "assistant", "content": "Here's a plan:\n\n- **Day 1**: the old town\n\n```python\nprint('hi')\n```"},
        {"role": "user", "content": [{"type": "text", "text": "and this photo?"},
                                     {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
        {"role": "user", "content": "inline data:image/jpeg;base64,/9j/4AAQSkZJRg== here"}]


def test_create_view_and_safety(srv):
    b, c, me, eve = srv
    r = c.post("/share", headers=me, json={"title": "Trip to Saint-Louis", "messages": CHAT}).json()
    assert r["url"].endswith("/c/" + r["id"]) and r["title"] == "Trip to Saint-Louis"
    page = c.get("/c/" + r["id"])
    csp = page.headers["content-security-policy"]
    assert page.status_code == 200 and "default-src 'none'" in csp and "script-src" not in csp      # no scripts at all
    assert "SECRET INSTRUCTIONS" not in page.text                                                     # only the conversation
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text and "<script>" not in page.text
    assert "<strong>Day 1</strong>" in page.text and "<pre" in page.text                             # formatted answers
    assert "and this photo?" in page.text and "AAAA" not in page.text and "[attachment]" in page.text
    assert 'name="robots" content="noindex"' in page.text
    listed = c.get("/shared", headers=me).json()["shared"]
    assert [x["title"] for x in listed] == ["Trip to Saint-Louis"] and listed[0]["views"] == 1
    assert c.get("/shared", headers=eve).json()["shared"] == []
    assert c.delete("/shared/" + r["id"], headers=eve).status_code == 404                           # not hers
    assert c.delete("/shared/" + r["id"], headers=me).json() == {"ok": True}
    assert c.get("/c/" + r["id"]).status_code == 404                                                 # stops working


def test_limits_and_account_deletion(srv, monkeypatch):
    b, c, me, eve = srv
    assert c.post("/share", headers=me, json={"messages": [{"role": "system", "content": "x"}]}).status_code == 422
    big = [{"role": "user", "content": "x" * 5000}] * 100
    assert c.post("/share", headers=me, json={"messages": big}).status_code == 422
    assert c.post("/share", json={"messages": CHAT}).status_code == 401
    sid = c.post("/share", headers=me, json={"messages": CHAT}).json()["id"]
    assert c.post("/account/delete", headers=me, json={"confirm": "DELETE"}).status_code == 200
    assert c.get("/c/" + sid).status_code == 404
