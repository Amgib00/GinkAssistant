"""
Settings -> Privacy -> Export my data: everything Gink keeps about you on
this device, in one readable JSON file -- chats, Workspace items, memories
and settings. (App stores and privacy laws such as the GDPR expect users
to be able to get a copy of their data.)
"""

import json
from datetime import datetime

EXPORT_VERSION = 1


def build_export(email: str, history, items, memory, prefs: dict) -> dict:
    sessions = history.get_all_sessions() if history else {}
    chats = []
    for sid, payload in sessions.items():
        msgs = payload.get("messages", [])
        if msgs:
            chats.append({"id": sid, "messages": [{"role": m.get("role"), "content": m.get("content"),
                                                    "time": str(m.get("timestamp") or m.get("ts") or "")}
                                                   for m in msgs]})
    workspace = []
    if items:
        for it in items.list(include_done=True, top_level_only=True):
            workspace.append({"kind": it.kind, "title": it.title, "notes": it.notes,
                              "due": it.due.isoformat() if it.due else None, "done": it.done,
                              "steps": [{"title": s.title, "done": s.done} for s in items.children(it.id)]})
    private = {"briefing_last_date"}
    return {
        "app": "Gink Assistant", "export_version": EXPORT_VERSION,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "account": email,
        "chats": chats, "workspace": workspace,
        "memories": [m["text"] for m in (memory.list() if memory else [])],
        "settings": {k: v for k, v in (prefs or {}).items() if k not in private},
    }


def export_filename() -> str:
    return datetime.now().strftime("Gink-export-%Y-%m-%d.json")


def write_export(path: str, data: dict) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def chat_markdown(title: str, messages) -> str:
    """One chat as readable Markdown (sidebar -> Export chat)."""
    lines = [f"# {title or 'Gink chat'}", "",
             f"_Exported from Gink Assistant on {datetime.now():%d %B %Y, %H:%M}_", ""]
    for m in messages:
        who = "**You**" if m.get("role") == "user" else "**Gink**"
        lines += [who, "", (m.get("content") or "").strip(), ""]
    return "\n".join(lines)


def chat_filename(title: str) -> str:
    import re
    safe = re.sub(r"[^\w\- ]+", "", title or "Gink chat").strip()[:60] or "Gink chat"
    return f"{safe}.md"


async def save_with_dialog(app, suggested: str, file_types, write) -> str:
    """Ask where to save (desktop); on devices without a Save dialog, use
    Downloads (or the app's data folder). Returns the path, or "" if the
    user cancelled."""
    import os
    from .paths import data_dir
    path = None
    try:
        import toga
        path = await app.main_window.dialog(toga.SaveFileDialog("Save", suggested_filename=suggested,
                                                                file_types=file_types))
        if path is None:
            return ""                       # user pressed Cancel
    except Exception:
        path = None                          # no Save dialog on this platform
    if path is None:
        downloads = os.path.expanduser("~/Downloads")
        folder = downloads if os.path.isdir(downloads) else str(data_dir(app))
        path = os.path.join(folder, suggested)
    write(str(path))
    return str(path)
