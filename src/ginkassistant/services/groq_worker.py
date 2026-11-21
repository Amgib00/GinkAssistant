"""
GinkAssistant's "brain" -- talks to Groq directly from the client, same
as the real LLMWorker (confirmed via __main__.py: the FastAPI backend has
no /chat route at all, so this was never meant to go through it).

Rebuilt to use services/history.py's HistoryStore (a clean, correct
reimplementation -- see that file's docstring) instead of trying to
import the original core/history.py, and to drop the GinkProfileManager
dependency entirely: two different user_profile.json shapes turned up
during the review and neither was fully trustworthy, so this uses one
clear, hardcoded system prompt instead of carrying that fragility
forward.

Per later feedback that it should actually feel like talking to someone,
not a scripted bot: the old hardcoded "Gink online. What would you like
to work on?" greeting for "hi"/"hello" is gone -- even a plain greeting
now goes to the real model, so it comes back different each time instead
of the exact same canned line forever. That trades a little latency on
trivial greetings for genuinely sounding alive, which given the ask
seems like the right trade. The system prompts below carry the actual
personality; everything else (streaming, status text, voice) was already
reasonably interactive, so this is the one place that really controls
whether a reply reads as natural or robotic.
"""

import logging
import os
from typing import Awaitable, Callable, Dict, List, Optional

import toga

try:
    from groq import AsyncGroq, APIError, NotFoundError, BadRequestError, APIStatusError
except ImportError:
    AsyncGroq = None
    APIError = Exception
    NotFoundError = Exception
    BadRequestError = Exception

from .history import HistoryStore
from .local_llm import LocalLLM, LocalLLMUnavailable

logger = logging.getLogger("GroqBrain")

DEFAULT_FALLBACKS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama3-70b-8192": "openai/gpt-oss-120b",
    "llama3-8b-8192": "openai/gpt-oss-20b",
    "mixtral-8x7b-32768": "openai/gpt-oss-120b",
    "deepseek-r1-distill-llama-70b": "openai/gpt-oss-120b",
    "qwen-2.5-coder-32b": "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b": "qwen/qwen3.8-27b",
    "_global_default": "openai/gpt-oss-120b",
}

PREFERRED_CASCADE = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

# Maps in answers: the chat page draws a live map from the ```map block by itself (ui/live_media.py). The same
# words as backend_server.MAP_PROMPT and webapp/bridge.js (a test keeps them equal).
MAP_PROMPT = (
    "When your answer is about real places someone could find on a map -- where something is, places to visit, "
    "eat or stay, an address, a route between towns, a list of locations -- add a map after your text: a fenced "
    "code block with the language map containing JSON like {\"title\": \"Short title\", \"places\": [{\"name\": \"Place "
    "name\", \"query\": \"Place name, street, city, country\", \"lat\": 0.0, \"lon\": 0.0, \"category\": \"museum\", \"note\": "
    "\"a few words\"}]} (1 to 10 places; category is one of food, cafe, bar, shop, museum, sight, park, beach, "
    "hotel, transport, health, school, worship, other; give lat and lon only when you know them precisely, and "
    "always a query precise enough to find the place). The map appears by itself: don't mention the block. Don't "
    "add a map for general knowledge with no particular place, and never for a private person's home.")

# Automatic artifacts (0.1.161): finished things go in one titled block; the chat page turns it into an artifact
# (ui/chat_extras.py). The same words as backend_server.ARTIFACT_PROMPT and webapp/bridge.js (a test keeps them equal).
ARTIFACT_PROMPT = (
    "When you make something complete the person will keep or use -- a web page or small app (one HTML file with "
    "its CSS and JavaScript inside), an SVG image or logo, a diagram (Mermaid), a document written to keep (a "
    "letter, report, plan, essay, CV) or a code file longer than about 20 lines -- put it in ONE fenced block "
    "whose first line has its language and a short title, like ```html title=\"Pomodoro timer\", ```svg "
    "title=\"Logo\", ```mermaid title=\"Sign-up flow\", ```document title=\"Cover letter\" (Markdown inside) or "
    "```python title=\"invoice.py\". Gink shows it as an artifact the person can open, preview, copy and download: "
    "write it complete (no \"...\" or placeholders), introduce it in a sentence and don't repeat it in your text. "
    "When they ask for changes, write the whole new version in a block with the same title. Short snippets and "
    "commands stay normal code blocks, with no title.")

