"""TaskAgent — Gink's 'do things' brain.

It sends the request to Groq with the tool list, runs whatever tools the model
asks for, feeds the real results back, and loops until the model gives a final
answer (up to MAX_ROUNDS). This is what lets Gink *analyse* a goal ("help me get
ready for my exam on Friday"), work out a plan, and actually save steps / set
reminders, instead of only talking about it.

0.1.159 -- a stronger, automatic agent: it writes a plan first (update_plan, shown live above the message box),
works through it with up to 30 rounds, and if it stops with steps of its plan still open it's told to carry on
(AUTO_CONTINUE times) instead of handing the work back. Apps, editors and text files are tools too (find, open,
close apps; open a project in an IDE; read, write and edit files, with a backup kept before every change).

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
MAX_ROUNDS = 30          # agent mode: long, real multi-step tasks (the server counts one message per 10 rounds)
AUTO_CONTINUE = 2        # times the agent is told to finish its own plan before it may stop

# ---- Agent mode: actions that need the user's OK before they run.
# Always: it leaves the device, or can't be undone. In a chain: fine when asked for directly
# ("lock my screen"), but asked about when Gink decides on it as part of a longer task.
ALWAYS_ASK = {"compose_message", "make_call", "delete_item", "forget"}
ASK_IN_CHAIN = {"lock_screen", "sleep_computer", "read_clipboard", "take_screenshot"}    # closing apps is automatic:
# an app still asks to save unsaved work, and file changes keep a backup, so they're undoable without asking first
PLAN_SPEC = {"type": "function", "function": {
    "name": "update_plan", "description": (
        "Write or update your plan for a task with several steps: every step, in order, each 'todo', 'doing' or "
        "'done'. Call it first for any multi-step task, then again as steps finish. The person sees it live."),
    "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "status": {"type": "string", "enum": ["todo", "doing", "done"]}},
        "required": ["title"]}}}, "required": ["steps"]}}}
# Connected Apps: writing to someone's calendar or email ALWAYS needs an OK on screen, whatever the
# "Ask before sensitive actions" setting; without a screen to ask on (voice), it isn't done.
MUST_ASK = {"calendar_create", "email_draft", "email_send"}


def describe(name: str, args: dict) -> str:
    """A short, plain description of one step ("Send a WhatsApp message to Awa")."""
    a = args or {}
    to = a.get("to") or a.get("contact") or a.get("name") or ""
    text = (a.get("body") or a.get("text") or a.get("message") or "").strip()
    if name == "compose_message":
        how = {"whatsapp": "a WhatsApp message", "sms": "a text message", "email": "an email"}.get(str(a.get("channel", "")).lower(), "a message")
        return f"Send {how}" + (f" to {to}" if to else "") + (f": \u201c{text[:80]}\u201d" if text else "")
    if name in ("email_send", "email_draft"):
        subject = (a.get("subject") or "").strip()
        return ("Send an email" if name == "email_send" else "Write an email draft") + (f" to {to}" if to else "") + \
               (f": \u201c{subject[:80]}\u201d" if subject else "")
    if name == "calendar_create":
        return f"Add \u201c{(a.get('title') or 'an event')[:80]}\u201d to your calendar" + (f" ({a.get('start')})" if a.get("start") else "")
    if name == "make_call":
        return "Call " + (to or "this number")
    if name == "delete_item":
        return "Delete an item from your Workspace" + (f" ({a.get('id')})" if a.get("id") else "")
    if name == "forget":
        return "Forget" + (f" \u201c{a.get('what')}\u201d" if a.get("what") else " a memory")
    if name == "quit_app":
        return "Close " + (a.get("name") or "an app")
    if name == "open_in_editor":
        return "Open " + (os.path.basename(str(a.get("path") or "").rstrip("/\\")) or "the editor") + \
            (f" in {a.get('editor')}" if a.get("editor") else " in your code editor")
    if name in ("write_text_file", "edit_text_file", "read_text_file"):
        what = os.path.basename(str(a.get("path") or a.get("which") or "a file")) or "a file"
        return {"write_text_file": ("Replace " if a.get("overwrite") else "Create ") + what,
                "edit_text_file": "Change " + what, "read_text_file": "Read " + what}[name]
    if name == "find_app":
        return "Find apps" + (f" like \u201c{a.get('query')}\u201d" if a.get("query") else "")
    if name == "running_apps":
        return "See which apps are open"
    if name == "update_plan":
        return "Plan the steps"
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
    r"recent files|recently|working on|google (?:it|for)|search google|"
    r"check (?:up )?(?:on )?(?:my |the |this )?(?:computer|laptop|mac|macbook|pc|device|phone|system|machine)|"
    r"health ?check|(?:do|run|make) a (?:quick |full )?(?:check|scan|diagnos\w*)|diagnos\w*|"
    r"(?:is|why is) (?:my |the |this )?(?:computer|laptop|mac|macbook|pc|phone|device|machine) (?:ok|okay|fine|healthy|slow|so slow|hot|lagging)|"
    r"speed (?:up|it up)|running slow|so slow|which device|what device|my specs|how much (?:ram|memory|storage))\b"
    # maths -> the exact calculator: "15% of 80000", "12 x 7", "1250*12" ('%' isn't a word
    # character, so it can't sit inside the \b(...)\b group above -- it never matched there)
    r"|\d\s*%|\b\d[\d,.]*\s*[x\u00d7*/+^]\s*\d"          # no "-": scores, dates and ranges use dashes
    # times and delays: "at 6:30", "at 5pm", "in 10 minutes", "tomorrow morning"
    r"|\bat \d{1,2}([:.]\d{2})?\s*(am|pm)?\b|\bin \d+\s*(sec|min|hour|hr)|\btomorrow\b|\btonight\b"
    # play a specific song, close or exit an app: "play Floating (...)", "can you play some Burna Boy", "close Safari"
    r"|^\s*(?:please\s+|can you\s+|could you\s+)?(?:play|close|exit)\b"
    r"|\bplay (?:the |a |some |my )?(?:song|track|album|playlist|music)\b|\b(?:close|exit) (?:the |this )?app\b",
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
    from .. import device_info
    from ..about_gink import about_gink
    return f"""You are Gink, a personal assistant that can take real actions on the user's {plat} device.{device_info.prompt_note()}{about_gink()}
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
- "Check my computer", "do a check", "why is it so slow", battery, storage or security questions: call device_check
  (updates=true if they mention updates), then explain what's fine and what needs attention in plain words, and offer
  what you can do about it (close the busiest app, open Storage settings...). Never ask which device or system they use.
