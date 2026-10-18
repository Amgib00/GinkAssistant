"""Owner dashboard: exact numbers from a known database; owner-only, with lockout after wrong keys."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest

KEY = "k" * 40


@pytest.fixture
def owner(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "o.db")); monkeypatch.setenv("GINK_ADMIN_KEY", KEY)
    monkeypatch.setenv("GROQ_API_KEY", "g"); monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._admin_failures.clear()
    now, day = time.time(), lambda ago: time.strftime("%Y-%m-%d", time.gmtime(time.time() - ago * 86400))
    for i, (email, created_days_ago, pro) in enumerate([("a@x.co", 30, True), ("b@x.co", 3, False), ("c@x.co", 0, False), ("d@x.co", 20, True)]):
        b._upsert_user(email, email[0], provider="password")
    con = b._usage_db()
    for email, ago, pro in [("a@x.co", 30, True), ("b@x.co", 3, False), ("c@x.co", 0, False), ("d@x.co", 20, False)]:
        con.execute("UPDATE users SET created=?, pro_until=? WHERE email=?", (now - ago * 86400 - 60, now + 86400 if pro else 0, email))
    for col in ("images", "voice_chars"):
        con.execute(f"ALTER TABLE ai_usage ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    rows = [("a@x.co", day(0), 5, 9, 1, 300), ("b@x.co", day(0), 3, 3, 0, 0), ("a@x.co", day(2), 10, 12, 2, 1000), ("c@x.co", day(10), 50, 50, 0, 0)]
    con.executemany("INSERT INTO ai_usage (email, day, messages, calls, images, voice_chars) VALUES (?, ?, ?, ?, ?, ?)", rows)
    con.execute("CREATE TABLE IF NOT EXISTS claude_usage (email TEXT, day TEXT, n INTEGER, PRIMARY KEY (email, day))")
    con.execute("CREATE TABLE IF NOT EXISTS search_usage (email TEXT, day TEXT, n INTEGER, PRIMARY KEY (email, day))")
    con.executemany("INSERT INTO claude_usage VALUES (?, ?, ?)", [("a@x.co", day(0), 4), ("a@x.co", day(1), 6)])
    con.executemany("INSERT INTO search_usage VALUES (?, ?, ?)", [("b@x.co", day(0), 2), ("a@x.co", day(5), 3)])
    con.executemany("INSERT INTO payments (reference, email, provider, plan, method, amount, currency, status, created, updated, credited)"
                    " VALUES (?, ?, 'cinetpay', 'pro_1m', 'wave', ?, ?, ?, ?, ?, ?)",
                    [("r1", "a@x.co", 3000, "XOF", "success", now - 86400, now, 1), ("r2", "b@x.co", 3000, "XOF", "pending", now, now, 0)])
    con.execute(b._API_KEYS_TABLE)
    con.execute("INSERT INTO api_keys (id, email, name, key_hash, hint, created, revoked) VALUES ('k1', 'a@x.co', 'x', 'h1', 'h', ?, 0)", (now,))
    con.execute("INSERT INTO api_keys (id, email, name, key_hash, hint, created, revoked) VALUES ('k2', 'a@x.co', 'y', 'h2', 'h', ?, 1)", (now,))
    con.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, rating TEXT NOT NULL, reason TEXT, model TEXT, chars INTEGER, created REAL NOT NULL)")
    con.executemany("INSERT INTO feedback (user, rating, reason, model, chars, created) VALUES ('u', ?, ?, 'm', 1, ?)",
                    [("up", "", now), ("up", "", now), ("down", "wrong", now), ("down", "wrong", now), ("down", "too long", now)])
    con.commit(); con.close()
    return b, TestClient(b.app)


def stats(c, key=KEY):
    return c.get("/admin/stats", headers={"x-admin-key": key})


def test_numbers_are_exact(owner):
    b, c = owner
    d = stats(c).json()
    assert d["users"] == {"total": 4, "new_today": 1, "new_7d": 2, "pro_active": 1, "api_keys_active": 1}
    assert d["today"]["messages"] == 8 and d["today"]["calls"] == 12 and d["today"]["active_users"] == 2
    assert d["today"]["claude"] == 4 and d["today"]["searches"] == 2 and d["today"]["images"] == 1 and d["today"]["voice_chars"] == 300
    assert d["last7"]["messages"] == 18 and d["last7"]["claude"] == 10 and d["last7"]["searches"] == 5     # 10 days ago is excluded
    assert len(d["daily"]) == 14 and d["daily"][-1]["messages"] == 8
    assert d["revenue_30d"] == [{"currency": "XOF", "amount": 3000.0, "payments": 1}]                       # pending not counted
    assert d["feedback_7d"]["up"] == 2 and d["feedback_7d"]["down"] == 3 and d["feedback_7d"]["top_reasons"][0] == {"reason": "wrong", "count": 2}
    assert d["services"]["groq"] is True and d["services"]["anthropic"] is False and d["services"]["storage"] == "temporary"


def test_owner_only_with_lockout(owner, monkeypatch):
    b, c = owner
    assert c.get("/admin/stats").status_code == 403            # a missing key counts as a wrong attempt too
    for _ in range(9):
        assert stats(c, "wrong-key-" * 4).status_code == 403
    assert stats(c, "wrong-key-" * 4).status_code == 429
    assert stats(c).status_code == 429                         # even the right key waits out the lockout
    b._admin_failures.clear()
    assert stats(c).status_code == 200
    monkeypatch.setenv("GINK_ADMIN_KEY", "short")
    assert stats(c, "short").status_code == 403                # a guessable key is refused outright


def test_dashboard_page_is_served_safely(owner):
    b, c = owner
    r = c.get("/admin")
    assert r.status_code == 200 and "Gink owner dashboard" in r.text and "noindex" in r.text
    assert "connect-src 'self'" in r.headers["content-security-policy"]
