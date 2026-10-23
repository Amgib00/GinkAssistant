"""
Behind the Settings window (ui/settings_page.py draws it): owns every value,
applies changes immediately, and runs actions (save city, export, delete
account, ...). Everything a switch says is something Gink actually does.
"""

import asyncio
import os
import time
from datetime import datetime

from ..services import data_export, languages, launch_at_login, prefs, server_config, voice_bridge
from ..services.profile import WORK_OPTIONS
from ..services.voice_profiles import SPEECH_LANG_CODES, SPEECH_LANGS, VOICE_PROFILES
from ..services.api_client import ApiClient, ApiError
from ..services.paths import data_dir

LANG_NOTES = {
    "en": "English", "fr": "French", "wo": "Wolof", "kri": "Krio (Sierra Leone)", "ar": "Arabic",
    "pt": "Portuguese", "es": "Spanish",
}
METHOD_LABELS = {"wave": "Wave", "orange_money": "Orange Money", "free_money": "Free Money", "card": "Card",
                 "mtn_momo": "MTN MoMo", "moov_money": "Moov Money", "mpesa": "M-Pesa"}
PLAN_LABELS = {"pro_1m": "Pro \u00b7 1 month", "pro_3m": "Pro \u00b7 3 months", "pro_12m": "Pro \u00b7 12 months"}
STATUS_LABELS = {"success": "Paid", "pending": "Pending", "failed": "Not completed"}
BOOL_KEYS = {"read_aloud", "notify_reminders", "briefing_enabled", "briefing_speak", "use_memory",
             "web_search", "video_suggestions", "single_keys", "wake_enabled", "wake_followup", "wake_front",
             "briefing_projects", "use_location", "agent_confirm"}
CHOICES = {"theme": {"system", "light", "dark"}, "chat_font": {"sans", "serif", "mono"},
           "motion": {"system", "reduced"}, "voice_speed": {"slow", "normal", "fast"},
           "reply_language": set(languages.BY_CODE), "send_key": {"enter", "mod"},
           "speech_lang": SPEECH_LANG_CODES}


