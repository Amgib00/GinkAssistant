"""Workspace screen (was "Tasks & alarms").

Opened from the sidebar ("Workspace") or the composer's + menu. A web page (ui/workspace_page.py) like Media
Studio: everything Gink keeps track of for you -- summary cards that filter, one "tell Gink" box that goes
through the TaskAgent (same as the chat), a segmented filter, items grouped into Overdue / Today / Upcoming /
Anytime (and Finished, when shown), steps under their task with a progress bar, Done / Delete on each row.

snapshot() is the whole state the page draws (and what the tests check); handle() runs the page's events.
"""
import asyncio
import json
from datetime import datetime, timedelta

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from ..services.actions import TaskAgent, TaskStore
from .theme import css_vars
from .workspace_page import PAGE

ICON = {"task": "\u2705", "reminder": "\U0001F514", "alarm": "\u23F0", "timer": "\u23F2", "event": "\U0001F4C5"}
FILTERS = [("All", None), ("Tasks", "task"), ("Reminders", "reminder"), ("Alarms", "alarm"),
           ("Timers", "timer"), ("Events", "event")]


def _when(due: datetime, now: datetime) -> str:
    if due.date() == now.date():
        return f"Today {due:%H:%M}"
    if due.date() == (now + timedelta(days=1)).date():
        return f"Tomorrow {due:%H:%M}"
    if due.date() == (now - timedelta(days=1)).date():
        return f"Yesterday {due:%H:%M}"
    if abs((due - now).days) < 7:
        return f"{due:%a %H:%M}"
    return f"{due:%a %d %b \u00b7 %H:%M}"


