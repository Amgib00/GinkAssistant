"""
Chat history storage -- a real implementation of the contract confirmed
against the actual GinkHistoryManager (core/history.py): get_history,
save_message, get_all_sessions, clear_history. Same sqlite3 + chat_history
table shape, but the database file lives under services/paths.py's
data_dir() instead of a __file__-relative guess.

Multiple sessions are supported (not just "default_session") so the
history sidebar (ui/history_sidebar.py) has something real to show --
GinkHistoryManager.get_all_sessions()'s shape (session_id -> {"messages",
"timestamp"}) is what ui/widgets/history_widget.py's HistoryWidget was
built to consume, so that's reproduced here too.
"""

import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

import toga

from .paths import data_dir

DB_NAME = "gink_history.db"


class HistoryStore:
    def __init__(self, app: toga.App):
        self.db_path = data_dir(app) / DB_NAME
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # sync support (services/sync.py): last-changed time per chat,
            # and deleted=1 rows as tombstones so deletions sync too
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chat_meta ("
                " session_id TEXT PRIMARY KEY, updated REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)"
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_meta)").fetchall()}
            if "title" not in cols:
                conn.execute("ALTER TABLE chat_meta ADD COLUMN title TEXT DEFAULT ''")
            if "pinned" not in cols:
                conn.execute("ALTER TABLE chat_meta ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
            if "archived" not in cols:
                conn.execute("ALTER TABLE chat_meta ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                "INSERT OR IGNORE INTO chat_meta (session_id, updated, deleted)"
                " SELECT DISTINCT session_id, ?, 0 FROM chat_history", (time.time(),)
            )
            conn.commit()

    # -- temporary chats ------------------------------------------------------
    # Ids starting with "tmp-" live only in memory: never written to the database, so never in
    # Recents, sync, export or backups, and gone when the app closes (or the chat is left).
    TEMP_PREFIX = "tmp-"

    @classmethod
    def is_temporary(cls, session_id) -> bool:
        return str(session_id or "").startswith(cls.TEMP_PREFIX)

    def _temp_store(self) -> Dict[str, List[Dict[str, str]]]:
        if not hasattr(self, "_temp"):
            self._temp = {}
        return self._temp

    def forget_temporary(self, session_id: str = None) -> None:
        """Drop one temporary chat (or all of them)."""
        if session_id is None:
            self._temp_store().clear()
        else:
            self._temp_store().pop(session_id, None)

    def save_message(self, session_id: str, role: str, content: str):
        # The same question twice in a row (sent again after the first got no answer -- a lost connection, a
        # limit) is kept once: opening the chat again showed "which device i'm using" twice (0.1.160).
        if self.is_temporary(session_id):
            kept = self._temp_store().setdefault(session_id, [])
            if role == "user" and kept and kept[-1] == {"role": "user", "content": content}:
                return
            kept.append({"role": role, "content": content})
            return
        if not content or not content.strip():
            return
        with self._connect() as conn:
            if role == "user":
                last = conn.execute("SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                                    (session_id,)).fetchone()
                if last and last[0] == "user" and last[1] == content.strip():
                    return
            conn.execute(
                "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content.strip()),
            )
            self._touch(conn, session_id)
            conn.commit()
        self._changed()

    def get_history(self, session_id: str, limit: int = 24) -> List[Dict[str, str]]:
        if self.is_temporary(session_id):
            return [dict(m) for m in self._temp_store().get(session_id, [])[-limit:]]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, role, content, timestamp FROM chat_history ORDER BY id ASC"
            ).fetchall()

        sessions: Dict[str, Dict[str, Any]] = {}
        for session_id, role, content, timestamp_str in rows:
            entry = sessions.setdefault(session_id, {"messages": [], "timestamp": None})
            entry["messages"].append({"role": role, "content": content})
            try:
                entry["timestamp"] = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                pass
        return sessions

    def clear_history(self, session_id: str):
        if self.is_temporary(session_id):
            return self.forget_temporary(session_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
            self._touch(conn, session_id, deleted=True)
            conn.commit()
        self._changed()

    def new_session_id(self, temporary: bool = False) -> str:
        # random suffix: two devices starting a chat in the same second
        # must not collide once they sync
        if temporary:
            return self.TEMP_PREFIX + uuid.uuid4().hex[:12]
        return datetime.now().strftime("session-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

    # -- sync --------------------------------------------------------------
    on_change = None

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    @staticmethod
    def _touch(conn, session_id: str, deleted: bool = False):
        # keep a chat's title / pin when it changes (INSERT OR REPLACE would wipe them)
        conn.execute("INSERT INTO chat_meta (session_id, updated, deleted) VALUES (?, ?, ?)"
                     " ON CONFLICT(session_id) DO UPDATE SET updated=excluded.updated, deleted=excluded.deleted",
                     (session_id, time.time(), int(deleted)))
        if deleted:
            conn.execute("UPDATE chat_meta SET title='', pinned=0 WHERE session_id=?", (session_id,))

    # -- rename / pin (sidebar chat menu) -----------------------------------
    def set_title(self, session_id: str, title: str) -> None:
        if self.is_temporary(session_id):
            return
        with self._connect() as conn:
            self._touch(conn, session_id)
            conn.execute("UPDATE chat_meta SET title=? WHERE session_id=?", ((title or "").strip()[:120], session_id))
            conn.commit()
        self._changed()

    def set_pinned(self, session_id: str, pinned: bool) -> None:
        if self.is_temporary(session_id):
            return
        with self._connect() as conn:
            self._touch(conn, session_id)
            conn.execute("UPDATE chat_meta SET pinned=? WHERE session_id=?", (int(bool(pinned)), session_id))
            conn.commit()
        self._changed()

    def set_archived(self, session_id: str, archived: bool) -> None:
        if self.is_temporary(session_id):
            return
        """Archived chats leave Recents but are kept (Settings > Privacy > Archived chats)."""
        with self._connect() as conn:
            self._touch(conn, session_id)
            conn.execute("UPDATE chat_meta SET archived=? WHERE session_id=?", (int(bool(archived)), session_id))
            conn.commit()
        self._changed()

    def archive_all(self) -> int:
        ids = [sid for sid, m in self.get_meta().items() if not m["archived"]]
        for sid in ids:
            self.set_archived(sid, True)
        return len(ids)

    def get_meta(self) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT session_id, title, pinned, archived FROM chat_meta WHERE deleted=0").fetchall()
        return {sid: {"title": t or "", "pinned": bool(p), "archived": bool(a)} for sid, t, p, a in rows}

    def changes_since(self, ts: float) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            metas = conn.execute("SELECT session_id, updated, deleted, title, pinned, archived FROM chat_meta WHERE updated > ?",
                                 (ts,)).fetchall()
            docs = []
            for sid, updated, deleted, title, pinned, archived in metas:
                msgs = [] if deleted else [
                    {"role": r, "content": c, "ts": t} for r, c, t in conn.execute(
                        "SELECT role, content, timestamp FROM chat_history WHERE session_id = ? ORDER BY id",
                        (sid,)).fetchall()]
                docs.append({"id": sid, "updated": updated, "deleted": bool(deleted),
                             "payload": {"messages": msgs, "title": title or "", "pinned": bool(pinned),
                                         "archived": bool(archived)}})
        return docs

    TASK_PREFIX = "task-"            # a scheduled task's chat: Gink's server adds each result (0.1.161)

    def pop_task_news(self) -> List[Dict[str, Any]]:
        """Scheduled tasks' new results since the last call: [{"id", "title", "text"}] (for a notification)."""
        news, self._task_news = getattr(self, "_task_news", []), []
        return news

    def apply_remote(self, docs: List[Dict[str, Any]]) -> int:
        """Whole-chat last-writer-wins: a newer copy from another device
        replaces this device's copy of that chat."""
        applied = 0
        if not hasattr(self, "_task_news"):
            self._task_news = []
        with self._connect() as conn:
            for d in docs:
                row = conn.execute("SELECT updated FROM chat_meta WHERE session_id = ?", (d["id"],)).fetchone()
                if row and row[0] >= d["updated"]:
                    continue
                if str(d["id"]).startswith(self.TASK_PREFIX) and not d.get("deleted"):
                    msgs = (d.get("payload") or {}).get("messages") or []
                    had = conn.execute("SELECT COUNT(*) FROM chat_history WHERE session_id = ?", (d["id"],)).fetchone()[0]
                    if len(msgs) > max(had, 1) and msgs[-1].get("role") == "assistant":
                        self._task_news.append({"id": d["id"], "title": (d.get("payload") or {}).get("title") or "",
                                                "text": str(msgs[-1].get("content") or "")})
                conn.execute("DELETE FROM chat_history WHERE session_id = ?", (d["id"],))
                if not d.get("deleted"):
                    for m in (d.get("payload") or {}).get("messages", []):
                        if m.get("content"):
                            conn.execute("INSERT INTO chat_history (session_id, role, content, timestamp)"
                                         " VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
                                         (d["id"], m.get("role", "user"), m["content"], m.get("ts")))
                p = d.get("payload") or {}
                conn.execute("INSERT OR REPLACE INTO chat_meta (session_id, updated, deleted, title, pinned, archived)"
                             " VALUES (?, ?, ?, ?, ?, ?)",
                             (d["id"], d["updated"], int(bool(d.get("deleted"))), p.get("title") or "",
                              int(bool(p.get("pinned"))), int(bool(p.get("archived")))))
                applied += 1
            conn.commit()
        if applied:
            self._changed()
        return applied
