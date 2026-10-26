"""
Gink Genie's app icons (pyproject: icon = "icons/ginkgenie"): the lamp line icon (the same drawing as
the sidebar's) in Gink's lime on Gink's dark tile -- like Gink's own lime snowflake -- styled exactly
like Gink's icons by tools/make_icons.py.
    python tools/make_genie_icons.py          (needs: pip install cairosvg)
"""
import io
import os

from PIL import Image

import make_icons as m

ROOT = m.ROOT
SQUARE = os.path.join(ROOT, "icons", "genie-source", "lamp-square.png")
LIME = "#A8F03C"
LAMP_PATHS = '<path d="M2 10.2c1.9.1 3.4 1.2 4.7 2.2 1 .8 2.2 1.4 3.7 1.4h4c2 0 3.7-1.2 4.2-3"/><path d="M7.2 13.4c.7 2 2.6 3.2 4.8 3.2h1.6c2.1 0 3.9-1.3 4.5-3.2"/><path d="M10.6 10.9c0-1.5 1.1-2.6 2.6-2.6s2.6 1.1 2.6 2.6"/><path d="M13.2 8.3V6.9"/><circle cx="13.2" cy="5.9" r="1.1" fill="currentColor" stroke="none"/><path d="M18.6 11.2c1.3-.4 2.7.2 3 1.4.3 1.2-.6 2.4-2 2.6-.5.1-1 0-1.4-.2"/><path d="M11.4 16.6l-.6 2.2h5l-.6-2.2"/><path d="M9.6 18.8h6.6"/>'


def square_source(size=1024):
    import cairosvg
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{LIME}" '
           f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" color="{LIME}">{LAMP_PATHS}</svg>')
    art = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=int(size * 0.74),
                                                 output_height=int(size * 0.74)))).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), m.BG + (255,))
    off = (size - art.width) // 2
    canvas.alpha_composite(art, (off, off - int(size * 0.02)))
    os.makedirs(os.path.dirname(SQUARE), exist_ok=True)
    canvas.convert("RGB").save(SQUARE)
    return SQUARE


def main():
    m.SRC = square_source()
    m.CROP = (0, 0, 1024, 1024)
    m.OUT = os.path.join(ROOT, "icons", "ginkgenie")
    m.RUNTIME = os.path.join(ROOT, "src", "ginkgenie", "resources", "ginkgenie.png")
    m.main()


if __name__ == "__main__":
    main()
