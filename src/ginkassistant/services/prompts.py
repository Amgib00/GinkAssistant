"""Your own prompts for the "/" menu (Settings > Personalization > Prompt library). Kept on this device."""
import json
import os
import uuid

MAX_PROMPTS, MAX_LENGTH = 50, 2000


class PromptStore:
    def __init__(self, path: str):
        self.path = path

    def all(self) -> list:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return [p for p in data if isinstance(p, dict) and p.get("id") and p.get("text")]
        except (OSError, ValueError):
            return []

    def _save(self, prompts: list) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False)
        os.replace(tmp, self.path)                  # never a half-written file

    def add(self, text: str) -> dict:
        text = str(text or "").strip()
        if not text:
            raise ValueError("Write the prompt first.")
        if len(text) > MAX_LENGTH:
            raise ValueError(f"A prompt can be up to {MAX_LENGTH} characters.")
        prompts = self.all()
        if any(p["text"] == text for p in prompts):
            raise ValueError("You already have this prompt.")
        if len(prompts) >= MAX_PROMPTS:
            raise ValueError(f"You can keep up to {MAX_PROMPTS} prompts. Delete one first.")
        item = {"id": uuid.uuid4().hex[:10], "text": text}
        self._save(prompts + [item])
        return item

    def delete(self, pid: str) -> bool:
        prompts = self.all()
        keep = [p for p in prompts if p["id"] != pid]
        if len(keep) != len(prompts):
            self._save(keep)
        return len(keep) != len(prompts)