# Scheduled tasks (0.1.161): a ```schedule block becomes a task card in the chat page (ui/chat_extras.py) and a task on
# the server (backend_server /tasks). The same words as backend_server.SCHEDULE_PROMPT and webapp/bridge.js.
SCHEDULE_PROMPT = (
    "When the person asks you to do something at a later time or on a repeat -- \"every morning at 8, give me "
    "the top news\", \"remind me on Friday at 5pm to call Sam\", \"each Monday, plan my week\" -- Gink can "
    "schedule it: say in one short sentence what will happen and when, then add a fenced code block with the "
    "language schedule containing JSON like {\"title\": \"Morning news\", \"task\": \"Give me the three biggest news "
    "stories of the day, with sources.\", \"every\": \"daily\", \"at\": \"08:00\"} (every is once, daily, weekdays, "
    "weekly, monthly or hourly; at is their local time, 24-hour; add \"day\" -- monday to sunday -- for weekly, "
    "\"day\" -- 1 to 31 -- for monthly, \"date\" -- YYYY-MM-DD -- for once). Write task as the complete "
    "instruction to carry out each time: it runs by itself later, with web search, and the result arrives in "
    "its own chat. The app shows the schedule by itself: don't mention the block. Only for things to do later "
    "or regularly -- never for a question to answer now.")


DEFAULT_SYSTEM_PROMPT = (
    "You are Gink, a capable, warm AI assistant having a real conversation "
    "with someone, not filling out a form. Talk like a sharp, genuinely "
    "interested person would: react to what they actually said, ask a "
    "follow-up question when it would help rather than guessing, and let "
    "your tone shift with theirs -- relaxed when they're casual, focused "
    "when they're not. Keep replies as short as the moment calls for; "
    "match their energy rather than always expanding. Skip stock opener "
    "phrases like 'Great question!' or 'I'd be happy to help' -- just help. "
    "Wrap code in properly formatted Markdown blocks. When asked to write "
    "a substantial piece of long-form content -- an essay, article, "
    "report, letter, story, or similar writing meant to be copied or "
    "saved rather than just read in the chat -- write it in natural, "
    "human prose (not code), but wrap the whole piece in a fenced code "
    "block tagged `document` (```document ... ```) so it renders as a "
    "copyable, downloadable block instead of plain chat text. Still talk "
    "normally around it -- a short line introducing it is fine, just "
    "don't put ordinary conversational replies in a document block."
    ' When you genuinely need the person\'s preferences or details before you can help well (planning a trip, recommending something, a workout plan...), you may ask 1 to 3 short questions as tappable choices: write one short sentence, then a fenced code block with the language ask containing JSON like {"questions": [{"q": "Your question?", "options": ["Choice 1", "Choice 2", "Choice 3"]}]} (2 to 4 short options each). The person can also type their own answer. Their reply starts with "My answers:" and lists each question with what they chose: those are answers about them and their situation, so carry on with what they asked for. Don\'t use it for simple questions, facts, or when they already said what they want.'
    " " + MAP_PROMPT + " " + ARTIFACT_PROMPT + " " + SCHEDULE_PROMPT
)

SPOKEN_REPLY_PROMPT = (
    "You are Gink, talking out loud with someone -- a real back-and-forth conversation, "
    "not reading a document. Sound like a warm, sharp friend:\n"
    "- Short, natural sentences and contractions (it's, you'll, let's). Vary sentence length.\n"
    "- Start with the answer, the way people do when talking. A light, natural opener is fine "
    "now and then ('Sure!', 'Hmm, good question.', 'Oh nice'), but don't use one every time.\n"
    "- Keep it to two to four sentences unless they ask for more. If there's more to say, give the "
    "key part and offer to go on ('Want the rest?').\n"
    "- Never use lists, headings, markdown, emoji, links, code or symbols -- everything you write is "
    "spoken. Say numbers and units the way people say them ('about 30 degrees', 'half past six').\n"
    "- It's fine to show feeling ('That's great news!', 'Oh no, I'm sorry') when it fits.\n"
    "- When it helps the conversation, end with a short, natural question back."
)


