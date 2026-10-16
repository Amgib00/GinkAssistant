"""
Things Gink can do ON this computer ("turn the volume down", "next song",
"take a screenshot", "find my CV", "turn on dark mode", "lock my screen",
"make a note", "how's my battery").

macOS first (AppleScript / built-in tools); Windows and Linux where there's
a standard way; phones say plainly that it isn't available.

SAFETY: text from the conversation (a note, an app name, a search) is passed
to AppleScript as an ARGUMENT (`on run argv`), never pasted into the script,
so quotes or code in it can't run anything. Commands are run without a shell.
Nothing here deletes anything.
"""

import os
import shutil
import sys
import time
from datetime import datetime
from typing import List, Optional

from ._shell import run

MAC, WIN, LINUX = sys.platform == "darwin", sys.platform.startswith("win"), sys.platform.startswith("linux")
MOBILE = hasattr(sys, "getandroidapilevel") or sys.platform == "ios"


def _ok(msg, **extra):
    return {"ok": True, "message": msg, **extra}


def _no(msg):
    return {"ok": False, "message": msg}


def osa(script_lines: List[str], *args: str, timeout: int = 15):
    """Run AppleScript with the user's text passed as arguments (item n of argv)."""
    cmd = ["osascript"]
    for line in ["on run argv"] + script_lines + ["end run"]:
        cmd += ["-e", line]
    return run(cmd + [str(a) for a in args], timeout=timeout)


