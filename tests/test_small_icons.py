"""Tiny icons (32 px and under) use a simpler, bolder snowflake: the full artwork blurred at 20 px."""
import os, sys
from PIL import Image, ImageChops, IcnsImagePlugin
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_icons as m

ICONS = os.path.join(ROOT, "icons")


def same(a, b):
    """Pixel-for-pixel (getbbox() on RGBA only looks at alpha, which hid colour differences)."""
    a, b = a.convert("RGBA"), b.convert("RGBA")
    return a.size == b.size and a.tobytes() == b.tobytes()


def test_tiny_pngs_use_the_simple_snowflake():
    for s in (20, 29):                                                    # iOS: opaque squares
        assert same(Image.open(os.path.join(ICONS, f"ginkassistant-{s}.png")), m.small_art(s))
    for s in (16, 32):                                                    # Linux: rounded
        assert same(Image.open(os.path.join(ICONS, f"ginkassistant-{s}.png")), m.small_rounded(s, pad=0.04))


def test_windows_and_mac_icon_files():
    ico = Image.open(os.path.join(ICONS, "ginkassistant.ico"))
    assert sorted(ico.info["sizes"]) == [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]   # none lost
    for s in (16, 24, 32):
        ico.size = (s, s)
        ico.load()
        assert same(ico, m.small_rounded(s, pad=0.02))
    ico.size = (48, 48)
    ico.load()
    assert ico.size == (48, 48)
    icns = IcnsImagePlugin.IcnsFile(open(os.path.join(ICONS, "ginkassistant.icns"), "rb"))
    assert same(icns.getimage((16, 16, 2)), m.small_rounded(32, pad=0.06))


def test_simple_snowflake_is_crisp():
    """Lots of fully-lime pixels and fully-dark ones, few in between (the old 20 px was mostly muddy)."""
    im = m.small_art(20)
    px = list(getattr(im, "get_flattened_data", im.getdata)())
    lime = sum(1 for r, g, b in px if g > 200 and r > 140)
    dark = sum(1 for r, g, b in px if g < 60)
    assert lime >= 40 and dark >= 200


def test_genie_tiny_icons_are_its_lamp_not_ginks_snowflake():
    """make_genie_icons.py reuses make_icons.py: its tiny sizes must be the lamp (SMALL_ART hook)."""
    for s in (20, 29):
        genie = Image.open(os.path.join(ICONS, f"ginkgenie-{s}.png"))
        assert not same(genie, m.small_art(s))
    ico = Image.open(os.path.join(ICONS, "ginkgenie.ico"))
    assert sorted(ico.info["sizes"]) == [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    import pytest
    pytest.importorskip("cairosvg")
    import make_genie_icons as g
    assert same(Image.open(os.path.join(ICONS, "ginkgenie-20.png")), g.small_lamp(20))
    m.SMALL_ART = None                                          # (the import doesn't set it; main() does)
