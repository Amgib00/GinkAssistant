"""
GinkAssistant main screen.

Per explicit request, this no longer renders the chat feed with native
Toga widgets alone -- it uses real HTML/CSS/JS (ui/web_chat_view.py, a
toga.WebView) for the message area, since that's what actually gets
rounded message bubbles, a real shadow on code blocks, proper markdown
rendering, and a working syntax-highlighted Copy button -- none of which
toga.Pack can do (no border-radius/box-shadow/border-color support at
all, confirmed earlier in this project). The header, sidebar, and input
bar stay native Toga widgets -- they're plain layout and text entry,
with no real benefit from being HTML, and native controls are simpler
and more predictable for that than bridging a web <input>'s events back
to Python.

Also still true from earlier feedback:
  - Song recognition is ambient (services/audio_engine.py's loop +
    services/song_recognition.py's shazamio-based recognizer), not a
    button -- the assistant notices a playing song and brings it up
    itself, offering to say more or help find where to listen (not
    "download", which would mean facilitating copyrighted-audio
    downloads).
  - "News" (typed or spoken) opens Live TV *and* speaks a headline
    summary together, as one combined action, through the same
    resolve_reply() routing every message goes through -- not separate
    buttons.

Multi-session chat (ui/history_sidebar.py / services/history.py), skill
routing (services/skills.py) checked before Groq, streaming replies
(services/groq_worker.py -- on_token is now an async callback, awaited
per token so it can safely drive the WebView), and voice in/out
(services/voice_bridge.py) are all unchanged in how they work, just in
how the result reaches the screen.

Media Studio moved out of the header and into the sidebar (right below
"+ New chat") per request -- it reads as a persistent nav item next to
session management now, not a one-off header button. A "Log out" button
is new too, using ui/login_screen.py's clear_saved_session() -- nothing
in the app could actually log out before this existed.

The voice model picker and Voice Assistant toggle moved out of the
header too, next to Send/Mic now -- and they auto-hide the moment you
start typing a text message (query_input.on_change), reappearing once
the field's empty again, so the input row stays simple while you're
actually typing.

The generic native toga.ActivityIndicator + "Thinking..." status text
are gone from the typed-chat path -- ui/web_chat_view.py now shows a
small branded spinning logo mark inside the reply itself the moment
start_assistant_message() runs, cleared automatically the moment real
content arrives (first token, or a finalized skill reply). status_label
stays, since set_voice_status() still uses it for the voice loop's own
"Listening..."/"Speaking..." text, a different concern.

The Voice Assistant toggle is icon-only now (a plain circle that
changes color on/off, VOICE_ACTIVE_COLOR when listening) instead of a
text-label button that swapped between "Voice Assistant"/"Stop Voice
Chat" -- closer to how Claude's own input bar shows voice-mode state as
an icon rather than a label, per request to move the input row toward
that look. A disclaimer line sits below the input row the same way too.
Honest limit: native Toga buttons/inputs can't do a true smooth pill
shape, custom hover states, or a glowing/pulsing indicator the way real
CSS can -- this gets the icon-only layout closer, not a pixel match.

The separate one-shot mic_button (tap, speak one message, same as
typing) is gone -- having it sit right next to the Voice Assistant
toggle read as two redundant buttons for "voice" (reported directly,
with a screenshot). The continuous Voice Assistant toggle is the single
voice entry point now; voice_bridge.listen() itself wasn't removed,
since audio_engine.py's continuous loop still genuinely needs it.

A sidebar hide/show toggle (the arrow button left of the title) is new
-- add()/remove() on root_box, the same proven pattern used elsewhere
in this file, rather than an unconfirmed visibility API. history_sidebar.py
itself also changed: each session row now has a "..." button that
reveals/hides Delete, instead of Delete sitting permanently visible.

ui/settings_screen.py is new too, opened from a "Settings" entry in the
sidebar: AI model choice (now a real brain.preferred_model attribute
instead of a hardcoded string in groq_worker.py), the voice picker
(kept in sync with the input row's own selector -- changing it in
either place updates both), Launch at login (macOS-only, real
LaunchAgent implementation in services/launch_at_login.py), and About.
"""

import asyncio
import json
import os
import re
import uuid
import datetime
import itertools
from typing import Optional

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from ..services import skills, voice_bridge
from ..services.voice_bridge import VOICES
from ..services.audio_engine import GinkAudioEngine
from ..services.groq_worker import SPOKEN_REPLY_PROMPT, GroqBrain
from ..services import attachments as att_svc, briefing, prefs
from ..services.actions import looks_like_action
from ..services.paths import data_dir
from ..services import data_export
from ..services.api_client import ApiClient, ApiError
from ..services.sync import SyncService
from ..services.video_search import video_id_from_url, video_markdown, watch_url
from .pro_screen import build_pro_screen
from .settings_controller import SettingsController
from .viewer import Viewer
from ..services.news import fetch_world_news
from ..services.song_recognition import identify_ambient_song
from .home_actions import HomeActions
from .login_screen import clear_saved_session
from .media_studio_screen import build_media_studio_screen
from .settings_screen import _initial_model_choices
from .tasks_screen import TasksScreen, show_due_dialog
from .toga_live_tv import build_live_tv_view
from .web_chat_view import WebChatFeed

# Palette for the native chrome around the WebView (header/sidebar/input
# bar) -- kept in sync with ui/web_chat_view.py's CSS custom properties
# by eye, since one's Python/Pack and the other's an embedded stylesheet;
# there's no single source both read from.
from .theme import (
    ACCENT, BG_ELEVATED, BG_MAIN, BG_SURFACE, COLOR_PRIMARY, ON_ACCENT, TEXT_MAIN,
    TEXT_MUTED, VOICE_ACTIVE_COLOR,
)

NEWS_TRIGGERS = ("news", "what's going on", "whats going on", "what's happening", "whats happening")
SONG_FOLLOWUP_TRIGGERS = ("tell me more", "more about it", "find it", "where can i listen", "download it", "download")

_message_id_counter = itertools.count(1)


def _new_message_id() -> str:
    return f"msg-{next(_message_id_counter)}"


