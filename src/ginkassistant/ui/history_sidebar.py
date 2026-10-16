"""
Session list sidebar -- rebuilds the multi-session browsing UI found in
ui/widgets/history_widget.py (HistoryWidget), consuming the same data
shape its load_saved_history() expected: session_id -> {"messages",
"timestamp"}, here from services/history.py's HistoryStore.get_all_sessions().

Toga has no built-in list-with-embedded-row-widgets control the way Qt's
QListWidget has, so this uses the same Box-column-in-a-ScrollContainer
pattern already proven for the chat feed, rather than relying on
toga.DetailedList's per-row action support, which isn't consistent
enough across backends to build on yet.

Per request, upgraded with:
  - A "..." button per row that reveals/hides a Delete button, instead
    of Delete sitting permanently visible next to every session.
  - A brief highlight "flash" on a row right after you select it --
    this is NOT a real CSS animation (there's no such thing available
    here): these rows have to stay native Toga buttons, since selecting
    or deleting a session needs to call back into Python, and Toga's
    WebView has no JS-to-Python bridge at all (confirmed earlier,
    github.com/beeware/toga/issues/2268) -- so moving this list into a
    WebView the way the chat feed did would make clicks silently do
    nothing. What IS achievable natively: stepping a row's
    background_color through a couple of timed stops via asyncio.sleep,
    which reads as a quick highlight pulse rather than a smooth
    animation, but is real motion rather than an instant snap.
"""

import asyncio
import datetime

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .style_utils import pack

# Matches ui/main_screen.py's palette (duplicated, not imported, to avoid
# a circular import -- main_screen.py imports build_history_panel from
# this file).
from .theme import ACCENT, BG_ELEVATED, BG_HOVER, BG_SIDEBAR, BG_SURFACE, DANGER, ON_ACCENT, TEXT_MAIN, TEXT_MUTED

BG_SELECTED = BG_ELEVATED
BG_FLASH = BG_HOVER


def _summarize(messages) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "")
            return (text[:32] + "...") if len(text) > 32 else text
    return "New conversation"


def _group_label(timestamp) -> str:
    if timestamp is None:
        return "Earlier"
    today = datetime.datetime.now().date()
    entry_date = timestamp.date()
    if entry_date == today:
        return "Today"
    if entry_date == today - datetime.timedelta(days=1):
        return "Yesterday"
    return "Earlier"


def build_history_panel(app, history_store, on_select, on_delete, current_session_id: str, on_open_media_studio=None, on_open_settings=None, on_open_tasks=None):
    """Returns (panel_box, refresh_fn). Call refresh_fn() after any
    change to the stored sessions to redraw the list.

    on_open_media_studio, if given, adds a "Media Studio" entry right
    below "+ New chat" -- moved here from main_screen.py's header per
    request, so it reads as a persistent nav item next to session
    management rather than a one-off header button. on_open_settings,
    if given, adds a "Settings" entry the same way."""

    list_box = toga.Box(style=Pack(direction=COLUMN, background_color=BG_SIDEBAR))

    async def _flash(widget, base_color):
        try:
            for color in (BG_FLASH, base_color, BG_FLASH, base_color):
                widget.style.background_color = color
                await asyncio.sleep(0.12)
        except Exception:
            pass  # see module docstring -- best-effort, not load-bearing

    def _make_row(session_id, messages):
        is_current = session_id == current_session_id
        base_color = BG_SELECTED if is_current else BG_SIDEBAR

        select_btn = toga.Button(
            _summarize(messages),
            style=pack(flex=1, margin=6, color=TEXT_MAIN, background_color=base_color if is_current else None),
        )
        more_btn = toga.Button(
            "\u2026", style=Pack(width=28, color=TEXT_MUTED, background_color=BG_SIDEBAR)
        )
        delete_btn = toga.Button(
            "Delete", style=Pack(width=60, color=DANGER, background_color=BG_SIDEBAR)
        )
        row = toga.Box(style=Pack(direction=ROW, margin_bottom=4, background_color=BG_SIDEBAR), children=[select_btn, more_btn])

        def _on_select(widget):
            asyncio.create_task(_flash(select_btn, base_color))
            on_select(session_id)

        def _toggle_menu(widget):
            if delete_btn in row.children:
                row.remove(delete_btn)
            else:
                row.add(delete_btn)

        def _on_delete(widget):
            on_delete(session_id)

        select_btn.on_press = _on_select
        more_btn.on_press = _toggle_menu
        delete_btn.on_press = _on_delete
        return row

    def refresh():
        existing = list(list_box.children)
        if existing:
            list_box.remove(*existing)

        sessions = history_store.get_all_sessions()
        grouped = {"Today": [], "Yesterday": [], "Earlier": []}
        for session_id, payload in sessions.items():
            messages = payload.get("messages", [])
            if not messages:
                continue
            grouped[_group_label(payload.get("timestamp"))].append(
                (session_id, messages, payload.get("timestamp"))
            )

        for label in ("Today", "Yesterday", "Earlier"):
            entries = sorted(grouped[label], key=lambda e: e[2] or datetime.datetime.min, reverse=True)
            if not entries:
                continue
            list_box.add(
                toga.Label(label, style=Pack(font_size=11, font_weight="bold", color=TEXT_MUTED, margin_top=8, background_color=BG_SIDEBAR))
            )
            for session_id, messages, _ts in entries:
                list_box.add(_make_row(session_id, messages))

    new_session_btn = toga.Button(
        "+ New chat",
        style=Pack(margin_bottom=10, color=ON_ACCENT, background_color=ACCENT, font_weight="bold"),
        on_press=lambda w: on_select(None),
    )

    top_items = [
        toga.Label("Gink", style=Pack(font_size=16, font_weight="bold", color=TEXT_MAIN, margin_bottom=10, background_color=BG_SIDEBAR)),
        new_session_btn,
    ]
    if on_open_tasks is not None:
        tasks_btn = toga.Button(
            "\u2705 Tasks & alarms",
            style=Pack(margin_bottom=10, color=TEXT_MAIN, background_color=BG_SIDEBAR),
            on_press=lambda w: on_open_tasks(),
        )
        top_items.append(tasks_btn)
    if on_open_media_studio is not None:
        media_studio_btn = toga.Button(
            "\U0001F3A8 Media Studio",
            style=Pack(margin_bottom=10, color=TEXT_MAIN, background_color=BG_SIDEBAR),
            on_press=lambda w: on_open_media_studio(),
        )
        top_items.append(media_studio_btn)
    if on_open_settings is not None:
        settings_btn = toga.Button(
            "\u2699 Settings",
            style=Pack(margin_bottom=10, color=TEXT_MAIN, background_color=BG_SIDEBAR),
            on_press=lambda w: on_open_settings(),
        )
        top_items.append(settings_btn)

    panel = toga.Box(
        style=Pack(direction=COLUMN, width=220, margin=10, background_color=BG_SIDEBAR),
        children=top_items + [toga.ScrollContainer(content=list_box, style=Pack(flex=1, background_color=BG_SIDEBAR))],
    )

    refresh()
    return panel, refresh