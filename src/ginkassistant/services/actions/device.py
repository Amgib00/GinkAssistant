"""Per-platform device actions.

Android uses Chaquopy's Java bridge to fire real Android intents (the phone's
own Clock, Phone, SMS, Calendar apps). iOS uses rubicon-objc (ships with
Toga's iOS backend) to open URLs/app schemes. Desktop uses OS commands.

Every method returns an ActionResult and never raises, so one broken platform
call can never crash the chat.
"""
from __future__ import annotations

import os
import shutil
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote

from .platform_info import current_platform
from ._shell import run, spawn
from . import system_alarms


@dataclass
class ActionResult:
    ok: bool
    message: str
    by_system: bool = False  # True when the OS itself will ring / handle it

    def to_dict(self):
        return {"ok": self.ok, "message": self.message, "by_system": self.by_system}


# Common app names -> Android package / iOS URL scheme.
ANDROID_PACKAGES = {
    "whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome", "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps", "google maps": "com.google.android.apps.maps",
    "spotify": "com.spotify.music", "instagram": "com.instagram.android",
    "facebook": "com.facebook.katana", "messenger": "com.facebook.orca",
    "tiktok": "com.zhiliaoapp.musically", "telegram": "org.telegram.messenger",
    "x": "com.twitter.android", "twitter": "com.twitter.android",
    "snapchat": "com.snapchat.android", "play store": "com.android.vending",
    "camera": None, "settings": None, "calculator": None, "clock": None,
}
IOS_SCHEMES = {
    "whatsapp": "whatsapp://", "youtube": "youtube://", "spotify": "spotify://",
    "instagram": "instagram://", "facebook": "fb://", "telegram": "tg://",
    "x": "twitter://", "twitter": "twitter://", "maps": "maps://",
    "google maps": "comgooglemaps://", "gmail": "googlegmail://",
    "settings": "app-settings:", "mail": "mailto:", "phone": "tel:",
    "messages": "sms:", "music": "music://", "safari": "x-web-search://",
    "clock": "clock-alarm:", "calendar": "calshow:",
}
# Android system apps reached by intent action rather than package name
ANDROID_ACTIONS = {
    "camera": "android.media.action.STILL_IMAGE_CAMERA",
    "settings": "android.settings.SETTINGS",
    "clock": "android.intent.action.SHOW_ALARMS",
}


