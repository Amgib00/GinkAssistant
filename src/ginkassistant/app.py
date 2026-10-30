"""
GinkAssistant Toga entry point -- the rebuilt version.

Wiring into the real project's __main__.py:
    __main__.py already correctly gates PySide6 behind
    `IS_ANDROID = hasattr(sys, "getandroidapilevel")` and routes Android
    to a Toga app via ui/android_app.py's build_android_app(). Point that
    same IS_ANDROID branch at this file's main() instead (or use this as
    the basis for a fuller cross-platform entry point that replaces the
    PySide6 desktop path too, since everything here now runs on desktop
    as well as mobile).

Login now goes straight to the OTP screen, matching what __main__.py
actually launches (GinkAssistantLogin) -- see ui/login_screen.py for the
full reasoning on dropping the password flow.

On desktop, this now also starts the FastAPI backend itself (in a
background thread, before showing the login screen) -- the original
__main__.py did this too, but that file is gone along with the PySide6
code, so nothing was left to start a server at all. Gated behind
is_desktop(): running Uvicorn in-process on a phone is a much bigger
architectural question than this rebuild has tackled, so Android/iOS
still expect a real backend reachable at GINK_API_URL instead.

The import of services.backend_server (and so of fastapi/uvicorn) lives
INSIDE _start_backend_if_needed() rather than at module level, for
exactly that reason -- see that function's docstring for what actually
broke on Android before this was fixed.
"""

import os
import socket
import sys
import threading
import time
from pathlib import Path

import toga
from dotenv import load_dotenv

from .services.actions import DeviceActions, ReminderScheduler, TaskAgent, TaskStore, ToolRunner
from .services.memory import MemoryStore
from .services.paths import data_dir
from .services.server_config import resolve_base_url
from .services.platform_utils import is_desktop
from .ui.login_screen import build_login_screen, load_saved_session
from .ui.main_screen import build_main_screen

BACKEND_PORT = 8000

# This was in the original __main__.py (now deleted along with the
# PySide6 code) and never got carried over into this rebuild -- meaning
# GMAIL_USER/GMAIL_APP_PASSWORD/GROQ_API_KEY/etc. could only ever be set
# via real shell environment variables, never a .env file, until now.
# Project-root/.env (next to pyproject.toml), not src/.env -- the old
# gitignore entry was for the old layout; make sure .env is listed at
# the root in .gitignore too, since this doesn't reuse that old path.
# This is a local-dev convenience only: a real packaged/distributed
# Briefcase build won't have a loose .env sitting next to it the way a
# source checkout does, so production secrets still need to be set as
# actual environment variables wherever the app is actually deployed.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _port_already_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def _start_backend_if_needed(app: toga.App):
    """Starts the local FastAPI backend as a daemon thread, unless
    something's already listening on that port -- in which case a
    backend (very likely this same app, left over from a previous run)
    is presumably already serving it, so this just leaves it alone
    rather than crashing the way the original's hard port check did.

    Only ever called when is_desktop() is True (see startup() below) --
    the import of backend_server (and therefore of fastapi/uvicorn) is
    deliberately INSIDE this function rather than at module level, so
    Android/iOS never attempt it at all. Confirmed via an actual Android
    build that this matters, not just in theory: fastapi pulls in
    pydantic v2, and pydantic-core (the compiled Rust engine pydantic v2
    actually needs) has no real Android build on Chaquopy's index at all
    -- it only has an ancient 0.0.1 stub, nowhere near what pydantic
    2.13.4 requires. Those packages were still being force-installed on
    Android before this fix purely because this import was unconditional
    at module level, even though the Android client never calls any of
    this code (confirmed: services/api_client.py, Android's actual
    backend-talking code, only uses httpx -- see the module docstring
    above for the by-design client/server split: Android/iOS connect to
    a real backend over HTTP via GINK_API_URL, they don't run one)."""
    import uvicorn

    from .services.backend_server import app as backend_app, configure_secret_path

    # Before anything can hit /send-otp or /verify-otp: give the backend
    # a real, writable, app.paths-derived place to persist its signing
    # secret, instead of a hardcoded shared default. See
    # services/backend_server.py's docstring for why that module can't
    # resolve this path itself (no Toga App instance of its own).
    configure_secret_path(data_dir(app) / "secret.key")

    if _port_already_in_use(BACKEND_PORT):
        return
    thread = threading.Thread(
        target=lambda: uvicorn.run(backend_app, host="127.0.0.1", port=BACKEND_PORT, log_level="warning"),
        daemon=True,
    )
    thread.start()
    time.sleep(1.2)  # give it a moment to bind before the login screen can hit it


