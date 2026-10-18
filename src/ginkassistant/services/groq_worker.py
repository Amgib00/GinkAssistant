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


def _limit_message(err) -> str:
    """Gink Cloud limit / Pro-only answers -> a friendly message with an upgrade link."""
    try:
        body = err.body if isinstance(err.body, dict) else {}
        info = body.get("error", body) if isinstance(body, dict) else {}
        code = (info or {}).get("code", "")
    except Exception:
        return ""
    if code in ("daily_limit", "pro_required"):
        return f"{info.get('message')}\n\n[\u2728 Upgrade to Gink Pro](gink://pro)"
    if code in ("turn_limit", "not_configured", "too_large"):
        return info.get("message", "")
    if getattr(err, "status_code", 0) == 401:
        return "Please sign out and sign in again."
    return ""


class GroqBrain:
    def __init__(self, app: toga.App, session_id: str = "default_session"):
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

    def use_cloud(self, server_url: str, session_token: str, http_client=None) -> bool:
        """Gink Cloud: talk to YOUR server's /ai routes with the user's session
        token -- no Groq key inside the app. The server applies the plan's limits."""
        if not (AsyncGroq and server_url and session_token):
            return False
        try:
            kw = {"http_client": http_client} if http_client is not None else {}
            self.client = AsyncGroq(api_key=session_token, base_url=server_url.rstrip("/") + "/ai",
                                    max_retries=1, **kw)
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
        return system_prompt + live_context(city) + (extra or "")

    last_turn = None
    TITLE_MODELS = ("openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.1-8b-instant")   # small + fast first

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
            return await self._cloud_reply(query, on_token, system_prompt, attachments, save_user)

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
                model=active_model, messages=messages, temperature=0.8, stream=True, extra_headers=turn
            )
        except APIStatusError as err:
            friendly = _limit_message(err)
            if friendly:
                return await self._emit(friendly, on_token)
            if images:
                return await self._emit(f"The photo couldn't be read by `{active_model}` ({err}). "
                                        "Try again, or set `GINK_VISION_MODEL` in `.env`.", on_token)
            logger.warning(f"'{active_model}' failed ({err}), retrying with a fallback model...")
            await self.refresh_active_models()
            retry_model = await self.resolve_model(DEFAULT_FALLBACKS["_global_default"])
            try:
                stream = await self.client.chat.completions.create(
                    model=retry_model, messages=messages, temperature=0.8, stream=True, extra_headers=turn
                )
            except APIStatusError as err2:
                return await self._emit(_limit_message(err2) or "The AI service had a problem. Please try again.",
                                        on_token)
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
                return await self._emit(_limit_message(err2) or "The AI service had a problem. Please try again.",
                                        on_token)
            except APIError:
                return await self._emit("I can't reach the Gink server right now. Check your internet "
                                        "connection and try again.", on_token)

        full_response = ""
        async for chunk in stream:
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