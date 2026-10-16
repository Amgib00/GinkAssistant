"""Small helpers for running OS commands safely (no shell string building)."""
import base64
import subprocess
import sys


def run(cmd, timeout=20):
    """Run a command, return (ok, combined_output). Never raises."""
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out.strip()
    except Exception as e:  # FileNotFoundError, TimeoutExpired, ...
        return False, str(e)


def spawn(cmd):
    """Start a command in the background and don't wait for it."""
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        return True
    except Exception:
        return False


def applescript_str(s: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def ps_str(s: str) -> str:
    """Quote a Python string as a PowerShell single-quoted literal."""
    return "'" + str(s).replace("'", "''") + "'"


def ps_encoded(script: str) -> str:
    """PowerShell -EncodedCommand payload (base64 of UTF-16LE) — avoids all quoting issues."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")
