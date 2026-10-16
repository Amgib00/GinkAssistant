"""
Checks (and with --fix, repairs) the project layout Briefcase depends on.

    python tools/check_project.py          # report only -- changes nothing
    python tools/check_project.py --fix    # move leftovers to a backup + put icons in place

Briefcase always works relative to the folder you RUN it from (the project root,
where pyproject.toml is):
  * it builds into   build/ginkassistant/<platform>/<format>    e.g. build/ginkassistant/macos/app
  * it reads icons from  <root>/<icon>.icns / .ico / -<size>.png   (pyproject: icon = "icons/ginkassistant")
    and copies them INTO the built app (Gink.app/Contents/Resources on macOS).
Folders like ./macOS or ./android at the root come from very old Briefcase versions
(or old settings) -- current Briefcase never uses them. Nothing is ever deleted:
--fix moves them into _old_builds/.
"""
import os
import shutil
import sys
import time

try:
    import tomllib
except ImportError:                       # Python 3.10
    import tomli as tomllib               # noqa  (pip install tomli)

STRAY = ["macOS", "macos", "iOS", "ios", "android", "Android", "windows", "Windows", "linux", "Linux",
         "tvOS", "web", "django", "MacOS"]
ICON_SUFFIXES = ([".icns", ".ico", ".png"] + [f"-{s}.png" for s in (16, 32, 64, 128, 256, 512)] +
                 [f"-{s}.png" for s in (20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 640, 1024, 1280, 1920)] +
                 [f"-round-{s}.png" for s in (48, 72, 96, 144, 192)] +
                 [f"-square-{s}.png" for s in (48, 72, 96, 144, 192, 320, 480, 640, 960, 1280)] +
                 [f"-adaptive-{s}.png" for s in (108, 162, 216, 324, 432)])


def _walk_apps(folder, depth=3):
    """Any *.app bundles inside (what old Briefcase versions left at the root)."""
    for dirpath, dirs, files in os.walk(folder):
        if dirpath[len(folder):].count(os.sep) >= depth:
            dirs[:] = []
        for d in list(dirs):
            if d.endswith(".app"):
                yield os.path.join(dirpath, d)
                dirs.remove(d)


def _real_name(root, name):
    """The folder's name as actually stored on disk (e.g. 'macOS' when asked about 'macos').
    Prefers the real folder over a shortcut (symlink) pointing to it, whatever order the
    system lists them in."""
    try:
        matches = [e for e in os.listdir(root)
                   if e.lower() == name.lower() and os.path.samefile(os.path.join(root, e), os.path.join(root, name))]
    except OSError:
        return name
    real = [e for e in matches if not os.path.islink(os.path.join(root, e))]
    return sorted(real or matches or [name])[0]


def _version_tuple(text):
    import re
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def _old_mac():
    """'10.15.7' on macOS 10.x (Catalina and older), else '' -- Briefcase 0.3.16+ apps need macOS 11."""
    if sys.platform != "darwin":
        return ""
    import platform
    ver = platform.mac_ver()[0]
    t = _version_tuple(ver)
    return ver if t and t < (11, 0, 0) else ""


