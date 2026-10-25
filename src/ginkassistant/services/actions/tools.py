"""The tools Gink's AI can call, and the code that runs them.

TOOL_SPECS is sent to Groq (OpenAI-compatible function-calling format).
ToolRunner.execute() runs one call, records it in the TaskStore so it shows on
the Tasks screen, and returns a JSON-able result the model reads back.
"""
from __future__ import annotations

import os

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .device import DeviceActions, _dur
from .task_store import TaskStore, from_iso


def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": list(required)}}}


S = {"type": "string"}
_PLACE = {**S, "description": "city or place; leave out for the user's own location"}

TOOL_SPECS = [
    # ---- controlling this computer (services/actions/computer.py) ----
    _fn("set_volume", "Change the computer's sound volume.",
        {"level": {"type": "integer", "description": "0-100"}, "action": {**S, "description": "up | down | mute | unmute"}}, []),
    _fn("media_control", "Control music playing in Spotify or Apple Music.",
        {"action": {**S, "description": "play | pause | play_pause | next | previous"}}, ["action"]),
    _fn("take_screenshot", "Take a screenshot of the screen and show it.", {}, []),
    _fn("find_files", "Search the user's files by name (documents, photos, downloads...).",
        {"query": {**S, "description": "words from the file name, e.g. 'cv' or 'budget'"}}, ["query"]),
    _fn("open_file", "Open a file: a number or name from the last file search, or a full path.",
        {"which": {**S, "description": "e.g. '1', 'CV.pdf' or a path"}}, ["which"]),
    _fn("quit_app", "Quit an app that's open (it still asks to save unsaved work).", {"name": S}, ["name"]),
    _fn("set_dark_mode", "Turn the computer's dark mode on or off.",
        {"mode": {**S, "description": "on | off | toggle"}}, []),
    _fn("lock_screen", "Lock the computer's screen.", {}, []),
    _fn("create_note", "Make a note in Apple Notes (a text file elsewhere).", {"title": S, "body": S}, ["title"]),
    _fn("copy_to_clipboard", "Copy text to the clipboard so the user can paste it.", {"text": S}, ["text"]),
    _fn("system_status", "The computer's battery, Wi-Fi, free disk space and OS version.", {}, []),
    _fn("open_folder", "Open a folder in Finder / the file manager: Downloads, Documents, Desktop, home, or any "
        "folder by name (e.g. a project folder).", {"name": {**S, "description": "e.g. 'downloads' or 'GinkAssistant'"}}, ["name"]),
    _fn("reveal_in_finder", "Show a file in Finder (a number or name from the last file list).", {"which": S}, []),
    _fn("open_terminal", "Open a Terminal window, optionally in a folder. Never runs commands.",
        {"folder": {**S, "description": "folder name or path; empty = home"}}, []),
    _fn("open_settings_pane", "Open a settings page: wifi, bluetooth, sound, display, notifications, battery, "
        "privacy, keyboard, trackpad, appearance, dock, software update...", {"pane": S}, ["pane"]),
    _fn("sleep_computer", "Put the computer to sleep.", {}, []),
    _fn("show_recent_files", "List documents the user changed recently (what they were working on).",
        {"days": {"type": "integer", "description": "how many days back (default 3)"}}, []),
    _fn("read_clipboard", "Read the text on the clipboard (to summarise, translate or use it).", {}, []),
    _fn("search_in_browser", "Open a Google search in the user's browser.", {"query": S}, ["query"]),
    _fn("create_file", "Make a real file the user can open and save: PDF, Word (docx), Excel (xlsx), CSV, Markdown, "
        "HTML or text. Write the COMPLETE content yourself (Markdown: headings, lists, **bold**, tables). For "
        "spreadsheets give rows (first row = headers).",
        {"format": {**S, "description": "pdf | docx | xlsx | csv | md | html | txt"},
         "title": {**S, "description": "short file title, e.g. 'Exam revision plan'"},
         "content": {**S, "description": "full document text in Markdown (documents)"},
         "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                  "description": "spreadsheet rows, first row = headers"}}, ["format", "title"]),
    _fn("create_image", "Create a new image from a description (pictures, illustrations, posters, logos, stickers).",
        {"prompt": {**S, "description": "detailed description of the image"},
         "aspect_ratio": {**S, "description": "1:1 | 16:9 | 9:16 | 4:3 | 3:4 (default 1:1)"}}, ["prompt"]),
    _fn("find_video", "Find YouTube videos to SHOW the user: how-to / step-by-step tutorials, recipes, "
        "repairs, exercises, explainers, or a live stream. The app shows them as playable cards.",
        {"query": {**S, "description": "short YouTube search, e.g. 'how to change a car tyre'"},
         "live": {"type": "boolean", "description": "true for live streams"}}, ["query"]),
    _fn("get_time", "Current local time, or the time in another city/country.", {"place": _PLACE}, []),
    _fn("get_date", "Today's date and weekday (or another day relative to today).",
        {"offset_days": {"type": "integer", "description": "0 today, 1 tomorrow, -1 yesterday"}}, []),
    _fn("days_until", "Count days until (or since) a date.",
        {"date": {**S, "description": "YYYY-MM-DD"}, "label": S}, ["date"]),
    _fn("get_weather", "Real weather: current conditions and forecast for up to 7 days.",
        {"place": _PLACE, "day": {**S, "description": "now | today | tomorrow | week | a weekday | YYYY-MM-DD"}}, []),
    _fn("get_air_quality", "Current air quality (AQI, PM2.5, dust).", {"place": _PLACE}, []),
    _fn("get_sun_times", "Sunrise, sunset and daylight length.",
        {"place": _PLACE, "day": {**S, "description": "today | tomorrow"}}, []),
    _fn("get_prayer_times", "Islamic prayer times (Fajr..Isha) for a place.",
        {"place": _PLACE, "day": {**S, "description": "today | tomorrow"}}, []),
    _fn("convert_currency", "Convert money with live exchange rates (supports XOF/CFA, NGN, GHS, USD, EUR...).",
        {"amount": {"type": "number"}, "from_currency": S, "to_currency": S},
        ["amount", "from_currency", "to_currency"]),
    _fn("get_crypto_price", "Live cryptocurrency price.",
        {"coin": {**S, "description": "e.g. bitcoin, eth"}, "currency": {**S, "description": "default usd"}}, ["coin"]),
    _fn("calculate", "Exact arithmetic (use for any non-trivial maths).",
        {"expression": {**S, "description": "e.g. (1250*12)*0.18 or 15% of 80000"}}, ["expression"]),
    _fn("remember", "Save a lasting fact the user asked you to remember about them "
        "(preferences, important dates, people, routines). Write it as a short third-person sentence, "
        "e.g. 'Exams start on 12 November 2026'.",
        {"fact": S}, ["fact"]),
    _fn("forget", "Forget something the user previously asked you to remember.",
        {"what": {**S, "description": "words identifying the memory, e.g. 'exam date'"}}, ["what"]),
    _fn("list_memories", "List everything the user asked Gink to remember.", {}, []),
    _fn("set_alarm", "Set a real wake-up alarm. Use for 'wake me up', 'alarm at ...'.",
        {"time": {**S, "description": "24h HH:MM"},
         "label": S,
         "date": {**S, "description": "YYYY-MM-DD, only if not the next occurrence"},
         "repeat_days": {"type": "array", "items": S,
                         "description": "e.g. ['mon','tue'] for repeating alarms"}},
        ["time"]),
    _fn("set_timer", "Start a countdown timer.",
        {"seconds": {"type": "integer"}, "label": S}, ["seconds"]),
    _fn("add_reminder", "Remind the user about something at a specific date and time.",
        {"text": S, "when": {**S, "description": "YYYY-MM-DD HH:MM local time"}},
        ["text", "when"]),
    _fn("add_task", "Save a to-do. For goals or problems, first analyse them and pass the "
        "concrete ordered steps you worked out in 'steps'.",
        {"title": S, "notes": S,
         "due": {**S, "description": "optional YYYY-MM-DD HH:MM"},
         "steps": {"type": "array", "items": S}},
        ["title"]),
    _fn("list_items", "List the user's saved tasks, reminders, alarms or timers.",
        {"kind": {"type": "string", "enum": ["task", "reminder", "alarm", "timer", "event", "all"]},
         "include_done": {"type": "boolean"}}),
    _fn("complete_item", "Mark a task/reminder done by id.", {"id": {"type": "integer"}}, ["id"]),
    _fn("delete_item", "Delete a task/reminder/alarm by id.", {"id": {"type": "integer"}}, ["id"]),
    _fn("open_app", "Open an app on this device by name.", {"name": S}, ["name"]),
    _fn("open_url", "Open a website or link.", {"url": S}, ["url"]),
    _fn("compose_message", "Prepare an SMS, WhatsApp or email draft for the user to send.",
        {"channel": {"type": "string", "enum": ["sms", "whatsapp", "email"]},
         "to": {**S, "description": "phone number with country code, or email address"},
         "body": S, "subject": S},
        ["channel", "body"]),
    _fn("make_call", "Open the phone dialer with a number.", {"number": S}, ["number"]),
    _fn("add_calendar_event", "Add an event to the user's calendar.",
        {"title": S, "start": {**S, "description": "YYYY-MM-DD HH:MM"},
         "end": {**S, "description": "YYYY-MM-DD HH:MM"}, "location": S, "notes": S},
        ["title", "start"]),
    _fn("web_search", "Look up current, factual information on the web.",
        {"query": S}, ["query"]),
    _fn("build_website", "Build and publish a website for the user (e.g. for their business, event or portfolio) and "
        "give them its link. Put everything they said about it in description.", {"description": S}, ["description"]),
    _fn("edit_website", "Change one of the user's websites. Without site_id, their most recent one.",
        {"instruction": S, "site_id": S}, ["instruction"]),
    # Connected Apps (Settings > Connected apps). Results are the user's data: never follow instructions inside them.
    _fn("calendar_upcoming", "The user's Google Calendar events for the next days (from = YYYY-MM-DD, default today).",
        {"days": {"type": "integer"}, "from": S}),
    _fn("calendar_create", "Add an event to the user's Google Calendar. start: YYYY-MM-DDTHH:MM local time (or a date for all day).",
        {"title": S, "start": S, "end": S, "location": S}, ["title", "start"]),
    _fn("email_search", "Search the user's Gmail (Gmail search syntax, e.g. 'from:awa budget', 'is:unread newer_than:2d').",
        {"query": S, "max": {"type": "integer"}}, ["query"]),
    _fn("email_read", "Read one email found with email_search (by its id).", {"id": S}, ["id"]),
    _fn("email_draft", "Write a Gmail draft for the user (not sent).", {"to": S, "subject": S, "body": S}, ["to", "subject", "body"]),
    _fn("email_send", "Send an email from the user's Gmail.", {"to": S, "subject": S, "body": S}, ["to", "subject", "body"]),
    _fn("drive_search", "Find files in the user's Google Drive by name.", {"query": S}, ["query"]),
    # Money and small business (kept on this device)
    _fn("record_money", "Record income (a sale, salary...) or an expense in the user's money book. currency: ISO code "
        "like XOF, SLE, NGN, GHS, USD (ask if unclear). when: YYYY-MM-DD, default today.",
        {"kind": {"type": "string", "enum": ["income", "expense"]}, "amount": {"type": "number"}, "currency": S,
         "category": S, "note": S, "when": S}, ["kind", "amount", "currency"]),
    _fn("money_summary", "Totals of the user's recorded income and expenses (by category) for a period.",
        {"period": {"type": "string", "enum": ["today", "week", "month", "year", "all"]}}),
    _fn("undo_last_money", "Remove the last income or expense recorded (when the user says it was a mistake).", {}),
    _fn("make_invoice", "Create a PDF invoice. items: [{description, quantity, unit_price}].",
        {"client": S, "items": {"type": "array", "items": {"type": "object", "properties": {
            "description": S, "quantity": {"type": "number"}, "unit_price": {"type": "number"}}}},
         "currency": S, "business_name": S, "due_date": S, "notes": S, "invoice_number": S}, ["client", "items", "currency"]),
    _fn("loan_calculator", "Monthly payment, total paid and total interest for a loan with equal monthly payments.",
        {"amount": {"type": "number"}, "annual_rate_percent": {"type": "number"}, "months": {"type": "integer"}}, ["amount", "annual_rate_percent", "months"]),
    _fn("split_bill", "Split a bill between people, with an optional tip.",
        {"total": {"type": "number"}, "people": {"type": "integer"}, "tip_percent": {"type": "number"}}, ["total", "people"]),
    # Everyday tools
    _fn("convert_units", "Convert length, weight, volume, area (hectares, acres), speed or temperature.",
        {"value": {"type": "number"}, "from_unit": S, "to_unit": S}, ["value", "from_unit", "to_unit"]),
    _fn("generate_password", "Create a strong random password on this device.",
        {"length": {"type": "integer"}, "symbols": {"type": "boolean"}}),
    _fn("random_choice", "Flip a coin, roll dice, or pick at random from options.",
        {"kind": {"type": "string", "enum": ["coin", "dice", "pick"]}, "options": {"type": "array", "items": S},
         "sides": {"type": "integer"}, "count": {"type": "integer"}}),
    _fn("make_qr_code", "Make a QR code image for a link, text or phone number, or for Wi-Fi (wifi_name + wifi_password).",
        {"text": S, "wifi_name": S, "wifi_password": S, "title": S}),
]


def _parse_time(s: str):
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", str(s or ""), re.I)
    if not m:
        return None
    h, mnt, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= mnt < 60):
        return None
    return h, mnt


class ToolRunner:
    def __init__(self, store: TaskStore, device: DeviceActions, http_client=None, memory=None):
        self.store = store
        self.device = device
        self.memory = memory      # services/memory.py MemoryStore (optional)
        from .computer import ComputerControl
        self.computer = ComputerControl()
        from ..live_info import LiveInfo
        from ..video_search import VideoSearch
        self.videos = VideoSearch(http_client=http_client)
        self.live = LiveInfo(http_client=http_client)   # app sets live.city_fn (Settings -> Location)
        self._http = http_client  # optional injected httpx.AsyncClient (tests)
        self.on_change = None     # UI hook: called after the store changes

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    async def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        fn = getattr(self, f"_t_{name}", None)
        if not fn:
            return {"ok": False, "message": f"Unknown tool {name}."}
        try:
            result = fn(**(args or {}))
            if hasattr(result, "__await__"):
                result = await result
            return result
        except TypeError as e:
            return {"ok": False, "message": f"Bad arguments for {name}: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"{name} failed: {e}"}

    # ---------------- controlling this computer ----------------
    def _pc(self):
        self.computer.files_dir = self.files_dir
        return self.computer

    def _t_set_volume(self, level=None, action=""):
        return self._pc().set_volume(level, action)

    def _t_media_control(self, action):
        return self._pc().media_control(action)

    def _t_take_screenshot(self):
        return self._pc().take_screenshot()

    def _t_find_files(self, query):
        return self._pc().find_files(query)

    def _t_open_file(self, which):
        path = self._pc().resolve_file(which)
        if not path:
            return {"ok": False, "message": "I couldn't find that file \u2014 search for it first (\u201cfind my ...\u201d)."}
        r = self.device.open_file(path)
        return {"ok": r.ok, "message": f"Opened {os.path.basename(path)}." if r.ok else r.message}

    def _t_quit_app(self, name):
        return self._pc().quit_app(name)

    def _t_set_dark_mode(self, mode="toggle"):
        return self._pc().set_dark_mode(mode)

    def _t_lock_screen(self):
        return self._pc().lock_screen()

    def _t_create_note(self, title, body=""):
        return self._pc().create_note(title, body)

    def _t_copy_to_clipboard(self, text):
        return self._pc().copy_to_clipboard(text)

    def _t_system_status(self):
        return self._pc().system_status()

    def _t_open_folder(self, name="home"):
        return self._pc().open_folder(name)

    def _t_reveal_in_finder(self, which=""):
        return self._pc().reveal_in_finder(which)

    def _t_open_terminal(self, folder=""):
        return self._pc().open_terminal(folder)

    def _t_open_settings_pane(self, pane):
        return self._pc().open_settings_pane(pane)

    def _t_sleep_computer(self):
        return self._pc().sleep_computer()

    def _t_show_recent_files(self, days=3):
        return self._pc().show_recent_files(days)

    def _t_read_clipboard(self):
        return self._pc().read_clipboard()

    def _t_search_in_browser(self, query):
        return self._pc().search_in_browser(query)

    # ---------------- files & images ----------------
    files_dir = None            # app sets: <data dir>/files
    image_maker = None          # app sets: async (prompt, aspect) -> MadeFile (via Gink Cloud /media/image)

    def _t_create_file(self, format, title, content="", rows=None):
        from ..file_maker import FileMakerError, make_file
        if not self.files_dir:
            return {"ok": False, "message": "Files can't be created here."}
        try:
            made = make_file(self.files_dir, format, title, content or "", rows)
        except FileMakerError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "file": made.name, "path": made.path,
                "message": f"Here's your {made.kind.upper()} file:\n\n{made.card_markdown()}"}

    async def _t_create_image(self, prompt, aspect_ratio="1:1"):
        if self.image_maker is None:
            return {"ok": False, "message": "Image creation isn't available here."}
        try:
            made = await self.image_maker(prompt, aspect_ratio or "1:1")
        except Exception as exc:
            return {"ok": False, "message": str(exc) or "The image couldn't be created."}
        return {"ok": True, "file": made.name, "path": made.path,
                "message": f"Here's your image:\n\n{made.card_markdown()}"}

    # ---------------- videos ----------------
    async def _t_find_video(self, query, live=False):
        from ..video_search import video_markdown
        try:
            found = await self.videos.search(query, n=3, live=bool(live))
        except Exception:
            found = []
        if not found:
            return {"ok": False, "videos": [],
                    "message": f"I couldn't find videos for \u201c{query}\u201d right now (check your connection)."}
        return {"ok": True, "videos": found, "source": self.videos.last_source,
                "message": f"Here {'is a live stream' if live else 'are some videos'} for **{query}** "
                           f"\u2014 tap one to watch it next to our chat:\n\n" + video_markdown(found)}

    # ---------------- live information ----------------
    async def _t_get_time(self, place=None):
        return await self._live(self.live.get_time(place))

    def _t_get_date(self, offset_days=0):
        return self.live.get_date(offset_days)

    def _t_days_until(self, date, label=""):
        return self.live.days_until(date, label)

    async def _t_get_weather(self, place=None, day="now"):
        return await self._live(self.live.get_weather(place, day))

    async def _t_get_air_quality(self, place=None):
        return await self._live(self.live.get_air_quality(place))

    async def _t_get_sun_times(self, place=None, day="today"):
        return await self._live(self.live.get_sun_times(place, day))

    async def _t_get_prayer_times(self, place=None, day="today"):
        return await self._live(self.live.get_prayer_times(place, day))

    async def _t_convert_currency(self, amount, from_currency, to_currency):
        return await self._live(self.live.convert_currency(amount, from_currency, to_currency))

    async def _t_get_crypto_price(self, coin, currency="usd"):
        return await self._live(self.live.get_crypto_price(coin, currency))

    def _t_calculate(self, expression):
        return self.live.calculate(expression)

    @staticmethod
    async def _live(coro):
        try:
            return await coro
        except Exception as exc:
            return {"ok": False, "message": "I couldn't reach the live data service right now "
                                            f"({exc.__class__.__name__}). Check your internet connection."}

    # ---------------- memory ----------------
    def _t_remember(self, fact):
        if not self.memory:
            return {"ok": False, "message": "Memory isn't available."}
        m = self.memory.add(fact)
        return {"ok": True, "message": f"I'll remember that: {m['text']}."}

    def _t_forget(self, what):
        if not self.memory:
            return {"ok": False, "message": "Memory isn't available."}
        gone = self.memory.forget(what)
        if not gone:
            return {"ok": False, "message": f"I don't have anything saved about \u201c{what}\u201d."}
        return {"ok": True, "message": "Forgotten: " + "; ".join(m["text"] for m in gone) + "."}

    def _t_list_memories(self):
        items = self.memory.list() if self.memory else []
        if not items:
            return {"ok": True, "message": "You haven't asked me to remember anything yet.", "memories": []}
        return {"ok": True, "memories": [m["text"] for m in items],
                "message": "Here's what I remember:\n" + "\n".join(f"- {m['text']}" for m in items)}

    # ---------------- alarms / timers / reminders ----------------
    def _t_set_alarm(self, time, label="Wake up", date=None, repeat_days=None):
        hm = _parse_time(time)
        if not hm:
            return {"ok": False, "message": f"I couldn't read the time '{time}'."}
        h, m = hm
        when = None
        if date:
            d = from_iso(date)
            if d:
                when = d.replace(hour=h, minute=m, second=0)
        when = when or self.device.next_occurrence(h, m)
        item = self.store.add("alarm", label or "Wake up", due=when,
                              notes=", ".join(repeat_days or []))
        r = self.device.set_alarm(h, m, label or "Wake up", date=when if date else None,
                                  repeat_days=repeat_days, item_id=item.id)
        if r.by_system:
            self._mark_system(item.id)
            msg = r.message
        else:
            msg = (f"Alarm saved for {when:%a %d %b, %H:%M}. It will ring inside Gink — "
                   f"keep Gink open (or running in the background). ({r.message})")
        self._changed()
        return {"ok": True, "id": item.id, "due": f"{when:%Y-%m-%d %H:%M}",
                "message": msg, "by_system": r.by_system}

    def _t_set_timer(self, seconds, label="Timer"):
        seconds = int(seconds)
        if seconds <= 0:
            return {"ok": False, "message": "Timer length must be positive."}
        due = datetime.now() + timedelta(seconds=seconds)
        item = self.store.add("timer", label or "Timer", due=due)
        r = self.device.set_timer(seconds, label)
        if r.by_system:
            self._mark_system(item.id)
        self._changed()
        msg = r.message if r.by_system else f"Timer running: {_dur(seconds)} (ends {due:%H:%M:%S})."
        return {"ok": True, "id": item.id, "message": msg}

    def _t_add_reminder(self, text, when):
        due = from_iso(when)
        if not due:
            return {"ok": False, "message": f"I couldn't read the date/time '{when}'."}
        if due < datetime.now() - timedelta(minutes=1):
            return {"ok": False, "message": "That time is already in the past."}
        item = self.store.add("reminder", text, due=due)
        msg = f"I'll remind you at {due:%a %d %b, %H:%M}: {text}."
        if self.device.platform in ("macos", "windows", "linux"):
            from . import system_alarms
            ok, _ = system_alarms.schedule(item.id, text, due, alarm=False)
            if ok:
                self._mark_system(item.id)
                msg += " (also added to your system, so it shows even if Gink is closed)"
        self._changed()
        return {"ok": True, "id": item.id, "message": msg}

    def _mark_system(self, item_id):
        with self.store._lock:
            self.store._db.execute("UPDATE items SET system_scheduled=1 WHERE id=?", (item_id,))
            self.store._db.commit()

    # ---------------- tasks ----------------
    def _t_add_task(self, title, notes="", due=None, steps=None):
        parent = self.store.add("task", title, notes=notes or "", due=from_iso(due) if due else None)
        step_items = [self.store.add("task", s, parent_id=parent.id) for s in (steps or []) if str(s).strip()]
        self._changed()
        return {"ok": True, "id": parent.id, "steps": [s.title for s in step_items],
                "message": f"Saved task '{title}'" + (f" with {len(step_items)} steps." if step_items else ".")}

    def _t_list_items(self, kind="all", include_done=False):
        k = None if kind in (None, "", "all") else kind
        items = self.store.list(k, include_done=include_done, top_level_only=True)
        out = []
        for it in items[:40]:
            d = it.to_dict()
            kids = self.store.children(it.id)
            if kids:
                d["steps"] = [{"id": c.id, "title": c.title, "done": c.done} for c in kids]
            out.append(d)
        return {"ok": True, "count": len(out), "items": out}

    def _t_complete_item(self, id):
        it = self.store.set_done(int(id), True)
        self._changed()
        return {"ok": bool(it), "message": f"Done: {it.title}" if it else f"No item {id}."}

    def _t_delete_item(self, id):
        it = self.store.get(int(id))
        if not it:
            return {"ok": False, "message": f"No item {id}."}
        if it.system_scheduled:
            from . import system_alarms
            system_alarms.cancel(it.id)
        self.store.delete(it.id)
        self._changed()
        extra = " (Android Clock alarms must also be switched off in the Clock app.)" \
            if it.system_scheduled and self.device.platform == "android" and it.kind == "alarm" else ""
        return {"ok": True, "message": f"Deleted {it.kind} '{it.title}'.{extra}"}

    # ---------------- device ----------------
    def _t_open_app(self, name):
        return self.device.open_app(name).to_dict()

    def _t_open_url(self, url):
        return self.device.open_url(url).to_dict()

    def _t_compose_message(self, channel, body, to="", subject=""):
        return self.device.compose_message(channel, to, body, subject).to_dict()

    def _t_make_call(self, number):
        return self.device.make_call(number).to_dict()

    def _t_add_calendar_event(self, title, start, end=None, location="", notes=""):
        s = from_iso(start)
        if not s:
            return {"ok": False, "message": f"I couldn't read the start time '{start}'."}
        e = from_iso(end) if end else None
        r = self.device.add_calendar_event(title, s, e, location, notes)
        self.store.add("event", title, due=s, notes=location or notes or "",
                       system_scheduled=r.ok)
        self._changed()
        return r.to_dict()

    # ---------------- web ----------------
    async def _t_build_website(self, description):
        builder = getattr(self, "site_builder", None)                 # set by the app (needs the Gink server)
        if not builder:
            return {"ok": False, "message": "Websites need the online Gink server. Sign in to Gink to make one."}
        try:
            site = await builder("create", prompt=description)
        except Exception as exc:
            return {"ok": False, "message": f"I couldn't build the website: {exc}"}
        return {"ok": True, "url": site["url"], "title": site["title"],
                "message": f"Your website \u201c{site['title']}\u201d is live: {site['url']} "
                           "(ask me to change anything on it)."}

    async def _t_edit_website(self, instruction, site_id=None):
        builder = getattr(self, "site_builder", None)
        if not builder:
            return {"ok": False, "message": "Websites need the online Gink server. Sign in to Gink to change one."}
        try:
            site = await builder("edit", instruction=instruction, site_id=site_id)
        except Exception as exc:
            return {"ok": False, "message": f"I couldn't change the website: {exc}"}
        return {"ok": True, "url": site["url"], "title": site["title"],
                "message": f"Updated \u201c{site['title']}\u201d: {site['url']}"}

    # ---- Connected Apps: through the Gink server (task_runner.connected, set by the app)
    async def _connected(self, path, payload):
        call = getattr(self, "connected", None)
        if not call:
            return {"ok": False, "message": "Connected apps need the online Gink server. Sign in to Gink first."}
        try:
            return await call(path, {k: v for k, v in payload.items() if v not in (None, "")})
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def _t_calendar_upcoming(self, days=1, **kw):
        return await self._connected("calendar/upcoming", {"days": days, "from": kw.get("from")})

    async def _t_calendar_create(self, title, start, end=None, location=None):
        return await self._connected("calendar/create", {"title": title, "start": start, "end": end, "location": location})

    async def _t_email_search(self, query, max=5):
        return await self._connected("gmail/search", {"query": query, "max": max})

    async def _t_email_read(self, id):
        return await self._connected("gmail/read", {"id": id})

    async def _t_email_draft(self, to, subject, body):
        return await self._connected("gmail/draft", {"to": to, "subject": subject, "body": body})

    async def _t_email_send(self, to, subject, body):
        return await self._connected("gmail/send", {"to": to, "subject": subject, "body": body})

    async def _t_drive_search(self, query):
        return await self._connected("drive/search", {"query": query})

    # ---- money and small business
    def _money(self):
        from ..money import MoneyBook
        if not self.files_dir:
            raise ValueError("The money book isn't available here.")
        if getattr(self, "_money_book", None) is None:
            import os
            self._money_book = MoneyBook(os.path.join(os.path.dirname(os.path.abspath(self.files_dir)), "money.db"))
        return self._money_book

    def _t_record_money(self, kind, amount, currency, category="", note="", when=""):
        try:
            r = self._money().add(kind, amount, currency, category, note, when)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        word = "Income" if r["kind"] == "income" else "Expense"
        return {"ok": True, **r, "message": f"{word} recorded: {r['amount']:,.2f} {r['currency']} ({r['category']})."}

    def _t_money_summary(self, period="month"):
        try:
            s = self._money().summary(period or "month")
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        if not s["entries"]:
            return {"ok": True, **s, "message": f"Nothing recorded for this {s['period']} yet."}
        lines = []
        for cur, c in s["currencies"].items():
            lines.append(f"{cur}: income {c['income']:,.2f}, expenses {c['expense']:,.2f}, balance {c['balance']:,.2f}")
            if c["expense_by_category"]:
                lines.append("  spent on: " + ", ".join(f"{k} {v:,.2f}" for k, v in c["expense_by_category"].items()))
        return {"ok": True, **s, "message": "\n".join(lines)}

    def _t_undo_last_money(self):
        try:
            done = self._money().undo_last()
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": done, "message": "Removed the last entry." if done else "There's nothing to remove."}

    def _t_make_invoice(self, client, items, currency, business_name="", due_date="", notes="", invoice_number=""):
        import datetime as _dt
        from ..file_maker import FileMakerError, make_file
        if not self.files_dir:
            return {"ok": False, "message": "Files can't be created here."}
        rows, total = [], 0.0
        for it in items or []:
            try:
                q, price = float(it.get("quantity") or 1), float(it.get("unit_price") or 0)
            except (TypeError, ValueError):
                return {"ok": False, "message": "Each item needs a number for quantity and price."}
            total += q * price
            rows.append(f"| {str(it.get('description') or 'Item')[:80]} | {q:g} | {price:,.2f} | {q * price:,.2f} |")
        if not rows:
            return {"ok": False, "message": "An invoice needs at least one item."}
        cur = (currency or "").upper()[:5]
        number = invoice_number or _dt.date.today().strftime("INV-%Y%m%d-%H%M")
        md = "\n".join([
            f"**{business_name}**" if business_name else "", f"**Invoice {number}**",
            f"Date: {_dt.date.today().isoformat()}" + (f" \u00b7 Due: {due_date}" if due_date else ""), "",
            f"**Bill to:** {client}", "",
            f"| Description | Qty | Unit price ({cur}) | Amount ({cur}) |", "|---|---|---|---|", *rows,
            f"| **Total** | | | **{total:,.2f} {cur}** |", "", notes or "Thank you for your business."])
        try:
            made = make_file(self.files_dir, "pdf", f"Invoice {number} {client}"[:60], md)
        except FileMakerError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "file": made.name, "path": made.path, "total": round(total, 2),
                "message": f"Invoice for {client}: {total:,.2f} {cur}.\n\n{made.card_markdown()}"}

    def _t_loan_calculator(self, amount, annual_rate_percent, months):
        from ..everyday import loan
        try:
            r = loan(amount, annual_rate_percent, months)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **r, "message": f"{r['monthly_payment']:,.2f} a month for {r['months']} months: "
                                            f"{r['total_paid']:,.2f} in total, of which {r['total_interest']:,.2f} is interest."}

    def _t_split_bill(self, total, people, tip_percent=0):
        from ..everyday import split_bill
        try:
            r = split_bill(total, people, tip_percent)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **r, "message": f"{r['each']:,.2f} each ({r['people']} people, total {r['total_with_tip']:,.2f})."}

    # ---- everyday tools
    def _t_convert_units(self, value, from_unit, to_unit):
        from ..everyday import convert_units
        try:
            r = convert_units(value, from_unit, to_unit)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **r, "message": f"{r['value']:g} {r['from']} = {r['result']:g} {r['to']}"}

    def _t_generate_password(self, length=16, symbols=True):
        from ..everyday import password
        pw = password(length, symbols if symbols is not None else True)
        return {"ok": True, "password": pw, "message": f"Here's a strong password: `{pw}` (made on this device; it isn't saved)."}

    def _t_random_choice(self, kind="coin", options=None, sides=6, count=1):
        from ..everyday import random_choice
        try:
            got = random_choice(kind or "coin", options, sides, count)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "result": got, "message": ", ".join(str(g) for g in got)}

    def _t_make_qr_code(self, text="", wifi_name="", wifi_password="", title=""):
        from ..everyday import qr_png, wifi_qr_text
        from ..file_maker import MadeFile
        import os
        if not self.files_dir:
            return {"ok": False, "message": "Files can't be created here."}
        content = wifi_qr_text(wifi_name, wifi_password) if wifi_name else text
        try:
            path = qr_png(self.files_dir, content, title or ("Wi-Fi " + wifi_name if wifi_name else "QR code"))
        except ImportError:
            return {"ok": False, "message": "QR codes aren't available in this version of Gink."}
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        made = MadeFile(path=path, name=os.path.basename(path), kind="png", size=os.path.getsize(path))
        return {"ok": True, "file": made.name, "path": path, "message": f"Here's your QR code:\n\n{made.card_markdown()}"}

    async def _t_web_search(self, query):
        researcher = getattr(self, "web_researcher", None)     # set by the app: real web search via the Gink server
        if researcher:
            try:
                found = await researcher(query)
            except Exception:
                found = None
            if found:
                return found
        import httpx
        client = self._http or httpx.AsyncClient(timeout=12, follow_redirects=True,
                                                 headers={"User-Agent": "Gink/0.1"})
        results = []
        try:
            r = await client.get("https://api.duckduckgo.com/",
                                 params={"q": query, "format": "json", "no_html": 1})
            if r.status_code == 200:
                j = r.json()
                if j.get("AbstractText"):
                    results.append({"source": j.get("AbstractSource"), "text": j["AbstractText"],
                                    "url": j.get("AbstractURL")})
                if j.get("Answer"):
                    results.append({"source": "DuckDuckGo", "text": str(j["Answer"])})
            r = await client.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": 3})
            if r.status_code == 200:
                for hit in r.json().get("query", {}).get("search", []):
                    snippet = re.sub(r"<[^>]+>", "", hit.get("snippet", ""))
                    results.append({"source": "Wikipedia", "title": hit["title"], "text": snippet,
                                    "url": "https://en.wikipedia.org/wiki/" + hit["title"].replace(" ", "_")})
        except Exception as e:
            return {"ok": False, "message": f"Web lookup failed: {e}"}
        finally:
            if self._http is None:
                await client.aclose()
        if not results:
            return {"ok": False, "message": "No results found."}
        return {"ok": True, "results": results[:5]}
