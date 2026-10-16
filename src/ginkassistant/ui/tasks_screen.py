"""Workspace screen (was "Tasks & alarms").

Opened from the sidebar ("Workspace") or the composer's + menu. Shows
everything Gink is keeping track of for you:
  * summary cards -- open tasks, upcoming reminders/events, alarms set
    (tap one to jump to that list)
  * one command box ("wake me up at 6:30", "plan my week") that goes
    through the TaskAgent, same as the chat
  * a filter bar (All / Tasks / Reminders / Alarms / Timers / Events),
    Show done, and Clear done
  * rows with Done / Delete, AI-planned steps indented under their task
    with a progress count, and overdue items flagged

Rows stay native Toga widgets so their buttons can call Python directly.
"""
from datetime import datetime

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from ..services.actions import TaskAgent, TaskStore
from .theme import (ACCENT, BG_ELEVATED, BG_MAIN, BG_SURFACE, DANGER, ON_ACCENT,
                    TEXT_MAIN, TEXT_MUTED)

ICON = {"task": "\u2705", "reminder": "\U0001F514", "alarm": "\u23F0", "timer": "\u23F2", "event": "\U0001F4C5"}
FILTERS = [("All", None), ("Tasks", "task"), ("Reminders", "reminder"), ("Alarms", "alarm"),
           ("Timers", "timer"), ("Events", "event")]
MUTED = TEXT_MUTED


