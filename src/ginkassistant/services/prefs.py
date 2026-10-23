"""Small app preferences file (prefs.json in the config folder):
morning briefing on/off, time, city, read aloud; last briefing date."""

import json

from .paths import config_dir

DEFAULTS = {
    "briefing_enabled": True,
    "briefing_time": "07:30",
    "briefing_city": "",            # kept for older saves; "city" is the one to use
    "city": "",
    "use_location": True,
    "agent_confirm": True,        # agent mode: ask before sending messages, calls, deleting...         # Settings -> Location: use the city / approximate location in answers
    "briefing_speak": True,
    "briefing_last_date": "",
    # Settings window
    "theme": "system",            # system | light | dark
    "chat_font": "sans",          # sans | serif | mono
    "motion": "system",           # system | reduced
    "voice_speed": "normal",      # slow | normal | fast
    "read_aloud": True,           # speak replies to typed messages
    "reply_language": "auto",     # auto | en | fr | wo | kri | ar | pt | es
    "notify_reminders": True,     # system notifications for due reminders/alarms
    "use_memory": True,           # use saved memories in answers
    "web_search": True,           # let Gink search the web
    "video_suggestions": True,    # add YouTube guides to how-to answers
    "speech_lang": "auto",        # Settings -> Voice -> Language (speech recognition); auto = any language
    "voice_intro_seen": False,    # "Meet Voice" shown once
    "send_key": "enter",          # Settings -> Keyboard: enter | mod (Cmd/Ctrl+Enter)
    "single_keys": True,          # "/" focus, Space mutes in voice
    "wake_enabled": False,        # "Hey Gink" -- off until the user turns it on (privacy)
    "wake_followup": True,        # keep listening a few seconds for a follow-up
    "wake_front": True,           # bring Gink to the front when woken
    "briefing_projects": True,    # briefing: "pick up where you left off" (tasks, chats, recent files)
}


def _path(app):
    return config_dir(app) / "prefs.json"


def load(app) -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(_path(app).read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save(app, **changes) -> dict:
    data = load(app)
    data.update(changes)
    try:
        _path(app).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    return data


def city(app) -> str:
    """Settings -> Location (falls back to the older briefing-only field)."""
    p = load(app)
    if not p.get("use_location", True):
        return ""
    return (p.get("city") or p.get("briefing_city") or "").strip()
