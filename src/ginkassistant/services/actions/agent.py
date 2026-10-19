"""TaskAgent — Gink's 'do things' brain.

It sends the request to Groq with the tool list, runs whatever tools the model
asks for, feeds the real results back, and loops until the model gives a final
answer (max 6 rounds). This is what lets Gink *analyse* a goal ("help me get
ready for my exam on Friday"), work out a plan, and actually save steps / set
reminders, instead of only talking about it.

Talks to Groq's OpenAI-compatible REST endpoint with plain httpx — no groq SDK,
so this path carries no pydantic dependency (good news for Android builds).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, List, Optional

from . import quick_parse
from .platform_info import current_platform
from .tools import TOOL_SPECS, ToolRunner

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GinkLimit(Exception):
    """Gink Cloud said no (daily limit, Pro-only feature...): show the message, don't fall back."""
DEFAULT_MODEL = "openai/gpt-oss-120b"     # llama-3.3-70b-versatile was retired by Groq on 16 Aug 2026
MAX_ROUNDS = 12          # agent mode: enough for real multi-step tasks

# ---- Agent mode: actions that need the user's OK before they run.
# Always: it leaves the device, or can't be undone. In a chain: fine when asked for directly
# ("lock my screen"), but asked about when Gink decides on it as part of a longer task.
ALWAYS_ASK = {"compose_message", "make_call", "delete_item", "forget"}
ASK_IN_CHAIN = {"quit_app", "lock_screen", "sleep_computer", "read_clipboard", "take_screenshot"}


def describe(name: str, args: dict) -> str:
    """A short, plain description of one step ("Send a WhatsApp message to Awa")."""
    a = args or {}
    to = a.get("to") or a.get("contact") or a.get("name") or ""
    text = (a.get("body") or a.get("text") or a.get("message") or "").strip()
    if name == "compose_message":
        how = {"whatsapp": "a WhatsApp message", "sms": "a text message", "email": "an email"}.get(str(a.get("channel", "")).lower(), "a message")
        return f"Send {how}" + (f" to {to}" if to else "") + (f": \u201c{text[:80]}\u201d" if text else "")
    if name == "make_call":
        return "Call " + (to or "this number")
    if name == "delete_item":
        return "Delete an item from your Workspace" + (f" ({a.get('id')})" if a.get("id") else "")
    if name == "forget":
        return "Forget" + (f" \u201c{a.get('what')}\u201d" if a.get("what") else " a memory")
    if name == "quit_app":
        return "Quit " + (a.get("name") or "an app")
    if name in ("lock_screen", "sleep_computer"):
        return {"lock_screen": "Lock the screen", "sleep_computer": "Put the computer to sleep"}[name]
    if name == "read_clipboard":
        return "Read what you copied (your clipboard)"
    if name == "take_screenshot":
        return "Take a screenshot of your screen"
    return _status_text(name).rstrip("\u2026.").strip()


def needs_ok(name: str, in_chain: bool) -> bool:
    return name in ALWAYS_ASK or (in_chain and name in ASK_IN_CHAIN)

_ACTION_WORDS = re.compile(
    r"\b(wake me|wake up|alarm|timer|count ?down|remind|reminder|remember to|don'?t (let me )?forget|"
    r"schedule|calendar|meeting|appointment|book|"
    r"to-?do|tasks?|my list|open|launch|start the|call|dial|ring|text|sms|whatsapp|email|e-mail|message|"
    r"plan|organi[sz]e|break (it|this) down|help me (get|prepare|finish|plan|organi[sz]e|study)|"
    r"search|look up|find out|latest|news about|"
    r"remember (?:that|my|this)|forget|what do you (?:remember|know) about me|"
    r"weather|forecast|temperature|rain|umbrella|hot|cold|humid|wind|sunrise|sunset|air quality|aqi|pollution|dust|"
    r"what time|the time|time in|time zone|what day|date|days? (?:until|till|left|since)|how long until|"
    r"prayer|salat|fajr|dhuhr|asr|maghrib|isha|"
    r"exchange rate|convert|how much is|in cfa|to cfa|xof|fcfa|naira|cedis?|dollars?|euros?|"
    r"price of|bitcoin|btc|ethereum|crypto|calculate|percent|%|"
    r"video|videos|youtube|tutorial|step[- ]by[- ]step|show me how|teach me|how (?:do|can|should) i|how to|"
    r"recipe|guide me|walk me through|live stream|livestream|"
    r"pdf|word document|docx|excel|spreadsheet|csv|make (?:a|me a|it) (?:file|document)|"
    r"create (?:an? )?(?:image|picture|poster|logo|drawing|illustration)|draw|generate (?:an? )?(?:image|picture)|"
    r"picture of|image of|"
    r"volume|louder|quieter|mute|unmute|next song|previous song|skip (?:this )?song|pause (?:the )?music|"
    r"play (?:some )?music|resume (?:the )?music|screenshot|screen shot|find (?:my )?files?|find my|open (?:number|file)|"
    r"quit|dark mode|light mode|lock (?:my |the )?(?:screen|computer|mac)|make a note|take a note|note that|"
    r"copy (?:this|that|it)|clipboard|battery|disk space|storage left|wi-?fi|system status|"
    r"finder|terminal|folder|downloads|desktop|documents|settings|preferences|go to sleep|sleep the|"
    r"recent files|recently|working on|google (?:it|for)|search google)\b"
    # maths -> the exact calculator: "15% of 80000", "12 x 7", "1250*12" ('%' isn't a word
    # character, so it can't sit inside the \b(...)\b group above -- it never matched there)
    r"|\d\s*%|\b\d[\d,.]*\s*[x\u00d7*/+^]\s*\d"          # no "-": scores, dates and ranges use dashes
    # times and delays: "at 6:30", "at 5pm", "in 10 minutes", "tomorrow morning"
    r"|\bat \d{1,2}([:.]\d{2})?\s*(am|pm)?\b|\bin \d+\s*(sec|min|hour|hr)|\btomorrow\b|\btonight\b",
    re.I)


