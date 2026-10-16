"""On-device storage for tasks, reminders, alarms and timers (stdlib sqlite3).

One table, one row per item. Tasks can have child steps (parent_id), which is
how the agent stores the plan it works out when you ask it to analyse a goal.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

KINDS = ("task", "reminder", "alarm", "timer", "event")
_FMT = "%Y-%m-%d %H:%M:%S"


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime(_FMT) if dt else None


def from_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in (_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@dataclass
class Item:
    id: int
    kind: str
    title: str
    notes: str
    due: Optional[datetime]
    done: bool
    fired: bool
    system_scheduled: bool
    parent_id: Optional[int]
    created: datetime

    def describe(self) -> str:
        when = f" — {self.due:%a %d %b, %H:%M}" if self.due else ""
        state = " ✓" if self.done else ""
        return f"{self.title}{when}{state}"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "notes": self.notes, "due": to_iso(self.due), "done": self.done,
            "parent_id": self.parent_id,
        }


class TaskStore:
    on_change = None      # called after any local write (sync, home summary)

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    due TEXT,
                    done INTEGER NOT NULL DEFAULT 0,
                    fired INTEGER NOT NULL DEFAULT 0,
                    system_scheduled INTEGER NOT NULL DEFAULT 0,
                    parent_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
                    created TEXT NOT NULL
                )"""
            )
            self._db.execute("PRAGMA foreign_keys = ON")
            # sync support (services/sync.py): a stable id across devices,
            # a last-changed time, and tombstones for deletions
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(items)").fetchall()}
            if "uid" not in cols:
                self._db.execute("ALTER TABLE items ADD COLUMN uid TEXT")
            if "updated" not in cols:
                self._db.execute("ALTER TABLE items ADD COLUMN updated REAL NOT NULL DEFAULT 0")
            for (rid,) in self._db.execute("SELECT id FROM items WHERE uid IS NULL").fetchall():
                self._db.execute("UPDATE items SET uid=?, updated=? WHERE id=?",
                                 (uuid.uuid4().hex, time.time(), rid))
            self._db.execute("CREATE TABLE IF NOT EXISTS item_tombstones (uid TEXT PRIMARY KEY, updated REAL NOT NULL)")
            self._db.commit()

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _row(r: sqlite3.Row) -> Item:
        return Item(
            id=r["id"], kind=r["kind"], title=r["title"], notes=r["notes"],
            due=from_iso(r["due"]), done=bool(r["done"]), fired=bool(r["fired"]),
            system_scheduled=bool(r["system_scheduled"]),
            parent_id=r["parent_id"], created=from_iso(r["created"]) or datetime.now(),
        )

    # -- writes ----------------------------------------------------------
    def add(self, kind: str, title: str, *, notes: str = "", due: Optional[datetime] = None,
            parent_id: Optional[int] = None, system_scheduled: bool = False) -> Item:
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}")
        title = (title or "").strip() or kind.capitalize()
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO items (kind, title, notes, due, parent_id, system_scheduled, created, uid, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, title, notes or "", to_iso(due), parent_id,
                 int(system_scheduled), to_iso(datetime.now()), uuid.uuid4().hex, time.time()),
            )
            self._db.commit()
            new_id = cur.lastrowid
        self._notify()
        return self.get(new_id)

    def set_done(self, item_id: int, done: bool = True) -> Optional[Item]:
        with self._lock:
            now = time.time()
            self._db.execute("UPDATE items SET done=?, updated=? WHERE id=?", (int(done), now, item_id))
            # finishing a parent finishes its steps too
            if done:
                self._db.execute("UPDATE items SET done=1, updated=? WHERE parent_id=? AND done=0", (now, item_id))
            self._db.commit()
        self._notify()
        return self.get(item_id)

    def mark_fired(self, item_id: int) -> None:
        with self._lock:
            self._db.execute("UPDATE items SET fired=1, updated=? WHERE id=?", (time.time(), item_id))
            self._db.commit()

    def delete(self, item_id: int) -> bool:
        with self._lock:
            now = time.time()
            for (uid,) in self._db.execute("SELECT uid FROM items WHERE id=? OR parent_id=?",
                                           (item_id, item_id)).fetchall():
                if uid:
                    self._db.execute("INSERT OR REPLACE INTO item_tombstones (uid, updated) VALUES (?, ?)", (uid, now))
            self._db.execute("DELETE FROM items WHERE parent_id=?", (item_id,))
            cur = self._db.execute("DELETE FROM items WHERE id=?", (item_id,))
            self._db.commit()
            ok = cur.rowcount > 0
        self._notify()
        return ok

    # -- reads -----------------------------------------------------------
    def get(self, item_id: int) -> Optional[Item]:
        with self._lock:
            r = self._db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return self._row(r) if r else None

    def list(self, kind: Optional[str] = None, include_done: bool = False,
             top_level_only: bool = False) -> List[Item]:
        q, args = "SELECT * FROM items WHERE 1=1", []
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if not include_done:
            q += " AND done=0"
        if top_level_only:
            q += " AND parent_id IS NULL"
        q += " ORDER BY (due IS NULL), due, id"
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [self._row(r) for r in rows]

    def children(self, parent_id: int) -> List[Item]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM items WHERE parent_id=? ORDER BY id", (parent_id,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def due_items(self, now: Optional[datetime] = None) -> List[Item]:
        now = now or datetime.now()
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM items WHERE fired=0 AND done=0 AND due IS NOT NULL"
                " AND kind IN ('reminder','alarm','timer','task','event') AND due<=?",
                (to_iso(now),),
            ).fetchall()
        return [self._row(r) for r in rows]


