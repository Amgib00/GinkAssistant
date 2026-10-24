"""Archived chats (synced), Settings > Storage, and usage-limit reset times."""
import os, sys, time, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest


def store(tmp_path, monkeypatch):
    from ginkassistant.services import history
    monkeypatch.setattr(history, "data_dir", lambda app: tmp_path)
    return history.HistoryStore(types.SimpleNamespace())


def test_archive_hides_syncs_and_unarchives(tmp_path, monkeypatch):
    h = store(tmp_path, monkeypatch)
    for sid in ("a", "b", "c"):
        h.save_message(sid, "user", f"hello {sid}")
    t0 = time.time() - 1
    h.set_archived("a", True)
    meta = h.get_meta()
    assert meta["a"]["archived"] and not meta["b"]["archived"]
    sent = {d["id"]: d for d in h.changes_since(t0)}
    assert sent["a"]["payload"]["archived"] is True                                     # goes to other devices
    other = store(tmp_path / "other", monkeypatch) if False else None
    (tmp_path / "phone").mkdir()
    from ginkassistant.services import history
    monkeypatch.setattr(history, "data_dir", lambda app: tmp_path / "phone")
    phone = history.HistoryStore(types.SimpleNamespace())
    phone.apply_remote(list(sent.values()))
    assert phone.get_meta()["a"]["archived"] is True                                    # ...and arrives archived
    assert h.archive_all() == 2 and all(m["archived"] for m in h.get_meta().values())
    h.set_archived("b", False)
    assert not h.get_meta()["b"]["archived"]


def test_storage_sizes_and_freeing(tmp_path):
    from ginkassistant.services import storage
    (tmp_path / "files").mkdir(); (tmp_path / "models" / storage.WAKE_MODEL).mkdir(parents=True)
    (tmp_path / "files" / "photo.png").write_bytes(b"x" * 4000)
    (tmp_path / "files" / "report.pdf").write_bytes(b"x" * 2000)
    (tmp_path / "models" / "model.gguf").write_bytes(b"x" * 9000)
    (tmp_path / "models" / storage.WAKE_MODEL / "am.bin").write_bytes(b"x" * 500)
    (tmp_path / "gink_history.db").write_bytes(b"x" * 300)
    u = storage.usage(str(tmp_path))
    assert u["parts"] == {"chats": 300, "images": 4000, "files": 2000, "offline_ai": 9000, "wake_model": 500, "songs": 0}
    assert u["counts"] == {"images": 1, "files": 1} and u["total"] == 15800 and u["free"] > 0
    assert storage.free_up(str(tmp_path), "images") == 4000
    assert os.path.exists(tmp_path / "files" / "report.pdf") and not os.path.exists(tmp_path / "files" / "photo.png")
    assert storage.free_up(str(tmp_path), "offline_ai") == 9000 and storage.usage(str(tmp_path))["parts"]["wake_model"] == 500
    assert storage.human(1536) == "1.5 KB" and storage.human(5 * 1024 ** 3) == "5 GB"
    with pytest.raises(ValueError):
        storage.free_up(str(tmp_path), "chats")                                          # chats: deleted elsewhere (synced)


def test_limit_answers_say_when(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "l.db"))
    from ginkassistant.services import backend_server as b
    r = b._ai_error(429, "You've reached today's limit of 30 messages. It resets at midnight (UTC).", "daily_limit")
    import json
    err = json.loads(r.body)["error"]
    assert err["resets_at"] % 86400 == 0 and 0 < err["resets_at"] - time.time() <= 86400
    assert 0 < int(r.headers["retry-after"]) <= 86400
    from ginkassistant.services.groq_worker import local_reset_time
    text = local_reset_time(err)
    assert "(UTC)" not in text and ("today" in text or "tomorrow" in text)
    assert "resets_at" not in json.loads(b._ai_error(429, "x", "rate_limited").body)["error"]
