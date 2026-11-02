"""
Make every app icon Briefcase needs from ONE picture (icons/source-icon.png).

    python tools/make_icons.py

Writes icons/ginkassistant*.{icns,ico,png} (pyproject: icon = "icons/ginkassistant")
and the in-app icon src/ginkassistant/resources/ginkassistant.png. Without these
files Briefcase falls back to BeeWare's default "bee" icon.

The source is a dark rounded square on a white background with a drop shadow.
We cut a square centred on the logo, apply a clean rounded mask (no white, no
shadow), then style it per platform:
  macOS   .icns -- Apple grid: 824 px body on a 1024 canvas + soft shadow
  Windows .ico, Linux PNGs -- rounded square
  iOS     -- full square, NO transparency (iOS rounds it; the App Store rejects alpha)
  Android -- round (circle), square, and adaptive (logo only, in the 66% safe zone)
Sizes of 32 px and under use a simpler, bolder snowflake (small_art): the full one blurs there.
"""
import os
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icons", "source-icon.png")
OUT = os.path.join(ROOT, "icons", "ginkassistant")
RUNTIME = os.path.join(ROOT, "src", "ginkassistant", "resources", "ginkassistant.png")
BG = (21, 29, 35)               # the icon's dark colour (#151D23)
CROP = (95, 100, 1156, 1161)    # square centred on the logo, kept INSIDE the square's light bevel/rim
RADIUS = 0.20                   # corner radius as a share of the side


def rounded_mask(size, radius=RADIUS, inset=0.0):
    big = size * 4                                     # supersampled -> smooth edges
    m = Image.new("L", (big, big), 0)
    pad = int(big * inset)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, big - 1 - pad, big - 1 - pad), radius=int(big * radius), fill=255)
    return m.resize((size, size), Image.LANCZOS)


def base_art(size=1024):
    """The artwork, square, with any white outside the rounded corners replaced by the dark colour."""
    art = Image.open(SRC).convert("RGB").crop(CROP).resize((size, size), Image.LANCZOS)
    full = Image.new("RGB", (size, size), BG)
    full.paste(art, (0, 0), rounded_mask(size, RADIUS * 0.9, inset=0.012))   # anything near the old edge -> dark
    return full                                        # full-bleed, opaque