class ComputerControl:
    def __init__(self, files_dir: Optional[str] = None):
        self.files_dir = files_dir
        self.last_files: List[str] = []           # from the last search -> "open number 2"

    # ---------------- sound ----------------
    def set_volume(self, level: Optional[int] = None, action: str = "") -> dict:
        action = (action or "").lower()
        if MOBILE:
            return _no("I can't change the volume on this phone yet.")
        if MAC:
            if action in ("mute", "unmute"):
                ok, out = osa([f"set volume output muted {'true' if action == 'mute' else 'false'}"])
                return _ok("Muted." if action == "mute" else "Sound is back on.") if ok else _no(out)
            ok, cur = osa(["return output volume of (get volume settings)"])
            current = int(cur) if ok and cur.strip().isdigit() else 50
            if level is None:
                level = current + 15 if action == "up" else current - 15 if action == "down" else current
            level = max(0, min(100, int(level)))
            ok, out = osa(["set volume output volume (item 1 of argv as integer)", "set volume output muted false"], str(level))
            return _ok(f"Volume set to {level}%.", level=level) if ok else _no(out)
        if LINUX and shutil.which("amixer"):
            arg = {"mute": "mute", "unmute": "unmute", "up": "10%+", "down": "10%-"}.get(action, f"{max(0, min(100, int(level or 50)))}%")
            ok, out = run(["amixer", "-q", "set", "Master", arg])
            return _ok("Done.") if ok else _no(out)
        return _no("I can't change the volume on this computer yet.")

    # ---------------- music ----------------
    def media_control(self, action: str) -> dict:
        action = (action or "").lower().replace(" ", "_")
        verb = {"play": "play", "pause": "pause", "play_pause": "playpause", "toggle": "playpause", "resume": "play",
                "next": "next track", "skip": "next track", "previous": "previous track", "back": "previous track"}.get(action)
        if not verb:
            return _no("I can play, pause, skip to the next song or go back.")
        if not MAC:
            return _no("Controlling music works on Mac for now.")
        for app in ("Spotify", "Music"):
            ok, running = osa(["return application (item 1 of argv) is running"], app)
            if ok and running.strip() == "true":
                # the app name must be written into the script (its commands are looked up when it
                # compiles) -- safe: it's one of these two fixed names, never text from the chat
                ok, out = osa([f'tell application "{app}" to {verb}'])
                if ok:
                    label = {"play": "Playing", "pause": "Paused", "playpause": "Done", "next track": "Next song",
                             "previous track": "Previous song"}[verb]
                    return _ok(f"{label} in {app}.")
                return _no(out)
        if verb in ("play", "playpause"):
            ok, out = osa(["tell application \"Music\" to play"])
            return _ok("Playing in Music.") if ok else _no("Open Spotify or Music first, then ask me again.")
        return _no("No music app is open. Open Spotify or Music first.")

    # ---------------- screenshot ----------------
    def take_screenshot(self) -> dict:
        if MOBILE:
            return _no("Use your phone's buttons to take a screenshot.")
        folder = self.files_dir or os.path.expanduser("~/Desktop")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, datetime.now().strftime("Screenshot %Y-%m-%d at %H.%M.%S.png"))
        if MAC:
            ok, out = run(["screencapture", "-x", path])
        elif LINUX and shutil.which("gnome-screenshot"):
            ok, out = run(["gnome-screenshot", "-f", path])
        elif WIN:
            try:
                from PIL import ImageGrab
                ImageGrab.grab().save(path)
                ok, out = True, ""
            except Exception as exc:
                ok, out = False, str(exc)
        else:
            return _no("I can't take screenshots on this computer yet.")
        if not ok or not os.path.exists(path):
            hint = " (allow Screen Recording for Gink/Terminal in System Settings \u2192 Privacy & Security)" if MAC else ""
            return _no("The screenshot didn't work" + hint + ".")
        from ..file_maker import MadeFile
        made = MadeFile(path=path, name=os.path.basename(path), kind="png", size=os.path.getsize(path))
        return _ok(f"Here's your screenshot:\n\n{made.card_markdown()}", file=made.name, path=path)

    # ---------------- files ----------------
    def find_files(self, query: str, limit: int = 8) -> dict:
        query = (query or "").strip()
        if not query:
            return _no("What should I look for?")
        if MOBILE:
            return _no("I can't search files on this phone yet.")
        home = os.path.expanduser("~")
        found: List[str] = []
        if MAC:
            ok, out = run(["mdfind", "-onlyin", home, "-name", query], timeout=15)
            found = [p for p in out.splitlines() if p.startswith("/") and "/Library/" not in p and "/." not in p] if ok else []
        if not found:                                     # fallback: walk the usual folders (all platforms)
            q = query.lower()
            for base in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Movies"):
                root = os.path.join(home, base)
                for dirpath, dirs, files in os.walk(root):
                    dirs[:] = [d for d in dirs if not d.startswith(".")][:200]
                    for f in files:
                        if q in f.lower():
                            found.append(os.path.join(dirpath, f))
                    if len(found) >= limit * 3:
                        break
        found = sorted(set(found), key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)[:limit]
        self.last_files = list(found)
        if not found:
            return _no(f"I couldn't find any files matching \u201c{query}\u201d.")
        lines = "\n".join(f"{i + 1}. {os.path.basename(p)} \u2014 {os.path.dirname(p).replace(home, '~')}" for i, p in enumerate(found))
        return _ok(f"I found {len(found)} file{'s' if len(found) != 1 else ''}:\n\n{lines}\n\nSay \u201copen number 1\u201d (or the name) to open one.",
                   files=found)

    def resolve_file(self, which: str) -> Optional[str]:
        """'1' / 'number 2' / a name from the last search / a full path -> a real file path."""
        w = (which or "").strip().strip('"')
        import re
        m = re.search(r"\d+", w)
        if m and self.last_files and 1 <= int(m.group()) <= len(self.last_files) and len(w) <= 12:
            return self.last_files[int(m.group()) - 1]
        for p in self.last_files:
            if w and w.lower() in os.path.basename(p).lower():
                return p
        p = os.path.expanduser(w)
        return p if os.path.isfile(p) else None

    # ---------------- Finder, Terminal, settings ----------------
    def _folder(self, name: str) -> Optional[str]:
        key = (name or "").strip().lower().replace(" folder", "").strip() or "home"
        if key in STD_FOLDERS:
            return os.path.expanduser(STD_FOLDERS[key])
        p = os.path.expanduser(name.strip())
        if os.path.isdir(p):
            return p
        home = os.path.expanduser("~")
        if MAC:                                         # a folder anywhere in the home folder, by name
            ok, out = run(["mdfind", "-onlyin", home, f"kMDItemContentType == 'public.folder' && kMDItemFSName == '{_md_escape(name)}'c"], timeout=10)
            hits = [x for x in out.splitlines() if x.startswith("/") and "/Library/" not in x and "/." not in x] if ok else []
            if hits:
                return min(hits, key=len)
        for base in ("", "Desktop", "Documents", "Downloads", "PycharmProjects", "Projects", "Developer"):
            cand = os.path.join(home, base, name.strip())
            if os.path.isdir(cand):
                return cand
        return None

    def open_folder(self, name: str = "home") -> dict:
        if MOBILE:
            return _no("Opening folders works on computers.")
        path = self._folder(name)
        if not path or not os.path.isdir(path):
            return _no(f"I couldn't find a folder called \u201c{name}\u201d.")
        cmd = ["open", path] if MAC else ["explorer", path] if WIN else ["xdg-open", path]
        ok, out = run(cmd)
        return _ok(f"Opened {os.path.basename(path.rstrip('/')) or 'your home folder'} in {'Finder' if MAC else 'your file manager'}.",
                   path=path) if ok or WIN else _no(out)

    def reveal_in_finder(self, which: str = "") -> dict:
        path = self.resolve_file(which) if which else (self.last_files[0] if self.last_files else None)
        if not path:
            return _no("Which file? Search for it first (\u201cfind my ...\u201d).")
        if MAC:
            ok, out = run(["open", "-R", path])
        elif WIN:
            ok, out = run(["explorer", "/select,", path])
        else:
            ok, out = run(["xdg-open", os.path.dirname(path)])
        return _ok(f"Showing {os.path.basename(path)}.") if ok or WIN else _no(out)

    def open_terminal(self, folder: str = "") -> dict:
        """Opens Terminal (in a folder). It never types or runs commands."""
        path = self._folder(folder) if folder else os.path.expanduser("~")
        if folder and not path:
            return _no(f"I couldn't find a folder called \u201c{folder}\u201d.")
        if MAC:
            ok, out = run(["open", "-a", "Terminal", path])
        elif WIN:
            ok, out = run(["cmd", "/c", "start", "", "cmd", "/K", "cd", "/d", path])
        elif shutil.which("x-terminal-emulator"):
            ok, out = run(["x-terminal-emulator", "--working-directory", path])
        else:
            return _no("I couldn't find a terminal app.")
        return _ok(f"Opened Terminal in {os.path.basename(path.rstrip('/')) or 'your home folder'}.") if ok else _no(out)

    def open_settings_pane(self, pane: str) -> dict:
        key = (pane or "").strip().lower().replace(" settings", "").replace(" preferences", "")
        if not MAC:
            return _no("Opening settings pages works on Mac for now.")
        target = SETTINGS_PANES.get(key)
        url = f"x-apple.systempreferences:{target}" if target else "x-apple.systempreferences:"
        ok, out = run(["open", url])
        return _ok(f"Opened {pane.strip().title()} settings." if target else "Opened System Preferences.") if ok else _no(out)

    def sleep_computer(self) -> dict:
        if MAC:
            ok, out = run(["pmset", "sleepnow"])
            return _ok("Putting your Mac to sleep.") if ok else _no(out)
        if WIN:
            ok, out = run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return _ok("Going to sleep.") if ok else _no(out)
        if LINUX and shutil.which("systemctl"):
            ok, out = run(["systemctl", "suspend"])
            return _ok("Going to sleep.") if ok else _no(out)
        return _no("I can't put this device to sleep.")

    def show_recent_files(self, days: int = 3) -> dict:
        files = recent_files(days=max(1, min(int(days or 3), 30)), limit=8)
        self.last_files = files
        if not files:
            return _no(f"I didn't find any documents changed in the last {days} days.")
        home = os.path.expanduser("~")
        lines = "\n".join(f"{i + 1}. {os.path.basename(p)} \u2014 {os.path.dirname(p).replace(home, '~')} "
                          f"({_ago(os.path.getmtime(p))})" for i, p in enumerate(files))
        return _ok(f"Recently changed:\n\n{lines}\n\nSay \u201copen number 1\u201d to open one.", files=files)

    def read_clipboard(self) -> dict:
        try:
            import subprocess
            if MAC:
                text = subprocess.run(["pbpaste"], capture_output=True, timeout=5).stdout.decode("utf-8", "replace")
            elif WIN:
                text = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, timeout=8).stdout.decode("utf-8", "replace")
            elif LINUX and shutil.which("xclip"):
                text = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=5).stdout.decode("utf-8", "replace")
            else:
                return _no("I can't read the clipboard here.")
        except Exception as exc:
            return _no(f"Reading the clipboard didn't work ({exc.__class__.__name__}).")
        text = text.strip()
        if not text:
            return _no("Your clipboard is empty (or holds a picture, which I can't read).")
        short = text[:4000]
        more = "\u2026" if len(short) > 500 else ""
        return _ok(f"On your clipboard:\n\n> {short[:500]}{more}", text=short)

    def search_in_browser(self, query: str) -> dict:
        from urllib.parse import quote_plus
        import webbrowser
        q = (query or "").strip()
        if not q:
            return _no("What should I search for?")
        try:
            webbrowser.open("https://www.google.com/search?q=" + quote_plus(q))
        except Exception as exc:
            return _no(f"I couldn't open the browser ({exc.__class__.__name__}).")
        return _ok(f"Searching Google for \u201c{q}\u201d.")

    # ---------------- apps & appearance ----------------
    def quit_app(self, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            return _no("Which app should I quit?")
        if name.lower() in ("gink", "gink assistant", "finder"):
            return _no(f"I won't quit {name}.")
        if MAC:
            ok, running = osa(["return application (item 1 of argv) is running"], name)
            if not (ok and running.strip() == "true"):
                return _no(f"{name} isn't open.")
            ok, out = osa(["tell application (item 1 of argv) to quit"], name)      # the app asks to save unsaved work
            return _ok(f"Quit {name}.") if ok else _no(out)
        if WIN:
            exe = name if name.lower().endswith(".exe") else name + ".exe"
            ok, out = run(["taskkill", "/IM", exe])                                # polite close, no /F
            return _ok(f"Asked {name} to close.") if ok else _no(f"{name} isn't open.")
        return _no("Quitting apps works on Mac and Windows for now.")

    def set_dark_mode(self, mode: str = "toggle") -> dict:
        if not MAC:
            return _no("Switching dark mode works on Mac for now.")
        mode = (mode or "toggle").lower()
        value = {"on": "true", "dark": "true", "off": "false", "light": "false"}.get(mode, "not dark mode")
        ok, out = osa(["tell application \"System Events\" to tell appearance preferences to set dark mode to " + value,
                       "tell application \"System Events\" to tell appearance preferences to return dark mode"])
        if not ok:
            return _no("I couldn't change it" + (" \u2014 allow Gink to control System Events (System Settings \u2192 Privacy & Security \u2192 Automation)." if "not allowed" in out.lower() else f": {out}"))
        return _ok("Dark mode is on." if out.strip() == "true" else "Light mode is on.")

    def lock_screen(self) -> dict:
        if MAC:
            ok, out = run(["pmset", "displaysleepnow"])
            return _ok("Locking your screen.") if ok else _no(out)
        if WIN:
            ok, out = run(["rundll32.exe", "user32.dll,LockWorkStation"])
            return _ok("Locking your screen.") if ok else _no(out)
        if LINUX and shutil.which("loginctl"):
            ok, out = run(["loginctl", "lock-session"])
            return _ok("Locking your screen.") if ok else _no(out)
        return _no("I can't lock this device.")

    # ---------------- notes & clipboard ----------------
    def create_note(self, title: str, body: str = "") -> dict:
        title = (title or "").strip() or "Note from Gink"
        if not MAC:
            if self.files_dir:
                from ..file_maker import make_file
                made = make_file(self.files_dir, "txt", title, (body or title))
                return _ok(f"Saved your note:\n\n{made.card_markdown()}", file=made.name)
            return _no("Notes work on Mac for now.")
        html = "<h1>" + _html_escape(title) + "</h1>" + "".join(f"<div>{_html_escape(l) or '<br>'}</div>" for l in (body or "").splitlines())
        ok, out = osa(['tell application "Notes" to make new note with properties {body:(item 1 of argv)}'], html, timeout=20)
        if ok:
            return _ok(f"Added \u201c{title}\u201d to Notes.")
        return _no("I couldn't add it to Notes" + (" \u2014 allow Gink to control Notes in System Settings \u2192 Privacy & Security \u2192 Automation." if "not allowed" in out.lower() else "."))

    def copy_to_clipboard(self, text: str) -> dict:
        text = text or ""
        try:
            if MAC:
                import subprocess
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5, check=True)
            elif WIN:
                import subprocess
                subprocess.run(["clip"], input=text.encode("utf-16le"), timeout=5, check=True)
            elif LINUX and shutil.which("xclip"):
                import subprocess
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), timeout=5, check=True)
            else:
                return _no("I can't use the clipboard here.")
        except Exception as exc:
            return _no(f"Copying didn't work ({exc.__class__.__name__}).")
        return _ok("Copied to your clipboard.")

    # ---------------- status ----------------
    def system_status(self) -> dict:
        bits = []
        if MAC:
            ok, out = run(["pmset", "-g", "batt"])
            if ok and "%" in out:
                import re
                m = re.search(r"(\d+)%;\s*([a-zA-Z ]+);", out)
                if m:
                    state = m.group(2).strip()
                    bits.append(f"\U0001F50B Battery {m.group(1)}% ({'charging' if state == 'charging' else 'charged' if state in ('charged', 'finishing charge') else 'on battery'})")
            ok, out = run(["networksetup", "-getairportnetwork", "en0"])
            if ok and ":" in out and "not associated" not in out.lower():
                bits.append(f"\U0001F4F6 Wi-Fi: {out.split(':', 1)[1].strip()}")
            ok, out = run(["sw_vers", "-productVersion"])
            if ok:
                bits.append(f"\U0001F4BB macOS {out.strip()}")
        try:
            du = shutil.disk_usage(os.path.expanduser("~"))
            bits.append(f"\U0001F4BE {du.free / 1e9:.0f} GB free of {du.total / 1e9:.0f} GB")
        except Exception:
            pass
        if not bits:
            return _no("I can't read this device's status.")
        return _ok("\n".join(f"- {b}" for b in bits))


DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".key", ".pages", ".numbers", ".txt", ".md",
           ".csv", ".py", ".js", ".ts", ".html", ".css", ".java", ".kt", ".swift", ".ipynb", ".psd", ".fig", ".sketch",
           ".rtf", ".odt", ".json", ".sql"}
SETTINGS_PANES = {   # x-apple.systempreferences URLs (System Preferences / System Settings)
    "wifi": "com.apple.preference.network", "wi-fi": "com.apple.preference.network", "network": "com.apple.preference.network",
    "internet": "com.apple.preference.network", "bluetooth": "com.apple.preferences.Bluetooth",
    "sound": "com.apple.preference.sound", "volume": "com.apple.preference.sound", "display": "com.apple.preference.displays",
    "displays": "com.apple.preference.displays", "screen": "com.apple.preference.displays",
    "notifications": "com.apple.preference.notifications", "notification": "com.apple.preference.notifications",
    "battery": "com.apple.preference.energysaver", "energy": "com.apple.preference.energysaver",
    "privacy": "com.apple.preference.security?Privacy", "security": "com.apple.preference.security",
    "keyboard": "com.apple.preference.keyboard", "trackpad": "com.apple.preference.trackpad",
    "mouse": "com.apple.preference.mouse", "appearance": "com.apple.preference.general", "general": "com.apple.preference.general",
    "dock": "com.apple.preference.dock", "software update": "com.apple.preferences.softwareupdate",
    "update": "com.apple.preferences.softwareupdate", "users": "com.apple.preferences.users",
    "date and time": "com.apple.preference.datetime", "time": "com.apple.preference.datetime",
    "language": "com.apple.Localization", "accessibility": "com.apple.preference.universalaccess",
}
STD_FOLDERS = {"desktop": "~/Desktop", "documents": "~/Documents", "downloads": "~/Downloads", "pictures": "~/Pictures",
               "photos folder": "~/Pictures", "music": "~/Music", "movies": "~/Movies", "videos": "~/Movies",
               "home": "~", "home folder": "~", "applications": "/Applications", "apps": "/Applications",
               "icloud": "~/Library/Mobile Documents/com~apple~CloudDocs", "icloud drive": "~/Library/Mobile Documents/com~apple~CloudDocs",
               "trash": "~/.Trash"}


