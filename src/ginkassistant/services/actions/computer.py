"""
Things Gink can do ON this computer ("turn the volume down", "next song",
"take a screenshot", "find my CV", "turn on dark mode", "lock my screen",
"make a note", "how's my battery").

macOS first (AppleScript / built-in tools); Windows and Linux where there's
a standard way; phones say plainly that it isn't available.

SAFETY: text from the conversation (a note, an app name, a search) is passed
to AppleScript as an ARGUMENT (`on run argv`), never pasted into the script,
so quotes or code in it can't run anything. Commands are run without a shell.
Nothing here deletes anything. Writing and editing text files (the agent's "write, edit" tools) stays inside the
person's home folder, never touches hidden or system folders, and keeps a copy of the old version first
(Gink's "file backups" folder), so every change can be undone.
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
                ok = True
            except Exception:
                ok = False
        else:
            return _no("I can't take screenshots on this computer yet.")
        if not ok or not os.path.exists(path):
            hint = " (allow Screen Recording for Gink/Terminal in System Settings \u2192 Privacy & Security)" if MAC else ""
            return _no("The screenshot didn't work" + hint + ".")
        from ..file_maker import MadeFile
        made = MadeFile(path=path, name=os.path.basename(path), kind="png", size=os.path.getsize(path))
        return _ok(f"Here's your screenshot:\n\n{made.card_markdown()}", file=made.name, path=path)

    def screen_image(self, max_side: int = 1600) -> str:
        """What's on the screen right now, as a JPEG data URL (for Live screen view and "look at my screen"), or "".
        Nothing is saved: the picture is made in a temporary file and deleted at once."""
        if MOBILE:
            return ""
        import base64
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png", prefix="gink-screen-")
        os.close(fd)
        try:
            ok = False
            if MAC:
                ok, _ = run(["screencapture", "-x", "-C", path], timeout=15)
            if not MAC or not ok:
                try:
                    from PIL import ImageGrab
                    ImageGrab.grab().save(path)
                    ok = True
                except Exception:
                    ok = False
            if not ok and LINUX:
                for cmd in (["gnome-screenshot", "-f", path], ["grim", path], ["import", "-window", "root", path],
                            ["spectacle", "-b", "-n", "-o", path]):
                    if shutil.which(cmd[0]):
                        ok, _ = run(cmd, timeout=15)
                        if ok:
                            break
            if not ok or not os.path.getsize(path):
                return ""
            try:
                from io import BytesIO
                from PIL import Image
                with Image.open(path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((max_side, max_side))
                    buf = BytesIO()
                    im.save(buf, "JPEG", quality=80)
                return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            except Exception:
                with open(path, "rb") as f:
                    raw = f.read()
                return "data:image/png;base64," + base64.b64encode(raw).decode() if len(raw) < 8_000_000 else ""
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

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
        if os.path.isabs(p) and os.path.isdir(p):        # only full paths as they are ("GinkAssistant" is a name to find)
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

    # ---------------- apps: find, list, close; editors and IDEs ----------------
    def installed_apps(self) -> List[str]:
        """The apps installed on this computer (names people would say)."""
        names = set()
        if MAC:
            from .device import DeviceActions
            names.update(DeviceActions.installed_mac_apps())
        elif WIN:
            roots = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                     os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
            for root in roots:
                for _dir, _sub, files in os.walk(root):
                    names.update(f[:-4] for f in files if f.lower().endswith(".lnk") and "uninstall" not in f.lower())
        elif LINUX:
            for root in ("/usr/share/applications", os.path.expanduser("~/.local/share/applications"),
                         "/var/lib/flatpak/exports/share/applications", "/var/lib/snapd/desktop/applications"):
                try:
                    files = os.listdir(root)
                except OSError:
                    continue
                for f in files:
                    if f.endswith(".desktop"):
                        names.add(_desktop_name(os.path.join(root, f)) or f[:-8])
        return sorted(n for n in names if n)

    def find_app(self, query: str = "") -> dict:
        """Installed apps whose names match `query` (all of them, briefly, when it's empty)."""
        if MOBILE:
            return _no("Finding apps works on computers.")
        q = (query or "").strip().lower()
        apps = self.installed_apps()
        hits = [a for a in apps if not q or q in a.lower()]
        if q and not hits:
            import difflib
            hits = difflib.get_close_matches(q, apps, n=5, cutoff=0.6)
        if not hits:
            return _no(f"I couldn't find an app called \u201c{query}\u201d on this computer.")
        shown = hits[:40]
        more = f" (and {len(hits) - len(shown)} more)" if len(hits) > len(shown) else ""
        return _ok(("Installed apps" + (f" matching \u201c{query}\u201d" if q else "") + f": {', '.join(shown)}{more}."),
                   apps=shown)

    def running_apps(self) -> dict:
        """The apps open right now (windows the person can see)."""
        if MOBILE:
            return _no("Listing open apps works on computers.")
        names: List[str] = []
        if MAC:
            ok, out = osa(['tell application "System Events" to get name of every application process whose background only is false'])
            if ok:
                names = [x.strip() for x in out.split(",") if x.strip()]
            else:
                return _no("I couldn't list the open apps" + (" \u2014 allow Gink to control System Events (System Settings \u2192 "
                           "Privacy & Security \u2192 Automation)." if "not allowed" in out.lower() else "."))
        elif WIN:
            ok, out = run(["powershell", "-NoProfile", "-Command",
                           "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty ProcessName"], timeout=15)
            names = [x.strip() for x in out.splitlines() if x.strip()] if ok else []
        elif LINUX and shutil.which("wmctrl"):
            ok, out = run(["wmctrl", "-l", "-x"])
            names = [ln.split()[2].split(".")[-1] for ln in out.splitlines() if len(ln.split()) > 2] if ok else []
        elif LINUX:
            ok, out = run(["ps", "-u", str(os.getuid()), "-o", "comm="])          # this person's own programs
            names = [x.strip() for x in out.splitlines() if x.strip() and x.strip() not in ("ps", "bash", "sh", "zsh")][:200] if ok else []
        names = sorted(set(names), key=str.lower)
        if not names:
            return _no("I couldn't see which apps are open.")
        return _ok(f"Open now: {', '.join(names)}.", apps=names)

    def open_in_editor(self, path: str = "", editor: str = "") -> dict:
        """Open a file or folder in a code editor or IDE: VS Code, PyCharm, Xcode, Android Studio, Sublime Text,
        Cursor, Zed, IntelliJ, Notepad++... (the one asked for, else the first one installed)."""
        if MOBILE:
            return _no("Editors and IDEs open on computers.")
        target = self.resolve_path(path) if path else None
        if path and not target:
            return _no(f"I couldn't find \u201c{path}\u201d. Search for it first (\u201cfind my ...\u201d) or give the full path.")
        installed = {a.lower(): a for a in self.installed_apps()} if MAC else {}
        asked = (editor or "").strip()
        wanted = [EDITOR_ALIASES.get(asked.lower(), asked.lower())] if asked else []
        for key in wanted + [k for k in EDITORS if k not in wanted]:
            spec, mine = EDITORS.get(key, {}), key in wanted
            if MAC:
                app = spec.get("mac", "") if spec else asked
                if not app:
                    continue
                real = installed.get(app.lower()) or next((v for k, v in installed.items() if app.lower() in k), None)
                if not real and not mine:
                    continue
                ok, out = run(["open", "-a", real or app] + ([target] if target else []))
                label = real or app
            else:
                exe = shutil.which(spec.get("cmd", "") or key) or shutil.which(key.replace(" ", ""))
                if not exe:
                    if mine:
                        return _no(f"I couldn't find {asked} on this computer.")
                    continue
                from ._shell import spawn
                ok, out, label = spawn([exe] + ([target] if target else [])), "", key.title() if spec else asked
            if ok:
                where = os.path.basename(target.rstrip("/\\")) if target else ""
                return _ok(f"Opened {where + ' in ' if where else ''}{label}.", path=target or "")
            if mine:
                return _no(f"I couldn't open {asked}: {out}")
        if target:                                         # no editor found: the system's own app for it
            ok, out = run(["open", target] if MAC else ["xdg-open", target] if LINUX else ["cmd", "/c", "start", "", target])
            return _ok(f"Opened {os.path.basename(target)}.") if ok else _no(out)
        return _no("I couldn't find a code editor. Install one (for example Visual Studio Code) and ask again.")

    # ---------------- text files: read, write, edit (inside the home folder, with a backup first) ----------------
    def resolve_path(self, which: str) -> Optional[str]:
        """A file or folder: a number or name from the last search, ~/..., or a full path inside the home folder."""
        w = (which or "").strip().strip('"')
        hit = self.resolve_file(w) if w else None
        if hit:
            return hit
        p = os.path.abspath(os.path.expanduser(w)) if w else ""
        if p and os.path.exists(p):
            return p
        folder = self._folder(w) if w else None
        return folder if folder and os.path.isdir(folder) else None

    def _writable(self, path: str) -> Optional[str]:
        """Why Gink won't write here (None = fine): only inside the home folder, never hidden or system folders."""
        home = os.path.realpath(os.path.expanduser("~"))
        real = os.path.realpath(path)
        if not (real == home or real.startswith(home + os.sep)):
            return "I only write files inside your home folder."
        parts = os.path.relpath(real, home).split(os.sep)
        if any(p.startswith(".") for p in parts) or (parts and parts[0] in ("Library", "AppData")):
            return "I don't change hidden or system files (like settings, keys or app data)."
        return None

    def _backup(self, path: str) -> str:
        folder = os.path.join(self.files_dir or os.path.expanduser("~/Documents"), "file backups")
        os.makedirs(folder, exist_ok=True)
        copy = os.path.join(folder, datetime.now().strftime("%Y-%m-%d %H.%M.%S ") + os.path.basename(path))
        shutil.copy2(path, copy)
        return copy

    def read_text_file(self, which: str, start_line: int = 1, max_lines: int = 400) -> dict:
        path = self.resolve_path(which)
        if not path or not os.path.isfile(path):
            return _no(f"I couldn't find the file \u201c{which}\u201d.")
        if os.path.getsize(path) > 5_000_000:
            return _no("That file is too big to read here (over 5 MB).")
        with open(path, "rb") as f:
            raw = f.read()
        if b"\x00" in raw[:4096]:
            return _no(f"{os.path.basename(path)} isn't a text file.")
        lines = raw.decode("utf-8", "replace").splitlines()
        start = max(1, int(start_line or 1))
        part = lines[start - 1:start - 1 + max(1, min(int(max_lines or 400), 2000))]
        numbered = "\n".join(f"{start + i:>5}  {ln}" for i, ln in enumerate(part))
        more = len(lines) - (start - 1 + len(part))
        return _ok(f"{path} ({len(lines)} lines){' -- ' + str(more) + ' more after this' if more > 0 else ''}:\n{numbered}",
                   path=path, lines=len(lines))

    def write_text_file(self, path: str, content: str, overwrite: bool = False) -> dict:
        """Create a text or code file (a name alone goes in Documents). An existing file is replaced only with
        overwrite=true, after a backup."""
        raw = (path or "").strip().strip('"')
        if not raw:
            return _no("What should the file be called?")
        full = os.path.abspath(os.path.expanduser(raw if (os.sep in raw or raw.startswith("~")) else os.path.join("~/Documents", raw)))
        why = self._writable(full)
        if why:
            return _no(why)
        backup = ""
        if os.path.exists(full):
            if not overwrite:
                return _no(f"{os.path.basename(full)} already exists. Say so if I should replace it (I keep a backup), or edit it instead.")
            backup = self._backup(full)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(content or "")
        self.last_files = [full]
        return _ok(f"{'Replaced' if backup else 'Created'} {full.replace(os.path.expanduser('~'), '~')}"
                   + (f" (the old version is in {os.path.basename(os.path.dirname(backup))})" if backup else "") + ".",
                   path=full, backup=backup)

    def edit_text_file(self, which: str, find: str, replace: str, all: bool = False) -> dict:
        """Replace an exact piece of a text file (once, or everywhere with all=true), after a backup."""
        path = self.resolve_path(which)
        if not path or not os.path.isfile(path):
            return _no(f"I couldn't find the file \u201c{which}\u201d.")
        why = self._writable(path)
        if why:
            return _no(why)
        if not find:
            return _no("Say exactly which text to change.")
        with open(path, encoding="utf-8", errors="strict", newline="") as f:
            text = f.read()
        n = text.count(find)
        if n == 0:
            return _no(f"That exact text isn't in {os.path.basename(path)}. Read the file first and copy it exactly.")
        if n > 1 and not all:
            return _no(f"That text appears {n} times in {os.path.basename(path)}: include more of the line, or set all=true.")
        backup = self._backup(path)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(find, replace or "") if all else text.replace(find, replace or "", 1))
        return _ok(f"Changed {os.path.basename(path)} ({n if all else 1} place{'s' if (n if all else 1) != 1 else ''}; "
                   f"the old version is kept in file backups).", path=path, backup=backup, replaced=n if all else 1)

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
        if LINUX:                                                                # polite: windows close, then the app
            if shutil.which("wmctrl"):
                ok, out = run(["wmctrl", "-c", name])
                if ok:
                    return _ok(f"Asked {name} to close.")
            ok, out = run(["pkill", "-TERM", "-i", "-x", name.replace(" ", "-")])
            return _ok(f"Asked {name} to close.") if ok else _no(f"{name} isn't open.")
        return _no("Quitting apps works on computers.")

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


