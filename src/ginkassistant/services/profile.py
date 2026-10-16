"""
Your profile (Settings -> Account) and your Instructions for Gink
(Settings -> Memory). Stored as one small JSON document that syncs to
your account like chats and memories.

  full_name, nickname ("What should Gink call you?"), work ("What best
  describes your work?"), photo (a small JPEG, max 256 px, as a data URL),
  instructions (free text Gink keeps in mind in every chat).
"""

import base64
import io
import json
import os
import time
from typing import Optional

WORK_OPTIONS = ["", "Student", "Teacher / educator", "Software & IT", "Business owner / entrepreneur",
                "Sales & marketing", "Healthcare", "Finance & accounting", "Engineering", "Design & creative",
                "Law", "Government & public service", "Trade, farming & crafts", "Research & science",
                "Media & journalism", "NGO & development", "Retired", "Something else"]
MAX_INSTRUCTIONS = 3000
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def profile_path(app, email: str) -> str:
    """One profile per ACCOUNT (not per device): a second person signing in on
    the same computer must never see the first person's name or photo.
    The old single profile.json moves to the first account that signs in."""
    import hashlib
    from .paths import data_dir
    base = data_dir(app)
    folder = base / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:16] + ".json")
    legacy = base / "profile.json"
    if legacy.exists() and not path.exists() and not any(folder.glob("*.json")):
        try:
            legacy.replace(path)
        except OSError:
            pass
    return str(path)


def _tidy_name(name: str) -> str:
    """'IBRAHIM A KARGBO' / 'ibrahim kargbo' -> 'Ibrahim A Kargbo'; mixed case is kept as typed."""
    name = " ".join((name or "").split())[:120]
    if not name or "@" in name:
        return ""
    if name.isupper() or name.islower():
        name = " ".join(w[:1].upper() + w[1:].lower() for w in name.split(" "))
    return name


class ProfileStore:
    def __init__(self, path: str):
        self.path = path
        self.on_change = None

    def get(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data.setdefault("updated", 0)
        return data

    def _write(self, data: dict, touch: bool = True):
        if touch:
            data["updated"] = time.time()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        if touch and self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def update(self, **fields) -> dict:
        data = self.get()
        for k, v in fields.items():
            if k == "work" and v not in WORK_OPTIONS:
                continue
            if k == "instructions":
                v = (v or "")[:MAX_INSTRUCTIONS]
            elif isinstance(v, str):
                v = " ".join(v.split())[:120]
            data[k] = v
        self._write(data)
        return data

    def set_photo(self, raw: Optional[bytes]) -> str:
        """Store a small square JPEG (PNG/JPEG/WebP up to 10 MB in). None removes it."""
        data = self.get()
        if raw is None:
            data["photo"] = ""
        else:
            if len(raw) > MAX_PHOTO_BYTES:
                raise ValueError("That photo is over 10 MB.")
            from PIL import Image, ImageOps
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
            except Exception:
                raise ValueError("That file isn't a photo Gink can read (use PNG, JPEG or WebP).")
            side = min(im.size)
            im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                          (im.width + side) // 2, (im.height + side) // 2)).resize((256, 256))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=86)
            data["photo"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        self._write(data)
        return data["photo"]

    def seed_from_signin(self, name: str) -> bool:
        """Fill Full name / what to call you from the name the sign-in provider
        (Google, GitHub, Microsoft, Apple, SSO) or the sign-up form gave.
        Only EMPTY fields are filled -- a name the user chose is never replaced.
        On a profile never edited on this device, the change is stamped as very
        old, so a profile already synced from another device still wins."""
        full = _tidy_name(name)
        if not full:
            return False
        data = self.get()
        changed = False
        if not data.get("full_name"):
            data["full_name"] = full
            changed = True
        if not data.get("nickname"):
            data["nickname"] = full.split(" ")[0]
            changed = True
        if not changed:
            return False
        if not data.get("updated"):
            data["updated"] = 1.0                 # older than any real edit anywhere
            self._write(data, touch=False)
        else:
            self._write(data)
        return True

    def call_name(self, fallback: str = "") -> str:
        p = self.get()
        return (p.get("nickname") or (p.get("full_name") or "").split(" ")[0] or fallback).strip()

    def as_prompt(self) -> str:
        p = self.get()
        bits = []
        if p.get("full_name"):
            bits.append(f"The user's name is {p['full_name']}.")
        if p.get("nickname"):
            bits.append(f"Call them {p['nickname']}.")
        if p.get("work"):
            bits.append(f"Their work: {p['work']} -- use examples that fit it when helpful.")
        out = ("\n\nAbout the user: " + " ".join(bits)) if bits else ""
        if (p.get("instructions") or "").strip():
            out += ("\n\nThe user's instructions for you (follow them unless they conflict with safety):\n"
                    + p["instructions"].strip())
        return out

    # -- sync (services/sync.py) ---------------------------------------------
    def changes_since(self, ts: float):
        p = self.get()
        return [{"id": "me", "updated": p["updated"], "deleted": False, "payload": p}] if p["updated"] > ts else []

    def apply_remote(self, docs) -> int:
        for d in docs:
            if d.get("id") == "me" and d.get("updated", 0) > self.get()["updated"]:
                data = dict(d.get("payload") or {})
                data["updated"] = d["updated"]
                self._write(data, touch=False)
                if self.on_change:
                    try:
                        self.on_change()
                    except Exception:
                        pass
                return 1
        return 0
