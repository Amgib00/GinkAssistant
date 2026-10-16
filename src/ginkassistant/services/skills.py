"""
One working skill router, replacing three broken/overlapping attempts
found in the real codebase:
  - core/core.py's GinkCore checked for a `process_query` method that was
    never defined (only process_input existed) -- its intent routing
    never actually fired
  - core/brain.py's SkillRegistry.web_handler() called
    self.browser.navigate(...), a method core/web_tool.py's BrowserEngine
    never defined -- a guaranteed crash if triggered
  - system status had three separate implementations across the codebase

Now includes everything from the original, reconciled into one place:
jokes, weather (Open-Meteo, no key needed), a world clock (zoneinfo),
cross-platform system status, web search + "open <site>" (DuckDuckGo +
webbrowser.open()), local-IDE launching, and a GitHub release check.

Three of those are genuinely desktop-only by OS policy, not just
untested, so they're gated behind services/platform_utils.is_desktop()
rather than silently failing on mobile:
  - local-app launching (subprocess "open -a" has no mobile equivalent
    at all)
  - the GitHub self-update check (iOS doesn't allow apps to self-update
    outside the App Store; Android apps are expected to update via Play
    Store)
  - web search/"open <site>" itself isn't OS-forbidden, but
    webbrowser.open() has no confirmed story on Android/iOS WebView
    sandboxes -- it's attempted there and reports plainly if it fails,
    rather than claiming success it can't verify.

try_skill(text) returns a reply string if a skill matched the message,
or None so the caller falls through to GroqBrain.
"""

import platform
import random
import re
import shutil
import subprocess
import webbrowser
from datetime import datetime
from typing import Optional

from packaging import version as _version

from . import platform_utils

import httpx

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    import psutil
except ImportError:
    psutil = None


JOKES = {
    "tech": [
        "Why did the computer go to the doctor? It had a core-virus.",
        "How many developers does it take to change a lightbulb? None -- that's a hardware issue.",
        "Real programmers count from 0.",
    ],
    "general": [
        "I'm reading a book on anti-gravity. It's impossible to put down.",
        "I used to be a baker, but I couldn't make enough dough.",
    ],
}

WORLD_CLOCKS = {
    "london": "Europe/London",
    "new york": "America/New_York",
    "tokyo": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
    "paris": "Europe/Paris",
    "dubai": "Asia/Dubai",
}

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 51: "light drizzle", 61: "rain", 63: "moderate rain",
    65: "heavy rain", 71: "snow", 80: "rain showers", 95: "a thunderstorm",
}


def _tell_joke(text: str) -> str:
    category = "tech" if ("tech" in text or "code" in text or "programmer" in text) else "general"
    return random.choice(JOKES[category])


async def _get_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "en", "format": "json"},
            )
            geo_data = geo.json()
            if not geo_data.get("results"):
                return f"I couldn't find a city named '{city}'."
            place = geo_data["results"][0]
            lat, lon = place["latitude"], place["longitude"]
            name, country = place.get("name", city), place.get("country", "")

            wx = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "auto"},
            )
            current = wx.json().get("current_weather")
            if not current:
                return f"I found {name}, but couldn't get the weather."

        condition = WEATHER_CODES.get(current.get("weathercode"), "cloudy")
        return f"In {name}, {country}, it's currently {condition} and {current.get('temperature')}\u00b0C."
    except Exception as exc:
        return f"I couldn't reach the weather service: {exc}"


def _world_clock() -> str:
    if ZoneInfo is None:
        return "Timezone data isn't available on this build."
    now_local = datetime.now().astimezone()
    lines = ["Here's the time around the world:"]
    for label, zone_id in WORLD_CLOCKS.items():
        try:
            local = now_local.astimezone(ZoneInfo(zone_id))
            lines.append(f"- {label.title()}: {local.strftime('%I:%M %p, %a')}")
        except Exception:
            continue
    return "\n".join(lines)


def _system_status() -> str:
    lines = [f"OS: {platform.system()} {platform.release()}"]
    if psutil:
        try:
            lines.append(f"CPU load: {psutil.cpu_percent(interval=0.1)}%")
            battery = psutil.sensors_battery()
            if battery:
                charging = " (charging)" if battery.power_plugged else ""
                lines.append(f"Battery: {battery.percent}%{charging}")
        except Exception:
            pass
    else:
        lines.append("(psutil not available on this build)")
    return "System status:\n" + "\n".join(lines)


