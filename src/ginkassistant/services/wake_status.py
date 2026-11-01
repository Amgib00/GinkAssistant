"""
What the "Hey Gink" chip in the composer says (ui/wake_ui.py), worked out in one place so the
Mac/Windows/Linux and Android apps -- and Settings > Voice -- always agree.

describe() is pure (no Toga, no microphone), so it's tested directly (tests/test_wake_status.py).

States (the chip's colour):
  off         Hey Gink is switched off, or this device can't do it yet (iPhone): no chip
  starting    getting ready (downloading the offline voice model, opening the mic)   amber
  ready       waiting for "Hey Gink"                                                  green, breathing
  paused      Gink is using the mic or speaking; it listens again right after         grey
  active      "Hey Gink" was heard: Gink is listening / thinking / answering          lime
  retrying    a passing problem (speech service busy, no network); it keeps trying    amber
  problem     it stopped and needs the person (mic permission, no speech service...)  red
"""
from typing import Optional


def _paused(listener) -> bool:
    p = getattr(listener, "paused", False)
    try:
        return bool(p() if callable(p) else p)
    except Exception:
        return False


def _running(listener) -> bool:
    r = getattr(listener, "running", False)
    try:
        return bool(r() if callable(r) else r)
    except Exception:
        return False


def describe(*, enabled: bool, supported: bool, listener=None, downloading: bool = False,
             progress: Optional[float] = None, busy: bool = False, status: str = "",
             device: str = "computer") -> dict:
    """-> {"state", "label", "detail"}: label is the short chip text, detail the full sentence
    (tooltip, screen readers, Settings > Voice)."""
    if not supported or not enabled:
        return {"state": "off", "label": "", "detail": "Hey Gink is off" if supported
                else "Hey Gink isn\u2019t available on this device yet"}
    if downloading:
        pct = f" {int(progress * 100)}%" if progress is not None and 0 <= progress <= 1 else ""
        return {"state": "starting", "label": "Getting ready" + pct,
                "detail": "Downloading the offline voice model (once)" + (f" \u2014{pct}" if pct else "") + "\u2026"}
    if listener is None:
        if status and status != "Off":
            return {"state": "problem", "label": "Hey Gink can\u2019t listen",
                    "detail": status + " \u2014 click to open Voice settings"}
        return {"state": "starting", "label": "Starting\u2026", "detail": "Hey Gink is starting\u2026"}
    error = str(getattr(listener, "error", "") or "")
    if not _running(listener):
        if error:
            return {"state": "problem", "label": "Hey Gink stopped",
                    "detail": f"Hey Gink stopped: {error} \u2014 click to open Voice settings"}
        return {"state": "starting", "label": "Starting\u2026", "detail": "Hey Gink is starting\u2026"}
    if busy:
        return {"state": "active", "label": "Listening\u2026", "detail": "Gink heard \u201cHey Gink\u201d and is listening"}
    if error:
        return {"state": "retrying", "label": "Hey Gink \u00b7 retrying",
                "detail": f"Having trouble listening ({error}). Gink keeps trying."}
    if _paused(listener):
        return {"state": "paused", "label": "Hey Gink paused",
                "detail": "Paused while Gink uses the microphone \u2014 it listens again right after"}
    online = getattr(listener, "prefer_offline", True) is False
    where = ("This phone has no offline speech pack, so it uses the phone\u2019s online speech service."
             if online else f"Nothing leaves this {device} until you say it.")
    return {"state": "ready", "label": "Hey Gink",
            "detail": f"Listening for \u201cHey Gink\u201d \u2014 say it any time. {where}"}
