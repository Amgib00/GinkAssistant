"""
"Launch at login", for macOS only -- confirmed as their actual test
platform throughout this build, and the one place a per-user mechanism
(LaunchAgents) is both standard and doesn't need admin rights. Windows
(registry Run key or a Startup-folder shortcut) and Linux (an autostart
.desktop file) would need their own, different implementations -- not
built here, so is_supported() reports False there rather than silently
doing nothing behind a toggle that looks like it worked.

Real constraint worth knowing: this only makes sense once Gink is an
actual installed .app bundle. A `python -m ginkassistant` dev run has no
stable path to point a login item at -- there's no .app bundle to find,
so is_supported() reports False in that case too, and the Settings
screen explains why rather than offering a toggle that can't do anything
real yet.
"""

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .platform_utils import is_macos

logger = logging.getLogger("LaunchAtLogin")

_BUNDLE_ID = "com.amgib.ginkassistant"
_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_BUNDLE_ID}.plist"


def _find_app_bundle() -> str | None:
    """Walk up from the running executable looking for a .app bundle --
    only exists for a real packaged/installed build, not `python -m
    ginkassistant`. Returns the .app path, or None if there isn't one."""
    for candidate in (sys.executable, __file__):
        path = Path(candidate).resolve()
        for parent in path.parents:
            if parent.suffix == ".app":
                return str(parent)
    return None


def is_supported() -> bool:
    return is_macos() and _find_app_bundle() is not None


def is_enabled() -> bool:
    return _AGENT_PATH.exists()


def enable() -> bool:
    """Returns True on success. Writes a per-user LaunchAgent plist that
    runs `open -a <Gink.app>` at login -- pointing at the .app bundle via
    `open -a` rather than the embedded Python binary directly, so this
    doesn't depend on guessing Briefcase's internal executable layout."""
    bundle = _find_app_bundle()
    if not bundle:
        return False
    try:
        _AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        plist = {
            "Label": _BUNDLE_ID,
            "ProgramArguments": ["/usr/bin/open", "-a", bundle],
            "RunAtLoad": True,
        }
        with open(_AGENT_PATH, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(["launchctl", "load", str(_AGENT_PATH)], capture_output=True, timeout=5)
        return True
    except Exception as e:
        logger.warning(f"Failed to enable launch at login: {e}")
        return False


def disable() -> bool:
    try:
        if _AGENT_PATH.exists():
            subprocess.run(["launchctl", "unload", str(_AGENT_PATH)], capture_output=True, timeout=5)
            _AGENT_PATH.unlink()
        return True
    except Exception as e:
        logger.warning(f"Failed to disable launch at login: {e}")
        return False