def looks_like_action(text: str) -> bool:
    """Cheap pre-check so normal chit-chat keeps your existing fast streaming path."""
    return bool(_ACTION_WORDS.search(text or ""))


@dataclass
class AgentReply:
    text: str
    actions: List[dict] = field(default_factory=list)  # [{tool, args, result}]
    used_ai: bool = True


LIVE_TOOLS = ("find_video", "get_time", "get_date", "days_until", "get_weather", "get_air_quality", "get_sun_times",
              "get_prayer_times", "convert_currency", "get_crypto_price", "calculate")


def _system_prompt(city: str = "") -> str:
    now = datetime.now().astimezone()
    plat = current_platform()
    notes = {
        "android": "Alarms/timers go into the phone's own Clock app and ring even if Gink is closed.",
        "ios": "iOS doesn't allow apps to set Clock alarms; Gink's alarms ring only while Gink is open.",
    }.get(plat, "Alarms and reminders are added to the computer's own scheduler so they fire even if Gink is closed.")
    return f"""You are Gink, a personal assistant that can take real actions on the user's {plat} device.
Current local date/time: {now:%A %Y-%m-%d %H:%M} (UTC{now:%z}).
User's location: {city or "unknown (the live tools fall back to an approximate location)"}.
{notes}

How to work:
- If the user asks you to DO something (alarm, timer, reminder, task, open an app, message, call, calendar), call the matching tool. Convert times to 24h HH:MM and dates to YYYY-MM-DD HH:MM in local time.
- If the user describes a goal or problem, analyse it first: identify what actually needs doing, the order, and realistic timing. Then save it with add_task including concrete 'steps', and add reminders for steps with deadlines. Give a short explanation of your reasoning.
- For anything live -- time anywhere, dates and countdowns, weather/forecast/rain, air quality, sunrise/sunset,
  prayer times, exchange rates, crypto prices -- ALWAYS call the matching tool; never guess numbers. Use calculate for
  exact maths. Answer practical questions from the data (e.g. "umbrella tomorrow?" -> check tomorrow's rain chance).
- You can control THIS computer: open apps, folders in Finder (incl. project folders by name), Terminal in a
  folder, settings pages, volume, music (Spotify / Apple Music), screenshots, finding / opening / revealing files,
  recent files, quitting apps, dark mode, locking or sleeping, Apple Notes, the clipboard, Google searches and
  system status (battery, Wi-Fi, disk). For "summarise / translate what I copied", call read_clipboard first. Use those tools when asked; never claim you did something a tool didn't confirm.
- When the user wants a FILE (PDF, Word, Excel, CSV...), call create_file with the COMPLETE content (don't
  summarise; write the whole document). For "make this a PDF" use the content from the conversation.
  The app shows a file card with Open / Save as, so don't paste the content again in your reply.
- When the user wants a new IMAGE (picture, illustration, poster, logo, sticker), call create_image with a
  rich, specific description. Don't promise images you can't make (real people's likeness, logos you don't own).
- For "how do I / how to / show me / teach me" requests: write clear, numbered steps yourself (with warnings
  where safety matters), AND call find_video with a short search so the user can watch along. The app shows
  the videos as cards under your answer, so don't paste video links into your text.
- For other factual or current questions, use web_search and base your answer on the results; say if results are thin.
- Only say something is done if the tool result has ok=true. If a tool fails, say what went wrong and offer the next best option.
- Messages and calls are drafts: tell the user they need to tap send/call.
- If an essential detail is missing (e.g. who to message), ask one short question instead of guessing.
- If the user tells you something lasting about themselves and asks you to remember it, call remember. If they ask you to forget something, call forget.
- Keep replies short and friendly."""


