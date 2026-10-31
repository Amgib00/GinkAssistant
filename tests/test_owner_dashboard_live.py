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
