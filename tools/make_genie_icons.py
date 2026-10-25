"""
Gink Genie's app icons (pyproject: icon = "icons/ginkgenie") from the owner's lamp picture
(icons/genie-source/lamp.png), styled exactly like Gink's own icons by tools/make_icons.py.
    python tools/make_genie_icons.py
The lamp photo is wide with a busy background, so it is placed on Gink's dark tile colour with
its edges fading into the dark: a glowing lamp, not a pasted photo.
"""
import os
from PIL import Image, ImageDraw, ImageFilter

import make_icons as m

ROOT = m.ROOT
LAMP = os.path.join(ROOT, "icons", "genie-source", "lamp.png")
SQUARE = os.path.join(ROOT, "icons", "genie-source", "lamp-square.png")


def square_source(size=1024):
    lamp = Image.open(LAMP).convert("RGB")
    w = int(size * 0.96); h = int(lamp.height * w / lamp.width)
    lamp = lamp.resize((w, h), Image.LANCZOS)
    fade = Image.new("L", (w, h), 0)                                  # soft oval: the edges melt into the dark
    ImageDraw.Draw(fade).ellipse((int(w * 0.04), int(h * 0.02), int(w * 0.96), int(h * 0.98)), fill=255)
    fade = fade.filter(ImageFilter.GaussianBlur(size * 0.035))
    canvas = Image.new("RGB", (size, size), m.BG)
    canvas.paste(lamp, ((size - w) // 2, (size - h) // 2 + int(size * 0.02)), fade)
    canvas.save(SQUARE)
    return SQUARE


def main():
    m.SRC = square_source()
    m.CROP = (0, 0, 1024, 1024)
    m.OUT = os.path.join(ROOT, "icons", "ginkgenie")
    m.RUNTIME = os.path.join(ROOT, "src", "ginkgenie", "resources", "ginkgenie.png")
    m.main()


if __name__ == "__main__":
    main()
