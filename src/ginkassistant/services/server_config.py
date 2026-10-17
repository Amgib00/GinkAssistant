"""
Where the login server lives -- saved on the device, so a phone can be
pointed at your hosted backend from inside the app (login screen or
Settings) instead of needing GINK_API_URL baked into a new build.

Priority, highest first:
  1. GINK_API_URL environment variable (dev/testing override)
  2. the address saved on this device (server.json in the config folder)
  3. platform default: this computer's own backend on desktop
     (127.0.0.1:8000, started by app.py), the Android emulator's alias
     for the host machine (10.0.2.2:8000) elsewhere.

A physical phone can never reach 127.0.0.1/10.0.2.2 on your Mac -- it
needs either your Mac's Wi-Fi address (http://192.168.x.x:8000, same
network only) or a hosted backend (see deploy/README.md).
"""

import json
import os
import sys
from typing import Optional, Tuple

import httpx

from .paths import config_dir

FILE_NAME = "server.json"


def _path(app):
    return config_dir(app) / FILE_NAME


def saved_url(app) -> Optional[str]:
    try:
        data = json.loads(_path(app).read_text(encoding="utf-8"))
        url = (data.get("base_url") or "").strip()
        return url or None
    except Exception:
        return None


def normalise(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        # bare LAN addresses are almost always plain http; hosted ones https
        looks_local = url.split(":")[0].replace(".", "").isdigit() or url.startswith("localhost")
        url = ("http://" if looks_local else "https://") + url
    return url


def save_url(app, url: str) -> str:
    url = normalise(url)
    if url:
        _path(app).write_text(json.dumps({"base_url": url}), encoding="utf-8")
    else:
        try:
            _path(app).unlink()
        except FileNotFoundError:
            pass
    return url


# Gink's online server (Render). Phones and tablets use it by default: a real phone can't
# reach a server on your Mac. Change it here if the server moves (or set GINK_API_URL).
ONLINE_SERVER = "https://gink-server.onrender.com"


def platform_default() -> str:
    """Phones/tablets -> the online server. Desktop -> its own built-in server on this computer
    (switch it in Settings -> Advanced -> Login server to share accounts and chats online)."""
    from .platform_utils import is_mobile
    if is_mobile():
        return ONLINE_SERVER
    return "http://127.0.0.1:8000"


def resolve_base_url(app) -> str:
    return os.environ.get("GINK_API_URL") or saved_url(app) or platform_default()


async def check_server(url: str, timeout: float = 8.0) -> Tuple[bool, str]:
    """(ok, human message). Uses /health, which backend_server.py serves."""
    url = normalise(url)
    if not url:
        return False, "Enter a server address first."
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{url}/health")
        if r.status_code == 200:
            return True, "Connected \u2713"
        return False, f"Server answered with error {r.status_code}."
    except httpx.ConnectError:
        return False, "Can't reach that address. Check it and your connection."
    except httpx.TimeoutException:
        return False, "That server took too long to answer."
    except Exception as exc:
        return False, f"Couldn't connect: {exc}"