# Code editors and IDEs, the order Gink tries them in: Mac app name, Windows/Linux command.
EDITORS = {
    "visual studio code": {"mac": "Visual Studio Code", "cmd": "code"}, "cursor": {"mac": "Cursor", "cmd": "cursor"},
    "pycharm": {"mac": "PyCharm", "cmd": "pycharm"}, "intellij idea": {"mac": "IntelliJ IDEA", "cmd": "idea"},
    "android studio": {"mac": "Android Studio", "cmd": "studio"}, "xcode": {"mac": "Xcode", "cmd": "xed"},
    "sublime text": {"mac": "Sublime Text", "cmd": "subl"}, "zed": {"mac": "Zed", "cmd": "zed"},
    "webstorm": {"mac": "WebStorm", "cmd": "webstorm"}, "notepad++": {"mac": "", "cmd": "notepad++"},
    "gedit": {"mac": "", "cmd": "gedit"}, "kate": {"mac": "", "cmd": "kate"},
}
EDITOR_ALIASES = {"vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
                  "intellij": "intellij idea", "sublime": "sublime text"}


def _desktop_name(path: str) -> str:
    """The Name= of a Linux .desktop file (skips hidden ones)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            name, hidden = "", False
            for line in f:
                if line.startswith("Name=") and not name:
                    name = line[5:].strip()
                elif line.strip() in ("NoDisplay=true", "Hidden=true"):
                    hidden = True
            return "" if hidden else name
    except OSError:
        return ""


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