class DeviceActions:
    def __init__(self, data_dir: Optional[str] = None):
        self.platform = current_platform()
        self.data_dir = Path(data_dir) if data_dir else Path.home() / ".gink"
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # ================================================================
    # Android plumbing (Chaquopy)
    # ================================================================
    @staticmethod
    def _activity():
        try:
            import toga
            native = toga.App.app._impl.native
            if native is not None:
                return native
        except Exception:
            pass
        from java import jclass
        return jclass("org.beeware.android.MainActivity").singletonThis

    def _android_start(self, intent, new_task: bool = True):
        from java import jclass
        Intent = jclass("android.content.Intent")
        if new_task:
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        self._activity().startActivity(intent)

    def _android_view(self, uri: str):
        from java import jclass
        Intent = jclass("android.content.Intent")
        Uri = jclass("android.net.Uri")
        self._android_start(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))

    # ================================================================
    # iOS plumbing (rubicon-objc)
    # ================================================================
    @staticmethod
    def _ios_open(url: str) -> bool:
        from rubicon.objc import ObjCClass
        UIApplication = ObjCClass("UIApplication")
        NSURL = ObjCClass("NSURL")
        NSDictionary = ObjCClass("NSDictionary")
        ns_url = NSURL.URLWithString(url)
        if ns_url is None:
            return False
        app = UIApplication.sharedApplication
        if not app.canOpenURL(ns_url):
            # canOpenURL is False for schemes not in LSApplicationQueriesSchemes,
            # but openURL may still work, so try anyway.
            pass
        app.openURL(ns_url, options=NSDictionary.dictionary(), completionHandler=None)
        return True

    # ================================================================
    # Generic open
    # ================================================================
    def open_url(self, url: str) -> ActionResult:
        url = (url or "").strip()
        if not url:
            return ActionResult(False, "No link given.")
        if "://" not in url and not url.split(":", 1)[0] in {"mailto", "tel", "sms", "smsto"}:
            url = "https://" + url
        try:
            if self.platform == "android":
                self._android_view(url)
            elif self.platform == "ios":
                if not self._ios_open(url):
                    return ActionResult(False, f"iOS couldn't open {url}.")
            else:
                if not webbrowser.open(url):
                    return ActionResult(False, f"No app on this computer can open {url}.")
            return ActionResult(True, f"Opened {url}.")
        except Exception as e:
            return ActionResult(False, f"Couldn't open {url}: {e}")

    def open_file(self, path: str) -> ActionResult:
        try:
            if self.platform == "macos":
                ok, out = run(["open", path])
            elif self.platform == "windows":
                os.startfile(path)  # type: ignore[attr-defined]
                ok, out = True, ""
            elif self.platform == "linux":
                ok = spawn(["xdg-open", path]); out = ""
            else:
                return ActionResult(False, "Opening files isn't supported here.")
            return ActionResult(ok, "Opened." if ok else out)
        except Exception as e:
            return ActionResult(False, str(e))

    # ================================================================
    # Alarms & timers
    # ================================================================
    def set_alarm(self, hour: int, minute: int, label: str = "Wake up",
                  date: Optional[datetime] = None,
                  repeat_days: Optional[Iterable[str]] = None,
                  item_id: int = 0) -> ActionResult:
        """Real alarm. Android -> Clock app. Desktop -> OS scheduler. iOS -> not allowed."""
        when = date or self.next_occurrence(hour, minute)
        if self.platform == "android":
            if date and (date - datetime.now()) > timedelta(hours=24):
                return ActionResult(False, "Android's Clock app only sets alarms by time of "
                                           "day, not a specific date further out.")
            try:
                from java import jclass, jint, jboolean
                Intent = jclass("android.content.Intent")
                AlarmClock = jclass("android.provider.AlarmClock")
                intent = Intent(AlarmClock.ACTION_SET_ALARM)
                intent.putExtra(AlarmClock.EXTRA_HOUR, jint(hour))
                intent.putExtra(AlarmClock.EXTRA_MINUTES, jint(minute))
                intent.putExtra(AlarmClock.EXTRA_MESSAGE, label or "Gink alarm")
                intent.putExtra(AlarmClock.EXTRA_SKIP_UI, jboolean(True))
                days = _android_days(repeat_days)
                if days:
                    ArrayList = jclass("java.util.ArrayList")
                    Integer = jclass("java.lang.Integer")
                    lst = ArrayList()
                    for d in days:
                        lst.add(Integer.valueOf(jint(d)))
                    intent.putExtra(AlarmClock.EXTRA_DAYS, lst)
                self._android_start(intent)
                return ActionResult(True, f"Alarm set in your Clock app for {hour:02d}:{minute:02d}.",
                                    by_system=True)
            except Exception as e:
                return ActionResult(False, f"The Clock app refused the alarm: {e}")
        if self.platform == "ios":
            return ActionResult(False, "iOS doesn't let apps create Clock alarms.")
        ok, detail = system_alarms.schedule(item_id, label or "Wake up", when, alarm=True)
        if ok:
            return ActionResult(True, f"Alarm set for {when:%a %H:%M} ({detail}) — it rings "
                                      "even if Gink is closed.", by_system=True)
        return ActionResult(False, f"System scheduler unavailable: {detail}")

    def set_timer(self, seconds: int, label: str = "Timer") -> ActionResult:
        if self.platform == "android":
            try:
                from java import jclass, jint, jboolean
                Intent = jclass("android.content.Intent")
                AlarmClock = jclass("android.provider.AlarmClock")
                intent = Intent(AlarmClock.ACTION_SET_TIMER)
                intent.putExtra(AlarmClock.EXTRA_LENGTH, jint(int(seconds)))
                intent.putExtra(AlarmClock.EXTRA_MESSAGE, label or "Gink timer")
                intent.putExtra(AlarmClock.EXTRA_SKIP_UI, jboolean(True))
                self._android_start(intent)
                return ActionResult(True, f"Timer started in your Clock app ({_dur(seconds)}).",
                                    by_system=True)
            except Exception as e:
                return ActionResult(False, f"The Clock app refused the timer: {e}")
        return ActionResult(False, "no system timer")  # caller uses in-app timer

    @staticmethod
    def next_occurrence(hour: int, minute: int, now: Optional[datetime] = None) -> datetime:
        now = now or datetime.now()
        t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return t if t > now else t + timedelta(days=1)

    # ================================================================
    # Apps
    # ================================================================
    # nicknames people say -> the real app name (macOS)
    MAC_ALIASES = {
        "chrome": "Google Chrome", "google chrome": "Google Chrome", "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code", "code": "Visual Studio Code", "word": "Microsoft Word", "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint", "outlook": "Microsoft Outlook", "teams": "Microsoft Teams",
        "settings": "System Preferences", "system settings": "System Preferences", "preferences": "System Preferences",
        "app store": "App Store", "pycharm": "PyCharm", "android studio": "Android Studio", "whatsapp": "WhatsApp",
        "zoom": "zoom.us", "facetime": "FaceTime", "calculator": "Calculator", "notes": "Notes", "photos": "Photos",
        "music": "Music", "itunes": "Music", "mail": "Mail", "messages": "Messages", "maps": "Maps",
        "activity monitor": "Activity Monitor", "terminal": "Terminal", "finder": "Finder", "safari": "Safari",
    }
    WEBSITES = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "google": "https://www.google.com",
                "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com", "x": "https://x.com",
                "twitter": "https://x.com", "linkedin": "https://www.linkedin.com", "chatgpt": "https://chatgpt.com",
                "netflix": "https://www.netflix.com", "github": "https://github.com", "google drive": "https://drive.google.com",
                "google docs": "https://docs.google.com", "wikipedia": "https://www.wikipedia.org", "tiktok": "https://www.tiktok.com"}

    @staticmethod
    def installed_mac_apps():
        names = []
        for folder in ("/Applications", "/System/Applications", "/System/Applications/Utilities",
                       "/Applications/Utilities", os.path.expanduser("~/Applications")):
            try:
                names += [f[:-4] for f in os.listdir(folder) if f.endswith(".app")]
            except OSError:
                pass
        return sorted(set(names))

    def resolve_mac_app(self, name: str, installed=None):
        """'chrome' -> 'Google Chrome', 'photoshop' -> 'Adobe Photoshop 2024' (closest installed match)."""
        key = (name or "").strip().lower()
        apps = installed if installed is not None else self.installed_mac_apps()
        low = {a.lower(): a for a in apps}
        alias = self.MAC_ALIASES.get(key)
        if not apps:                                    # can't see the Applications folders: trust the nickname
            return alias
        for want in ([alias.lower()] if alias else []) + [key]:
            if want in low:
                return low[want]
        for want in ([alias.lower()] if alias else []) + [key]:
            contains = [a for a in apps if want and want in a.lower()]
            if contains:
                return min(contains, key=len)            # "pycharm" -> "PyCharm CE" if that's what's installed
        import difflib
        close = difflib.get_close_matches(key, list(low), n=1, cutoff=0.75)
        return low[close[0]] if close else None

    def open_app(self, name: str) -> ActionResult:
        key = (name or "").strip().lower()
        if not key:
            return ActionResult(False, "Which app?")
        try:
            if self.platform == "android":
                return self._android_open_app(key, name)
            if self.platform == "ios":
                scheme = IOS_SCHEMES.get(key)
                if not scheme:
                    return ActionResult(False, f"I don't know how to open {name} on iPhone yet.")
                return ActionResult(self._ios_open(scheme), f"Opening {name}.")
            if self.platform == "macos":
                real = self.resolve_mac_app(name) or name
                ok, out = run(["open", "-a", real])
                if ok:
                    return ActionResult(True, f"Opened {real}.")
                if key in self.WEBSITES:                       # "open youtube" -> the website
                    return self.open_url(self.WEBSITES[key])
                return ActionResult(False, f"I couldn't find an app called {name} on this Mac.")
            if self.platform == "windows":
                ok, out = run(["cmd", "/c", "start", "", name])
                if not ok and key in self.WEBSITES:
                    return self.open_url(self.WEBSITES[key])
                return ActionResult(ok, f"Opened {name}." if ok else f"Couldn't find {name}.")
            exe = shutil.which(key) or shutil.which(key.replace(" ", "-"))
            if exe:
                return ActionResult(spawn([exe]), f"Opened {name}.")
            ok, _ = run(["gtk-launch", key.replace(" ", "-")])
            return ActionResult(ok, f"Opened {name}." if ok else f"Couldn't find {name}.")
        except Exception as e:
            return ActionResult(False, f"Couldn't open {name}: {e}")

    def _android_open_app(self, key, name):
        from java import jclass
        Intent = jclass("android.content.Intent")
        if key in ANDROID_ACTIONS:
            self._android_start(Intent(ANDROID_ACTIONS[key]))
            return ActionResult(True, f"Opening {name}.")
        pkg = ANDROID_PACKAGES.get(key) or (key if "." in key else None)
        if pkg:
            try:
                intent = Intent(Intent.ACTION_MAIN)
                intent.addCategory(Intent.CATEGORY_LAUNCHER)
                intent.setPackage(pkg)
                self._android_start(intent)
                return ActionResult(True, f"Opening {name}.")
            except Exception:
                self._android_view(f"market://details?id={pkg}")
                return ActionResult(False, f"{name} isn't installed — opened it in the Play Store.")
        self._android_view(f"market://search?q={quote(name)}")
        return ActionResult(False, f"I don't know {name}'s package — searched the Play Store.")

    # ================================================================
    # Communication — always opens a pre-filled draft; YOU tap send.
    # ================================================================
    def compose_message(self, channel: str, to: str = "", body: str = "",
                        subject: str = "") -> ActionResult:
        channel = (channel or "sms").lower()
        to_clean = "".join(c for c in (to or "") if c.isdigit() or c == "+")
        if channel == "whatsapp":
            url = f"https://wa.me/{to_clean.lstrip('+')}?text={quote(body)}"
        elif channel == "email":
            url = f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"
        else:
            if self.platform == "android":
                try:
                    from java import jclass
                    Intent = jclass("android.content.Intent")
                    Uri = jclass("android.net.Uri")
                    intent = Intent(Intent.ACTION_SENDTO, Uri.parse(f"smsto:{to_clean}"))
                    intent.putExtra("sms_body", body)
                    self._android_start(intent)
                    return ActionResult(True, "SMS draft ready — tap send to deliver it.")
                except Exception as e:
                    return ActionResult(False, f"Couldn't open Messages: {e}")
            url = f"sms:{to_clean}&body={quote(body)}" if self.platform == "ios" \
                else f"sms:{to_clean}?body={quote(body)}"
        r = self.open_url(url)
        if r.ok:
            r.message = f"{channel.capitalize()} draft ready — tap send to deliver it."
        return r

    def make_call(self, number: str) -> ActionResult:
        n = "".join(c for c in (number or "") if c.isdigit() or c == "+")
        if not n:
            return ActionResult(False, "No phone number given.")
        if self.platform == "android":
            try:
                from java import jclass
                Intent = jclass("android.content.Intent")
                Uri = jclass("android.net.Uri")
                self._android_start(Intent(Intent.ACTION_DIAL, Uri.parse(f"tel:{n}")))
                return ActionResult(True, f"Dialer open with {n} — tap call.")
            except Exception as e:
                return ActionResult(False, f"Couldn't open the dialer: {e}")
        r = self.open_url(f"tel:{n}")
        if r.ok:
            r.message = f"Calling {n} — confirm in the dialer."
        return r

    # ================================================================
    # Calendar
    # ================================================================
    def add_calendar_event(self, title: str, start: datetime, end: Optional[datetime] = None,
                           location: str = "", notes: str = "") -> ActionResult:
        end = end or (start + timedelta(hours=1))
        if self.platform == "android":
            try:
                from java import jclass, jlong
                Intent = jclass("android.content.Intent")
                Events = jclass("android.provider.CalendarContract$Events")
                intent = Intent(Intent.ACTION_INSERT)
                intent.setData(Events.CONTENT_URI)
                intent.putExtra("beginTime", jlong(int(start.timestamp() * 1000)))
                intent.putExtra("endTime", jlong(int(end.timestamp() * 1000)))
                intent.putExtra(Events.TITLE, title)
                if location:
                    intent.putExtra(Events.EVENT_LOCATION, location)
                if notes:
                    intent.putExtra(Events.DESCRIPTION, notes)
                self._android_start(intent)
                return ActionResult(True, "Calendar event ready — tap Save to add it.")
            except Exception as e:
                return ActionResult(False, f"Couldn't open the calendar: {e}")
        if self.platform == "ios":
            return ActionResult(False, "Adding calendar events on iPhone isn't supported yet.")
        path = self.data_dir / f"gink-event-{int(start.timestamp())}.ics"
        path.write_text(_ics(title, start, end, location, notes), encoding="utf-8")
        r = self.open_file(str(path))
        if r.ok:
            r.message = "Event opened in your calendar app — confirm to add it."
        return r


# ---------------------------------------------------------------------------
def _dur(seconds: int) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = [f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s" if s else ""]
    return " ".join(p for p in parts if p) or "0s"


_DAY_NUM = {"sun": 1, "mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7}  # java.util.Calendar


def _android_days(days):
    if not days:
        return []
    out = []
    for d in days:
        n = _DAY_NUM.get(str(d).strip().lower()[:3])
        if n and n not in out:
            out.append(n)
    return out


def _ics(title, start, end, location, notes):
    def esc(s):
        return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    fmt = "%Y%m%dT%H%M%S"
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Gink//EN", "BEGIN:VEVENT",
        f"UID:gink-{int(start.timestamp())}@gink.local",
        f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        f"DTSTART:{start:{fmt}}", f"DTEND:{end:{fmt}}",
        f"SUMMARY:{esc(title)}", f"LOCATION:{esc(location)}", f"DESCRIPTION:{esc(notes)}",
        "BEGIN:VALARM", "TRIGGER:-PT15M", "ACTION:DISPLAY", f"DESCRIPTION:{esc(title)}", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR", "",
    ])
