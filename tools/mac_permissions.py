"""
Put the privacy texts macOS needs into Gink's Info.plist -- for Mac apps built with Briefcase 0.3.15 (the Catalina
build: .github/workflows/macos-catalina.yml, and "gbrief" on the owner's Mac).

Why (0.1.160): Briefcase 0.3.15 ignores [tool.briefcase.app.ginkassistant.macOS.permission] and [..macOS.info]
(checked in its source and its macOS template: neither knows them; Briefcase 0.4 does). Without
NSMicrophoneUsageDescription macOS never asks for the microphone and gives the app silence -- the
"Hey Gink can't hear you" / "The microphone is sending only silence" the owner saw on Catalina.
(INTEGRATION.md 0.1.46 said 0.3.15 reads "permission": it doesn't.)

    python tools/mac_permissions.py build/ginkassistant/macos/app/Gink.app          # after `briefcase create/build`
    python tools/mac_permissions.py /Applications/Gink.app --sign                    # an app already installed

--sign signs it again (ad hoc), because changing Info.plist breaks the old signature. Then
`tccutil reset Microphone com.amgib.ginkassistant` and open Gink: macOS asks for the microphone.
"""
import argparse
import os
import plistlib
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:          # Python 3.10 (the owner's Catalina Mac)
    try:
        import tomli as tomllib      # type: ignore
    except ModuleNotFoundError:
        tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Briefcase's permission names -> Info.plist keys (what Briefcase 0.4 writes for them)
PERMISSION_KEYS = {
    "microphone": "NSMicrophoneUsageDescription",
    "camera": "NSCameraUsageDescription",
    "photo_library": "NSPhotoLibraryUsageDescription",
    "bluetooth": "NSBluetoothAlwaysUsageDescription",
    "fine_location": "NSLocationUsageDescription",
    "coarse_location": "NSLocationUsageDescription",
}


def _tables(text: str, app_name: str) -> dict:
    """Without tomllib/tomli (Python 3.10): the two macOS tables' plain  key = "text"  lines."""
    import json
    import re
    out = {}
    for table in ("permission", "info"):
        head = r"^\[tool\.briefcase\.app\.%s\.macOS\.%s\][ \t]*(?:#[^\n]*)?$" % (re.escape(app_name), table)
        m = re.search(head + r"(.*?)(?=^\[|\Z)", text, re.M | re.S)
        if m:
            out[table] = {k: json.loads('"' + v + '"')
                          for k, v in re.findall(r'^([A-Za-z_][\w.-]*)[ \t]*=[ \t]*"((?:[^"\\\n]|\\.)*)"', m.group(1), re.M)}
    return out


def wanted(app_name: str = "ginkassistant", pyproject: str = "") -> dict:
    """The Info.plist entries pyproject.toml asks for: [..macOS.permission] mapped, plus [..macOS.info] as is."""
    with open(pyproject or os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        raw = f.read()
    if tomllib is not None:
        mac = tomllib.loads(raw.decode("utf-8"))["tool"]["briefcase"]["app"][app_name].get("macOS", {})
    else:
        mac = _tables(raw.decode("utf-8"), app_name)
    out = {}
    for name, text in (mac.get("permission") or {}).items():
        if name in PERMISSION_KEYS and text:
            out[PERMISSION_KEYS[name]] = str(text)
    for key, value in (mac.get("info") or {}).items():
        out[str(key)] = value
    return out


def apply(app_path: str, entries: dict) -> list:
    """Add or update the entries in <App>.app/Contents/Info.plist. Returns the keys it changed."""
    plist = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist, "rb") as f:
        info = plistlib.load(f)
    changed = [k for k, v in entries.items() if info.get(k) != v]
    if changed:
        info.update(entries)
        with open(plist, "wb") as f:
            plistlib.dump(info, f)
    return changed


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("app", help="path to Gink.app")
    p.add_argument("--sign", action="store_true", help="sign it again (ad hoc) afterwards")
    p.add_argument("--app-name", default="ginkassistant")
    p.add_argument("--pyproject", default="")
    a = p.parse_args(argv)
    if not os.path.isfile(os.path.join(a.app, "Contents", "Info.plist")):
        print(f"No Info.plist in {a.app}: give the path to the .app", file=sys.stderr)
        return 2
    entries = wanted(a.app_name, a.pyproject)
    changed = apply(a.app, entries)
    for key in sorted(entries):
        print(("updated " if key in changed else "already ") + key)
    if a.sign:
        r = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", a.app])
        if r.returncode:
            return r.returncode
        print("signed again (ad hoc)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