def default_base_url() -> str:
    """GINK_API_URL if set, else the same default as Settings shows (services/server_config.py):
    phones -> the online server, desktop -> the built-in server on this computer."""
    override = os.environ.get("GINK_API_URL")
    if override:
        return override
    from .services.server_config import platform_default
    return platform_default()


class AppState:
    def __init__(self, base_url: str):
        self.base_url = base_url


def _build_stamp() -> str:
    """Date/time of the newest Gink source file -- shown in Settings -> About so
    it's easy to tell which version is really running."""
    import datetime
    newest = 0.0
    for root, _dirs, files in os.walk(os.path.dirname(os.path.abspath(__file__))):
        for f in files:
            if f.endswith(".py"):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
    return datetime.datetime.fromtimestamp(newest).strftime("%d %b %Y, %H:%M") if newest else ""


class GinkAssistantApp(toga.App):
    def startup(self):
        self.gink_build = _build_stamp()
        # Saved-on-device address first (set from the login screen or
        # Settings), so phones can point at a hosted backend without a
        # rebuild -- see services/server_config.py.
        self.state = AppState(base_url=resolve_base_url(self))
        data_dir(self)  # ensure the writable data directory exists up front

        if is_desktop():
            _start_backend_if_needed(self)

        self._setup_task_system()

        self.main_window = toga.MainWindow(title="")      # no "Gink" in the title bar (the app is named by its icon and menu)
        self._try_auto_login()
        self.main_window.show()

    def _setup_task_system(self):
        """Alarms, timers, reminders, tasks and device actions
        (services/actions/). Created once per app run, before any
        screen, so the store/agent survive logging out and back in.
        The scheduler is started by main_screen.py, once Toga's event
        loop is running and the screen can show what's due."""
        d = data_dir(self)
        self.task_store = TaskStore(str(d / "tasks.db"))
        self.memory = MemoryStore(str(d / "memory.db"))
        self.task_runner = ToolRunner(self.task_store, DeviceActions(str(d)), memory=self.memory)
        from .services import prefs as _prefs
        self.task_runner.live.city_fn = lambda: _prefs.city(self)     # Settings -> Location
        self.task_runner.live.allowed_fn = lambda: _prefs.load(self).get("use_location", True)
        self.task_agent = TaskAgent(self.task_runner)
        self.task_scheduler = ReminderScheduler(self.task_store)

    def _try_auto_login(self):
        saved = load_saved_session(self)
        if saved:
            self.session_token = saved.get("token")      # used by sync (services/sync.py)
            self.show_main(saved["email"])
        else:
            self.show_login()

    def show_login(self):
        self.main_window.content = build_login_screen(self, on_success=self.show_main)

    def show_main(self, email: str):
        self.main_window.content = build_main_screen(self, email)


def main():
    # icon: Gink's own icon in the Dock / taskbar even when run with `python -m
    # ginkassistant` (otherwise macOS shows Python's icon). Packaged apps also get it
    # from pyproject's `icon` (icons/ginkassistant.*), so BeeWare's bee never appears.
    return GinkAssistantApp("Gink", "com.amgib.ginkassistant", icon="resources/ginkassistant")


if __name__ == "__main__":
    # Lets `python -m ginkassistant.app` work too, not just `python -m
    # ginkassistant` (which is what actually runs __main__.py). Running
    # app.py directly only defines main() otherwise -- it never calls it,
    # which is why that command previously just printed pygame's import
    # banner and exited.
    main().main_loop()