def rounded(size=1024, pad=0.0):
    art = base_art(1024)
    rgba = art.convert("RGBA")
    rgba.putalpha(rounded_mask(1024))
    if pad:
        body = int(1024 * (1 - 2 * pad))
        canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
        canvas.paste(rgba.resize((body, body), Image.LANCZOS), ((1024 - body) // 2,) * 2)
        rgba = canvas
    return rgba.resize((size, size), Image.LANCZOS)


def mac_icon():
    """Apple's macOS grid: 824 px body centred on 1024, with a soft drop shadow."""
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    body = rounded(824)
    shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    sh = Image.new("RGBA", (824, 824), (0, 0, 0, 110))
    sh.putalpha(ImageChops.multiply(rounded_mask(824), Image.new("L", (824, 824), 110)))
    shadow.paste(sh, (100, 112), sh)
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.alpha_composite(body, (100, 100))
    return canvas


def logo_only(size):
    """The green snowflake alone on transparency (Android adaptive foreground)."""
    art = base_art(1024)
    # how far each pixel is from the dark background (lime is high in red AND green,
    # so "green minus red" under-counted it and made the logo faint)
    diff = ImageChops.difference(art, Image.new("RGB", art.size, BG))
    dr, dg, db = diff.split()
    alpha = ImageChops.lighter(ImageChops.lighter(dr, dg), db).point(lambda v: max(0, min(255, int((v - 18) * 2.2))))
    logo = art.convert("RGBA"); logo.putalpha(alpha)
    # Android shows the central 66/108 (61%); the snowflake fills ~72% of its square,
    # so scaling the square to 80% keeps the snowflake (~58%) inside the safe zone
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    inner = int(1024 * 0.80)
    canvas.paste(logo.resize((inner, inner), Image.LANCZOS), ((1024 - inner) // 2,) * 2)
    return canvas.resize((size, size), Image.LANCZOS)


def circle(size):
    art = base_art(1024).convert("RGBA")
    m = Image.new("L", (4096, 4096), 0); ImageDraw.Draw(m).ellipse((0, 0, 4095, 4095), fill=255)
    art.putalpha(m.resize((1024, 1024), Image.LANCZOS))
    return art.resize((size, size), Image.LANCZOS)


# ---- Tiny sizes (32 px and under): the full snowflake's thin branches and end circles blur into a
# green smudge, so these sizes get a simpler, bolder snowflake drawn for the pixel grid: six thick
# spokes with round tips, a side branch pair on each spoke from 24 px, and the hexagon hub.
LIME = (171, 245, 57)           # the snowflake's green (sampled from the artwork)
SMALL = 32                      # this size and smaller use small_art()


def small_art(size):
    """The simplified snowflake, full-bleed and opaque (like base_art), drawn 8x and scaled down."""
    import math
    big = size * 8
    c, r_out = big / 2, big * 0.40
    w = max(big * 0.085, 10)                       # never thinner than ~1.25 px at the final size
    im = Image.new("RGB", (big, big), BG)
    d = ImageDraw.Draw(im)
    for k in range(6):
        a = math.pi / 2 + k * math.pi / 3
        x, y = c + r_out * math.cos(a), c - r_out * math.sin(a)
        d.line((c, c, x, y), fill=LIME, width=int(w))
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=LIME)
        if size >= 24:
            bx, by = c + r_out * 0.62 * math.cos(a), c - r_out * 0.62 * math.sin(a)
            for side in (-1, 1):
                b = a + side * math.pi / 4
                d.line((bx, by, bx + r_out * 0.30 * math.cos(b), by - r_out * 0.30 * math.sin(b)),
                       fill=LIME, width=int(w * 0.8))
    d.regular_polygon((c, c, big * 0.12), 6, rotation=0, fill=BG, outline=LIME, width=int(w * 0.9))
    return im.resize((size, size), Image.LANCZOS)


SMALL_ART = None                # another app's tiny art (tools/make_genie_icons.py sets its lamp)


def tiny(size):
    return (SMALL_ART or small_art)(size)


def small_rounded(size, pad=0.0):
    """The tiny art as a rounded square on transparency (Linux, Windows, macOS tiny sizes)."""
    body = max(1, round(size * (1 - 2 * pad)))
    art = tiny(body).convert("RGBA")
    art.putalpha(rounded_mask(body))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(art, ((size - body) // 2,) * 2)
    return canvas


def save(img, suffix):
    path = f"{OUT}{suffix}"
    img.save(path)
    return path


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    made = []
    mac = mac_icon()
    mac.save(OUT + ".icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
             append_images=[small_rounded(32, pad=0.06)])     # 16 pt @2x (32 px): the simpler art
    made.append(OUT + ".icns")
    ico = rounded(256, pad=0.02)
    # every size given explicitly: Pillow resizes a missing size from the LAST extra image, not the big one
    ico.save(OUT + ".ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)],
             append_images=[small_rounded(s, pad=0.02) if s <= SMALL else ico.resize((s, s), Image.LANCZOS)
                            for s in (16, 24, 32, 48, 64, 128)])
    made.append(OUT + ".ico")
    made.append(save(rounded(1024, pad=0.04), ".png"))
    for s in (16, 32, 64, 128, 256, 512):                                   # Linux
        made.append(save(small_rounded(s, pad=0.04) if s <= SMALL else rounded(s, pad=0.04), f"-{s}.png"))
    for s in (20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024):     # iOS: opaque squares
        made.append(save(tiny(s) if s <= SMALL else base_art(1024).resize((s, s), Image.LANCZOS), f"-{s}.png"))
    for s in (640, 1280, 1920):                                             # iOS launch images: icon on the splash colour
        made.append(save(rounded(s, pad=0.2), f"-{s}.png"))
    for s in (48, 72, 96, 144, 192):                                        # Android
        made.append(save(circle(s), f"-round-{s}.png"))
        made.append(save(rounded(s, pad=0.02), f"-square-{s}.png"))
    for s in (320, 480, 640, 960, 1280):                                    # Android splash images
        made.append(save(rounded(s, pad=0.2), f"-square-{s}.png"))
    for s in (108, 162, 216, 324, 432):                                     # Android adaptive foreground
        made.append(save(logo_only(s), f"-adaptive-{s}.png"))
    os.makedirs(os.path.dirname(RUNTIME), exist_ok=True)
    rounded(512, pad=0.04).save(RUNTIME)                                    # Dock / window icon at runtime
    made.append(RUNTIME)
    print(f"made {len(made)} icon files")


if __name__ == "__main__":
    main()