class TaskAgent:
    def __init__(self, runner: ToolRunner, api_key: Optional[str] = None,
                 model: Optional[str] = None, http_client=None):
        self.runner = runner
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self._http = http_client
        self.base_url = GROQ_URL          # Gink Cloud: <server>/ai/openai/v1/chat/completions
        self._turn = None

    async def _chat(self, messages, use_tools=True):
        import httpx
        body = {"model": self.model, "messages": messages, "temperature": 0.3}
        if use_tools:
            off = getattr(self.runner, "disabled_tools", set())
            body["tools"] = [t for t in TOOL_SPECS if t["function"]["name"] not in off]
            body["tool_choice"] = "auto"
        client = self._http or httpx.AsyncClient(timeout=45)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if getattr(self, "_turn", None):
            headers["X-Gink-Turn"] = self._turn
        try:
            r = await client.post(self.base_url, json=body, headers=headers)
        finally:
            if self._http is None:
                await client.aclose()
        if r.status_code in (403, 429, 503):
            try:
                info = r.json().get("error", {})
            except ValueError:
                info = {}
            if info.get("code") in ("daily_limit", "pro_required", "turn_limit", "not_configured"):
                extra = "\n\n[\u2728 Upgrade to Gink Pro](gink://pro)" if info["code"] in ("daily_limit", "pro_required") else ""
                raise GinkLimit(info.get("message", "") + extra)
        if r.status_code != 200:
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]

    async def run(self, user_text: str, history: Optional[list] = None,
                  on_status: Optional[Callable[[str], Awaitable[None]]] = None,
                  on_step: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
                  confirm: Optional[Callable[[str, dict, str], Awaitable[bool]]] = None) -> AgentReply:
        """on_step(index, label, state) drives the live checklist (state: running/done/failed/skipped);
        confirm(tool, args, description) -> bool asks the user before sensitive actions."""
        import uuid as _uuid
        self._turn = _uuid.uuid4().hex          # all AI rounds for this request count as ONE message
        self._on_step, self._confirm = on_step, confirm
        try:
            return await self._run(user_text, history, on_status)
        except GinkLimit as limit:
            return AgentReply(str(limit), [], used_ai=True)

    async def _run(self, user_text: str, history: Optional[list] = None,
                   on_status: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentReply:
        # 1) Instant offline path for simple, unambiguous commands.
        quick = quick_parse.parse(user_text)
        if quick and (not self.api_key or quick[0] in ("set_timer", "set_alarm", "open_app", "make_call", "remember", "forget",
                                      "list_memories") + LIVE_TOOLS + ("set_volume", "media_control", "take_screenshot", "find_files", "open_file", "set_dark_mode", "lock_screen", "system_status", "quit_app", "create_note",
                                         "open_folder", "reveal_in_finder", "open_terminal", "open_settings_pane", "sleep_computer",
                                         "show_recent_files", "read_clipboard", "search_in_browser")):
            name, args = quick
            result = await self.runner.execute(name, args)
            return AgentReply(_summarise(name, result), [{"tool": name, "args": args, "result": result}],
                              used_ai=False)
        if not self.api_key:
            return AgentReply("I can handle simple commands offline (alarms, timers, reminders, "
                              "opening apps). For planning and anything more complex I need a "
                              "GROQ_API_KEY set.", used_ai=False)

        # 2) Full tool-calling loop.
        memory_note = ""
        if getattr(self.runner, "memory", None) is not None:
            memory_note = self.runner.memory.as_prompt()
        city = ""
        try:
            city = self.runner.live.city_fn() or ""
        except Exception:
            pass
        if not getattr(self.runner, "use_memory", True):
            memory_note = ""
        lang = getattr(self.runner, "reply_language_note", lambda: "")()
        lang = getattr(self.runner, "profile_note", lambda: "")() + lang
        messages = [{"role": "system", "content": _system_prompt(city) + memory_note + lang}]
        for m in (history or [])[-10:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_text})
        actions = []
        on_step, confirm = getattr(self, "_on_step", None), getattr(self, "_confirm", None)
        try:
            for round_no in range(MAX_ROUNDS):
                msg = await self._chat(messages)
                calls = msg.get("tool_calls") or []
                if not calls:
                    return AgentReply((msg.get("content") or "").strip() or _done_text(actions), actions)
                messages.append({"role": "assistant", "content": msg.get("content") or "",
                                 "tool_calls": calls})
                for call in calls:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if on_status:
                        await on_status(_status_text(name))
                    step, label = len(actions), describe(name, args)
                    in_chain = round_no > 0 or len(calls) > 1
                    if confirm is not None and needs_ok(name, in_chain):
                        if on_step:
                            await on_step(step, label, "asking")
                        try:
                            allowed = await confirm(name, args, label)
                        except Exception:
                            allowed = False
                        if not allowed:
                            result = {"ok": False, "skipped": True,
                                      "message": "The user didn't allow this step, so it was not done."}
                            actions.append({"tool": name, "args": args, "result": result})
                            if on_step:
                                await on_step(step, label, "skipped")
                            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
                            continue
                    if on_step:
                        await on_step(step, label, "running")
                    result = await self.runner.execute(name, args)
                    actions.append({"tool": name, "args": args, "result": result})
                    if on_step:
                        await on_step(step, label, "done" if (result or {}).get("ok", True) else "failed")
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps(result, default=str)[:6000]})
            msg = await self._chat(messages, use_tools=False)
            return AgentReply((msg.get("content") or "").strip() or _done_text(actions), actions)
        except GinkLimit:
            raise                          # a limit message must reach the user, not a fallback
        except Exception as e:
            # Network/model failure: fall back to the offline parser if it understood the request.
            if quick and not actions:
                name, args = quick
                result = await self.runner.execute(name, args)
                return AgentReply(_summarise(name, result),
                                  [{"tool": name, "args": args, "result": result}], used_ai=False)
            done = "; ".join(a["result"].get("message", a["tool"]) for a in actions if a["result"].get("ok"))
            return AgentReply(f"I hit a problem reaching the AI ({e})."
                              + (f" Already done: {done}." if done else ""), actions)