class TasksScreen:
    """Kept under its old name so existing imports keep working."""

    def __init__(self, app: toga.App, store: TaskStore, agent: TaskAgent, on_back=None):
        self.app, self.store, self.agent, self.on_back = app, store, agent, on_back
        self.kind = None
        self.show_done = False
        self.status = ""
        self._busy = False
        self.web = toga.WebView(style=Pack(flex=1))
        self.web.set_content("https://gink.local/workspace", PAGE.replace("__THEME__", css_vars()))
        self.view = toga.Box(children=[self.web], style=Pack(direction=COLUMN, flex=1))
        self.token = object()
        app._workspace_token = self.token
        try:
            asyncio.get_event_loop().create_task(self.run())
        except RuntimeError:
            pass

    # ------------------------------------------------------------ the state the page draws
    def _item(self, it, now, steps=()):
        overdue = bool(it.due and not it.done and not it.parent_id and it.due < now and it.kind in ("task", "reminder", "event"))
        out = {"id": it.id, "title": it.title, "kind": it.kind, "done": bool(it.done), "overdue": overdue,
               "when": _when(it.due, now) if it.due and not it.parent_id else "", "device": bool(it.system_scheduled)}
        if steps:
            out.update(steps_done=sum(1 for s in steps if s.done), steps_total=len(steps),
                       steps=[self._item(s, now) for s in steps if self.show_done or not s.done])
        return out

    def snapshot(self) -> dict:
        now = datetime.now()
        top = self.store.list(include_done=False, top_level_only=True)
        stats = {"task": sum(1 for i in top if i.kind == "task"),
                 "upcoming": sum(1 for i in top if i.kind in ("reminder", "event") and (i.due is None or i.due >= now)),
                 "alarm": sum(1 for i in top if i.kind == "alarm"), "timer": sum(1 for i in top if i.kind == "timer")}
        items = self.store.list(self.kind, include_done=self.show_done, top_level_only=True)
        groups = {"overdue": [], "today": [], "upcoming": [], "anytime": [], "finished": []}
        for it in items:
            row = self._item(it, now, self.store.children(it.id))
            if it.done:
                groups["finished"].append(row)
            elif row["overdue"]:
                groups["overdue"].append(row)
            elif it.due and it.due.date() == now.date():
                groups["today"].append(row)
            elif it.due:
                groups["upcoming"].append(row)
            else:
                groups["anytime"].append(row)
        titles = {"overdue": "Overdue", "today": "Today", "upcoming": "Upcoming", "anytime": "Anytime", "finished": "Finished"}
        done_count = sum(1 for i in self.store.list(include_done=True) if i.done)
        return {"date": f"{now:%A, %d %B}".replace(" 0", " "), "kind": self.kind or "", "show_done": self.show_done,
                "stats": stats, "done_count": done_count,
                "groups": [{"key": k, "title": titles[k], "items": v} for k, v in groups.items() if v]}

    # ------------------------------------------------------------ page plumbing
    async def js(self, script: str):
        try:
            await asyncio.wait_for(self.web.evaluate_javascript(script), timeout=3)
        except Exception:
            pass

    async def call(self, fn, *args):
        await self.js(f"{fn}({', '.join(json.dumps(a) for a in args)})")

    def alive(self):
        return getattr(self.app, "_workspace_token", None) is self.token

    async def run(self):
        from .page_events import EventQueue
        events = EventQueue()
        await asyncio.sleep(0.4)
        while self.alive():
            for ev in await events.take(self.web):
                asyncio.create_task(self.handle(ev))
            await asyncio.sleep(0.15)

    def refresh(self):
        """Redraw (sync callers: the scheduler, Settings)."""
        try:
            asyncio.get_event_loop().create_task(self.call("setData", self.snapshot()))
        except RuntimeError:
            pass

    async def handle(self, ev):
        kind, value = ev.get("type"), ev.get("value")
        if kind == "ready":
            await self.call("setData", self.snapshot())
        elif kind == "back":
            self.app._workspace_token = None
            if self.on_back:
                self.on_back()
        elif kind == "filter":
            self._set_kind(value or None)
        elif kind == "show_done":
            self.show_done = bool(value)
        elif kind == "done":
            self._done(int(value))
        elif kind == "undone":
            self.store.set_done(int(value), False)
        elif kind == "delete":
            await self._delete_async(int(value))
        elif kind == "clear_done":
            self._clear_done(None)
        elif kind == "command":
            await self._run_command(str(value or ""))
            return
        await self.call("setData", self.snapshot())

    # ------------------------------------------------------------ actions (kept names)
    def _set_kind(self, kind):
        self.kind = kind if kind in dict((k, k) for _, k in FILTERS if k) else None

    def _done(self, item_id):
        self.store.set_done(item_id, True)

    def _clear_done(self, widget):
        for it in self.store.list(include_done=True):
            if it.done:
                self.store.delete(it.id)
        self.status = "Cleared finished items."

    async def _delete_async(self, item_id):
        # goes through the tool so OS-scheduled alarms get cancelled too
        res = await self.agent.runner.execute("delete_item", {"id": item_id})
        self.status = res.get("message", "")

    async def _run_command(self, text):
        text = (text or "").strip()
        if not text or self._busy:
            return
        self._busy = True

        async def on_status(msg):
            self.status = msg
            await self.call("setStatus", msg, True)

        try:
            reply = await self.agent.run(text, on_status=on_status)
            self.status = _plain(reply.text)
        except Exception as e:
            self.status = f"Something went wrong: {e}"
        finally:
            self._busy = False
            await self.call("setStatus", self.status, False)
            await self.call("setData", self.snapshot())


def _plain(md: str) -> str:
    """The status line is plain text -- strip simple markdown."""
    import re
    s = re.sub(r"[*_~`#]", "", md or "")
    return s if len(s) < 400 else s[:397] + "\u2026"


async def show_due_dialog(window, title, message):
    """Kept for older callers; the main screen now shows an in-app notification instead (ui/notify)."""
    try:
        await window.dialog(toga.InfoDialog(title, message))
    except AttributeError:
        await window.info_dialog(title, message)