# ---------------------------------------------------------------- sync
# Alarms and timers stay on the device that set them (they go into that
# device's own Clock app / scheduler); tasks, reminders and events sync.
SYNC_KINDS = ("task", "reminder", "event")


def _item_changes_since(self, ts: float) -> List[dict]:
    with self._lock:
        rows = self._db.execute(
            f"SELECT i.*, p.uid AS parent_uid FROM items i LEFT JOIN items p ON i.parent_id = p.id"
            f" WHERE i.updated > ? AND i.kind IN ({','.join('?' * len(SYNC_KINDS))})",
            (ts, *SYNC_KINDS)).fetchall()
        tombs = self._db.execute("SELECT uid, updated FROM item_tombstones WHERE updated > ?", (ts,)).fetchall()
    docs = [{"id": r["uid"], "updated": r["updated"], "deleted": False, "payload": {
        "kind": r["kind"], "title": r["title"], "notes": r["notes"], "due": r["due"],
        "done": bool(r["done"]), "fired": bool(r["fired"]), "parent": r["parent_uid"], "created": r["created"]}}
        for r in rows]
    docs += [{"id": t["uid"], "updated": t["updated"], "deleted": True, "payload": {}} for t in tombs]
    return docs


def _item_apply_remote(self, docs: List[dict]) -> int:
    applied = 0
    # parents before steps, so a step can find its parent
    docs = sorted(docs, key=lambda d: bool((d.get("payload") or {}).get("parent")))
    with self._lock:
        for d in docs:
            uid, upd = d["id"], d["updated"]
            row = self._db.execute("SELECT id, updated FROM items WHERE uid=?", (uid,)).fetchone()
            tomb = self._db.execute("SELECT updated FROM item_tombstones WHERE uid=?", (uid,)).fetchone()
            newest_local = max(row["updated"] if row else 0, tomb["updated"] if tomb else 0)
            if newest_local >= upd:
                continue
            if d.get("deleted"):
                if row:
                    self._db.execute("DELETE FROM items WHERE parent_id=?", (row["id"],))
                    self._db.execute("DELETE FROM items WHERE id=?", (row["id"],))
                self._db.execute("INSERT OR REPLACE INTO item_tombstones (uid, updated) VALUES (?, ?)", (uid, upd))
                applied += 1
                continue
            p = d.get("payload") or {}
            if p.get("kind") not in SYNC_KINDS:
                continue
            parent_id = None
            if p.get("parent"):
                pr = self._db.execute("SELECT id FROM items WHERE uid=?", (p["parent"],)).fetchone()
                parent_id = pr["id"] if pr else None
            if row:
                self._db.execute("UPDATE items SET kind=?, title=?, notes=?, due=?, done=?, fired=?, parent_id=?,"
                                 " updated=? WHERE id=?",
                                 (p["kind"], p.get("title", ""), p.get("notes", ""), p.get("due"),
                                  int(bool(p.get("done"))), int(bool(p.get("fired"))), parent_id, upd, row["id"]))
            else:
                self._db.execute("INSERT INTO items (kind, title, notes, due, done, fired, system_scheduled,"
                                 " parent_id, created, uid, updated) VALUES (?,?,?,?,?,?,0,?,?,?,?)",
                                 (p["kind"], p.get("title", ""), p.get("notes", ""), p.get("due"),
                                  int(bool(p.get("done"))), int(bool(p.get("fired"))), parent_id,
                                  p.get("created") or to_iso(datetime.now()), uid, upd))
            self._db.execute("DELETE FROM item_tombstones WHERE uid=?", (uid,))
            applied += 1
        self._db.commit()
    return applied


TaskStore.changes_since = _item_changes_since
TaskStore.apply_remote = _item_apply_remote
