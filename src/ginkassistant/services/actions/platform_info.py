"""Single source of truth for 'which platform am I on?'."""
import os
import sys

_cached = None


def current_platform() -> str:
    """Return one of: android, ios, macos, windows, linux."""
    global _cached
    if _cached:
        return _cached
    name = None
    try:
        import toga.platform
        name = (toga.platform.current_platform or "").lower()
    except Exception:
        pass
    if not name:
        if hasattr(sys, "getandroidapilevel") or "ANDROID_DATA" in os.environ:
            name = "android"
        elif sys.platform == "ios":
            name = "ios"
        elif sys.platform == "darwin":
            name = "macos"
        elif sys.platform.startswith("win"):
            name = "windows"
        else:
            name = "linux"
    if name not in {"android", "ios", "macos", "windows", "linux"}:
        name = "linux"
    _cached = name
    return name


def is_mobile() -> bool:
    return current_platform() in {"android", "ios"}


def is_desktop() -> bool:
    return not is_mobile()
