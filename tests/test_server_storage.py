"""Persistent storage on Render: /health says where accounts live, a missing disk is caught, and
the owner can download a consistent backup."""
import sqlite3

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

ADMIN = "k" * 32


@pytest.fixture
def server(tmp_path, monkeypatch):
    for k in ("RENDER", "RENDER_SERVICE_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "data" / "gink.db"))
    monkeypatch.setenv("GINK_ADMIN_KEY", ADMIN)
    from ginkassistant.services import backend_server as b
    b._admin_failures.clear()
    return b, TestClient(b.app)


def test_local_server(server):
    b, c = server
    assert c.get("/health").json()["storage"] == "local"
    assert b._storage_status()["ok"] is True


def test_render_without_db_path_is_temporary(server, monkeypatch):
    b, c = server
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("GINK_DB_PATH")
    st = b._storage_status()
    assert st["mode"] == "temporary" and st["ok"] is False and "GINK_DB_PATH" in st["detail"]
    assert c.get("/health").json()["storage"] == "temporary"


def test_render_with_missing_disk_is_temporary(server, monkeypatch):
    b, _ = server
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(b.os.path, "ismount", lambda p: False)
    st = b._storage_status()
    assert st["mode"] == "temporary" and st["ok"] is False and "No disk" in st["detail"]


def test_render_with_disk(server, monkeypatch, tmp_path):
    b, c = server
    monkeypatch.setenv("RENDER", "true")
    disk = str(tmp_path / "data")
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.setattr(b.os.path, "ismount", lambda p: str(p) == disk)
    assert b._storage_status() == {"mode": "disk", "ok": True,
                                   "detail": "Accounts are stored on the disk and survive restarts."}
    assert c.get("/health").json()["storage"] == "disk"


def test_missing_disk_is_a_dashboard_problem(server, monkeypatch):
    b, _ = server
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(b.os.path, "ismount", lambda p: False)
    before = len(b._health["problems"])
    b._check_storage_at_startup()
    assert b._health["problems"][0]["kind"] == "Storage" and len(b._health["problems"]) >= min(before + 1, 8)


def test_database_uses_write_ahead_log(server):
    b, _ = server
    b._check_storage_at_startup()
    con = sqlite3.connect(str(b._db_path()))
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.close()


def test_backup_is_owner_only(server):
    _, c = server
    assert c.get("/admin/backup").status_code == 403
    assert c.get("/admin/backup", headers={"x-admin-key": "wrong" * 6}).status_code == 403


def test_backup_contains_accounts(server, tmp_path):
    b, c = server
    b._upsert_user("ib@example.com", "Ibrahim")
    r = c.get("/admin/backup", headers={"x-admin-key": ADMIN})
    assert r.status_code == 200 and "gink-backup-" in r.headers["content-disposition"]
    out = tmp_path / "copy.db"
    out.write_bytes(r.content)
    rows = sqlite3.connect(str(out)).execute("SELECT email, name FROM users").fetchall()
    assert rows == [("ib@example.com", "Ibrahim")]