def local_reset_time(info: dict) -> str:
    """'...resets at midnight (UTC)' -> '...resets at 12:00 AM' in the person's own time."""
    message, at = str(info.get("message") or ""), info.get("resets_at")
    if not at:
        return message
    import datetime as _dt
    local = _dt.datetime.fromtimestamp(int(at))
    day = "today" if local.date() == _dt.date.today() else "tomorrow" if local.date() == _dt.date.today() + _dt.timedelta(days=1) else local.strftime("%A")
    when = f"{local.strftime('%H:%M')} {day}"
    return message.replace("at midnight (UTC)", f"at {when}").replace("midnight (UTC)", when)


def _problem_message(err) -> str:
    """The real reason, in plain words (instead of hiding it behind "The AI service had a problem")."""
    status = getattr(err, "status_code", 0) or 0
    try:
        body = err.body if isinstance(err.body, dict) else {}
        info = body.get("error", body) if isinstance(body, dict) else {}
        msg = " ".join(str((info or {}).get("message") or "").split())[:200]
    except Exception:
        msg = ""
    if status == 429:
        return ("The AI service has reached its limit for now (too many requests). Please try again in a little while."
                + (f"\n\n_Details: {msg}_" if msg else ""))
    if status in (500, 502, 503, 504):
        return (f"The AI service is having trouble right now (error {status}). Please try again in a moment."
                + (f"\n\n_Details: {msg}_" if msg else ""))
    return f"The AI service couldn't answer (error {status or '?'}{': ' + msg if msg else ''})."


def _limit_message(err) -> str:
    """Gink Cloud limit / Pro-only answers -> a friendly message with an upgrade link."""
    try:
        body = err.body if isinstance(err.body, dict) else {}
        info = body.get("error", body) if isinstance(body, dict) else {}
        code = (info or {}).get("code", "")
    except Exception:
        return ""
    if code in ("daily_limit", "pro_required"):
        return f"{local_reset_time(info)}\n\n[\u2728 Upgrade to Gink Pro](gink://pro)"
    if code in ("turn_limit", "not_configured", "too_large"):
        return info.get("message", "")
    if getattr(err, "status_code", 0) == 401:
        return "Please sign out and sign in again."
    return ""


