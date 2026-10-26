"""Settings on every device: the same synced list everywhere; the server merges; prefs.save notifies."""
import os, re, sys, types
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import pytest


def test_the_three_lists_are_the_same():
    from ginkassistant.services import prefs, backend_server as b
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    web = set(re.findall(r'"([a-z_]+)"', re.search(r"var SYNCED_PREFS = \[(.*?)\];", bridge, re.S).group(1)))
    assert prefs.SYNCED == b.SYNCED_PREFS == web
    assert not ({"wake_enabled", "use_location", "city", "briefing_last_date", "voice_intro_seen"} & prefs.SYNCED)   # device-only


def test_save_notifies_only_synced_changes_and_never_echoes(tmp_path, monkeypatch):
    from ginkassistant.services import prefs
    monkeypatch.setattr(prefs, "config_dir", lambda app: tmp_path)
    got = []
    monkeypatch.setattr(prefs, "on_change", [got.append])
    app = types.SimpleNamespace()
    prefs.save(app, theme="dark", wake_enabled=True, briefing_last_date="x")
    prefs.save(app, _from_sync=True, chat_font="serif")                  # from the account: not sent back
    assert got == [{"theme": "dark"}] and prefs.load(app)["chat_font"] == "serif"


def test_server_merges_per_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "p.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    me = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "E")["token"]}
    assert c.get("/account/preferences", headers=me).json() == {"prefs": {}, "updated": 0}
    c.put("/account/preferences", headers=me, json={"prefs": {"theme": "dark", "wake_enabled": True, "evil": "x"}})
    r = c.put("/account/preferences", headers=me, json={"prefs": {"chat_font": "serif", "voice_speed": 1.2, "theme": "x" * 301}}).json()
    assert r["prefs"] == {"theme": "dark", "chat_font": "serif", "voice_speed": 1.2}            # merged; unknown/device/huge dropped
    assert c.get("/account/preferences", headers=eve).json()["prefs"] == {}
    c.post("/account/delete", headers=me, json={"confirm": "DELETE"})
    assert b._prefs_db(lambda con: con.execute("SELECT COUNT(*) FROM account_preferences").fetchone()[0]) == 0
