"""Gink's own Facebook Page, Instagram and TikTok on the owner dashboard: tokens set on Render (no
connect buttons), read-only, owner only, TikTok's day-long token renewed."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 32)
    for k in ("GINK_FB_PAGE_ID", "GINK_FB_PAGE_TOKEN", "GINK_IG_USER_ID", "GINK_IG_TOKEN", "GINK_TIKTOK_TOKEN",
              "GINK_TIKTOK_REFRESH", "GINK_TIKTOK_CLIENT_KEY", "GINK_TIKTOK_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._admin_failures.clear(); b._social_cache.update(at=0, data=None); b._tiktok_token["value"] = ""
    seen = []

    def api(request):
        u = str(request.url)
        seen.append(u)
        if "graph.facebook.com" in u and "/posts" in u:
            return httpx.Response(200, json={"data": [{"message": "Gink 0.1.110 is out", "created_time": "2026-11-05",
                "permalink_url": "https://facebook.com/p/1", "comments": {"summary": {"total_count": 4}},
                "reactions": {"summary": {"total_count": 31}}}]})
        if "graph.facebook.com" in u and "/media" in u:
            return httpx.Response(200, json={"data": [{"caption": "Hey Gink!", "permalink": "https://instagram.com/p/x",
                                                       "like_count": 120, "comments_count": 9}]})
        if "graph.facebook.com" in u and "1784" in u:
            return httpx.Response(200, json={"username": "gink.app", "followers_count": 2300})
        if "graph.facebook.com" in u:
            return httpx.Response(200, json={"name": "Gink", "followers_count": 5100, "link": "https://facebook.com/gink"})
        if "oauth/token" in u:
            return httpx.Response(200, json={"access_token": "renewed"})
        if "user/info" in u:
            if request.headers.get("authorization") == "Bearer expired":
                return httpx.Response(401, json={"error": {"code": "access_token_invalid"}})
            return httpx.Response(200, json={"data": {"user": {"display_name": "Gink", "follower_count": 900, "likes_count": 15000}}})
        if "video/list" in u:
            return httpx.Response(200, json={"data": {"videos": [{"title": "Hey Gink demo", "share_url": "https://tiktok.com/v/1",
                                                                  "like_count": 800, "comment_count": 40, "view_count": 12000}]}})
        return httpx.Response(404)
    from httpx import _client

    class Mock(_client.AsyncClient):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(api); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    return b, TestClient(b.app), monkeypatch, seen


H = {"x-admin-key": "k" * 32}


def test_nothing_set_up(srv):
    b, c, mp, seen = srv
    assert c.get("/admin/social").status_code == 403
    j = c.get("/admin/social", headers=H).json()
    assert j == {"facebook": {"set_up": False}, "instagram": {"set_up": False}, "tiktok": {"set_up": False}} and seen == []


def test_all_three(srv):
    b, c, mp, seen = srv
    mp.setenv("GINK_FB_PAGE_ID", "1001"); mp.setenv("GINK_FB_PAGE_TOKEN", "page-token")
    mp.setenv("GINK_IG_USER_ID", "17841"); mp.setenv("GINK_TIKTOK_TOKEN", "expired")
    mp.setenv("GINK_TIKTOK_REFRESH", "r"); mp.setenv("GINK_TIKTOK_CLIENT_KEY", "ck"); mp.setenv("GINK_TIKTOK_CLIENT_SECRET", "cs")
    j = c.get("/admin/social", headers=H).json()
    assert j["facebook"]["followers"] == 5100 and j["facebook"]["posts"][0] == {
        "text": "Gink 0.1.110 is out", "at": "2026-11-05", "link": "https://facebook.com/p/1", "comments": 4, "likes": 31}
    assert j["instagram"]["name"] == "@gink.app" and j["instagram"]["posts"][0]["likes"] == 120
    assert j["tiktok"]["followers"] == 900 and j["tiktok"]["posts"][0]["views"] == 12000          # renewed the token
    assert b._tiktok_token["value"] == "renewed"
    n = len(seen)
    c.get("/admin/social", headers=H)
    assert len(seen) == n                                                         # cached


def test_expired_tiktok_without_renewal_says_why(srv):
    b, c, mp, seen = srv
    mp.setenv("GINK_TIKTOK_TOKEN", "expired")
    assert "lasts a day" in c.get("/admin/social", headers=H).json()["tiktok"]["error"]


def test_dashboard_has_no_connect_buttons():
    admin = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "web_app", "admin.html"),
                 encoding="utf-8").read()
    social = admin.split('aria-label="Social accounts"')[1].split("</section>")[0]
    assert "button" not in social.lower() and "function loadSocial" in admin
