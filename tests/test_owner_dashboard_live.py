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
                 'stroke="#FB923C" stroke-width="3"', 'mini(hh, "AI refusals", fmt(h.ai_refused), h.ai_refused > 0);'):
        assert part in page, part
    assert "fonts.googleapis" not in page        # the page's security rules only allow its own files: system fonts



def test_one_screen_layout():
    """The owner didn't want a long list to scroll: figures in one row, tiles side by side, settings in Tools."""
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "admin.html"), encoding="utf-8").read()
    for part in ('class="bento"', 'id="kpis"', "grid-template-columns: repeat(8, minmax(0, 1fr))", 'class="tile s5"', 'class="tile s3 glowcard"',
                 "height: clamp(165px, calc((100vh - 305px) / 2), 340px)", '<dialog id="tools"', '$("tools").showModal()'):
        assert part in page, part
    dialog = page[page.index('<dialog id="tools"'):page.index("</dialog>")]
    for moved in ('id="revenue"', 'id="rates"', 'id="test-form"', 'id="limits"'):      # settings-type sections live in Tools
        assert moved in dialog, moved


def test_crashes_are_recorded_and_alerts_are_bundled(tmp_path, monkeypatch):
    import time as _t
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "a.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._health.update(problems=[], errors=0, alerted_at=0.0, alert_timer=None)
    sent = []
    monkeypatch.setattr(b, "_send_email", lambda to, subject, text, html="": sent.append((to, subject, text)) or "")
    if not any(getattr(r, "path", "") == "/test-crash-alert" for r in b.app.routes):
        @b.app.get("/test-crash-alert")
        def _crash():
            return {}["missing"]
    c = TestClient(b.app, raise_server_exceptions=False)
    monkeypatch.delenv("GINK_ALERT_EMAIL", raising=False)
    assert c.get("/test-crash-alert").status_code == 500
    p = b._health["problems"][0]
    assert p["kind"] == "Server error" and "on /test-crash-alert" in p["reason"] and "KeyError" in p["reason"] and b._health["errors"] == 1
    assert b._health["alert_timer"] is None and sent == []                 # no alert address: no email
    monkeypatch.setenv("GINK_ALERT_EMAIL", "owner@example.com")
    monkeypatch.setattr(b, "ALERT_EVERY", 0.3)
    b._health["alerted_at"] = _t.time()                                     # just alerted: the next ones wait and bundle
    c.get("/test-crash-alert"); c.get("/test-crash-alert")
    _t.sleep(0.8)
    assert len(sent) == 1 and sent[0][0] == "owner@example.com" and sent[0][1] == "Gink: 2 problems on your server"
    assert sent[0][2].count("KeyError") == 2
    b._health.update(problems=[], errors=0, alerted_at=0.0, alert_timer=None)