class TasksScreen:
    """Kept under its old name so existing imports keep working."""

    def __init__(self, app: toga.App, store: TaskStore, agent: TaskAgent, on_back=None):
        self.app = app
        self.store = store
        self.agent = agent
        self.on_back = on_back
        self._busy = False
        self.kind = None
        self.view = self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build(self):
        bg = BG_SURFACE
        back = toga.Button("\u2190 Back", on_press=self._back,
                           style=Pack(margin_right=12, color=TEXT_MUTED, background_color=BG_ELEVATED))
        title = toga.Label("Workspace", style=Pack(font_size=22, font_weight="bold",
                                                   color=TEXT_MAIN, background_color=bg))
        subtitle = toga.Label("Everything Gink is keeping track of for you",
                              style=Pack(font_size=12, color=TEXT_MUTED, background_color=bg))
        header = toga.Box(
            children=[back, toga.Box(children=[title, subtitle],
                                     style=Pack(direction=COLUMN, flex=1, background_color=bg))],
            style=Pack(direction=ROW, align_items=CENTER, margin=(16, 18, 12, 18), background_color=bg))

        # summary cards
        self.stat_labels = {}
        cards = []
        for key, label, kind in (("tasks", "Open tasks", "task"),
                                 ("upcoming", "Upcoming reminders", "reminder"),
                                 ("alarms", "Alarms set", "alarm")):
            num = toga.Label("0", style=Pack(font_size=24, font_weight="bold", color=TEXT_MAIN,
                                             background_color=BG_ELEVATED))
            cap = toga.Label(label, style=Pack(font_size=12, color=TEXT_MUTED, background_color=BG_ELEVATED))
            open_btn = toga.Button("View \u2192", on_press=lambda w, k=kind: self._set_kind(k),
                                   style=Pack(margin_top=6, color=ACCENT, background_color=BG_ELEVATED, font_size=12))
            self.stat_labels[key] = num
            cards.append(toga.Box(children=[num, cap, open_btn],
                                  style=Pack(direction=COLUMN, margin=12, background_color=BG_ELEVATED)))
        stats = toga.Box(children=[toga.Box(children=[c], style=Pack(flex=1, margin=(0, 4), background_color=BG_ELEVATED))
                                   for c in cards],
                         style=Pack(direction=ROW, margin=(0, 14, 14, 14), background_color=bg))

        self.command = toga.TextInput(
            placeholder="Tell Gink what to do \u2014 \u201cwake me up at 6:30\u201d, \u201cplan my exam revision\u201d",
            on_confirm=self._run_command,
            style=Pack(flex=1, margin_right=6, color=TEXT_MAIN, background_color=BG_ELEVATED))
        self.go = toga.Button("Do it", on_press=self._run_command,
                              style=Pack(color=ON_ACCENT, background_color=ACCENT, font_weight="bold"))
        cmd_row = toga.Box(children=[self.command, self.go],
                           style=Pack(direction=ROW, margin=(0, 18, 6, 18), background_color=bg))

        self.status = toga.Label("", style=Pack(color=ACCENT, margin=(0, 20, 8, 20), background_color=bg))

        # filter bar
        self.filter_buttons = {}
        chips = []
        for label, kind in FILTERS:
            b = toga.Button(label, on_press=lambda w, k=kind: self._set_kind(k),
                            style=Pack(margin_right=6, background_color=BG_ELEVATED, color=TEXT_MAIN))
            self.filter_buttons[kind] = b
            chips.append(b)
        chip_row = toga.ScrollContainer(
            content=toga.Box(children=chips, style=Pack(direction=ROW, background_color=bg)),
            vertical=False, style=Pack(flex=1, height=44, background_color=bg))
        self.show_done = toga.Switch("Show done", on_change=lambda w: self.refresh(),
                                     style=Pack(margin_left=8, color=TEXT_MUTED, background_color=bg))
        clear_done = toga.Button("Clear done", on_press=self._clear_done,
                                 style=Pack(margin_left=8, color=TEXT_MUTED, background_color=BG_ELEVATED))
        filter_row = toga.Box(children=[chip_row, self.show_done, clear_done],
                              style=Pack(direction=ROW, align_items=CENTER, margin=(4, 18, 10, 18),
                                         background_color=bg))

        self.list_box = toga.Box(style=Pack(direction=COLUMN, margin=(0, 18), background_color=BG_MAIN))
        scroll = toga.ScrollContainer(content=self.list_box, horizontal=False,
                                      style=Pack(flex=1, background_color=BG_MAIN))

        return toga.Box(children=[header, stats, cmd_row, self.status, filter_row, scroll],
                        style=Pack(direction=COLUMN, flex=1, background_color=bg))

    def _set_kind(self, kind):
        self.kind = kind
        self.refresh()

    def _refresh_stats(self):
        now = datetime.now()
        top = self.store.list(include_done=False, top_level_only=True)
        self.stat_labels["tasks"].text = str(sum(1 for i in top if i.kind == "task"))
        self.stat_labels["upcoming"].text = str(sum(1 for i in top if i.kind in ("reminder", "event")
                                                    and (i.due is None or i.due >= now)))
        self.stat_labels["alarms"].text = str(sum(1 for i in top if i.kind == "alarm"))
        for kind, b in self.filter_buttons.items():
            active = kind == self.kind
            b.style.background_color = ACCENT if active else BG_ELEVATED
            b.style.color = ON_ACCENT if active else TEXT_MAIN

    def refresh(self):
        self._refresh_stats()
        for child in list(self.list_box.children):
            self.list_box.remove(child)
        items = self.store.list(self.kind, include_done=bool(self.show_done.value), top_level_only=True)
        if not items:
            what = dict((k, l) for l, k in FILTERS).get(self.kind, "All")
            hint = ("Nothing here yet. Try \u201cremind me to drink water in 30 minutes\u201d or "
                    "\u201chelp me plan my exam revision\u201d.") if self.kind is None else f"No {what.lower()} yet."
            self.list_box.add(toga.Label(hint, style=Pack(color=MUTED, margin=(24, 4), background_color=BG_MAIN)))
            return
        for it in items:
            steps = self.store.children(it.id)
            self.list_box.add(self._row(it, indent=0, steps=steps))
            for step in steps:
                if step.done and not self.show_done.value:
                    continue
                self.list_box.add(self._row(step, indent=28))

    def _row(self, it, indent, steps=()):
        card = BG_MAIN if indent else BG_ELEVATED
        icon = "\u2022" if it.parent_id else ICON.get(it.kind, "\u2022")
        text = f"\u2713  {it.title}" if it.done else f"{icon}  {it.title}"
        label = toga.Label(text, style=Pack(flex=1, font_weight="normal" if indent else "bold",
                                            color=MUTED if it.done else TEXT_MAIN, background_color=card))
        col = [label]
        meta = []
        if it.due and not it.parent_id:
            meta.append(f"{it.due:%a %d %b \u00b7 %H:%M}")
            if it.system_scheduled:
                meta.append("on your device")
        if steps:
            done = sum(1 for s in steps if s.done)
            meta.append(f"{done}/{len(steps)} steps done")
        overdue = bool(it.due and not it.done and not it.parent_id and it.due < datetime.now()
                       and it.kind in ("task", "reminder", "event"))
        if overdue:
            meta.insert(0, "Overdue")
        if meta:
            col.append(toga.Label("  \u00b7  ".join(meta),
                                  style=Pack(color=DANGER if overdue else ACCENT, font_size=11, background_color=card)))
        text_col = toga.Box(children=col, style=Pack(direction=COLUMN, flex=1, background_color=card))
        buttons = []
        if not it.done:
            buttons.append(toga.Button("Done", on_press=lambda w, i=it.id: self._done(i),
                                       style=Pack(margin_left=6, color=ON_ACCENT, background_color=ACCENT)))
        buttons.append(toga.Button("Delete", on_press=lambda w, i=it.id: self._delete(i),
                                   style=Pack(margin_left=6, color=DANGER, background_color=card)))
        row = toga.Box(children=[text_col, *buttons],
                       style=Pack(direction=ROW, align_items=CENTER, margin=(10, 12, 10, 12 + indent),
                                  background_color=card))
        return toga.Box(children=[row], style=Pack(direction=COLUMN, margin_bottom=6, background_color=card))

    def _clear_done(self, widget):
        for it in self.store.list(include_done=True):
            if it.done:
                self.store.delete(it.id)
        self.status.text = "Cleared finished items."
        self.refresh()

    # ------------------------------------------------------------- actions
    def _back(self, widget):
        if self.on_back:
            self.on_back()

    def _done(self, item_id):
        self.store.set_done(item_id, True)
        self.refresh()

    def _delete(self, item_id):
        # goes through the tool so OS-scheduled alarms get cancelled too
        self.app.loop.create_task(self._delete_async(item_id))

    async def _delete_async(self, item_id):
        res = await self.agent.runner.execute("delete_item", {"id": item_id})
        self.status.text = res.get("message", "")
        self.refresh()

    async def _run_command(self, widget):
        text = (self.command.value or "").strip()
        if not text or self._busy:
            return
        self._busy = True
        self.go.enabled = False
        self.status.text = "Thinking…"

        async def on_status(msg):
            self.status.text = msg

        try:
            reply = await self.agent.run(text, on_status=on_status)
            self.status.text = _plain(reply.text)
            self.command.value = ""
        except Exception as e:
            self.status.text = f"Something went wrong: {e}"
        finally:
            self._busy = False
            self.go.enabled = True
            self.refresh()


def _plain(md: str) -> str:
    """Status line is a plain Label — strip simple markdown."""
    import re
    s = re.sub(r"[*_~`#]", "", md or "")
    return s if len(s) < 400 else s[:397] + "…"


async def show_due_dialog(window, title, message):
    """Works on both Toga 0.4 (info_dialog) and 0.5+ (dialog(InfoDialog))."""
    try:
        await window.dialog(toga.InfoDialog(title, message))
    except AttributeError:
        await window.info_dialog(title, message)