- Apps, editors and files: find_app / running_apps see what's installed and open; open_app opens one, quit_app
  closes one. open_in_editor opens a file or project folder in an IDE (VS Code, PyCharm, Xcode...). read_text_file,
  write_text_file and edit_text_file read, create and change text or code files in the user's home folder (a backup
  is kept). To change code: find the file, read it, then edit_text_file with the exact text.
- Work like a capable assistant that finishes jobs: for anything with several steps, call update_plan FIRST with
  every step, then do the steps one after another with your tools, updating the plan as each is done. Don't stop
  half-way to ask "shall I continue?" -- carry on until the whole task is done. Only ask when an essential detail is
  missing or a step needs the user's OK.
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
            body["tools"] = [PLAN_SPEC] + [t for t in TOOL_SPECS if t["function"]["name"] not in off]
            body["tool_choice"] = "auto"
        client = self._http or httpx.AsyncClient(timeout=60)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if getattr(self, "_turn", None):
            headers["X-Gink-Turn"] = self._turn
            headers["X-Gink-Agent"] = "1"            # Gink Cloud: a long agent turn counts one message per 10 rounds
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
                  confirm: Optional[Callable[[str, dict, str], Awaitable[bool]]] = None,
                  ask_sensitive: bool = True,
                  on_plan: Optional[Callable[[list], Awaitable[None]]] = None) -> AgentReply:
        """on_step(index, label, state) drives the live checklist (state: running/done/failed/skipped);
        confirm(tool, args, description) -> bool asks the user before sensitive actions;
        on_plan([{"title", "status"}]) shows the agent's plan as it changes."""
        import uuid as _uuid
        self._turn = _uuid.uuid4().hex          # all AI rounds for this request are one request
        self._on_step, self._confirm, self._ask_sensitive, self._on_plan = on_step, confirm, ask_sensitive, on_plan
        self.plan = []
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
        nudges = 0
        try:
            for round_no in range(MAX_ROUNDS):
                msg = await self._chat(messages)
                calls = msg.get("tool_calls") or []
                if not calls:
                    left = [s["title"] for s in self.plan if s.get("status") != "done"]
                    if left and nudges < AUTO_CONTINUE and round_no < MAX_ROUNDS - 2:   # automatic: finish the plan
                        nudges += 1
                        messages.append({"role": "assistant", "content": msg.get("content") or ""})
                        messages.append({"role": "user", "content": (
                            "Keep going without waiting for me: these steps of your plan aren't done yet: " + "; ".join(left)
                            + ". Do them now with your tools (and update the plan). If one truly can't be done, mark it "
                              "done and say why in your final answer.")})
                        continue
                    return AgentReply(_with_held_back((msg.get("content") or "").strip() or _done_text(actions), actions), actions)
                messages.append({"role": "assistant", "content": msg.get("content") or "",
                                 "tool_calls": calls})
                for call in calls:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if name == "update_plan":                       # the plan: shown live, not a step of its own
                        self.plan = _clean_plan(args.get("steps"))
                        if getattr(self, "_on_plan", None):
                            try:
                                await self._on_plan([dict(s) for s in self.plan])
                            except Exception:
                                pass
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(
                            {"ok": True, "message": f"Plan saved ({len(self.plan)} steps). Now do the next step."})})
                        continue
                    if on_status:
                        await on_status(_status_text(name))
                    step, label = len(actions), describe(name, args)
                    in_chain = round_no > 0 or len(calls) > 1
                    must = name in MUST_ASK
                    if must and confirm is None:                       # nowhere to ask (voice): don't do it
                        result = {"ok": False, "skipped": True,
                                  "message": "This needs the user's OK on screen. Ask them to type the request in the chat."}
                        actions.append({"tool": name, "args": args, "result": result})
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
                        continue
                    if confirm is not None and (must or (getattr(self, "_ask_sensitive", True) and needs_ok(name, in_chain))):
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
            return AgentReply(_with_held_back((msg.get("content") or "").strip() or _done_text(actions), actions), actions)
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


