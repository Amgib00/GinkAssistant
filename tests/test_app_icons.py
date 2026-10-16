"""Every icon Briefcase looks for must exist -- a missing one means BeeWare's default 'bee'."""
import os
try:
    import tomllib
except ImportError:            # Python 3.10
    import tomli as tomllib
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")
PREFIX = os.path.join(ROOT, tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))
                      ["tool"]["briefcase"]["app"]["ginkassistant"]["icon"])
# the exact files Briefcase asks for (BeeWare tutorial: "Customizing icons")
LINUX = [16, 32, 64, 128, 256, 512]
IOS = [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 640, 1024, 1280, 1920]
ANDROID = ([f"round-{s}" for s in (48, 72, 96, 144, 192)] +
           [f"square-{s}" for s in (48, 72, 96, 144, 192, 320, 480, 640, 960, 1280)] +
           [f"adaptive-{s}" for s in (108, 162, 216, 324, 432)])


def test_every_platform_icon_exists_at_the_right_size():
    missing = []
    for suffix in [".icns", ".ico"]:
        if not os.path.isfile(PREFIX + suffix):
            missing.append(PREFIX + suffix)
    for name in [str(s) for s in sorted(set(LINUX + IOS))] + ANDROID:
        path = f"{PREFIX}-{name}.png"
        if not os.path.isfile(path):
            missing.append(path); continue
        size = int(name.split("-")[-1])
        assert Image.open(path).size == (size, size), path
    assert not missing, "Briefcase would use the default bee for: " + ", ".join(os.path.basename(m) for m in missing)


def test_formats_and_transparency():
    assert Image.open(PREFIX + ".icns").format == "ICNS"
    assert (256, 256) in Image.open(PREFIX + ".ico").info["sizes"]
    for s in (180, 1024):                                   # the App Store rejects icons with transparency
        assert Image.open(f"{PREFIX}-{s}.png").mode == "RGB"
    fg = Image.open(f"{PREFIX}-adaptive-432.png").convert("RGBA")
    assert fg.getpixel((2, 2))[3] == 0                                      # logo only, on transparency
    assert fg.split()[3].getextrema()[1] >= 250                             # ...and fully solid, not faint
    corner = Image.open(f"{PREFIX}-round-192.png").convert("RGBA").getpixel((1, 1))
    assert corner[3] == 0                                                   # round icon is really round


def test_runtime_icon_for_python_m_runs():
    assert os.path.isfile(os.path.join(ROOT, "src", "ginkassistant", "resources", "ginkassistant.png"))
    src = open(os.path.join(ROOT, "src", "ginkassistant", "app.py")).read()
    assert 'icon="resources/ginkassistant"' in src
