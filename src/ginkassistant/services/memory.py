"""
What Gink remembers about you -- only things you asked it to remember
("remember that my exams start on 12 November", "remember I'm vegetarian").

Each memory is a short sentence. They're added to the AI's instructions
for every reply, so Gink can use them without being reminded, and they
sync to your account (services/sync.py). Settings -> Memory lists them,
with Forget buttons.

Stored in SQLite (memory.db in the app's data folder). Deleting keeps a
tombstone row (deleted=1) so the deletion can sync to your other devices.
"""

import re
import sqlite3
import threading
import time
import uuid
from typing import List, Optional

MAX_MEMORIES_IN_PROMPT = 60


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", " ".join((text or "").lower().split()))


class MemoryStore:
    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS memories ("
                " uid TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL NOT NULL,"
                " updated REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)"
            )
            self._db.commit()
        self.on_change = None

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # -- writes ----------------------------------------------------------
    def add(self, text: str) -> dict:
        text = " ".join((text or "").split()).strip().rstrip(".")
        if not text:
            raise ValueError("Nothing to remember.")
        text = text[0].upper() + text[1:]
        key = _norm(text)
        for m in self.list():
            if _norm(m["text"]) == key:
                return m                              # already remembered
        now = time.time()
        uid = uuid.uuid4().hex
        with self._lock:
            self._db.execute("INSERT INTO memories (uid, text, created, updated, deleted) VALUES (?,?,?,?,0)",
                             (uid, text, now, now))
            self._db.commit()
        self._changed()
        return {"uid": uid, "text": text}

    def forget(self, query: str) -> List[dict]:
        """Forget by uid, or every memory whose text contains all the words
        of `query` ("forget my exam date" -> anything mentioning exam + date)."""
        query = (query or "").strip()
        rows = self.list()
        hit = [m for m in rows if m["uid"] == query]
        if not hit:
            words = [w for w in _norm(query).split() if w not in {"my", "the", "a", "an", "that", "about", "i"}]
            if words:
                hit = [m for m in rows if all(w in _norm(m["text"]) for w in words)]
        now = time.time()
        with self._lock:
            for m in hit:
                self._db.execute("UPDATE memories SET deleted=1, updated=? WHERE uid=?", (now, m["uid"]))
            self._db.commit()
        if hit:
            self._changed()
        return hit

    def clear(self) -> int:
        rows = self.list()
        now = time.time()
        with self._lock:
            self._db.execute("UPDATE memories SET deleted=1, updated=? WHERE deleted=0", (now,))
            self._db.commit()
        self._changed()
        return len(rows)

    # -- reads -----------------------------------------------------------
    def list(self) -> List[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT uid, text, created FROM memories WHERE deleted=0 ORDER BY created").fetchall()
        return [{"uid": r["uid"], "text": r["text"], "created": r["created"]} for r in rows]

    def recall(self, query: str, k: int = 3) -> List[dict]:
        """The memories that match a message (shared meaningful words), best first -- shown as
        "Recalled memory" above the answer. The same scoring as the web app's recallMemories()."""
        return recall(self.list(), query, k)

    def as_prompt(self) -> str:
        items = self.list()[-MAX_MEMORIES_IN_PROMPT:]
        if not items:
            return ""
        lines = "\n".join(f"- {m['text']}" for m in items)
        return ("\n\nThings the user asked you to remember about them (use them when relevant, "
                "don't recite them unprompted):\n" + lines)

    # -- sync ------------------------------------------------------------
    def changes_since(self, ts: float) -> List[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM memories WHERE updated > ?", (ts,)).fetchall()
        return [{"id": r["uid"], "updated": r["updated"], "deleted": bool(r["deleted"]),
                 "payload": {"text": r["text"], "created": r["created"]}} for r in rows]

    def apply_remote(self, docs: List[dict]) -> int:
        applied = 0
        with self._lock:
            for d in docs:
                cur = self._db.execute("SELECT updated FROM memories WHERE uid=?", (d["id"],)).fetchone()
                if cur and cur["updated"] >= d["updated"]:
                    continue
                p = d.get("payload") or {}
                self._db.execute(
                    "INSERT OR REPLACE INTO memories (uid, text, created, updated, deleted) VALUES (?,?,?,?,?)",
                    (d["id"], p.get("text", ""), p.get("created", d["updated"]), d["updated"],
                     int(bool(d.get("deleted")))))
                applied += 1
            self._db.commit()
        if applied:
            self._changed()
        return applied


STOP = frozenset("""a an and are as at be but by can could did do does for from had has have how i if in into is it its
me my no not of on or our so than that the their them then there these they this to was we were what when where which
who why will with would you your yes please tell about just like some any also very really want need know""".split())


def _words(text: str) -> set:
    import re
    return {w for w in re.findall(r"[\w']+", (text or "").lower()) if len(w) >= 3 and w not in STOP}


def recall(memories: list, query: str, k: int = 3) -> list:
    """Score = shared meaningful words (longer words count a little more); ties: the newest first."""
    q = _words(query)
    if not q:
        return []
    scored = []
    for m in memories:
        shared = q & _words(m.get("text", ""))
        if shared:
            scored.append((sum(1 + len(w) / 10 for w in shared), m.get("created", 0), m))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [m for _, _, m in scored[:k]]