def _done_text(actions) -> str:
    """When the AI gives no final words: say what actually happened."""
    done = [a["result"].get("message") or describe(a["tool"], a["args"]) for a in actions
            if (a["result"] or {}).get("ok", True) and not a["result"].get("skipped")]
    skipped = [describe(a["tool"], a["args"]) for a in actions if (a["result"] or {}).get("skipped")]
    parts = (["Done: " + "; ".join(done) + "."] if done else []) + (["Not done (you didn\u2019t allow it): " + "; ".join(skipped) + "."] if skipped else [])
    return " ".join(parts) or "Done."


def _status_text(tool):
    return {
        "set_alarm": "Setting your alarm…", "set_timer": "Starting the timer…",
        "add_reminder": "Saving the reminder…", "add_task": "Saving your plan…",
        "web_search": "Searching the web…", "open_app": "Opening the app…",
        "compose_message": "Preparing the message…", "add_calendar_event": "Adding to calendar…",
        "get_weather": "Checking the weather…", "get_air_quality": "Checking the air quality…",
        "get_time": "Checking the time…", "get_date": "Checking the date…", "days_until": "Counting the days…",
        "get_sun_times": "Looking up sunrise and sunset…", "get_prayer_times": "Looking up prayer times…",
        "convert_currency": "Getting today’s exchange rate…", "get_crypto_price": "Checking the price…",
        "calculate": "Calculating…", "find_video": "Finding videos…", "open_url": "Opening the page…",
        "make_call": "Preparing the call…", "remember": "Saving to memory…", "forget": "Updating my memory…",
        "list_memories": "Checking what I remember…", "list_items": "Checking your Workspace…",
        "create_file": "Making your file…", "create_image": "Creating your image…",
        "set_volume": "Changing the volume…", "media_control": "Controlling your music…",
        "take_screenshot": "Taking a screenshot…", "find_files": "Searching your files…", "open_file": "Opening the file…",
        "quit_app": "Quitting the app…", "set_dark_mode": "Switching the appearance…", "lock_screen": "Locking the screen…",
        "create_note": "Making a note…", "copy_to_clipboard": "Copying…", "system_status": "Checking your computer…",
        "open_folder": "Opening the folder…", "reveal_in_finder": "Showing it in Finder…", "open_terminal": "Opening Terminal…",
        "open_settings_pane": "Opening settings…", "sleep_computer": "Going to sleep…",
        "show_recent_files": "Looking at what you worked on…", "read_clipboard": "Reading your clipboard…",
        "search_in_browser": "Searching Google…",
        "complete_item": "Updating your Workspace…", "delete_item": "Updating your Workspace…",
    }.get(tool, "Working on it…")


def _summarise(name, result) -> str:
    if name == "list_items" and result.get("ok"):
        items = result.get("items", [])
        if not items:
            return "Nothing saved yet."
        lines = []
        for it in items:
            when = f" — {it['due'][:16]}" if it.get("due") else ""
            lines.append(f"- **{it['title']}**{when} _(#{it['id']}, {it['kind']})_")
            for st in it.get("steps", []):
                lines.append(f"    - {'~~' if st['done'] else ''}{st['title']}{'~~' if st['done'] else ''}")
        return "\n".join(lines)
    return result.get("message") or ("Done." if result.get("ok") else "That didn't work.")
