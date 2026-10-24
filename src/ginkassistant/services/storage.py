"""Settings > Storage: what Gink keeps on this device, how big it is, and freeing space.
Nothing here touches the server or other devices."""
import os
import shutil

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
WAKE_MODEL = "vosk-model-small-en-us-0.15"


def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1024
    return f"{n:.1f} GB"


def usage(base: str) -> dict:
    """Sizes by kind, plus free space on this device."""
    files_dir = os.path.join(base, "files")
    made = images = 0
    made_n = images_n = 0
    if os.path.isdir(files_dir):
        for f in os.listdir(files_dir):
            p = os.path.join(files_dir, f)
            if not os.path.isfile(p):
                continue
            if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                images += os.path.getsize(p); images_n += 1
            else:
                made += os.path.getsize(p); made_n += 1
    parts = {
        "chats": _size(os.path.join(base, "gink_history.db")) if os.path.exists(os.path.join(base, "gink_history.db")) else 0,
        "images": images, "files": made,
        "offline_ai": _size(os.path.join(base, "models", "model.gguf")) if os.path.exists(os.path.join(base, "models", "model.gguf")) else 0,
        "wake_model": _size(os.path.join(base, "models", WAKE_MODEL)) if os.path.exists(os.path.join(base, "models", WAKE_MODEL)) else 0,
        "songs": _size(os.path.join(base, "shazam_db.pkl")) if os.path.exists(os.path.join(base, "shazam_db.pkl")) else 0,
    }
    try:
        free = shutil.disk_usage(base).free
    except OSError:
        free = 0
    return {"parts": parts, "counts": {"images": images_n, "files": made_n}, "total": sum(parts.values()), "free": free}


def free_up(base: str, kind: str) -> int:
    """Delete one kind of data; returns the bytes freed. Chats are deleted elsewhere (and synced)."""
    before = usage(base)["parts"].get(kind, 0)
    files_dir = os.path.join(base, "files")
    if kind in ("images", "files") and os.path.isdir(files_dir):
        for f in os.listdir(files_dir):
            p = os.path.join(files_dir, f)
            is_image = os.path.splitext(f)[1].lower() in IMAGE_EXT
            if os.path.isfile(p) and (is_image if kind == "images" else not is_image):
                os.remove(p)
    elif kind == "offline_ai":
        p = os.path.join(base, "models", "model.gguf")
        if os.path.exists(p):
            os.remove(p)
    elif kind == "wake_model":
        shutil.rmtree(os.path.join(base, "models", WAKE_MODEL), ignore_errors=True)
    elif kind == "songs":
        p = os.path.join(base, "shazam_db.pkl")
        if os.path.exists(p):
            os.remove(p)
    else:
        raise ValueError(kind)
    return before