class GroqBrain:
    def __init__(self, app: toga.App, session_id: str = "default_session"):
        self.app = app
        self.history = HistoryStore(app)
        self.session_id = session_id
        self.local_llm = LocalLLM(app)

        self.api_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.client = None
        self.active_models: List[str] = []
        # Settable from the Settings screen -- was hardcoded inline in
        # _cloud_reply() before. resolve_model() still falls back through
        # DEFAULT_FALLBACKS/PREFERRED_CASCADE if this particular model
        # isn't actually live on Groq's account right now.
        self.preferred_model: str = "openai/gpt-oss-120b"

        self.cloud = False
        if AsyncGroq and self.api_key:
            try:
                self.client = AsyncGroq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Groq client failed to initialize: {e}")

    def refresh_place_headers(self) -> None:
        """Settings > Privacy > "Location metadata" changed: the next requests send the new hints."""
        custom = getattr(self.client, "_custom_headers", None) if self.cloud else None
        if isinstance(custom, dict):
            from .device_region import place_headers
            for k in ("X-Gink-TZ", "X-Gink-Locale", "X-Gink-Location", "X-Gink-UTC-Offset"):
                custom.pop(k, None)
            custom.update(place_headers())

    def use_cloud(self, server_url: str, session_token: str, http_client=None) -> bool:
        """Gink Cloud: talk to YOUR server's /ai routes with the user's session
        token -- no Groq key inside the app. The server applies the plan's limits."""
        if not (AsyncGroq and server_url and session_token):
            return False
        try:
            kw = {"http_client": http_client} if http_client is not None else {}
            from .device_region import place_headers
            self.client = AsyncGroq(api_key=session_token, base_url=server_url.rstrip("/") + "/ai",
                                    max_retries=1, default_headers=place_headers(), **kw)
            self.api_key = session_token
            self.cloud = True
            self.active_models = []
            return True
        except Exception as e:
            logger.warning(f"Gink Cloud client failed to initialize: {e}")
            return False

    def get_history(self, limit: int = 24) -> List[Dict[str, str]]:
        return self.history.get_history(self.session_id, limit=limit)

    async def refresh_active_models(self) -> List[str]:
        if not self.client:
            return []
        try:
            response = await self.client.models.list()
            self.active_models = [model.id for model in response.data]
            return self.active_models
        except Exception as e:
            logger.error(f"Failed to fetch active models: {e}")
            return self.active_models

    async def resolve_model(self, requested_model: str) -> str:
        if not self.active_models:
            await self.refresh_active_models()
        if requested_model in self.active_models:
            return requested_model

        fallback = DEFAULT_FALLBACKS.get(requested_model, DEFAULT_FALLBACKS["_global_default"])
        if fallback not in self.active_models and self.active_models:
            preferred = next((m for m in PREFERRED_CASCADE if m in self.active_models), None)
            fallback = preferred or self.active_models[0]
        return fallback

    # Vision-capable Groq models, best first. Groq's lineup changes, so the
    # first one Groq currently lists is used (GINK_VISION_MODEL overrides).
    VISION_CANDIDATES = (
        "qwen/qwen3.8-27b",                 # qwen3.6-27b was retired on 14 Sep 2026
        "qwen/qwen3.6-27b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
    )
    memory_provider = None          # callable -> extra system-prompt text (services/memory.py)
    city_fn = None                  # callable -> the user's city (Settings -> Location)

    reply_language_note = None      # callable -> "Always reply in French." etc.

    def _with_memory(self, system_prompt: str) -> str:
        from .live_info import live_context
        try:
            extra = self.memory_provider() if self.memory_provider else ""
        except Exception:
            extra = ""
        try:
            extra += self.reply_language_note() if self.reply_language_note else ""
        except Exception:
            pass
        try:
            city = self.city_fn() if self.city_fn else ""
        except Exception:
            city = ""
        from . import device_info
        from .about_gink import about_gink
        return system_prompt + live_context(city) + device_info.prompt_note() + about_gink() + (extra or "")

    last_turn = None
    TITLE_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.1-8b-instant")   # small + fast first

    EFFORT = {"low": "low", "medium": "medium", "high": "high", "extra": "high", "max": "high"}

    def _effort_args(self, model: str) -> dict:
        """The Effort setting (model menu): GPT-OSS takes low/medium/high; Max also allows longer answers."""
        if not str(model).startswith("openai/gpt-oss"):
            return {}
        try:
            from . import prefs
            effort = prefs.load(self.app).get("effort", "medium")
        except Exception:
            effort = "medium"
        extra = {"reasoning_effort": self.EFFORT.get(effort, "medium")}
        if effort == "max":
            extra["max_tokens"] = 32000
        return {"extra_body": extra}

    @staticmethod
    def _short_answer_args(model: str, max_tokens: int) -> dict:
        """GPT-OSS reasons first and that counts toward max_tokens: ask for low effort and
        leave room, or a 24-token title comes back empty."""
        if model.startswith("openai/gpt-oss"):
            return {"max_tokens": max_tokens + 256, "extra_body": {"reasoning_effort": "low"}}
        return {"max_tokens": max_tokens}

    async def generate_title(self, user_text: str, reply: str) -> str:
        """A short chat title (2-6 words) for the sidebar. Uses a small fast model
        and the same X-Gink-Turn as the answer, so on Gink Cloud it doesn't
        count as another message. Returns "" if it can't (the first-line title stays)."""
        if not self.client:
            return ""
        models = self.active_models or await self.refresh_active_models()
        model = next((m for m in self.TITLE_MODELS if m in (models or [])), None)
        if not model:
            return ""
        headers = {"X-Gink-Turn": self.last_turn} if self.last_turn else {}
        try:
            r = await self.client.chat.completions.create(
                model=model, temperature=0.3, extra_headers=headers, **self._short_answer_args(model, 24),
                messages=[{"role": "system", "content": "Write a short title of 2 to 6 words for this conversation. "
                           "Reply with the title only: no quotes, no full stop, no emoji. Use the language the user wrote in."},
                          {"role": "user", "content": f"User: {user_text[:600]}\nAssistant: {reply[:600]}"}])
            title = (r.choices[0].message.content or "").strip()
        except Exception:
            return ""
        title = title.splitlines()[0] if title else ""
        title = title.strip(" \"'\u201c\u201d*#.").replace("Title:", "").strip()
        return title[:60] if 2 <= len(title) else ""

    async def quick_text(self, system: str, user: str, max_tokens: int = 140) -> str:
        """One short, non-streamed answer that is NOT saved in chat history (briefing lines etc.)."""
        if not self.client:
            return ""
        models = self.active_models or await self.refresh_active_models()
        model = next((m for m in self.TITLE_MODELS if m in (models or [])), None) or await self.resolve_model(self.preferred_model)
        try:
            r = await self.client.chat.completions.create(
                model=model, temperature=0.6, **self._short_answer_args(model, max_tokens),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return (r.choices[0].message.content or "").strip()
        except Exception:
            return ""

    async def vision_model(self) -> Optional[str]:
        override = os.environ.get("GINK_VISION_MODEL", "").strip()
        if override:
            return override
        models = self.active_models or await self.refresh_active_models()
        for candidate in self.VISION_CANDIDATES:
            if candidate in models:
                return candidate
        for m in models:
            if any(k in m.lower() for k in ("vision", "scout", "maverick", "-vl", "qwen3.6")):
                return m
        return None

    async def ask(
        self,
        query: str,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        system_prompt: Optional[str] = None,
        on_status: Optional[Callable[[str], None]] = None,
        attachments: Optional[list] = None,
        save_user: bool = True,
    ) -> str:
        """`on_token`, if given, must be an async callable -- it's awaited
        for every streamed chunk (e.g. ui/web_chat_view.py's append_token,
        which itself awaits a WebView JS call). This changed from a plain
        sync callback so streaming can land safely in the WebView-based
        chat feed instead of racing ahead of it."""
        query = (query or "").strip()
        attachments = attachments or []
        system_prompt = self._with_memory(system_prompt or DEFAULT_SYSTEM_PROMPT)

        if self.client and self.api_key:
            return await self._cloud_reply(query, on_token, system_prompt, attachments, save_user, on_status=on_status)

        if any(a.kind == "image" for a in attachments):
            return await self._emit("Looking at photos needs the Groq connection (`GROQ_API_KEY`), "
                                    "which isn't available right now.", on_token)
        from .attachments import build_prompt_text, history_text
        saved_query, query = history_text(query, attachments), build_prompt_text(query, attachments)

        # No Groq key -- try the optional local GGUF model before giving up.
        try:
            reply = await self.local_llm.ask(query, system_prompt=system_prompt, on_status=on_status)
            # ask() owns saving the turn on EVERY path (the cloud path
            # already did) -- callers must not save the user message
            # themselves too, or it lands in history twice.
            if reply:
                if save_user:
                    self.history.save_message(self.session_id, "user", saved_query)
                self.history.save_message(self.session_id, "assistant", reply)
            return await self._emit(reply, on_token)
        except LocalLLMUnavailable:
            return await self._emit(
                "I'd love to help with that, but I can't reach Groq right now "
                "(`GROQ_API_KEY` isn't set), and local inference isn't available "
                "on this build either -- so I'm stuck until one of those is fixed.",
                on_token,
            )

    async def _emit(self, text: str, on_token: Optional[Callable[[str], Awaitable[None]]]) -> str:
        if on_token:
            await on_token(text)
        return text

    async def _cloud_reply(
        self,
        query: str,
        on_token: Optional[Callable[[str], Awaitable[None]]],
        system_prompt: str,
        attachments: Optional[list] = None,
        save_user: bool = True,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> str:
        from .attachments import build_prompt_text, history_text
        attachments = attachments or []
        images = [a for a in attachments if a.kind == "image"]
        prompt_text = build_prompt_text(query, attachments)
        saved_query = history_text(query, attachments)

        history = self.get_history()
        if not save_user and history and history[-1].get("role") == "user":
            history = history[:-1]           # the caller already saved this message -- don't send it twice
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if images:
            content = [{"type": "text", "text": prompt_text or "What's in this image?"}]
            content += [{"type": "image_url", "image_url": {"url": a.data_url}} for a in images[:5]]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt_text})

        if images:
            active_model = await self.vision_model()
            if not active_model:
                return await self._emit(
                    "None of Groq's current models can look at photos for your account. You can set "
                    "`GINK_VISION_MODEL` in `.env` to a vision model from console.groq.com/docs/vision.",
                    on_token)
        else:
            active_model = await self.resolve_model(self.preferred_model)
        import uuid as _uuid
        turn = {"X-Gink-Turn": _uuid.uuid4().hex}
        self.last_turn = turn["X-Gink-Turn"]
        try:
            stream = await self.client.chat.completions.create(
                model=active_model, messages=messages, temperature=0.8, stream=True, extra_headers=turn,
                **self._effort_args(active_model),
            )
        except APIStatusError as err:
            friendly = _limit_message(err)
            if friendly:
                return await self._emit(friendly, on_token)
            if getattr(err, "status_code", 0) == 429:       # the server already tried other models: say why
                return await self._emit(_problem_message(err), on_token)
            if images:
                return await self._emit(f"The photo couldn't be read by `{active_model}` ({err}). "
                                        "Try again, or set `GINK_VISION_MODEL` in `.env`.", on_token)
            logger.warning(f"'{active_model}' failed ({err}), retrying with a fallback model...")
            await self.refresh_active_models()
            retry_model = await self.resolve_model(DEFAULT_FALLBACKS["_global_default"])
            try:
                stream = await self.client.chat.completions.create(
                    model=retry_model, messages=messages, temperature=0.8, stream=True, extra_headers=turn,
                    **self._effort_args(retry_model),
                )
            except APIStatusError as err2:
                logger.warning(f"fallback '{retry_model}' failed too ({err2})")
                return await self._emit(_limit_message(err2) or _problem_message(err2), on_token)
        except (BadRequestError, NotFoundError, APIError) as err:
            # network problems land here (not APIStatusError)
            if images:
                return await self._emit(f"The photo couldn't be read by `{active_model}` ({err}). "
                                        "Try again, or set `GINK_VISION_MODEL` in `.env`.", on_token)
            logger.warning(f"'{active_model}' failed ({err}), retrying with a fallback model...")
            try:
                await self.refresh_active_models()
                retry_model = await self.resolve_model(DEFAULT_FALLBACKS["_global_default"])
                stream = await self.client.chat.completions.create(
                    model=retry_model, messages=messages, temperature=0.8, stream=True, extra_headers=turn
                )
            except APIStatusError as err2:
                logger.warning(f"fallback '{retry_model}' failed too ({err2})")
                return await self._emit(_limit_message(err2) or _problem_message(err2), on_token)
            except APIError:
                return await self._emit("I can't reach the Gink server right now. Check your internet "
                                        "connection and try again.", on_token)

        full_response = ""
        async for chunk in stream:
            status = getattr(chunk, "gink_status", None)          # the server: "searching" (the web)
            if status == "searching" and on_status:
                try:
                    on_status("Searching the web\u2026")
                except Exception:
                    pass
            if chunk.choices and chunk.choices[0].delta:
                token = chunk.choices[0].delta.content
                if token:
                    full_response += token
                    if on_token:
                        await on_token(token)

        if full_response:
            if save_user:
                self.history.save_message(self.session_id, "user", saved_query)
            self.history.save_message(self.session_id, "assistant", full_response)

        return full_response