def _active_text(s: dict) -> str:
    if s.get("current"):
        return "This device"
    ago = time.time() - float(s.get("last_seen") or 0)
    if ago < 600:
        return "Active now"
    if ago < 86400:
        return "Active today"
    days = int(ago // 86400)
    return "Last active yesterday" if days == 1 else f"Last active {days} days ago"


class SettingsController:
    def __init__(self, app, web_chat, brain, selected_voice, audio_engine, *, email, display_name,
                 models_fn, push_models, open_pro, on_log_out, refresh_sidebar, clear_all_chats,
                 brief_now, sync_fn, open_url):
        self.app, self.web, self.brain = app, web_chat, brain
        self.selected_voice, self.audio_engine = selected_voice, audio_engine
        self.email, self.display_name = email, display_name
        self.models_fn, self.push_models, self.open_pro = models_fn, push_models, open_pro
        self.on_log_out, self.refresh_sidebar, self.clear_all_chats = on_log_out, refresh_sidebar, clear_all_chats
        self.brief_now, self.sync_fn, self.open_url = brief_now, sync_fn, open_url
        self._server_info = None
        self.apply_all()

    # ------------------------------------------------------------ applying
    def p(self) -> dict:
        return prefs.load(self.app)

    def apply_all(self):
        """Make the saved settings take effect (at startup and after changes)."""
        p = self.p()
        voice_bridge.listen_language[0] = p.get("speech_lang") if p.get("speech_lang") in SPEECH_LANG_CODES else "auto"
        voice = p.get("voice")
        if voice in voice_bridge.VOICES:
            self.selected_voice["value"] = voice
            self.audio_engine.voice_key = voice
        voice_bridge.set_speed(p.get("voice_speed", "normal"))
        runner = self.app.task_runner
        runner.disabled_tools = ({"web_search"} if not p.get("web_search", True) else set()) | \
                                ({"find_video"} if not p.get("video_suggestions", True) else set())
        runner.use_memory = bool(p.get("use_memory", True))
        runner.reply_language_note = self.reply_language_note
        self.brain.reply_language_note = self.reply_language_note
        profile = getattr(self.app, "profile", None)
        profile_note = (profile.as_prompt if profile else (lambda: ""))
        memory_note = (self.app.memory.as_prompt if p.get("use_memory", True) else (lambda: ""))
        self.brain.memory_provider = lambda: profile_note() + memory_note()
        runner.profile_note = profile_note
        self.app.task_scheduler.notifications_enabled = lambda: bool(prefs.load(self.app).get("notify_reminders", True))
        if p.get("model"):
            self.brain.preferred_model = p["model"]

    def reply_language_note(self) -> str:
        return languages.reply_note(prefs.load(self.app).get("reply_language", "auto"))

    async def apply_appearance(self):
        p = self.p()
        await self.web.set_appearance(p.get("theme", "system"), p.get("chat_font", "sans"), p.get("motion", "system"))

    # ------------------------------------------------------------ state for the page
    def _values(self) -> dict:
        p = self.p()
        v = {k: p.get(k) for k in ("theme", "chat_font", "motion", "voice_speed", "read_aloud", "reply_language",
                                   "notify_reminders", "briefing_enabled", "briefing_time", "briefing_speak",
                                   "use_memory", "web_search", "video_suggestions", "speech_lang", "send_key",
                                   "single_keys", "wake_enabled", "wake_followup", "wake_front", "briefing_projects")}
        v.update(voice=self.selected_voice["value"], model=self.brain.preferred_model,
                 city=prefs.city(self.app), server_url=server_config.saved_url(self.app) or "",
                 launch_at_login=bool(launch_at_login.is_supported() and launch_at_login.is_enabled()))
        v["reply_language"] = languages.normalise(v.get("reply_language") or "auto")
        prof = self.app.profile.get() if getattr(self.app, "profile", None) else {}
        v.update(full_name=prof.get("full_name", ""), nickname=prof.get("nickname", ""),
                 work=prof.get("work", ""), instructions=prof.get("instructions", ""))
        return v

    def _info(self) -> dict:
        sync = getattr(self.app, "_sync_service", None)
        if sync is None:
            sync_status = "Not running"
        elif sync.last_error:
            sync_status = sync.last_error
        elif sync.last_ok:
            mins = int((time.time() - sync.last_ok) // 60)
            sync_status = "Synced just now" if mins < 1 else f"Last synced {mins} min ago"
        else:
            sync_status = "Waiting to sync\u2026"
        info = {"name": self.display_name, "email": self.email, "voices": list(voice_bridge.VOICES),
                "models": self.models_fn(), "version": getattr(self.app, "version", None) or "0.1.0",
                "server": self.app.state.base_url, "default_server": server_config.platform_default(),
                "launch_supported": launch_at_login.is_supported(), "sync_status": sync_status,
                "plan": getattr(self, "_plan", "free"), "speech_langs": [list(x) for x in SPEECH_LANGS],
                "wake_status": self.wake_status_fn() if self.wake_status_fn else "Off",
                "wake_supported": self.wake_supported,
                "photo": (self.app.profile.get().get("photo", "") if getattr(self.app, "profile", None) else ""),
                "work_options": WORK_OPTIONS,
                "language_label": languages.label(prefs.load(self.app).get("reply_language", "auto")),
                "build": getattr(self.app, "gink_build", ""),
                "location_text": self._location_text()}
        if not getattr(self, "_langs_sent", False):
            info["languages"] = [[c, n, e, x] for c, n, e, x in languages.LANGUAGES]
            self._langs_sent = True
        if getattr(self, "_pro_until", 0):
            info["pro_until_text"] = datetime.fromtimestamp(self._pro_until).strftime("%d %B %Y")
        info.update(self._server_info or {})
        return info

    def _lists(self) -> dict:
        return {"memories": [{"uid": m["uid"], "text": m["text"]} for m in self.app.memory.list()]}

    async def push(self, extra_info: dict = None, extra_lists: dict = None):
        info = self._info()
        info.update(extra_info or {})
        lists = self._lists()
        lists.update(extra_lists or {})
        await self.web.set_settings_state({"values": self._values(), "info": info, "lists": lists})
        await self.push_page_prefs()

    def voice_config(self) -> dict:
        p = self.p()
        return {"intro_seen": bool(p.get("voice_intro_seen")), "voice": self.selected_voice["value"],
                "voices": [{"key": v["key"], "name": v["name"], "desc": v["desc"], "colors": v["colors"]}
                           for v in VOICE_PROFILES]}

    async def push_page_prefs(self):
        """Keyboard prefs + voice list for the chat page (used outside the Settings window too)."""
        p = self.p()
        await self.web.set_keyboard_prefs({"send_mod": p.get("send_key") == "mod",
                                           "single_keys": bool(p.get("single_keys", True))})
        await self.web.set_voice_config(self.voice_config())

    async def refresh(self, panel: str = ""):
        """Called when the window opens or a section is shown: local values at
        once, then server-side details (plan, usage, payments, links)."""
        await self.push()
        token = getattr(self.app, "session_token", None)
        api = ApiClient(self.app.state.base_url)
        extra_info, extra_lists = {}, {}
        if self._server_info is None:
            self._server_info = {k: v for k, v in (await api.app_info()).items() if v}
            extra_info.update(self._server_info)
        if token and panel in ("general", "account", "billing", "usage", ""):
            try:
                u = await asyncio.wait_for(api.ai_usage(token), timeout=8)
                left = max(0, int(u["resets_at"] - time.time()))
                u["resets_text"] = f"in {left // 3600} h {left % 3600 // 60} min"
                extra_info["usage"] = u
                self._plan = u.get("plan", "free")
            except Exception:
                extra_info["usage_error"] = "Usage isn't available right now (offline, or the server is older)."
            try:
                st = await asyncio.wait_for(api.billing_status(token), timeout=8)
                self._plan, self._pro_until = st.get("plan", "free"), st.get("pro_until", 0)
            except Exception:
                pass
        if token and panel == "account":                      # two-step verification
            try:
                status = await asyncio.wait_for(api.twofa_status(token), timeout=8)
                extra_info["twofa"] = dict(status, **self._twofa)
            except Exception:
                extra_info["twofa"] = dict(self._twofa)
        if token and panel == "account":                      # your websites
            try:
                extra_lists["sites"] = await asyncio.wait_for(api.sites(token), timeout=8)
            except Exception:
                extra_lists["sites"] = []
        if token and panel == "account":                      # signed-in devices
            try:
                found = await asyncio.wait_for(api.sessions(token), timeout=8)
                extra_lists["sessions"] = [dict(s, when=_active_text(s)) for s in found]
            except Exception:
                extra_lists["sessions"] = []
                extra_info["sessions_error"] = "Your devices aren't available right now."
        if token and panel == "billing":
            try:
                pays = await asyncio.wait_for(api.billing_history(token), timeout=8)
                extra_lists["payments"] = [dict(p, method_label=METHOD_LABELS.get(p["method"], p["method"] or ""),
                                                plan_label=PLAN_LABELS.get(p["plan"], p["plan"]),
                                                status_label=STATUS_LABELS.get(p["status"], p["status"]),
                                                date=datetime.fromtimestamp(p["created"]).strftime("%d %b %Y"))
                                           for p in pays]
            except Exception:
                extra_lists["payments"] = []
                extra_info["payments_error"] = "Payment history isn't available right now."
        await self.push(extra_info, extra_lists)

    # ------------------------------------------------------------ changes
    async def on_setting(self, key: str, value):
        if key in BOOL_KEYS:
            prefs.save(self.app, **{key: bool(value)})
            if key.startswith("wake_") and self.on_wake_change:      # "Hey Gink": start / stop right away
                await self.on_wake_change()
        elif key in CHOICES:
            if value not in CHOICES[key]:
                return
            prefs.save(self.app, **{key: value})
        elif key == "voice" and value in voice_bridge.VOICES:
            prefs.save(self.app, voice=value)
        elif key == "model" and value:
            prefs.save(self.app, model=value)
            self.brain.preferred_model = value
            await self.push_models()
        elif key in ("full_name", "nickname", "work") and getattr(self.app, "profile", None) is not None:
            if key == "work" and value not in WORK_OPTIONS:
                return
            self.app.profile.update(**{key: str(value or "")})
            if self.on_profile_change:
                self.on_profile_change()
        elif key == "launch_at_login":
            ok = launch_at_login.enable() if value else launch_at_login.disable()
            if not ok:
                await self.web.settings_toast("Couldn't change that on this computer.", "err")
        else:
            return
        self.apply_all()
        if key in ("theme", "chat_font", "motion"):
            await self.apply_appearance()
        await self.push()

    async def on_action(self, name: str, value=None):
        try:
            handler = getattr(self, "_a_" + (name or ""), None)
            if handler is None:
                return
            await handler(value)
        except ApiError as exc:
            await self.web.settings_toast(str(exc), "err")
        except Exception as exc:
            await self.web.settings_toast(f"Something went wrong ({exc.__class__.__name__}).", "err")

    on_profile_change = None           # main screen: refresh avatar + greeting
    on_wake_change = None              # main screen: start / stop listening for "Hey Gink"
    wake_status_fn = None
    wake_supported = True

    async def _a_set_photo(self, data_url):
        import base64, re as _re
        m = _re.match(r"data:image/(png|jpe?g|webp);base64,(.+)", str(data_url or ""), _re.S)
        if not m:
            return await self.web.settings_toast("Use a PNG, JPEG or WebP photo.", "err")
        try:
            self.app.profile.set_photo(base64.b64decode(m.group(2)))
        except ValueError as exc:
            return await self.web.settings_toast(str(exc), "err")
        if self.on_profile_change:
            self.on_profile_change()
        await self.push()
        await self.web.settings_toast("Profile photo updated.")

    async def _a_remove_photo(self, _):
        self.app.profile.set_photo(None)
        if self.on_profile_change:
            self.on_profile_change()
        await self.push()

    def _location_text(self) -> str:
        p = prefs.load(self.app)
        if not p.get("use_location", True):
            return "Off \u2014 Gink won\u2019t use your location"
        city = (p.get("city") or p.get("briefing_city") or "").strip()
        if city:
            return f"{city} \u00b7 set by you"
        live = getattr(getattr(self.app, "task_runner", None), "live", None)
        place = getattr(live, "_ip_place", None) if live else None
        if place:
            label = ", ".join(x for x in (place.get("name"), place.get("country")) if x)
            return f"{label} \u00b7 estimated from your IP address"
        return "Not set \u2014 add your city, or use your approximate location"

    async def _a_detect_location(self, _):
        live = getattr(getattr(self.app, "task_runner", None), "live", None)
        place = await live.approximate_place(fresh=True) if live else None
        if not place or place.get("name") in (None, "", "your area"):
            await self.web.settings_toast("Couldn\u2019t estimate your location right now. Type your city instead.")
            return
        prefs.save(self.app, city=place["name"], use_location=True)
        await self.push()
        await self.web.settings_toast(f"Location set to {place['name']}" + (f", {place['country']}" if place.get("country") else "") + ".")

    async def _a_save_instructions(self, text):
        self.app.profile.update(instructions=str(text or ""))
        await self.push()
        await self.web.settings_toast("Instructions saved \u2014 Gink will follow them in every chat.")

    async def _a_test_voice(self, _):
        await self.web.settings_toast("Testing the natural voice\u2026")
        reason = await voice_bridge.test_natural_voice(self.selected_voice["value"])
        if not reason:
            await self.web.settings_toast("The natural voice works \u2713")
        else:
            await self.web.settings_toast(f"Natural voice not working: {reason}", "err")

    async def _a_refresh(self, panel):
        await self.refresh(panel or "")

    async def _a_logout(self, _):
        token = getattr(self.app, "session_token", None)
        if token:                                   # end this device's session on the server too
            try:
                await asyncio.wait_for(ApiClient(self.app.state.base_url).logout(token), timeout=6)
            except Exception:
                pass
        self.on_log_out()

    @property
    def _twofa(self) -> dict:                 # setup in progress / codes to show once (not saved anywhere)
        if not hasattr(self, "_twofa_state"):
            self._twofa_state = {}
        return self._twofa_state

    async def _twofa_call(self, fn, *args):
        token = getattr(self.app, "session_token", None)
        if not token:
            return None
        try:
            return await fn(token, *args)
        except ApiError as exc:
            await self.web.settings_toast(str(exc))
            return None

    async def _a_twofa_setup(self, _):
        api = ApiClient(self.app.state.base_url)
        setup = await self._twofa_call(api.twofa_setup)
        if setup:
            self._twofa.clear(); self._twofa["setup"] = setup
            await self.refresh("account")

    async def _a_twofa_enable(self, code):
        api = ApiClient(self.app.state.base_url)
        done = await self._twofa_call(api.twofa_enable, str(code or "").strip())
        if done:
            self._twofa.clear(); self._twofa["codes"] = done.get("recovery_codes", [])
            await self.web.settings_toast("Two-step verification is on.")
            await self.refresh("account")

    async def _a_twofa_disable(self, code):
        api = ApiClient(self.app.state.base_url)
        if await self._twofa_call(api.twofa_disable, str(code or "").strip()):
            self._twofa.clear()
            await self.web.settings_toast("Two-step verification is off.")
            await self.refresh("account")

    async def _a_twofa_cancel(self, _):
        self._twofa.clear()
        await self.refresh("account")

    async def _a_twofa_done(self, _):
        self._twofa.clear()                    # the codes are never shown again
        await self.refresh("account")

    async def _a_delete_site(self, site_id):
        token = getattr(self.app, "session_token", None)
        if token and site_id:
            await ApiClient(self.app.state.base_url).delete_site(token, str(site_id))
            await self.web.settings_toast("Website deleted.")
            await self.refresh("account")

    async def _a_revoke_session(self, sid):
        token = getattr(self.app, "session_token", None)
        if token and sid:
            await ApiClient(self.app.state.base_url).revoke_session(token, str(sid))
            await self.web.settings_toast("That device is signed out.")
            await self.refresh("account")

    async def _a_sign_out_others(self, _):
        token = getattr(self.app, "session_token", None)
        if token:
            await ApiClient(self.app.state.base_url).sign_out_others(token)
            await self.web.settings_toast("All your other devices are signed out.")
            await self.refresh("account")

    async def _a_open_url(self, url):
        if url:
            await self.open_url(url)

    async def _a_save_city(self, name):
        name = (name or "").strip()
        if not name:
            prefs.save(self.app, city="", briefing_city="")
            await self.web.settings_toast("Cleared \u2014 using an approximate location from your connection.")
            return await self.push()
        try:
            place = await self.app.task_runner.live.geocode(name)
        except Exception:
            place = None
        if not place:
            return await self.web.settings_toast(f"Couldn't find \u201c{name}\u201d. Check the spelling.", "err")
        label = place["name"] + (f", {place['country']}" if place.get("country") else "")
        prefs.save(self.app, city=label, briefing_city=label)
        await self.web.settings_toast(f"Saved: {label}")
        await self.push()

    async def _a_save_briefing_time(self, t):
        import re
        m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", t or "")
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            return await self.web.settings_toast("Use a 24-hour time like 07:30.", "err")
        prefs.save(self.app, briefing_time=f"{int(m.group(1)):02d}:{m.group(2)}")
        await self.web.settings_toast("Briefing time saved.")
        await self.push()

    async def _a_brief_now(self, _):
        await self.brief_now()

    async def _a_forget_memory(self, uid):
        self.app.memory.forget(uid or "")
        await self.push()

    async def _a_forget_all(self, _):
        n = self.app.memory.clear()
        await self.web.settings_toast(f"Forgot {n} thing{'s' if n != 1 else ''}.")
        await self.push()

    async def _a_sync_now(self, _):
        if not self.sync_fn:
            return
        ok = await self.sync_fn()
        await self.web.settings_toast("Synced." if ok else "Couldn't sync right now.", "ok" if ok else "err")
        await self.push()

    async def _a_save_server(self, url):
        server_config.save_url(self.app, url or "")
        self.app.state.base_url = server_config.resolve_base_url(self.app)
        ok, msg = await server_config.check_server(self.app.state.base_url)
        await self.web.settings_toast(f"{msg} ({self.app.state.base_url})", "ok" if ok else "err")
        self._server_info = None
        await self.push()

    async def _a_delete_chats(self, _):
        n = self.clear_all_chats()
        await self.web.settings_toast(f"Deleted {n} chat{'s' if n != 1 else ''}.")
        self.refresh_sidebar()

    async def _a_export(self, _):
        data = data_export.build_export(self.email, self.brain.history, self.app.task_store, self.app.memory, self.p())
        path = await data_export.save_with_dialog(self.app, data_export.export_filename(), ["json"],
                                                  lambda p: data_export.write_export(p, data))
        if path:
            await self.web.settings_toast(f"Exported to {path}")

    async def _a_delete_account(self, _):
        token = getattr(self.app, "session_token", None)
        if not token:
            return await self.web.settings_toast("Sign in again first, then delete your account.", "err")
        await ApiClient(self.app.state.base_url).delete_account(token)
        # remove this account's data from the device too
        self.clear_all_chats()
        self.app.memory.clear()
        for it in self.app.task_store.list(include_done=True, top_level_only=True):
            self.app.task_store.delete(it.id)
        await self.web.settings_toast("Your account was deleted.")
        await asyncio.sleep(1.2)
        self.on_log_out()
