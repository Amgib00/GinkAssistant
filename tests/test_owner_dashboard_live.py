"""Owner dashboard: auto-refresh that never logs out on hiccups; server health without anyone's messages."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))


def test_health_counts_problems_without_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "h.db"))
    monkeypatch.setenv("GINK_ADMIN_KEY", "owner-key-0123456789-abcdefghij-KLMN")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._health.update(ai_refused=0, ai_fallbacks=0, live_ok=0, live_failed=0, problems=[])
    b._health["ai_refused"] += 1
    b._note_problem("AI refused", 429, "openai/gpt-oss-120b", b'{"error": {"message": "Rate limit reached: tokens per day"}}')
    assert b._health["problems"][0]["reason"] == "Rate limit reached: tokens per day"     # the provider's message, not the JSON
    for i in range(12):
        b._note_problem("Live weather", 0, "", "TimeoutError")
    h = TestClient(b.app).get("/admin/stats", headers={"x-admin-key": "owner-key-0123456789-abcdefghij-KLMN"}).json()["health"]
    assert h["ai_refused"] == 1 and len(h["problems"]) == 8 and h["uptime_s"] >= 0       # only the latest 8 kept
    assert all(p["reason"] == "TimeoutError" for p in h["problems"])                        # newest first: the old one dropped
    b._health.update(problems=[])


def test_dashboard_refreshes_by_itself_and_keeps_you_signed_in():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "admin.html"), encoding="utf-8").read()
    assert 'id="auto"' in page and "}, 30000);" in page and "visibilitychange" in page and "setInterval(tick, 1000)" in page
    assert "if (e.auth || !data)" in page               # only a rejected key (or the first load) logs out
    assert "clearInterval(timer)" not in page           # Lock no longer stops refreshing for good


def test_right_now_counts_anonymously_and_forgets_after_an_hour(monkeypatch):
    import json, time as _t
    from ginkassistant.services import backend_server as b
    b._activity.clear(); b._models_used.clear()
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(b.time, "time", lambda: clock["t"])
    b._record_activity("old@example.com", "openai/gpt-oss-20b")              # 2 hours ago: forgotten
    clock["t"] += 7200
    for who, model in (("ib@example.com", "openai/gpt-oss-120b"), ("ib@example.com", "openai/gpt-oss-120b"), ("awa@example.com", "openai/gpt-oss-20b")):
        b._record_activity(who, model)
    clock["t"] += 600                                                          # 10 minutes later: one more
    b._record_activity("awa@example.com", "openai/gpt-oss-20b")
    now = b._right_now()
    assert now["requests_1h"] == 4 and now["online_5min"] == 1                 # the old one dropped; Awa online
    assert now["per_minute"][59] == 1 and now["per_minute"][49] == 3 and len(now["per_minute"]) == 60
    assert now["models"][0] == {"model": "openai/gpt-oss-20b", "requests": 3}  # since the server started
    assert "example.com" not in json.dumps(now) and all("@" not in w for _, w, _ in b._activity)   # never who
    b._activity.clear(); b._models_used.clear()


def test_glow_design():
    """The owner chose design D ("Glow"): navy, glowing figures, donut, area chart, gradient bars, combo chart, ring."""
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "admin.html"), encoding="utf-8").read()
    for part in ("--bg: #0A1520", 'el("div", "donut")', 'class="area"', 'id="usagebars"', 'id="ring"', "url(#skybar)",
                 'stroke="#FB923C" stroke-width="3"', 'if (h.ai_refused) hh.lastChild.classList.add("bad");'):
        assert part in page, part
    assert "fonts.googleapis" not in page        # the page's security rules only allow its own files: system fonts
