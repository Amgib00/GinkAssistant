"""
Image/video generation -- async port of core/media_engine.py's MediaWorker
(Gemini for text, Imagen for images, Veo for video, via google-genai),
with the same offline PIL-based mock mode when GEMINI_API_KEY is missing
or offline mode is forced.

Two corrections versus the original:
  - generated files save under services/paths.py's data_dir() instead of
    a bare relative filename (the original saved to whatever the current
    working directory happened to be).
  - Veo's long-running polling loop (`while not operation.done:
    time.sleep(10)`) is now `await asyncio.sleep(10)`, so it doesn't
    block the UI thread -- the original would have frozen the whole app
    for however long video generation takes.
"""

import asyncio
import io
import os
import time
from typing import Optional

import toga
from PIL import Image, ImageDraw

from .paths import data_dir

try:
    from google import genai
    from google.genai import types

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class MediaEngine:
    def __init__(self, app: toga.App, force_offline: Optional[bool] = None):
        self.app = app
        self.out_dir = data_dir(app) / "media"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        if force_offline is not None:
            self.offline_mode = force_offline
        else:
            self.offline_mode = os.environ.get("GINK_OFFLINE_MODE", "false").lower() in ("true", "1", "yes")

        if not os.environ.get("GEMINI_API_KEY") and not self.offline_mode:
            self.offline_mode = True

        self.client = None
        if not self.offline_mode and HAS_GENAI:
            try:
                self.client = genai.Client()
            except Exception:
                self.offline_mode = True

    async def generate_text(self, prompt: str) -> str:
        if self.offline_mode or not self.client:
            await asyncio.sleep(0.3)
            return f"[Offline mock] Received prompt: '{prompt}'"
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None, lambda: self.client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            )
            return response.text
        except Exception as e:
            return f"Error: could not retrieve a live text response ({e})."

    async def generate_image(self, prompt: str, base_filename: Optional[str] = None) -> Optional[str]:
        base_filename = base_filename or f"generated_image_{int(time.time())}"
        target = self.out_dir / f"{base_filename}.jpg"

        if self.offline_mode or not self.client:
            await asyncio.sleep(0.5)
            img = Image.new("RGB", (512, 512), color=(41, 128, 185))
            draw = ImageDraw.Draw(img)
            draw.rectangle([40, 40, 472, 472], outline=(255, 255, 255), width=4)
            draw.ellipse([206, 206, 306, 306], fill=(231, 76, 60))
            img.save(target)
            return str(target)

        loop = asyncio.get_event_loop()
        try:
            def _call():
                return self.client.models.generate_images(
                    model="imagen-3.0-generate-002",
                    prompt=prompt,
                    config=types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="1:1"),
                )

            result = await loop.run_in_executor(None, _call)
            generated = result.generated_images[0]
            image = Image.open(io.BytesIO(generated.image.image_bytes))
            image.save(target)
            return str(target)
        except Exception:
            return None

    async def generate_video(self, prompt: str, base_filename: Optional[str] = None) -> Optional[str]:
        base_filename = base_filename or f"generated_video_{int(time.time())}"

        if self.offline_mode or not self.client:
            target = self.out_dir / f"{base_filename}.gif"
            await asyncio.sleep(0.6)
            frames = []
            for i in range(16):
                frame = Image.new("RGB", (512, 512), color=(41, 128, 185))
                draw = ImageDraw.Draw(frame)
                x = 60 + int(392 * (i / 15.0))
                draw.rectangle([20, 20, 492, 492], outline=(255, 255, 255), width=4)
                draw.ellipse([x - 40, 236, x + 40, 316], fill=(231, 76, 60))
                frames.append(frame)
            frames[0].save(target, save_all=True, append_images=frames[1:], duration=80, loop=0)
            return str(target)

        target = self.out_dir / f"{base_filename}.mp4"
        loop = asyncio.get_event_loop()
        try:
            operation = await loop.run_in_executor(
                None,
                lambda: self.client.models.generate_videos(
                    model="veo-2.0-generate-001", prompt=prompt, config=types.GenerateVideosConfig(number_of_videos=1)
                ),
            )
            while not operation.done:
                await asyncio.sleep(10)  # was time.sleep(10) -- no longer blocks the UI
                operation = await loop.run_in_executor(None, lambda: self.client.operations.get(operation))

            generated_video = operation.response.generated_videos[0]
            await loop.run_in_executor(None, lambda: self.client.files.download(file=generated_video.video))
            await loop.run_in_executor(None, lambda: generated_video.video.save(str(target)))
            return str(target)
        except Exception:
            return None
