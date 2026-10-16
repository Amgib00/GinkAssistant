"""
Correct platform checks -- `is_desktop()` gates everything that's
categorically impossible on mobile (local app launching, GitHub
self-update, launch-on-startup), rather than leaving it to the broken
sys.frozen/sys._MEIPASS-style checks found across the original codebase.

IS_ANDROID mirrors the one correct check __main__.py already uses
(hasattr(sys, "getandroidapilevel"), which Chaquopy adds only on
Android). iOS detection follows the same spirit: sys.platform == "ios"
is what CPython reports on iOS builds (including Toga's iOS backend).
"""

import sys
import os


def is_android() -> bool:
    return hasattr(sys, "getandroidapilevel") or "ANDROID_ARGUMENT" in os.environ


def is_ios() -> bool:
    return sys.platform == "ios"


def is_mobile() -> bool:
    return is_android() or is_ios()


def is_desktop() -> bool:
    return not is_mobile()


def is_macos() -> bool:
    return sys.platform == "darwin" and not is_ios()