def build_main_screen(app: toga.App, email: str):
    brain = GroqBrain(app, session_id="default_session")
    agent_answers = {}            # agent mode: approval id -> future answered by Allow / Don't allow
    # Default voice, previously hardcoded with no way to change it anywhere
    # in the UI -- matches the original Settings screen's "Voice Synthesis
    # Profile" idea (never rebuilt here as a full Settings screen yet),
    # just surfaced directly since that's the one setting actually missing.
    selected_voice = {"value": next(iter(VOICES))}
    audio_engine = GinkAudioEngine(voice_key=selected_voice["value"])
    app.audio_engine = audio_engine
    audio_engine.stop_listening()
    current_session = {"id": brain.session_id}
    last_song = {"value": None}

    # Welcome screen: greeting + the composer as a centred bar (it glides
    # to the bottom on the first message -- see web_chat_view.py).
    user_name = (email or "").split("@")[0].split(".")[0].capitalize()
    # Sidebar footer name: "ibrahim.kargbo@x" -> "Ibrahim Kargbo"
    user_display_name = " ".join(
        part.capitalize() for part in (email or "").split("@")[0].replace("_", ".").split(".") if part and not part.isdigit()
    ) or "Gink user"
    # Gemini-style: one big friendly question; the composer's placeholder
    # cycles through examples ("Wake me up at 6:30", ...) instead of a
    # subtitle full of hints.
    WELCOME_SUB = ""

    def call_name() -> str:
        prof = getattr(app, "profile", None)
        return prof.call_name(user_name) if prof is not None else user_name

    def welcome_title() -> str:
        n = call_name()
        return f"Hi {n}, what\u2019s on your mind?" if n else "Hi, what\u2019s on your mind?"

    web_chat = WebChatFeed(welcome_title=welcome_title(), welcome_subtitle=WELCOME_SUB)

    # -- automatic history: smart titles + per-chat drafts -------------------
    import json as _json
    drafts_path = data_dir(app) / "drafts.json"

    def _drafts() -> dict:
        try:
            return _json.loads(drafts_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_draft(session_id: str, text: str):
        d = _drafts()
        text = (text or "")[:20000]
        if text.strip():
            d[session_id] = text
        else:
            d.pop(session_id, None)
        try:
            drafts_path.write_text(_json.dumps(d), encoding="utf-8")
        except OSError:
            pass

    async def maybe_auto_title(session_id: str, message: str, reply: str):
        """After the FIRST answer in a chat, give it a short title (2-6 words)
        -- only if it still has no name (a rename always wins)."""
        try:
            msgs = brain.history.get_all_sessions().get(session_id, {}).get("messages", [])
            if sum(1 for m in msgs if m.get("role") == "user") != 1:
                return
            if brain.history.get_meta().get(session_id, {}).get("title"):
                return
            title = await brain.generate_title(message, reply or "")
            if title and not brain.history.get_meta().get(session_id, {}).get("title"):
                brain.history.set_title(session_id, title)
                refresh_sidebar()
        except Exception:
            pass                                   # the first-line title simply stays

    async def load_session(session_id: str):
        await web_chat.clear()
        history = brain.history.get_history(session_id)
        if history:
            for turn in history:
                if turn.get("role") == "user":
                    await web_chat.add_user_message(turn.get("content", ""))
                else:
                    await web_chat.add_complete_assistant_message(_new_message_id(), turn.get("content", ""))
        else:
            await web_chat.show_welcome(welcome_title(), WELCOME_SUB)
        await web_chat.set_composer_text(_drafts().get(session_id, ""))     # unsent text comes back

    async def add_assistant_message(text: str, save: bool = True):
        await web_chat.add_complete_assistant_message(_new_message_id(), text)
        if save:
            brain.history.save_message(current_session["id"], "assistant", text)
        refresh_sidebar()

    # The input box is now an HTML "composer" card inside the chat page
    # (ui/web_chat_view.py), so the status line lives there too.
    def set_voice_status(s: str):
        asyncio.create_task(web_chat.set_status(s))

    def open_live_tv(channel=None):
        def back_to_main():
            app.main_window.content = root_box

        if viewer.is_open:
            viewer.close()
        app.main_window.content = build_live_tv_view(
            app, on_back=back_to_main, initial_channel=channel if isinstance(channel, str) else None)

    def open_pro(widget=None):
        def back_to_main():
            app.main_window.content = root_box

        if viewer.is_open:
            viewer.close()
        app.main_window.content = build_pro_screen(app, on_back=back_to_main)

    def open_genie(widget=None):
        """Gink Genie (multi-file projects) runs in the browser, signed in with the web app."""
        from .login_screen import _open_in_browser
        _open_in_browser(app, app.state.base_url.rstrip("/") + "/genie")

    def open_media_studio(widget=None):
        def back_to_main():
            app.main_window.content = root_box

        app.main_window.content = build_media_studio_screen(app, on_back=back_to_main)

    def open_tasks(widget=None):
        def back_to_main():
            app.main_window.content = root_box
            refresh_home()

        screen = TasksScreen(app, app.task_store, app.task_agent, on_back=back_to_main)
        app.main_window.content = screen.view

    def open_settings(widget=None, panel="general"):
        """The Settings window lives inside the chat page (ui/settings_page.py)."""
        asyncio.create_task(web_chat.open_settings(panel if isinstance(panel, str) else "general"))

    async def handle_news_and_tv() -> str:
        """World News and Live TV, together: open the live broadcast and
        speak a headline summary over it, rather than two separate
        buttons doing two separate things."""
        try:
            summary, _headlines = await fetch_world_news()
        except Exception as exc:
            summary = f"I couldn't reach the news service: {exc}"
        brain.history.save_message(current_session["id"], "user", "news")
        brain.history.save_message(current_session["id"], "assistant", summary)
        open_live_tv()
        await voice_bridge.speak(summary, voice_key=selected_voice["value"])
        return summary

    def song_followup_reply() -> Optional[str]:
        song = last_song["value"]
        if not song:
            return "I haven't noticed a song playing recently."
        title, artist = song.get("title", "that track"), song.get("artist", "")
        who = f" by {artist}" if artist else ""
        query = f"{title} {artist}".strip().replace(" ", "+")
        return f"That was **{title}**{who}. You can find it here: https://www.youtube.com/results?search_query={query}"

    BRIEFING_TRIGGER = re.compile(
        r"^(?:hey gink[, ]*)?(?:brief me|(?:my |the |daily |morning )?briefing|good morning(?: gink)?|"
        r"what'?s (?:on )?my day(?: look like)?|what do i have today|plan for today)[.!?]*$")

    pending_attachments = []

    LIVE_TV_TRIGGER = re.compile(
        r"^(?:play|watch|open|put on|show me|turn on)\s+(.+?)\s+(?:live|tv|channel|live stream|livestream)[.!?]*$|"
        r"^(?:open |show )?live tv[.!?]*$()")

    async def make_briefing():
        """Weather, today's plans, tasks, a headline -- and (if on) what you were working
        on: tasks in progress, recent chats, recently edited files, plus a personal
        opening line written by the AI."""
        p = prefs.load(app)
        chats, files, writer = None, None, None
        if p.get("briefing_projects", True):
            import time as _t
            meta = brain.history.get_meta()
            recent = []
            for sid, sess in brain.history.get_all_sessions().items():
                msgs = sess.get("messages", [])
                users = [m for m in msgs if m.get("role") == "user"]
                if not users or sid == current_session["id"]:
                    continue
                title = (meta.get(sid, {}).get("title") or _chat_title(msgs) or "").strip()
                if not title or "briefing" in title.lower():
                    continue
                ts = sess.get("timestamp") or ""
                recent.append((str(ts), sid, title))
            recent.sort(reverse=True)
            today = datetime.date.today()

            def when(ts):
                try:
                    d = datetime.datetime.fromisoformat(str(ts)[:19]).date()
                except Exception:
                    return "recently"
                return "earlier today" if d == today else "yesterday" if (today - d).days == 1 else f"{(today - d).days} days ago"
            chats = [{"id": sid, "title": title[:70], "when": when(ts)} for ts, sid, title in recent[:3]
                     if when(ts) in ("earlier today", "yesterday", "2 days ago", "3 days ago", "recently")]
            try:
                from ..services.actions.computer import MOBILE, recent_files
                if not MOBILE:
                    files = await asyncio.get_event_loop().run_in_executor(None, lambda: recent_files(days=2, limit=3))
            except Exception:
                files = None

            async def writer(facts: str) -> str:
                return await brain.quick_text(
                    "You write the opening line of someone's morning briefing: one or two warm, encouraging sentences "
                    "(max 40 words) that nudge them to continue or finish what they were working on, naming it. "
                    "Plain text, no lists, no quotes, no emoji. Address them by name if given.",
                    f"Name: {call_name() or 'unknown'}\n{facts}")
        return await briefing.build_briefing(app.task_store, p, call_name(), news_fn=fetch_world_news,
                                             chats=chats, files=files, writer=writer)

    async def resolve_reply(message: str) -> Optional[str]:
        """Shared routing for both typed and spoken input: news+TV first
        (it's a special combined action, not a plain text reply), then a
        song follow-up if one was recently announced, then the normal
        skill router, then Groq. Returns None when news+TV already
        handled everything itself (including speaking)."""
        lowered = message.lower().strip()

        if BRIEFING_TRIGGER.match(lowered):
            return "__BRIEFING__"

        m = LIVE_TV_TRIGGER.match(lowered)
        if m:
            open_live_tv(m.group(1))
            return None

        if any(trigger in lowered for trigger in NEWS_TRIGGERS):
            await handle_news_and_tv()
            return None

        if any(trigger in lowered for trigger in SONG_FOLLOWUP_TRIGGERS) and last_song["value"]:
            return song_followup_reply()

        # Real actions (alarms, reminders, timers, tasks, apps, messages,
        # calls, calendar, planning, live lookups) go to the TaskAgent
        # before the plain skill router -- it can actually DO them, and
        # it falls back to a normal answer when no action is needed.
        if looks_like_action(message):
            return "__ASK_AGENT__"

        skill_reply = await skills.try_skill(message)
        if skill_reply is not None:
            return skill_reply

        return "__ASK_BRAIN__"  # sentinel: caller should stream from GroqBrain instead

    async def step_media_for(actions) -> list:
        """Thumbnails for steps that produced something visible (chat_extras.py
        shows them at the right of the step): created images, made files,
        found videos. -> [(step label, [items])]"""
        from ..services.actions.agent import _status_text
        out = []
        for a in actions or []:
            tool, res = a.get("tool"), a.get("result") or {}
            if not res.get("ok"):
                continue
            items = []
            if tool == "create_image" and res.get("file"):
                try:
                    thumb = await asyncio.get_event_loop().run_in_executor(None, images.thumb_data_url, res["file"], 160)
                    items.append({"kind": "img", "src": thumb, "text": res["file"]})
                except Exception:
                    pass
            elif tool == "create_file" and res.get("file"):
                items.append({"kind": "file", "text": os.path.splitext(res["file"])[1].lstrip(".").upper() or "FILE",
                              "title": res["file"]})
            elif tool == "find_video":
                items += [{"kind": "img", "src": v.get("thumb", ""), "text": v.get("title", "")}
                          for v in (res.get("videos") or [])[:3] if v.get("thumb")]
            if items:
                out.append((_status_text(tool), items))
        return out

    async def run_agent(message: str, on_step=None, on_media=None) -> Optional[str]:
        """Runs the TaskAgent with this chat's recent history. Returns
        None if the agent couldn't do anything useful (e.g. no Groq key
        and the offline parser didn't understand the request), so the
        caller can fall back to the normal chat brain instead."""
        agent = app.task_agent
        agent.model = brain.preferred_model

        async def on_status(msg: str):
            if on_step is not None:
                await on_step(msg)              # under the spinner
            else:
                set_voice_status(msg)

        history = brain.get_history()
        if history and history[-1].get("role") == "user":
            history = history[:-1]                  # answer() already saved this message
        # Agent mode (typed chats): live checklist + approvals before sensitive steps.
        # Voice turns keep the old behaviour: the voice screen covers the panel.
        typed = on_step is not None
        asks_ok = typed and prefs.load(app).get("agent_confirm", True)

        async def agent_step(i, label, state):
            await web_chat._js(f"agentStep({int(i)}, {json.dumps(label)}, {json.dumps(state)})")

        async def agent_confirm(tool, args, label):
            ask_id = uuid.uuid4().hex[:12]
            fut = asyncio.get_running_loop().create_future()
            agent_answers[ask_id] = fut
            await web_chat._js(f"agentAsk({json.dumps(ask_id)}, {json.dumps(label)})")
            try:
                return bool(await asyncio.wait_for(fut, timeout=120))   # no answer in 2 minutes = no
            except asyncio.TimeoutError:
                return False
            finally:
                agent_answers.pop(ask_id, None)

        try:
            # typed chats can always ask (Connected Apps' writing actions always do); the
            # "Ask before sensitive actions" switch only controls the optional questions
            result = await agent.run(message, history=history, on_status=on_status,
                                     on_step=agent_step if typed else None,
                                     confirm=agent_confirm if typed else None, ask_sensitive=asks_ok)
        finally:
            if typed:
                await web_chat._js("agentEnd()")
        set_voice_status("")
        if on_media is not None:
            for label, items in await step_media_for(result.actions):
                await on_media(label, items)
        if not result.actions and not result.used_ai:
            return None
        text = result.text
        # videos the AI found -> playable cards under its written steps
        videos = [v for a in result.actions if a.get("tool") == "find_video"
                  for v in (a.get("result") or {}).get("videos", [])]
        fresh = [v for v in videos if v["id"] not in text]
        if fresh and result.used_ai:
            text = text.rstrip() + "\n\n" + video_markdown(fresh[:3])
        return text

    async def answer(message: str, route: str, spoken: bool = False, attachments=None, speech=None) -> str:
        """Shows the user's message and the reply in the feed, saving each
        turn exactly once. The user's message is saved the MOMENT it's sent
        (before any answer), so nothing is lost if the app closes mid-answer,
        and the chat appears in the sidebar straight away. brain.ask() is told
        not to save it again (save_user=False)."""
        attachments = attachments or []
        saved_message = att_svc.history_text(message, attachments)
        if attachments:
            await web_chat.add_user_message_with(message, [a.chip() for a in attachments])
        else:
            await web_chat.add_user_message(message)
        brain.history.save_message(current_session["id"], "user", saved_message)
        refresh_sidebar()

        # One reply row per answer, with a centred spinner whose label says what
        # Gink is really doing (chat_extras.py). Simple text replies skip it.
        msg_id = _new_message_id()
        if route == "__BRIEFING__":
            await web_chat.start_assistant_message(msg_id, "Preparing your briefing\u2026")
            md, spoken_text = await make_briefing()
            await web_chat.finalize_message(msg_id, md)
            brain.history.save_message(current_session["id"], "assistant", md)
            return spoken_text

        if route == "__ASK_AGENT__":
            await web_chat.start_assistant_message(msg_id, "Thinking\u2026")

            async def step(label: str):
                await web_chat.set_spin_label(msg_id, label)

            async def media(label: str, items: list):
                await web_chat.set_step_media(msg_id, label, items)
            # documents can feed an action ("turn this timetable into reminders")
            try:
                agent_reply = await run_agent(att_svc.build_prompt_text(message, attachments), on_step=step, on_media=media)
            except asyncio.CancelledError:
                await web_chat.finalize_message(msg_id, "*Stopped.*")
                brain.history.save_message(current_session["id"], "assistant", "*Stopped.*")
                raise
            if agent_reply is not None:
                await web_chat.finalize_message(msg_id, agent_reply)
                brain.history.save_message(current_session["id"], "assistant", agent_reply)
                refresh_home()
                return agent_reply
            route = "__ASK_BRAIN__"                 # same row carries on below
            started = True
        else:
            started = False

        if route != "__ASK_BRAIN__":
            await web_chat.add_complete_assistant_message(msg_id, route)
            brain.history.save_message(current_session["id"], "assistant", route)
            return route

        images = any(a.kind == "image" for a in attachments)
        label = ("Looking at your photo\u2026" if images else
                 "Reading your file\u2026" if attachments else "Thinking\u2026")
        if started:
            await web_chat.set_spin_label(msg_id, label)
        else:
            await web_chat.start_assistant_message(msg_id, label)

        # Live-rendered streaming: re-render the reply-so-far as formatted
        # text at most ~8 times a second (so **bold** never shows as
        # asterisks), with the spinner riding after the newest line.
        stream = {"text": "", "last": 0.0, "pending": False}
        loop = asyncio.get_event_loop()

        async def flush():
            stream["pending"] = False
            stream["last"] = loop.time()
            await web_chat.render_stream(msg_id, stream["text"])

        async def on_token(token: str):
            stream["text"] += token
            if speech is not None:
                speech(token)                  # voice conversation: speak each sentence as it arrives
            if loop.time() - stream["last"] >= 0.12:
                await flush()
            elif not stream["pending"]:
                stream["pending"] = True

                async def later():
                    await asyncio.sleep(0.12)
                    if stream["pending"]:
                        await flush()
                asyncio.create_task(later())

        try:
            reply = await brain.ask(message, on_token=on_token, system_prompt=SPOKEN_REPLY_PROMPT if spoken else None,
                                    attachments=attachments, save_user=False)
        except asyncio.CancelledError:
            # Stop ring: keep what was already written, mark it, and save the turn
            stream["pending"] = False
            partial = stream["text"].rstrip()
            shown = (partial + "\n\n" if partial else "") + "*Stopped.*"
            await web_chat.finalize_message(msg_id, shown)
            brain.history.save_message(current_session["id"], "assistant", shown)
            raise
        stream["pending"] = False
        await web_chat.finalize_message(msg_id, reply)
        return reply

    _sending = {"value": False}

    async def send_query(text: str):
        # Guards against a double-send -- reported as every user message
        # appearing twice in the feed. Nothing in this file's own
        # handler wiring double-binds on_press/on_confirm (checked), so
        # this is a defensive fix for whatever's actually double-firing
        # (possibly a platform-level double-dispatch of the button press)
        # rather than a located-and-patched root cause. Checked and set
        # synchronously, before any `await`, so it closes the gap even
        # if two calls land back to back in the same event-loop tick.
        if _sending["value"]:
            return
        message = text.strip()
        attachments = list(pending_attachments)
        if not message and not attachments:
            return
        _sending["value"] = True
        pending_attachments.clear()
        await web_chat.set_attachments([])
        await web_chat.set_busy(True)

        try:
            if attachments:
                has_photo = any(a.kind == "image" for a in attachments)
                route = ("__ASK_AGENT__" if message and not has_photo and looks_like_action(message)
                         else "__ASK_BRAIN__")
            else:
                route = await resolve_reply(message)
                if route is None:
                    return  # news+TV handled everything, including navigation

            save_draft(current_session["id"], "")              # sent -> no draft any more
            reply = await answer(message, route, attachments=attachments)
            asyncio.create_task(maybe_auto_title(current_session["id"], message, reply))
        except Exception as exc:
            reply = f"[error] {exc}"
            await add_assistant_message(reply, save=False)
        finally:
            _sending["value"] = False
            await web_chat.set_busy(False)
            refresh_sidebar()

        if reply:
            if prefs.load(app).get("read_aloud", True):
                await voice_bridge.speak(reply, voice_key=selected_voice["value"])


    # -- voice conversation screen (ui/voice_ui.py) -------------------------
    voice_session = {"active": False, "muted": False, "busy": False, "preview": None, "level_at": 0.0}

    def voice_ui(coro):
        if voice_session["active"]:
            asyncio.create_task(coro)

    def on_voice_status(text: str):
        set_voice_status(text if not voice_session["active"] else "")
        t = (text or "").lower()
        if t.startswith("listening"):
            voice_ui(web_chat.voice_state("muted" if voice_session["muted"] else "listening"))
        elif t.startswith("processing"):
            voice_ui(web_chat.voice_state("thinking"))
        elif t and not t.startswith(("speaking", "gink is ready")):
            voice_ui(web_chat.voice_state("error", text))          # e.g. "No microphone found"

    def on_speak_level(level: float):
        import time as _t
        now = _t.monotonic()
        if voice_session["active"] and now - voice_session["level_at"] > 0.08:
            voice_session["level_at"] = now
            asyncio.create_task(web_chat.voice_level(level))

    async def start_voice_session(voice_key: str):
        from ..services.voice_profiles import BY_KEY
        if voice_key in BY_KEY:
            selected_voice["value"] = voice_key
            audio_engine.voice_key = voice_key
            prefs.save(app, voice=voice_key)
        voice_bridge.stop_speaking()
        await take_mic()
        voice_session.update(active=True, muted=False, busy=False)
        audio_engine.start_listening()
        await web_chat.set_voice_on(True)
        await web_chat.voice_state("listening")

    def end_voice_session():
        voice_session.update(active=False, muted=False)
        asyncio.get_event_loop().call_later(1.0, resume_wake)
        audio_engine.stop_listening()
        voice_bridge.stop_speaking()
        asyncio.create_task(web_chat.set_voice_on(False))
        set_voice_status("")

    async def preview_voice(key: str):
        from ..services.voice_profiles import BY_KEY, sample_text
        if key not in BY_KEY:
            return
        old = voice_session.get("preview")
        if old is not None and not old.done():
            old.cancel()
        voice_bridge.stop_speaking()
        await asyncio.sleep(0.05)
        voice_session["preview"] = asyncio.create_task(voice_bridge.speak(sample_text(key), voice_key=key))

    async def handle_voice_turn(text: str):
        in_session = voice_session["active"]      # this turn belongs to the voice screen
        q = {"queue": None, "started": False, "waited": False}
        if in_session:
            voice_session["busy"] = True
            await web_chat.voice_caption(text, "")
            await web_chat.voice_state("thinking")
        try:
            route = await resolve_reply(text)
            if route is None:
                return  # news+TV handled everything, including navigation and speaking

            # Speak while the reply is still being written: each complete sentence
            # goes to a SpeechQueue (voice_bridge.py), which prepares the next
            # sentence while the current one plays. The mic is paused meanwhile.
            def on_level(level: float):
                if not q["started"] and voice_session["active"]:
                    q["started"] = True
                    asyncio.create_task(web_chat.voice_state("speaking"))
                on_speak_level(level)

            def speech(chunk: str):
                if not (voice_session["active"] or not voice_session["muted"]):
                    return
                if q["queue"] is None:
                    audio_engine.stop_listening()
                    q["queue"] = voice_bridge.SpeechQueue(selected_voice["value"], on_level)
                q["queue"].feed(chunk)

            try:
                reply = await answer(text, route, spoken=True, speech=speech)
                asyncio.create_task(maybe_auto_title(current_session["id"], text, reply))
            except Exception as exc:
                reply = f"[error] {exc}"
                await add_assistant_message(reply, save=False)

            refresh_sidebar()
            if reply and (voice_session["active"] or not voice_session["muted"]):
                if voice_session["active"]:
                    shown = voice_bridge._speakable(reply)
                    await web_chat.voice_caption(None, shown[:220] + ("\u2026" if len(shown) > 220 else ""))
                if q["queue"] is None:                      # not streamed (actions, briefing...): speak it all now
                    speech(reply)
                if q["queue"] is not None:
                    q["queue"].finish()
                    q["waited"] = True
                    await q["queue"].wait()
                if voice_session["active"] and not voice_session["muted"]:
                    audio_engine.start_listening()
        finally:
            voice_session["busy"] = False
            if q["queue"] is not None and not q["waited"]:      # stopped / ended mid-reply: always tidy up
                q["queue"].finish()
                asyncio.ensure_future(q["queue"].wait())
            # respect Mute, and End pressed while Gink was thinking or speaking
            if voice_session["muted"] or (in_session and not voice_session["active"]):
                audio_engine.stop_listening()
            elif not in_session and not audio_engine._is_listening and audio_engine.is_running:
                audio_engine.start_listening()             # classic voice mode resumes listening
            if voice_session["active"]:
                await web_chat.voice_state("muted" if voice_session["muted"] else "listening")

    async def on_song_detected(song: dict):
        last_song["value"] = song
        title, artist = song.get("title", "a song"), song.get("artist", "")
        who = f" by {artist}" if artist else ""
        message = (
            f"I'm hearing **{title}**{who} right now. Want to know more, "
            f"or should I find where to listen to it?"
        )
        await add_assistant_message(message)
        await audio_engine.speak(message, on_status=set_voice_status)

    # app.add_background_task is deprecated in newer Toga versions --
    # asyncio.create_task() is the direct replacement, and works fine
    # here since build_main_screen() only ever runs once Toga's own
    # event loop is already active (it's called from an async login
    # handler, or from startup() after the loop has started).
    asyncio.create_task(
        audio_engine.run_loop(handle_voice_turn, on_status=on_voice_status, on_song_detected=on_song_detected)
    )

    # ---- "a newer Gink is out" (services/updates.py): once a day, a little after start
    from ..services import updates as updates_svc, paths as paths_svc     # own names: no clash with names used above
    update_offer = {}
    update_state_path = str(paths_svc.data_dir(app) / "updates.json")

    async def check_for_update():
        await asyncio.sleep(8)
        try:
            offer = await updates_svc.check(app.state.base_url, getattr(app, "version", None) or "0.1.0", update_state_path)
        except Exception:
            offer = None
        if offer:
            update_offer.update(offer)
            await web_chat.show_update(offer["version"])
    asyncio.create_task(check_for_update())

    async def on_item_due(item):
        """A reminder/alarm/timer came due. Items handed to the OS
        (Android Clock, macOS Reminders, Windows Task Scheduler) already
        rang there -- this just notes it in the chat. Everything else
        rings here: chat line + spoken + a dialog."""
        icon = {"alarm": "\u23F0", "timer": "\u23F2", "reminder": "\U0001F514", "event": "\U0001F4C5"}.get(item.kind, "\u2705")
        text = f"{icon} **{item.title}**"
        await add_assistant_message(text)
        refresh_home()
        if not item.system_scheduled:
            await voice_bridge.speak(f"{item.kind.capitalize()}: {item.title}", voice_key=selected_voice["value"])
            await show_due_dialog(app.main_window, "Gink", f"{icon}  {item.title}")

    app.task_scheduler.on_due = on_item_due
    if not getattr(app, "_task_scheduler_started", False):
        app.task_scheduler.start()
        app._task_scheduler_started = True

    async def toggle_voice_assistant():
        """Composer's waveform button (shown when the box is empty): the
        same hands-free voice conversation the old \u25cf button started.
        The status orb glows while it's on."""
        if not audio_engine._is_listening:
            await take_mic()
            audio_engine.start_listening()
            await web_chat.set_voice_on(True)
            set_voice_status("Listening\u2026 just talk")
        else:
            audio_engine.stop_listening()
            await web_chat.set_voice_on(False)
            set_voice_status("")
            resume_wake()

    async def dictate():
        """Composer's mic button: listen once and put the words in the
        box, so you can check or edit them before sending."""
        await web_chat.set_dictating(True)
        set_voice_status("Listening\u2026")
        await take_mic()
        try:
            text = await voice_bridge.listen()
            if text:
                await web_chat.insert_text(text)
                set_voice_status("")
            else:
                set_voice_status("Didn't catch that \u2014 try again")
        except voice_bridge.VoiceUnavailable as exc:
            set_voice_status(str(exc))
        except Exception as exc:
            set_voice_status(f"Mic problem: {exc}")
        finally:
            resume_wake()
            await web_chat.set_dictating(False)

    async def identify_song():
        set_voice_status("Listening for a song\u2026")
        try:
            song = await identify_ambient_song()
        except Exception:
            song = None
        if song:
            await on_song_detected(song)
            set_voice_status("")
        else:
            set_voice_status("Couldn't recognise a song \u2014 try closer to the music")

    MODEL_LABELS = {
        "llama-3.3-70b-versatile": ("Llama 3.3 70B", "Smart"),
        "llama-3.1-8b-instant": ("Llama 3.1 8B", "Fast"),
        "openai/gpt-oss-120b": ("Gink Crystal", "Free \u00b7 GPT-OSS 120B"),
        "qwen/qwen3.8-27b": ("Gink Prism", "Free \u00b7 Qwen 3.8"),
        "gink-search": ("Gink Search", "Free \u00b7 searches the web"),
        "claude-sonnet-5-5": ("Gink Frost", "Pro \u00b7 Claude Sonnet"),
        "claude-opus-5-5": ("Gink Glacier", "Pro \u00b7 Claude Opus"),
        "claude-haiku-5-5": ("Gink Flurry", "Pro \u00b7 Claude Haiku"),
        "claude-fable-5-1": ("Gink Aurora", "Pro \u00b7 Claude Fable"),
        "openai/gpt-oss-20b": ("Gink Flake", "Free \u00b7 GPT-OSS 20B"),
        "qwen/qwen3-32b": ("Qwen3 32B", "Balanced"),
        "moonshotai/kimi-k2-instruct": ("Kimi K2", "Deep"),
        "meta-llama/llama-4-scout-17b-16e-instruct": ("Llama 4 Scout", "Fast"),
        "meta-llama/llama-4-maverick-17b-128e-instruct": ("Llama 4 Maverick", "Smart"),
    }

    def _model_entry(model_id: str) -> dict:
        name, tier = MODEL_LABELS.get(model_id, (model_id.split("/")[-1], ""))
        return {"id": model_id, "name": name, "tier": tier}

    def prompt_store():
        from ..services.prompts import PromptStore
        if getattr(app, "prompts", None) is None:
            app.prompts = PromptStore(os.path.join(str(app.paths.data), "prompts.json"))
        return app.prompts

    async def push_prompts():
        await web_chat.set_prompts(prompt_store().all())
    app.push_prompts = push_prompts                        # Settings calls it after changes

    async def sync_prompts(upload: bool = False):
        """Signed in: the account holds the list. upload=True after a change here; otherwise take the
        account's list (or, the first time, give it this device's prompts)."""
        from ..services.api_client import ApiClient
        token = getattr(app, "session_token", None)
        if not token:
            return
        api = ApiClient(app.state.base_url)
        try:
            if upload:
                await api.put_prompts(token, prompt_store().all())
                return
            remote = await asyncio.wait_for(api.get_prompts(token), timeout=10)
            if remote.get("updated"):
                prompt_store().replace_all(remote.get("prompts") or [])
            elif prompt_store().all():
                await api.put_prompts(token, prompt_store().all())
        except Exception:
            return                                         # offline: this device's list still works
        await push_prompts()
    app.sync_prompts = sync_prompts

    # ---- settings on every device: upload changes, take the account's settings now and every 2 minutes
    pref_sync = {"pending": {}, "task": None, "seen": 0.0, "loop": None}

    def _queue_pref_upload(changes: dict):
        pref_sync["pending"].update(changes)
        if pref_sync["task"] is None or pref_sync["task"].done():
            pref_sync["task"] = asyncio.ensure_future(_upload_prefs())

    async def _upload_prefs():
        from ..services.api_client import ApiClient
        await asyncio.sleep(1.0)                             # bundle quick successive changes
        token = getattr(app, "session_token", None)
        changes, pref_sync["pending"] = pref_sync["pending"], {}
        if token and changes:
            try:
                pref_sync["seen"] = (await ApiClient(app.state.base_url).put_preferences(token, changes)).get("updated", 0)
            except Exception:
                pref_sync["pending"] = {**changes, **pref_sync["pending"]}      # try again with the next change
    if _queue_pref_upload not in prefs.on_change:
        prefs.on_change[:] = [_queue_pref_upload]

    async def pull_prefs():
        from ..services.api_client import ApiClient
        token = getattr(app, "session_token", None)
        if not token:
            return
        try:
            remote = await asyncio.wait_for(ApiClient(app.state.base_url).get_preferences(token), timeout=10)
        except Exception:
            return
        if not remote.get("updated") or remote["updated"] <= pref_sync["seen"]:
            if not remote.get("updated") and prefs.synced(prefs.load(app)):           # first time: share this device's
                _queue_pref_upload({k: v for k, v in prefs.synced(prefs.load(app)).items() if v != prefs.DEFAULTS.get(k)})
            return
        pref_sync["seen"] = remote["updated"]
        theirs = dict(remote.get("prefs") or {})
        if "instructions" in theirs:                        # these live in the profile, not in prefs
            text = str(theirs.pop("instructions") or "")
            if text != str((app.profile.get() or {}).get("instructions") or ""):
                app.profile.update(instructions=text)
                await settings.push()
        remote = dict(remote, prefs=theirs)
        mine = prefs.load(app)
        from .settings_controller import CHOICES
        changed = {k: v for k, v in prefs.synced(remote.get("prefs") or {}).items() if mine.get(k) != v
                   and (k not in CHOICES or v in CHOICES[k]) and (k != "voice" or v in voice_bridge.VOICES)}
        if changed:
            prefs.save(app, _from_sync=True, **changed)
            if changed.get("model"):
                brain.preferred_model = changed["model"]
                await push_models_only()
            if changed.get("voice"):
                selected_voice["value"] = changed["voice"]
            await settings.apply_appearance()
            await settings.push()

    async def _pull_prefs_forever():
        while True:
            await pull_prefs()
            await asyncio.sleep(120)

    async def push_models_only():
        ids = _initial_model_choices()
        if brain.preferred_model not in ids:
            ids.insert(0, brain.preferred_model)
        await web_chat.set_models([_model_entry(m) for m in ids], brain.preferred_model)

    async def maybe_whats_new():
        """Once after an update: the changelog points since the version this device last ran."""
        from ..services import whats_new
        current = str(getattr(app, "version", "") or "")
        if not current or pref_sync.get("whats_new_done"):
            return
        pref_sync["whats_new_done"] = True
        existed = prefs._path(app).exists()
        last = prefs.load(app).get("last_version_seen", "")
        if last == current:
            return
        prefs.save(app, last_version_seen=current)
        if not last and not existed:
            return                                          # a fresh install: nothing was missed
        items = whats_new.since(whats_new.changelog_text(), last or "", current, limit=3 if last else 1)
        if items:
            await web_chat.show_whats_new(current, [[v, p] for v, p in items])

    async def push_models():
        await push_prompts()
        asyncio.ensure_future(maybe_whats_new())
        asyncio.create_task(sync_prompts())
        if pref_sync["loop"] is None:
            pref_sync["loop"] = asyncio.ensure_future(_pull_prefs_forever())
        ids = _initial_model_choices()
        if brain.preferred_model not in ids:
            ids.insert(0, brain.preferred_model)
        await web_chat.set_models([_model_entry(m) for m in ids], brain.preferred_model)

    async def handle_composer_event(event: dict):
        kind, value = event.get("type"), event.get("value")
        if kind == "send":
            await send_query(value or "")
        elif kind == "voice_toggle":
            await toggle_voice_assistant()
        elif kind == "draft":
            save_draft(current_session["id"], str(value or ""))
        elif kind == "voice_intro_seen":
            prefs.save(app, voice_intro_seen=True)
        elif kind == "voice_preview" and isinstance(value, dict):
            await preview_voice(value.get("key", ""))
        elif kind == "voice_preview_stop":
            voice_bridge.stop_speaking()
        elif kind == "voice_start":
            await start_voice_session((value or {}).get("voice", ""))
        elif kind == "voice_mute" and isinstance(value, dict):
            voice_session["muted"] = bool(value.get("muted"))
            if voice_session["muted"]:
                audio_engine.stop_listening()
            elif voice_session["active"] and not voice_session["busy"]:
                audio_engine.start_listening()
        elif kind == "voice_end":
            end_voice_session()
        elif kind == "dictate":
            await dictate()
        elif kind == "model" and value:
            brain.preferred_model = value
            prefs.save(app, model=value)                    # remembered, and on every device
            await push_models_only()
            set_voice_status(f"Now using {_model_entry(value)['name']}")
        elif kind == "attach_data" and isinstance(value, dict):
            await add_attachment(lambda: att_svc.load_data_url(value.get("data", ""), value.get("name", "file")))
        elif kind == "remove_attachment" and value is not None:
            idx = int(value)
            if 0 <= idx < len(pending_attachments):
                pending_attachments.pop(idx)
            await web_chat.set_attachments([a.chip() for a in pending_attachments])
        elif kind == "play_video" and isinstance(value, dict) and value.get("id"):
            viewer.show(watch_url(value["id"]), value.get("title") or "Video")
        elif kind == "open_url" and value:
            await open_link(str(value))
        elif kind == "agent_answer" and isinstance(value, dict):          # Allow / Don't allow
            fut = agent_answers.get(str(value.get("id")))
            if fut is not None and not fut.done():
                fut.set_result(bool(value.get("ok")))
        elif kind == "update_get" and update_offer.get("url"):
            await open_link(update_offer["url"])
            await web_chat.hide_update()
        elif kind == "update_later" and update_offer.get("version"):
            updates_svc.dismiss(update_state_path, update_offer["version"])
        elif kind == "setting" and isinstance(value, dict):
            await settings.on_setting(value.get("key"), value.get("value"))
        elif kind == "settings_action" and isinstance(value, dict):
            await settings.on_action(value.get("name"), value.get("value"))
        elif kind == "save_code" and isinstance(value, dict):
            code, name = str(value.get("code", "")), os.path.basename(str(value.get("name") or "gink-code.txt"))

            def write_code(dest):
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(code)
            saved = await data_export.save_with_dialog(app, name, [os.path.splitext(name)[1].lstrip(".") or "txt"], write_code)
            if saved:
                set_voice_status(f"Saved to {saved}")
        elif kind in ("file_open", "file_save", "file_thumb") and value:
            await file_action(kind.split("_")[1], str(value))
        elif kind == "feedback" and isinstance(value, dict):
            token = getattr(app, "session_token", None)
            if token:
                try:
                    await ApiClient(app.state.base_url).feedback(
                        token, value.get("rating", ""), value.get("reason", ""),
                        brain.preferred_model, int(value.get("chars") or 0))
                except Exception:
                    pass                         # feedback must never get in the way
        elif kind == "rename_session" and isinstance(value, dict) and value.get("id"):
            brain.history.set_title(value["id"], value.get("title", ""))
            refresh_sidebar()
        elif kind == "pin_session" and isinstance(value, dict) and value.get("id"):
            brain.history.set_pinned(value["id"], bool(value.get("pinned")))
            refresh_sidebar()
        elif kind == "archive_session" and isinstance(value, dict) and value.get("id"):
            brain.history.set_archived(value["id"], bool(value.get("archived", True)))
            if value.get("archived", True) and value["id"] == current_session["id"]:
                on_select_session(None)                # leave the chat you just archived (like New chat)
            refresh_sidebar()
        elif kind == "share_session" and value:
            await share_chat(str(value))
        elif kind == "export_session" and value:
            await export_chat(str(value))
        elif kind == "branch" and value is not None:
            branch_to_new_chat(int(value))
        elif kind == "read_aloud" and value:
            await voice_bridge.speak(value, voice_key=selected_voice["value"])
        elif kind == "new_chat":
            on_select_session(None)
        elif kind == "temporary":
            # only on the new-chat screen: the empty chat becomes temporary (or normal again)
            on_select_session(None, temporary=bool(value))
        elif kind == "select_session" and value:
            on_select_session(value)
        elif kind == "delete_session" and value:
            on_delete_session(value)
        elif kind == "open":
            {"settings": open_settings, "tasks": open_tasks, "media": open_media_studio,
             "livetv": open_live_tv, "pro": open_pro, "genie": open_genie}.get(value, lambda: None)()
        elif kind == "menu":
            if value == "tasks":
                open_tasks()
            elif value == "media":
                open_media_studio()
            elif value == "news":
                await send_query("What's the news today?")
            elif value == "song":
                await identify_song()
            elif value == "newchat":
                on_select_session(None)
            elif value == "attach":
                await pick_files()
            elif value == "briefing":
                await send_query("Morning briefing")

    async def add_attachment(loader):
        """Runs a file loader off the UI thread, then shows its chip."""
        if len(pending_attachments) >= 6:
            set_voice_status("You can attach up to 6 files at a time.")
            await web_chat.set_attachments([a.chip() for a in pending_attachments])
            return
        try:
            att = await asyncio.get_event_loop().run_in_executor(None, loader)
            pending_attachments.append(att)
            set_voice_status("")
        except att_svc.AttachmentError as exc:
            set_voice_status(str(exc))
        except Exception as exc:
            set_voice_status(f"Couldn't attach that file ({exc.__class__.__name__}).")
        await web_chat.set_attachments([a.chip() for a in pending_attachments])

    async def pick_files():
        exts = sorted(e.lstrip(".") for e in att_svc.IMAGE_EXT | att_svc.TEXT_EXT | {".pdf", ".docx"})
        paths = None
        try:
            paths = await app.main_window.dialog(toga.OpenFileDialog(
                "Attach photos or files", file_types=exts, multiple_select=True))
        except AttributeError:
            try:   # older Toga
                paths = await app.main_window.open_file_dialog(
                    "Attach photos or files", file_types=exts, multiple_select=True)
            except Exception:
                paths = None
        except NotImplementedError:
            set_voice_status("Picking files isn't supported on this device yet — on a computer you can "
                             "also paste or drag files into the message box.")
            return
        except Exception as exc:
            set_voice_status(f"Couldn't open the file picker ({exc.__class__.__name__}).")
            return
        if not paths:
            return
        if not isinstance(paths, (list, tuple)):
            paths = [paths]
        for path in paths:
            await add_attachment(lambda p=path: att_svc.load_path(p))

    async def run_auto_briefing():
        """Once a day at the briefing time (Settings), in its own new chat."""
        p = prefs.load(app)
        prefs.save(app, briefing_last_date=datetime.date.today().isoformat())
        on_select_session(None)
        await asyncio.sleep(0.6)
        md, spoken_text = await make_briefing()
        await web_chat.add_user_message("\u2600\ufe0f Morning briefing")
        brain.history.save_message(current_session["id"], "user", "\u2600\ufe0f Morning briefing")
        await web_chat.add_complete_assistant_message(_new_message_id(), md)
        brain.history.save_message(current_session["id"], "assistant", md)
        refresh_sidebar()
        if p.get("briefing_speak", True):
            await voice_bridge.speak(spoken_text, voice_key=selected_voice["value"])

    async def briefing_loop():
        await asyncio.sleep(5)
        while getattr(app, "_main_screen_token", None) is screen_token:
            try:
                if not _sending["value"] and briefing.is_due(prefs.load(app)):
                    await run_auto_briefing()
            except Exception:
                pass
            await asyncio.sleep(30)

    # -- sync across devices ---------------------------------------------
    old_sync = getattr(app, "_sync_service", None)
    if old_sync is not None:
        old_sync.stop()

    def on_sync_status(text: str):
        if text == "Synced":
            text = "Synced \u2713"
        asyncio.create_task(web_chat.set_sync_status(text))

    def on_remote_change(counts: dict):
        refresh_sidebar()
        refresh_home()
        if counts.get("chats") and not _sending["value"]:
            asyncio.create_task(load_session(current_session["id"]))

    sync_service = SyncService(
        data_dir(app) / "sync_state.json", base_url_fn=lambda: app.state.base_url,
        token_fn=lambda: getattr(app, "session_token", None), email=email,
        history=brain.history, items=app.task_store, memory=app.memory,
        on_status=on_sync_status, on_remote_change=on_remote_change,
    )
    app._sync_service = sync_service
    brain.history.on_change = sync_service.changed
    app.memory.on_change = sync_service.changed
    brain.memory_provider = app.memory.as_prompt

    # -- Gink Cloud: AI goes through YOUR server (no key in the app) --------
    # On for every real user (a release build has no GROQ_API_KEY). On your
    # Mac, .env has a key for development; GINK_CLOUD_AI=1 tests the real path.
    def connect_cloud_ai():
        token = getattr(app, "session_token", None)
        want = os.environ.get("GINK_CLOUD_AI", "").strip() == "1" or not os.environ.get("GROQ_API_KEY", "").strip()
        if want and token and brain.use_cloud(app.state.base_url, token):
            app.task_agent.api_key = token
            app.task_agent.base_url = app.state.base_url.rstrip("/") + "/ai/openai/v1/chat/completions"
            return True
        return False

    cloud_ai = connect_cloud_ai()
    # natural voices (Google Gemini TTS) come from your server, like the AI itself
    voice_bridge.cloud["base_url_fn"] = lambda: app.state.base_url
    voice_bridge.cloud["token_fn"] = lambda: getattr(app, "session_token", None)

    # -- files & images Gink makes (file_maker.py / image_service.py) -------
    files_dir = str(data_dir(app) / "files")
    from ..services.image_service import ImageService
    images = ImageService(files_dir, lambda: app.state.base_url, lambda: getattr(app, "session_token", None))
    app.image_service = images
    app.task_runner.files_dir = files_dir

    async def make_image(prompt, aspect):
        try:
            return await images.create(prompt, aspect)
        except ApiError as exc:
            raise RuntimeError(str(exc))
    app.task_runner.image_maker = make_image

    async def research(query):
        """web_search through the Gink server (real search + sources). None -> the tool's old lookup."""
        token = getattr(app, "session_token", None)
        if not token:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            r = await client.post(app.state.base_url.rstrip("/") + "/web/search", json={"query": query},
                                  headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            j = r.json()
            return {"ok": True, "answer": j.get("answer", ""), "sources": j.get("sources", [])}
        if r.status_code == 429:                                   # today's searches are used up: say so
            try:
                return {"ok": False, "message": r.json()["error"]["message"]}
            except Exception:
                return None
        return None
    app.task_runner.web_researcher = research

    async def site_builder(action, prompt="", instruction="", site_id=None):
        """Websites through the Gink server ("make me a website for...")."""
        from ..services.api_client import ApiClient
        token = getattr(app, "session_token", None)
        if not token:
            raise RuntimeError("sign in to Gink first")
        api = ApiClient(app.state.base_url)
        if action == "create":
            return await api.create_site(token, prompt)
        if not site_id:
            mine = await api.sites(token)
            if not mine:
                raise RuntimeError("you don't have a website yet \u2014 ask me to make one")
            site_id = mine[0]["id"]                     # the most recently changed
        return await api.edit_site(token, site_id, instruction)
    app.task_runner.site_builder = site_builder

    async def connected(path, payload):
        """Connected Apps actions through the Gink server (Settings > Connected apps)."""
        from ..services.api_client import ApiClient
        token = getattr(app, "session_token", None)
        if not token:
            raise RuntimeError("sign in to Gink first")
        if path == "calendar/create":
            try:
                from tzlocal import get_localzone_name
                payload.setdefault("timezone", get_localzone_name())
            except Exception:
                payload.setdefault("timezone", "UTC")
        return await ApiClient(app.state.base_url).connected_call(token, path, payload)
    app.task_runner.connected = connected

    def file_path(name: str) -> str:
        path = os.path.join(files_dir, os.path.basename(name or ""))
        return path if os.path.isfile(path) else ""

    def open_local_file(path: str) -> bool:
        """Open a file in its normal app (Preview, Word, Excel...)."""
        import subprocess, sys as _sys
        try:
            if _sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif _sys.platform.startswith("win"):
                os.startfile(path)                                  # noqa -- Windows only
            elif not getattr(_sys, "getandroidapilevel", None):
                subprocess.Popen(["xdg-open", path])
            else:
                return False
            return True
        except Exception:
            return False

    async def file_action(kind: str, name: str):
        path = file_path(name)
        if not path:
            set_voice_status("That file isn't on this device any more.")
            return
        if kind == "thumb":
            try:
                thumb = await asyncio.get_event_loop().run_in_executor(None, images.thumb_data_url, name)
                await web_chat.set_file_thumb(name, thumb)
            except Exception:
                pass
        elif kind == "open":
            if not open_local_file(path):
                await file_action("save", name)                     # phones: let the user save it somewhere
        elif kind == "save":
            import shutil
            saved = await data_export.save_with_dialog(app, os.path.basename(path), [os.path.splitext(path)[1].lstrip(".")],
                                                       lambda dest: shutil.copyfile(path, dest))
            if saved:
                set_voice_status(f"Saved to {saved}")

    app.gink_file_action = file_action          # Media Studio uses the same Open / Save as
    brain.city_fn = lambda: prefs.city(app)

    screen_token = object()
    app._main_screen_token = screen_token

    def clear_all_chats() -> int:
        sessions = brain.history.get_all_sessions()
        for sid in list(sessions):
            brain.history.clear_history(sid)
        on_select_session(None)
        refresh_sidebar()
        return len([1 for p in sessions.values() if p.get("messages")])

    async def brief_now():
        await web_chat._js("closeSettings()")
        await send_query("Morning briefing")

    # -- profile (Settings -> Account) + Instructions for Gink (Memory) ------
    from ..services.profile import ProfileStore
    from ..services.profile import profile_path
    app.profile = ProfileStore(profile_path(app, email))
    sync_service.profile = app.profile

    def push_user():
        prof = app.profile.get()
        shown = prof.get("full_name") or user_display_name
        asyncio.create_task(web_chat.set_user(shown, prof.get("photo", ""), app.profile.call_name(user_display_name)))

    def on_profile_change():
        push_user()
        sync_service.changed()
    app.profile.on_change = on_profile_change

    settings = SettingsController(
        app, web_chat, brain, selected_voice, audio_engine, email=email, display_name=user_display_name,
        models_fn=lambda: [_model_entry(m) for m in dict.fromkeys([brain.preferred_model] + _initial_model_choices())],
        # these three are defined further down -> looked up when used
        push_models=push_models, open_pro=open_pro, on_log_out=lambda: on_log_out(),
        refresh_sidebar=lambda: refresh_sidebar(), clear_all_chats=clear_all_chats, brief_now=brief_now,
        sync_fn=lambda: sync_service.sync_once(), open_url=lambda u: open_external(u),
    )
    settings.on_profile_change = push_user

    # -- "Hey Gink" wake word (services/wake_word.py + ui/wake_ui.py) ---------
    from ..services import wake_word
    from ..services.platform_utils import is_android as _is_android, is_mobile as _is_mobile
    wake = {"listener": None, "status": "Off", "busy": False, "downloading": False}
    _loop = asyncio.get_event_loop()

    def wake_status() -> str:
        if _is_mobile() and not _is_android():
            return "Not available on iPhone yet"
        if not prefs.load(app).get("wake_enabled"):
            return "Off"
        lst = wake["listener"]
        if lst is not None and lst.running and not wake["downloading"]:
            if lst.error:
                return f"Microphone problem: {lst.error}"
            heard = getattr(lst.engine, "last_heard", "")
            extra = f" \u00b7 woke {lst.detections}\u00d7" if lst.detections else ""
            extra += f" \u00b7 last heard \u201c{heard}\u201d" if heard else ""
            return f"Listening for \u201cHey Gink\u201d \u00b7 {lst.engine.name}{extra}"
        return wake["status"]

    def pause_wake():
        if wake["listener"] is not None:
            wake["listener"].pause()

    async def take_mic():
        """Before Gink uses the microphone: the wake listener must have really let go
        of it (two input streams at once = macOS AUHAL -10863 errors)."""
        lst = wake["listener"]
        if lst is not None:
            lst.pause()
            await asyncio.get_event_loop().run_in_executor(None, lambda: lst.pause(wait=True))
            await asyncio.sleep(0.05)                       # let CoreAudio settle

    def resume_wake():
        lst = wake["listener"]
        if lst is not None and not voice_session["active"] and not wake["busy"] and not audio_engine._is_listening:
            lst.resume()

    def on_wake_detected():                     # runs on the listener's thread
        _loop.call_soon_threadsafe(lambda: asyncio.ensure_future(wake_turn()))

    async def configure_wake():
        """Start / stop listening to match Settings (downloads the offline model once)."""
        lst = wake["listener"]
        if not prefs.load(app).get("wake_enabled") or (_is_mobile() and not _is_android()):
            if lst is not None:
                lst.stop()
                wake["listener"] = None
            await settings.push()
            return
        if lst is not None and lst.running:
            await settings.push()
            return
        if _is_android():                          # the phone's own recognizer (services/android_voice.py)
            from ..services.android_voice import AndroidWakeListener
            wake["listener"] = AndroidWakeListener(on_wake_detected, language=voice_bridge.listen_language[0])
            wake["listener"].start()
            await settings.push()
            return
        engine, reason = await _loop.run_in_executor(None, wake_word.best_engine, data_dir(app))
        if engine is None and "isn't downloaded" in reason and not wake["downloading"]:
            wake.update(downloading=True, status=f"Downloading the offline voice model ({wake_word.MODEL_MB} MB, once)\u2026")
            await settings.push()
            try:
                await wake_word.download_model(data_dir(app))
            except Exception as exc:
                wake.update(downloading=False,
                            status=f"Couldn't download the voice model ({exc.__class__.__name__}) \u2014 check your connection and switch it on again")
                await settings.push()
                return
            wake["downloading"] = False
            engine, reason = await _loop.run_in_executor(None, wake_word.best_engine, data_dir(app))
        if engine is None:
            wake["status"] = "Can\u2019t listen: " + reason
            await settings.push()
            return
        wake["listener"] = wake_word.WakeWordListener(engine, on_wake_detected)
        wake["listener"].start()
        await settings.push()

    def bring_to_front():
        try:
            app.main_window.show()
        except Exception:
            pass
        try:                                                    # macOS: actually come forward
            from rubicon.objc import ObjCClass
            ObjCClass("NSApplication").sharedApplication.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    def play_chime():
        import subprocess, sys as _sys
        try:
            if _sys.platform == "darwin" and os.path.exists("/System/Library/Sounds/Tink.aiff"):
                subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])
            elif _sys.platform.startswith("win"):
                import winsound
                winsound.MessageBeep()
        except Exception:
            pass

    async def wake_speak_turn(text: str):
        route = await resolve_reply(text)
        if route is None:
            return
        q = {"queue": None, "started": False}

        def on_level(level: float):
            if not q["started"]:
                q["started"] = True
                asyncio.create_task(web_chat.wake_glow("speaking"))

        def speech(chunk: str):
            if q["queue"] is None:
                q["queue"] = voice_bridge.SpeechQueue(selected_voice["value"], on_level)
            q["queue"].feed(chunk)
        try:
            reply = await answer(text, route, spoken=True, speech=speech)
            asyncio.create_task(maybe_auto_title(current_session["id"], text, reply))
            refresh_sidebar()
            if reply and q["queue"] is None:
                speech(reply)
        finally:
            if q["queue"] is not None:
                q["queue"].finish()
                await q["queue"].wait()

    async def wake_turn():
        """'Hey Gink' heard: glow, listen, answer out loud, then a short follow-up window."""
        if wake["busy"] or voice_session["active"] or _sending["value"]:
            resume_wake()
            return
        wake["busy"] = True
        p = prefs.load(app)
        try:
            if p.get("wake_front", True):
                bring_to_front()
            play_chime()
            await take_mic()
            await web_chat.wake_glow("listening")
            # "Hey Gink, what's the weather?" said in one go (Android): use the question straight away
            said = getattr(wake["listener"], "heard_after_wake", "") if wake["listener"] is not None else ""
            if wake["listener"] is not None:
                wake["listener"].heard_after_wake = ""
            for turn in range(5):
                text = said if (turn == 0 and said) else await voice_bridge.listen()
                if not text:
                    break
                await web_chat.wake_caption(text)
                await web_chat.wake_glow("thinking")
                await wake_speak_turn(text)
                if not p.get("wake_followup", True):
                    break
                await web_chat.wake_glow("listening")
        except Exception as exc:
            set_voice_status(f"Something went wrong ({exc.__class__.__name__}).")
        finally:
            await web_chat.wake_glow("off")
            wake["busy"] = False
            resume_wake()

    settings.on_wake_change = configure_wake
    settings.wake_status_fn = wake_status
    settings.wake_supported = not _is_mobile() or _is_android()
    app.wake = wake

    running = {"task": None}

    def stop_everything():
        """The green ring: stop the answer being written and the voice reading it."""
        voice_bridge.stop_speaking()
        task = running.get("task")
        if task is not None and not task.done():
            task.cancel()
        running["task"] = None

    def _on_speaking(on: bool):
        asyncio.create_task(web_chat.set_speaking(on))
        pause_wake() if on else resume_wake()
    voice_bridge.on_speaking = _on_speaking

    async def safe_handle(event: dict):
        """Any unexpected error from one action is reported in the status
        line instead of disappearing as a background-task traceback."""
        try:
            await handle_composer_event(event)
        except asyncio.CancelledError:
            set_voice_status("Stopped")         # Stop ring -- not an error
        except Exception as exc:
            import traceback
            traceback.print_exc()
            set_voice_status(f"Something went wrong ({exc.__class__.__name__}) \u2014 please try again.")
            if _sending["value"] and event.get("type") == "send":
                _sending["value"] = False
                await web_chat.set_busy(False)

    async def composer_loop():
        """Polls the composer a few times a second (Toga's WebView can't
        call Python directly). Stops when this screen is replaced, e.g.
        after logging out and back in."""
        await asyncio.sleep(0.6)            # let the page finish loading
        await settings.apply_appearance()
        await settings.push_page_prefs()            # keyboard prefs + voice list (ui/voice_ui.py)
        if prefs.load(app).get("wake_enabled"):
            asyncio.create_task(configure_wake())
        await push_models()
        refresh_home()
        push_user()
        refresh_sidebar()
        while getattr(app, "_main_screen_token", None) is screen_token:
            for event in await web_chat.poll():
                if event.get("type") == "stop":
                    stop_everything()
                    continue
                task = asyncio.create_task(safe_handle(event))
                if event.get("type") == "send":
                    running["task"] = task
            await asyncio.sleep(0.15)

    asyncio.create_task(composer_loop())
    asyncio.create_task(briefing_loop())
    if getattr(app, "session_token", None):
        asyncio.create_task(sync_service.run())
    else:
        asyncio.create_task(web_chat.set_sync_status("Sign in again to sync"))

    # -- Session sidebar --------------------------------------------------

    def on_select_session(session_id, temporary=False):
        leaving = current_session.get("id")
        if leaving and brain.history.is_temporary(leaving) and leaving != session_id:
            brain.history.forget_temporary(leaving)          # a temporary chat is gone once you leave it
        if session_id is None:
            session_id = brain.history.new_session_id(temporary=temporary)
        asyncio.create_task(web_chat.set_temporary(brain.history.is_temporary(session_id)))
        current_session["id"] = session_id
        brain.session_id = session_id
        asyncio.create_task(load_session(session_id))
        refresh_sidebar()

    def on_delete_session(session_id):
        brain.history.clear_history(session_id)
        if session_id == current_session["id"]:
            on_select_session(None)
        else:
            refresh_sidebar()

    def _chat_title(messages) -> str:
        for msg in messages:
            if msg.get("role") == "user":
                text = " ".join((msg.get("content") or "").split())
                return (text[:60] + "\u2026") if len(text) > 60 else (text or "New conversation")
        return "New conversation"

    async def open_link(url: str):
        low = url.lower()
        if low.startswith("gink://chat/"):                      # briefing: "Continue" a conversation
            sid = url[len("gink://chat/"):]
            if sid in brain.history.get_all_sessions():
                on_select_session(sid)
            return
        if low.startswith("gink://open/"):                      # briefing: "Open" a file you were editing
            from urllib.parse import unquote
            path = os.path.realpath(unquote(url[len("gink://open/"):]))
            home = os.path.realpath(os.path.expanduser("~"))
            if path.startswith(home + os.sep) and os.path.isfile(path):   # only your own files
                app.task_runner.device.open_file(path)
            else:
                set_voice_status("That file isn't available any more.")
            return
        if url.lower().startswith("gink://file/"):
            from urllib.parse import unquote
            await file_action("open", unquote(url[len("gink://file/"):]))
            return
        if url.lower().startswith("gink://pro"):
            open_pro()
            return
        """Link clicked in a reply: web pages open in the viewer beside the
        chat (so a guide can be followed step by step); mailto:, tel: and
        similar go to the right app."""
        if url.lower().startswith(("http://", "https://")) and viewer is not None:
            vid = video_id_from_url(url)
            viewer.show(watch_url(vid) if vid else url, "" if vid else url)
            return
        await open_external(url)

    async def open_external(url: str):
        """Default browser (desktop) or the matching app (phone), off the UI thread."""
        def _open():
            try:
                res = app.task_runner.device.open_url(url)
                if getattr(res, "ok", False):
                    return True
            except Exception:
                pass
            try:
                import webbrowser
                return webbrowser.open(url)
            except Exception:
                return False
        ok = await asyncio.get_event_loop().run_in_executor(None, _open)
        set_voice_status("" if ok else f"Couldn't open {url}")

    def branch_to_new_chat(user_index: int):
        """User message "\u22ef" -> Branch to new chat: copies this chat up to
        and including that message and Gink's reply to it into a new chat,
        then opens it -- so you can take the conversation another way
        without losing the original."""
        session = brain.history.get_all_sessions().get(current_session["id"], {})
        messages = session.get("messages", [])
        user_positions = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if not 0 <= user_index < len(user_positions):
            set_voice_status("Couldn't find that message to branch from")
            return
        later_users = [p for p in user_positions if p > user_positions[user_index]]
        cut = later_users[0] if later_users else len(messages)
        new_id = brain.history.new_session_id()
        for m in messages[:cut]:
            brain.history.save_message(new_id, m.get("role", "user"), m.get("content", ""))
        on_select_session(new_id)
        set_voice_status("Branched into a new chat")

    async def share_chat(session_id: str):
        """A public, read-only snapshot link of a chat (Settings > Privacy > Shared links)."""
        from ..services.api_client import ApiClient, ApiError
        token = getattr(app, "session_token", None)
        if not token:
            return await web_chat.show_share_link("", "Sign in to Gink to share chats.")
        session = brain.history.get_all_sessions().get(session_id, {})
        msgs = [{"role": m.get("role"), "content": m.get("content")} for m in session.get("messages", [])]
        title = brain.history.get_meta().get(session_id, {}).get("title") or _chat_title(session.get("messages", []))
        try:
            made = await ApiClient(app.state.base_url).share_chat(token, title, msgs)
        except ApiError as exc:
            return await web_chat.show_share_link("", str(exc))
        await web_chat.show_share_link(made["url"], made["title"])

    async def export_chat(session_id: str):
        session = brain.history.get_all_sessions().get(session_id, {})
        msgs = session.get("messages", [])
        if not msgs:
            set_voice_status("That chat is empty.")
            return
        title = brain.history.get_meta().get(session_id, {}).get("title") or _chat_title(msgs)
        text = data_export.chat_markdown(title, msgs)

        def write(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        path = await data_export.save_with_dialog(app, data_export.chat_filename(title), ["md", "txt"], write)
        if path:
            set_voice_status(f"Saved to {path}")

    def refresh_sidebar():
        """Sends the Recents list to the HTML sidebar (newest first)."""
        sessions = brain.history.get_all_sessions()
        rows = [
            (payload.get("timestamp") or datetime.datetime.min, sid, payload.get("messages", []))
            for sid, payload in sessions.items() if payload.get("messages")
        ]
        rows.sort(key=lambda r: r[0], reverse=True)
        meta = brain.history.get_meta()
        items = [{"id": sid, "title": (meta.get(sid, {}).get("title") or _chat_title(msgs)),
                  "pinned": meta.get(sid, {}).get("pinned", False), "current": sid == current_session["id"]}
                 for _ts, sid, msgs in rows
                 if not meta.get(sid, {}).get("archived") or sid == current_session["id"]]   # archived: not in Recents
        asyncio.create_task(web_chat.set_sessions(items))
    settings.on_history_changed = refresh_sidebar

    def on_log_out(widget=None):
        # Lives in Settings now (removed from the main screen header).
        audio_engine.stop_listening()
        if getattr(app, "wake", None) and app.wake.get("listener") is not None:
            app.wake["listener"].stop()
        app._main_screen_token = None          # stops this screen's composer loop
        sync_service.stop()
        app.session_token = None
        clear_saved_session(app)
        app.show_login()

    # -- Layout: the whole screen is the chat page now -- sidebar,
    # top bar, chat and composer are all HTML (ui/web_chat_view.py), so
    # the sidebar can slide out on hover and use the delete dialog.
    # HomeActions isn't shown as a strip any more -- its "Today" summary
    # appears as a small chip under the centred welcome bar instead.
    home = HomeActions(app.task_store, on_prompt=None, on_open_tasks=open_tasks, user_name=user_name)

    def refresh_home():
        home.refresh()
        has_items = not home.today.text.startswith("Nothing scheduled")
        asyncio.create_task(web_chat.set_today(home.today.text if has_items else ""))

    app.task_runner.on_change = refresh_home

    def on_store_change():
        sync_service.changed()
    app.task_store.on_change = on_store_change

    root_box = toga.Box(style=Pack(direction=ROW, flex=1, background_color=BG_SURFACE), children=[web_chat.web_view])
    viewer = Viewer(app, root_box, open_external=lambda u: asyncio.create_task(open_external(u)))

    return root_box