def check_briefcase(out):
    """The `briefcase` your Terminal runs: is it new enough, and is it the one in this environment?"""
    import subprocess
    problems = 0
    try:
        from importlib.metadata import version
        env_v = version("briefcase")
    except Exception:
        env_v = None
    cmd = shutil.which("briefcase")
    cmd_v = None
    if cmd:
        try:
            cmd_v = subprocess.run([cmd, "-V"], capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception:
            cmd_v = None
    env_bin = os.path.dirname(sys.executable)
    old_mac = _old_mac()
    if old_mac:
        fix = 'python -m pip install "briefcase==0.3.15"'
    elif sys.version_info < (3, 11):
        fix = 'python -m pip install -U "briefcase==0.4.4"'
    else:
        fix = 'python -m pip install -U "briefcase>=0.4.4"'
    ev = _version_tuple(env_v) if env_v else None
    if env_v is None:
        out(f"  ! Briefcase isn't installed in this Python environment ({sys.executable}).")
        out(f"      fix: {fix}   then use:  python -m briefcase ...")
        problems += 1
    elif ev < (0, 3, 13):
        out(f"  ! Briefcase {env_v} in this environment is too old: versions up to 0.3.12 build into ./macOS/ "
            f"at the project root, not build/.")
        out(f"      fix: {fix}")
        problems += 1
    elif old_mac and ev >= (0, 3, 16):
        out(f"  ! Briefcase {env_v} makes Mac apps that need macOS 11 or newer -- they won't open on this Mac "
            f"(macOS {old_mac}). 0.3.15 is the newest whose apps open on 10.15 and that builds into build/.")
        out(f"      fix: {fix}   then:  python -m briefcase create macOS")
        problems += 1
    else:
        out(f"  \u2713 Briefcase {env_v} in this environment (builds into build/"
            + (f"; apps open on this Mac, macOS {old_mac})" if old_mac else ")"))
    if cmd and os.path.dirname(os.path.realpath(cmd)) != os.path.realpath(env_bin):
        tv = _version_tuple(cmd_v)
        out(f"  ! Typing `briefcase` runs {cmd} (version {cmd_v or 'unknown'}), NOT the one in this environment.")
        out("      use  python -m briefcase ...  instead (or remove the other copy)")
        problems += 1
    elif cmd_v and _version_tuple(cmd_v) and _version_tuple(cmd_v) < (0, 3, 13) and env_v and _version_tuple(env_v) >= (0, 3, 13):
        out(f"  ! `briefcase` reports {cmd_v} -- older than 0.3.13; reinstall it: {fix}")
        problems += 1
    return problems


def find_root(start):
    p = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(p, "pyproject.toml")) and os.path.isdir(os.path.join(p, "src")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def check(root, fix=False, out=print, briefcase_check=True):
    problems, fixed = 0, 0
    cfg = tomllib.load(open(os.path.join(root, "pyproject.toml"), "rb"))
    app_name = next(iter(cfg["tool"]["briefcase"]["app"]))
    app = cfg["tool"]["briefcase"]["app"][app_name]
    formal = app.get("formal_name", app_name)
    out(f"Project root: {root}")
    if os.path.abspath(os.getcwd()) != root:
        out(f"  ! You're in {os.getcwd()} -- run briefcase from the project root:  cd \"{root}\"")
        problems += 1

    # 0) which Briefcase actually runs (an old one builds into ./macOS/ at the root)
    if briefcase_check:
        problems += check_briefcase(out)

    # 1) old settings Briefcase ignores
    for plat, sec in app.items():
        if isinstance(sec, dict) and "output_dir" in sec:
            out(f"  ! pyproject.toml [{plat}] has output_dir -- Briefcase has no such setting; remove it.")
            problems += 1

    # 2) leftover build folders outside build/
    backup = os.path.join(root, "_old_builds", time.strftime("%Y-%m-%d_%H%M%S"))
    seen = set()
    for name in STRAY:
        p = os.path.join(root, name)
        if os.path.isdir(p) and not os.path.isfile(os.path.join(p, "__init__.py")):
            # macOS disks usually ignore capital letters: ./macOS, ./macos and ./MacOS are
            # then ONE folder -- count and move it once (identified by the disk, not the spelling)
            st = os.stat(p)
            if (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            name = _real_name(root, name)
            problems += 1
            if fix:
                os.makedirs(backup, exist_ok=True)
                shutil.move(p, os.path.join(backup, name))
                fixed += 1
                out(f"  \u2713 moved leftover ./{name}/ -> {os.path.relpath(backup, root)}/{name}/")
            else:
                apps = [d for d in _walk_apps(p)]
                made_by = " -- built by Briefcase 0.3.12 or older" if apps else ""
                out(f"  ! leftover build folder ./{name}/ outside build/{made_by} -- --fix moves it to _old_builds/")

    # 3) icons where pyproject says
    icon = app.get("icon")
    if not icon:
        out("  ! pyproject.toml has no icon -> Briefcase uses its default bee")
        problems += 1
    else:
        prefix = os.path.join(root, icon)
        missing = [s for s in ICON_SUFFIXES if not os.path.isfile(prefix + s)]
        if missing:
            problems += 1
            # look for a complete set somewhere else in the project (e.g. resources/)
            base = os.path.basename(icon)
            found = None
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in ("build", "dist", ".git", "_old_builds", "node_modules") and not d.startswith(".")]
                if os.path.abspath(dirpath) == os.path.dirname(prefix):
                    continue
                if base + ".icns" in files and base + "-1024.png" in files:
                    found = dirpath
                    break
            if found and fix:
                os.makedirs(os.path.dirname(prefix), exist_ok=True)
                n = 0
                for s in ICON_SUFFIXES:
                    src = os.path.join(found, base + s)
                    if os.path.isfile(src) and not os.path.isfile(prefix + s):
                        shutil.copy2(src, prefix + s); n += 1
                fixed += 1
                out(f"  \u2713 copied {n} icon files from {os.path.relpath(found, root)}/ into {os.path.dirname(icon)}/")
            elif found:
                out(f"  ! {len(missing)} icon files missing in {os.path.dirname(icon) or '.'}/ but found in "
                    f"{os.path.relpath(found, root)}/ -- --fix copies them over")
            else:
                out(f"  ! {len(missing)} icon files missing (e.g. {base}{missing[0]}) -- run: python tools/make_icons.py")
        else:
            out(f"  \u2713 all {len(ICON_SUFFIXES)} icon files present ({icon}.*)")

    # 4) the built Mac app (if there is one)
    mac_app = os.path.join(root, "build", app_name, "macos", "app", f"{formal}.app")
    if os.path.isdir(mac_app):
        res = os.path.join(mac_app, "Contents", "Resources")
        icns = [f for f in os.listdir(res) if f.endswith(".icns")] if os.path.isdir(res) else []
        if icns:
            out(f"  \u2713 built app: build/{app_name}/macos/app/{formal}.app (icon inside: {', '.join(icns)})")
            if icon and os.path.isfile(os.path.join(root, icon) + ".icns"):
                newest = max(os.path.getmtime(os.path.join(res, f)) for f in icns)
                if os.path.getmtime(os.path.join(root, icon) + ".icns") > newest + 1:
                    out("  ! the app's icon is older than icons/ -- run: briefcase update macOS --update-resources")
                    problems += 1
        else:
            out(f"  ! built app has no icon in Contents/Resources -- run: briefcase update macOS --update-resources")
            problems += 1
    else:
        out(f"  \u00b7 no Mac app built yet (expected at build/{app_name}/macos/app/{formal}.app)")

    out("")
    if problems == 0:
        out("Everything is in place.")
    elif fix:
        out(f"Fixed {fixed} of {problems} problem(s)." + ("" if fixed == problems else " See the notes above for the rest."))
    else:
        out(f"{problems} problem(s) found. Run again with --fix to repair what can be repaired automatically.")
    return problems, fixed


def main():
    root = find_root(os.getcwd()) or find_root(os.path.dirname(os.path.abspath(__file__)))
    if not root:
        print("Couldn't find the project (a folder with pyproject.toml and src/).")
        sys.exit(1)
    problems, fixed = check(root, fix="--fix" in sys.argv)
    sys.exit(0 if problems == fixed or problems == 0 else 1)


if __name__ == "__main__":
    main()
