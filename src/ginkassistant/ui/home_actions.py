"""Main-screen 'home' strip: a greeting and a "Today" line (next alarm,
upcoming reminders, open tasks). Tasks & alarms is reached from the
sidebar or the composer's + menu, not a button here.

No quick-action buttons: actions are automatic -- you just tell the
assistant ("wake me up at 6:30", "remind me to call mom at 5") in the
normal chat box and it does it.

    home = HomeActions(store, on_prompt=send_to_chat, on_open_tasks=show_tasks)
    main_column.insert(1, home.view)   # under the header, above the chat feed
    home.refresh()                     # call after anything changes

on_prompt(text) should put the text through the same send path as the input
row (so it shows in the chat and goes through the TaskAgent).
"""
from datetime import datetime

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from ..services.actions import TaskStore

from .theme import ACCENT, BG_ELEVATED, BG_MAIN, BG_SURFACE, DANGER, ON_ACCENT, TEXT_MAIN, TEXT_MUTED

MUTED = TEXT_MUTED



def greeting(name: str = "") -> str:
    h = datetime.now().hour
    part = "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"
    return f"{part}{', ' + name if name else ''}"


class HomeActions:
    def __init__(self, store: TaskStore, on_prompt, on_open_tasks, user_name: str = "",
                 prefill=None):
        """on_prompt/prefill are accepted for compatibility but unused now
        that the quick-action buttons are gone."""
        self.store = store
        self.on_prompt = on_prompt
        self.on_open_tasks = on_open_tasks
        self.prefill = prefill
        self.user_name = user_name
        self.view = self._build()
        self.refresh()

    def _build(self):
        bg = BG_SURFACE
        self.hello = toga.Label(greeting(self.user_name),
                                style=Pack(font_size=22, font_weight="bold", color=TEXT_MAIN,
                                           margin_bottom=2, background_color=bg))
        self.today = toga.Label("", style=Pack(color=ACCENT, font_size=12, margin_bottom=10,
                                               background_color=bg))
        top = toga.Box(children=[self.hello, self.today],
                       style=Pack(direction=COLUMN, flex=1, background_color=bg))

        return toga.Box(children=[top],
                        style=Pack(direction=COLUMN, margin=(10, 14, 6, 14), background_color=bg))


    def refresh(self):
        self.hello.text = greeting(self.user_name)
        now = datetime.now()
        upcoming = [i for i in self.store.list() if i.due and i.due >= now and not i.parent_id]
        alarms = [i for i in upcoming if i.kind == "alarm"]
        open_tasks = [i for i in self.store.list("task", top_level_only=True)]
        bits = []
        if alarms:
            a = alarms[0]
            day = "today" if a.due.date() == now.date() else a.due.strftime("%a")
            bits.append(f"Next alarm {a.due:%H:%M} {day}")
        rem = [i for i in upcoming if i.kind in ("reminder", "event")]
        if rem:
            bits.append(f"{len(rem)} upcoming reminder{'s' if len(rem) != 1 else ''}")
        if open_tasks:
            bits.append(f"{len(open_tasks)} open task{'s' if len(open_tasks) != 1 else ''}")
        self.today.text = "  ·  ".join(bits) if bits else "Nothing scheduled — ask me to set something up."
