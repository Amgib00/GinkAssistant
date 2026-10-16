"""
The device's time zone (IANA name, e.g. "Africa/Dakar") and region setting
(e.g. "fr_SN"), sent to the server as hints for the user's country.
Only these two settings are read -- no GPS, no IP lookup, nothing stored.
"""

import locale as _locale
import os
import sys


def _android():
    return hasattr(sys, "getandroidapilevel")


def timezone_name() -> str:
    if _android():
        try:
            from java.util import TimeZone
            return str(TimeZone.getDefault().getID())
        except Exception:
            return ""
    tz = os.environ.get("TZ", "")
    if "/" in tz:
        return tz.lstrip(":")
    try:                                   # macOS / Linux: /etc/localtime -> .../zoneinfo/Africa/Dakar
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except Exception:
        pass
    try:                                   # Linux fallback
        with open("/etc/timezone", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        pass
    try:                                   # Windows: optional tzlocal if installed
        import tzlocal
        return str(tzlocal.get_localzone_name())
    except Exception:
        return ""


def region_locale() -> str:
    if _android():
        try:
            from java.util import Locale
            loc = Locale.getDefault()
            return f"{loc.getLanguage()}_{loc.getCountry()}"
        except Exception:
            return ""
    for getter in (lambda: _locale.getlocale()[0], lambda: os.environ.get("LANG", "").split(".")[0]):
        try:
            val = getter()
            if val and "_" in val:
                return val
        except Exception:
            continue
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True, timeout=3)
            if out.stdout.strip():
                return out.stdout.strip().split("@")[0]
        except Exception:
            pass
    return ""