def _clean_plan(steps) -> list:
    """update_plan's steps, tidied: at most 20, each {"title", "status"} with a known status."""
    out = []
    for s in (steps if isinstance(steps, list) else [])[:20]:
        if isinstance(s, str):
            s = {"title": s}
        if not isinstance(s, dict):
            continue
        title = " ".join(str(s.get("title") or "").split())[:140]
        if title:
            out.append({"title": title, "status": s.get("status") if s.get("status") in ("todo", "doing", "done") else "todo"})
    return out


def _with_held_back(text: str, actions) -> str:
    """Steps that needed an OK on screen and couldn't get one (voice) are ALWAYS reported, whatever
    the AI wrote -- so nobody believes an email was sent when it wasn't."""
    held = [describe(a["tool"], a["args"]) for a in actions
            if (a["result"] or {}).get("skipped") and "OK on screen" in (a["result"].get("message") or "")]
    if not held:
        return text
    return (text + "\n\n" if text else "") + "Not done: " + "; ".join(held) + \
        ". This needs your OK on screen \u2014 type the request in the chat to approve it."


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
        "web_search": "Searching the web…", "build_website": "Building your website…",
        "calendar_upcoming": "Checking your calendar…", "calendar_create": "Adding to your calendar…",
        "email_search": "Searching your email…", "email_read": "Reading the email…", "email_draft": "Writing the draft…",
        "email_send": "Sending the email…", "drive_search": "Searching your Drive…",
        "play_music": "Finding the song…",
        "record_money": "Recording it…", "money_summary": "Adding it up…", "make_invoice": "Making the invoice…",
        "loan_calculator": "Calculating…", "split_bill": "Splitting the bill…", "convert_units": "Converting…",
        "generate_password": "Making a password…", "random_choice": "Choosing…", "make_qr_code": "Making the QR code…",
        "edit_website": "Updating your website…", "open_app": "Opening the app…",
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
        "quit_app": "Closing the app…", "set_dark_mode": "Switching the appearance…", "lock_screen": "Locking the screen…",
        "find_app": "Looking for apps…", "running_apps": "Checking which apps are open…",
        "open_in_editor": "Opening the editor…", "read_text_file": "Reading the file…",
        "write_text_file": "Writing the file…", "edit_text_file": "Changing the file…", "update_plan": "Planning…",
        "create_note": "Making a note…", "copy_to_clipboard": "Copying…", "system_status": "Checking your computer…",
        "device_check": "Checking your device…",
        "open_folder": "Opening the folder…", "reveal_in_finder": "Showing it in Finder…", "open_terminal": "Opening Terminal…",
        "open_settings_pane": "Opening settings…", "sleep_computer": "Going to sleep…",
        "show_recent_files": "Looking at what you worked on…", "read_clipboard": "Reading your clipboard…",
        "search_in_browser": "Searching Google…",
        "complete_item": "Updating your Workspace…", "delete_item": "Updating your Workspace…",
    }.get(tool, "Working on it…")


def _summarise(name, result) -> str:
    if name == "device_check":
        from .health import format_report
        return format_report(result)
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