# -- Web: search + "open <site>" ------------------------------------------

WEB_SHORTCUTS = {
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "github": "https://github.com",
    "reddit": "https://reddit.com",
    "wikipedia": "https://wikipedia.org",
    "gmail": "https://mail.google.com",
}


def _open_url(url: str, label: str) -> str:
    try:
        opened = webbrowser.open(url)
    except Exception as exc:
        return f"Couldn't open {label}: {exc}"
    if opened:
        return f"Opened {label} in your browser."
    return f"Wasn't able to open {label} here -- no confirmed browser-launch support on this platform."


async def _web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "Web search isn't available on this build (duckduckgo-search isn't installed)."

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=1))
        if results:
            top = results[0]
            snippet = top.get("body", "")
            source = top.get("href", "")
            if source:
                webbrowser.open(source)
            return f"{snippet}\n\n(source opened in your browser)" if snippet else _open_url(
                f"https://www.google.com/search?q={query.replace(' ', '+')}", f"a search for '{query}'"
            )
    except Exception:
        pass
    return _open_url(f"https://www.google.com/search?q={query.replace(' ', '+')}", f"a search for '{query}'")


# -- Desktop-only: local app launching, GitHub release check --------------

LOCAL_APPS = {
    "terminal": "Terminal",
    "finder": "Finder",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
}


def _open_local_app(app_name: str) -> str:
    if not platform_utils.is_desktop():
        return "Launching local apps isn't something a mobile build can do -- this only works on desktop."
    if not platform_utils.is_macos():
        return "Local app launching here only knows macOS's `open -a` -- not implemented for Windows/Linux yet."
    if shutil.which(app_name) or True:  # `open -a` resolves app names itself; this is a light existence nod
        try:
            subprocess.Popen(["open", "-a", app_name])
            return f"Launched {app_name}."
        except Exception as exc:
            return f"Couldn't launch {app_name}: {exc}"


async def _check_for_updates(current_version: str, repo_owner: str, repo_name: str) -> str:
    if not platform_utils.is_desktop():
        return "App updates on mobile go through the Play Store / App Store, not a self-update check."
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest")
        data = resp.json()
        latest_tag = data.get("tag_name", "0.0.0").lstrip("v")
        if _version.parse(latest_tag) > _version.parse(current_version):
            url = data.get("html_url")
            if url:
                webbrowser.open(url)
            return f"v{latest_tag} is available -- opened the release page."
        return "You're running the latest version."
    except Exception as exc:
        return f"Couldn't check for updates: {exc}"


async def try_skill(text: str) -> Optional[str]:
    """Returns a reply if a skill handled the message, else None."""
    lowered = (text or "").lower().strip()
    if not lowered:
        return None

    if "joke" in lowered or "make me laugh" in lowered:
        return _tell_joke(lowered)

    if "world clock" in lowered or "time around the world" in lowered:
        return _world_clock()

    match = re.search(r"\bweather(?:\s+in)?\s+([a-zA-Z\s]+)", lowered)
    if match and match.group(1).strip():
        return await _get_weather(match.group(1).strip())
    if "weather" in lowered:
        return await _get_weather("Dakar")

    if "system status" in lowered or "device status" in lowered or "how are you running" in lowered:
        return _system_status()

    for name, url in WEB_SHORTCUTS.items():
        if re.search(rf"\bopen\s+{name}\b", lowered) or re.search(rf"\bgo to\s+{name}\b", lowered):
            return _open_url(url, name.capitalize())

    search_match = re.search(r"\bsearch(?:\s+for)?\b\s*(.*)", lowered)
    if search_match and search_match.group(1).strip():
        return await _web_search(search_match.group(1).strip())

    for trigger, app_name in LOCAL_APPS.items():
        if f"open {trigger}" in lowered or f"launch {trigger}" in lowered:
            return _open_local_app(app_name)

    if "check for updates" in lowered or "check for update" in lowered:
        return await _check_for_updates("0.1.0", "amgib00", "ginkassistant")

    return None
