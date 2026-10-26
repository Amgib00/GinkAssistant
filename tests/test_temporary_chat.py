"""Temporary chats: kept only in memory -- never in the database, Recents, sync or export."""
import os, sqlite3, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")


def store(tmp_path):
    from ginkassistant.services.history import HistoryStore
    app = types.SimpleNamespace(paths=types.SimpleNamespace(data=tmp_path))
    try:
        return HistoryStore(app)
    except Exception:
        h = HistoryStore.__new__(HistoryStore); h.app = app; h.db_path = str(tmp_path / "history.db"); h._init_db(); return h


def test_temporary_chats_never_reach_the_disk(tmp_path):
    h = store(tmp_path)
    normal = h.new_session_id()
    temp = h.new_session_id(temporary=True)
    assert temp.startswith("tmp-") and not normal.startswith("tmp-") and h.is_temporary(temp)
    h.save_message(normal, "user", "keep me")
    h.save_message(temp, "user", "my private question")
    h.save_message(temp, "assistant", "a private answer")
    assert [m["content"] for m in h.get_history(temp)] == ["my private question", "a private answer"]   # the chat still has context
    h.set_title(temp, "Secret"); h.set_pinned(temp, True); h.set_archived(temp, True)                  # ignored, no error
    db = [f for f in os.listdir(tmp_path) if f.endswith(".db")]
    dump = "".join(str(r) for f in db for t in ("chat_history", "chat_meta")
                   for r in sqlite3.connect(os.path.join(tmp_path, f)).execute(f"SELECT * FROM {t}").fetchall())
    assert "keep me" in dump and "private" not in dump and temp not in dump and "Secret" not in dump      # nothing on disk
    assert temp not in h.get_all_sessions() and normal in h.get_all_sessions()                          # not in Recents
    assert all(d.get("id") != temp for d in h.changes_since(0))                                          # not synced
    h.forget_temporary(temp)
    assert h.get_history(temp) == []                                                                     # gone when left
    assert [m["content"] for m in h.get_history(normal)] == ["keep me"]


def test_switch_and_web_app_wiring():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    assert 'id="temp-btn"' in page and 'id="temp-banner"' in page and "window.setTemporary" in page
    bridge = open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "if (!W.sessions[k].temporary) keep[k]" in bridge and "if (!s.temporary) W.dirty[id] = true" in bridge
    assert "!s.temporary && (s.messages || []).length" in bridge                      # not in Recents