def recent_files(days: int = 2, limit: int = 6, folders=("Desktop", "Documents", "Downloads")) -> List[str]:
    """Documents / code / designs changed in the last few days (newest first)."""
    home = os.path.expanduser("~")
    cutoff = time.time() - days * 86400
    found = []
    if MAC:
        roots = [os.path.join(home, f) for f in folders]
        ok, out = run(["mdfind", f"kMDItemFSContentChangeDate >= $time.today(-{int(days)})"] +
                      sum([["-onlyin", r] for r in roots], []), timeout=15)
        if ok:
            found = [p for p in out.splitlines() if p.startswith("/")]
    if not found:
        for f in folders:
            for dirpath, dirs, files in os.walk(os.path.join(home, f)):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv", "build")]
                for name in files:
                    p = os.path.join(dirpath, name)
                    try:
                        if os.path.getmtime(p) >= cutoff:
                            found.append(p)
                    except OSError:
                        pass
    docs = [p for p in found if os.path.splitext(p)[1].lower() in DOC_EXT and "/." not in p and os.path.isfile(p)]
    docs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return docs[:limit]


def _md_escape(s: str) -> str:
    """For a Spotlight query string: no quotes or backslashes from user text."""
    return (s or "").replace("\\", "").replace("'", "").replace('"', "").strip()


def _ago(ts: float) -> str:
    d = time.time() - ts
    if d < 3600:
        return f"{max(1, int(d // 60))} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    return "yesterday" if d < 2 * 86400 else f"{int(d // 86400)} days ago"


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
