"""
Tells people when a newer Gink is out. Once a day the app asks the Gink server
(GET /app/version -- the server asks GitHub, so users' addresses aren't sent to GitHub),
compares versions, and offers the installer for THIS device. "Later" hides that version.
iPhone/iPad updates come from the App Store, so nothing is offered there.
"""
import json
import os
import platform
import sys
import time
from typing import Optional

CHECK_EVERY = 24 * 3600


def version_tuple(v) -> tuple:
    parts = []
    for p in str(v or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def asset_name() -> Optional[str]:
    from .platform_utils import is_android
    if is_android():
        return "Gink-android.apk"
    if sys.platform == "darwin":
        if os.environ.get("GINK_FAKE_IOS") or platform.system() == "iOS" or sys.platform == "ios":
            return None
        return "Gink-mac-arm64.dmg" if platform.machine() == "arm64" else "Gink-mac-x86_64.dmg"
    if sys.platform.startswith("win"):
        return "Gink-windows-x64.msi"
    if sys.platform.startswith("linux"):
        return "Gink-linux-amd64.deb"
    return None


def _load(path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path, state):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def _offer(state, current) -> Optional[dict]:
    latest = state.get("latest") or {}
    v, name = latest.get("version"), asset_name()
    if not v or not name or version_tuple(v) <= version_tuple(current) or state.get("dismissed") == v:
        return None
    url = (latest.get("assets") or {}).get(name) or latest.get("page")
    return {"version": v, "url": url} if url else None


async def check(base_url: str, current: str, state_path: str, http=None, now: float = None) -> Optional[dict]:
    """{'version', 'url'} when a newer version is out for this device, else None. Asks at most daily."""
    now = now or time.time()
    state = _load(state_path)
    last = state.get("last_check")                       # None = never checked: check now
    if (last is None or now - last >= CHECK_EVERY) and asset_name():
        try:
            if http is None:
                import httpx
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(base_url.rstrip("/") + "/app/version")
            else:
                r = await http.get(base_url.rstrip("/") + "/app/version")
            if r.status_code == 200:
                state["latest"] = r.json()
            state["last_check"] = now
            _save(state_path, state)
        except Exception:
            pass                                  # offline: try again next time
    return _offer(state, current)


def dismiss(state_path: str, version: str):
    state = _load(state_path)
    state["dismissed"] = version
    _save(state_path, state)
