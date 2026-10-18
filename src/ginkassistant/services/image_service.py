"""
Image creation for Media Studio and chat ("create an image of ...").

Goes through YOUR Gink server (POST /media/image), which holds the Google
key and applies the plan's daily image limit -- the app never contains a
Google key. (The old Media Studio called Google directly with an in-app
GEMINI_API_KEY, and used Imagen models Google has since shut down.)
Images are saved in the app's files folder and listed as a gallery.
"""

import base64
import json
import os
import time
from typing import List

from .api_client import ApiClient, ApiError
from .file_maker import MadeFile, save_image

ASPECTS = ["1:1", "16:9", "9:16", "4:3", "3:4"]
STYLES = {
    "": "No style",
    "photo": "photorealistic photograph, natural light, high detail",
    "illustration": "clean digital illustration, vibrant colours",
    "3d": "3D render, soft studio lighting, tactile materials",
    "sticker": "die-cut sticker, bold outlines, simple shading, white background",
    "poster": "bold graphic poster design with strong typography",
    "logo": "minimal modern logo, flat vector, simple shapes, white background",
    "watercolor": "soft watercolour painting on textured paper",
    "anime": "anime style, cel shading, expressive",
}


class ImageService:
    def __init__(self, files_dir: str, base_url_fn, token_fn):
        self.files_dir = files_dir
        self.base_url_fn = base_url_fn
        self.token_fn = token_fn
        self.index_path = os.path.join(files_dir, "images.json")

    def _index(self) -> List[dict]:
        try:
            with open(self.index_path, encoding="utf-8") as f:
                items = json.load(f)
            return [i for i in items if os.path.exists(os.path.join(self.files_dir, i["name"]))]
        except Exception:
            return []

    def _save_index(self, items: List[dict]):
        os.makedirs(self.files_dir, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(items[-500:], f, ensure_ascii=False)

    async def create(self, prompt: str, aspect_ratio: str = "1:1", style: str = "") -> MadeFile:
        token = self.token_fn()
        if not token:
            raise ApiError("Sign in again to create images.")
        style_text = STYLES.get(style, "")
        data = await ApiClient(self.base_url_fn()).generate_image(
            token, prompt, aspect_ratio if aspect_ratio in ASPECTS else "1:1", style_text)
        raw = base64.b64decode(data["image_b64"])
        made = save_image(self.files_dir, " ".join(prompt.split()[:6]) or "Gink image", raw, data.get("mime_type", "image/png"))
        items = self._index()
        items.append({"name": made.name, "prompt": prompt, "aspect": aspect_ratio, "style": style,
                      "created": time.time(), "used": data.get("used"), "limit": data.get("limit")})
        self._save_index(items)
        return made

    def gallery(self) -> List[dict]:
        return list(reversed(self._index()))

    def delete(self, name: str) -> None:
        items = [i for i in self._index() if i["name"] != name]
        path = os.path.join(self.files_dir, os.path.basename(name))
        if os.path.exists(path):
            os.remove(path)
        self._save_index(items)

    def thumb_data_url(self, name: str, size: int = 512) -> str:
        """A small JPEG preview (the chat page can't read local files directly)."""
        import io
        path = os.path.join(self.files_dir, os.path.basename(name))
        try:
            from PIL import Image
        except ImportError:                     # 32-bit Android edition: the image itself, no preview
            import base64, mimetypes
            mime = mimetypes.guess_type(path)[0] or "image/png"
            with open(path, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        im = Image.open(path)
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
