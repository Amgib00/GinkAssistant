"""
"Do a check" (0.1.160): Gink checks the computer it runs on and says what it found -- instead of asking which
operating system the person's laptop has and handing them a list of steps (what it did before).

check_device() looks at: the system and its age (no more security updates?), how long since a restart, the
processor's load and what's using it, memory, storage, the battery's charge and health, and the built-in
protections (FileVault/BitLocker-style disk encryption, the firewall, Gatekeeper, antivirus). Optionally the
pending system updates (slow: the update server is asked). Every command has a time limit and nothing is changed:
it only reads. The AI gets the facts plus `issues` (each with what to do), and explains them in plain words.

Mac, Windows and Linux; on a phone only what's readable (storage, battery). Never raises.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import sys
import time
from typing import Dict, List, Optional

from ._shell import run

MAC, WIN = sys.platform == "darwin", sys.platform.startswith("win")
ANDROID, IOS = hasattr(sys, "getandroidapilevel"), sys.platform == "ios"

MAC_NAMES = {"10.13": "High Sierra", "10.14": "Mojave", "10.15": "Catalina", "11": "Big Sur", "12": "Monterey",
             "13": "Ventura", "14": "Sonoma", "15": "Sequoia", "26": "Tahoe"}
MAC_UNSUPPORTED = ("10.", "11.", "12.")          # Apple no longer sends these security updates (2026)


def _psutil():
    try:
        import psutil
        return psutil
    except Exception:
        return None


def _gb(n: float) -> str:
    return f"{n / 1e9:.0f} GB" if n >= 10e9 else f"{n / 1e9:.1f} GB"


def _days(seconds: float) -> str:
    if seconds < 3600:
        return "less than an hour"
    d = int(seconds // 86400)
    h = int(seconds % 86400 // 3600)
    return f"{d} day{'s' if d != 1 else ''}" + (f", {h} h" if d < 3 and h else "") if d else f"{h} h"


def _mac_version() -> str:
    return platform.mac_ver()[0] or (run(["sw_vers", "-productVersion"], timeout=5)[1] or "")


def _system(report: dict, issues: list) -> None:
    from .. import device_info
    info = device_info.details()
    report["device"] = device_info.describe(info)
    if MAC:
        ver = _mac_version()
        major = ver.split(".")[0] if not ver.startswith("10.") else ".".join(ver.split(".")[:2])
        report["system"] = f"macOS {MAC_NAMES.get(major, '')} {ver}".replace("  ", " ")
        if ver.startswith(MAC_UNSUPPORTED):
            issues.append({"level": "warn", "what": f"{report['system']} no longer gets security updates from Apple.",
                           "fix": "If this Mac can run a newer macOS, update it (Software Update). If not, keep "
                                  "your browser and apps up to date, and be careful with downloads."})
    elif WIN:
        report["system"] = info.get("os") or f"Windows {platform.release()}"
        if "Windows 10" in report["system"] or platform.release() in ("7", "8", "8.1"):
            issues.append({"level": "warn", "what": f"{report['system']} no longer gets free security updates from Microsoft.",
                           "fix": "Upgrade to Windows 11 if this PC supports it (Settings > Windows Update), or enrol "
                                  "in Extended Security Updates."})
    else:
        report["system"] = info.get("os") or platform.platform()


def _uptime(report: dict, issues: list) -> None:
    boot = None
    ps = _psutil()
    if ps:
        try:
            boot = ps.boot_time()
        except Exception:
            boot = None
    if boot is None and MAC:
        ok, out = run(["sysctl", "-n", "kern.boottime"], timeout=5)
        m = re.search(r"sec\s*=\s*(\d+)", out) if ok else None
        boot = float(m.group(1)) if m else None
    if boot is None and os.path.exists("/proc/uptime"):
        try:
            boot = time.time() - float(open("/proc/uptime").read().split()[0])
        except Exception:
            boot = None
    if boot:
        up = time.time() - boot
        report["since_restart"] = _days(up)
        if up > 14 * 86400:
            issues.append({"level": "tip", "what": f"It hasn't restarted in {_days(up)}.",
                           "fix": "Restart it: that clears memory, finishes updates and often fixes slowness."})


def _top_processes(limit: int = 5) -> List[dict]:
    rows = []
    if MAC or sys.platform.startswith("linux"):
        cmd = ["ps", "-Ao", "pcpu,pmem,comm", "-r"] if MAC else ["ps", "-eo", "pcpu,pmem,comm", "--sort=-pcpu"]
        ok, out = run(cmd, timeout=6)
        for line in (out.splitlines()[1:] if ok else []):
            parts = line.split(None, 2)
            if len(parts) == 3:
                try:
                    rows.append({"name": os.path.basename(parts[2].strip())[:40], "cpu": float(parts[0]), "memory": float(parts[1])})
                except ValueError:
                    continue
    else:
        ps = _psutil()
        if ps:
            try:
                procs = list(ps.process_iter(["name", "memory_percent"]))
                for p in procs:
                    try:
                        p.cpu_percent(None)
                    except Exception:
                        pass
                time.sleep(0.5)
                for p in procs:
                    try:
                        rows.append({"name": (p.info.get("name") or "?")[:40], "cpu": p.cpu_percent(None),
                                     "memory": round(p.info.get("memory_percent") or 0, 1)})
                    except Exception:
                        continue
                rows.sort(key=lambda r: r["cpu"], reverse=True)
            except Exception:
                rows = []
    rows = [r for r in rows if r["name"] and not r["name"].isdigit() and r["name"] not in ("ps", "System Idle Process", "Idle")]
    return rows[:limit]


def _cpu_memory(report: dict, issues: list) -> None:
    cores = os.cpu_count() or 1
    try:
        load = os.getloadavg()[0]
        report["processor_load"] = f"{round(100 * load / cores)}% of {cores} cores (last minute)"
        busy = load / cores
    except (AttributeError, OSError):
        busy = None
        ps = _psutil()
        if ps:
            try:
                pct = ps.cpu_percent(interval=0.5)
                report["processor_load"] = f"{pct:.0f}% of {cores} cores"
                busy = pct / 100
            except Exception:
                pass
    top = _top_processes()
    if top:
        report["busiest_apps"] = [f"{r['name']} ({r['cpu']:.0f}% processor, {r['memory']:.0f}% memory)" for r in top]
    if busy is not None and busy > 1.2 and top:
        issues.append({"level": "warn", "what": f"The processor is very busy; {top[0]['name']} uses the most.",
                       "fix": f"Quit {top[0]['name']} if you don't need it (or ask me to close it)."})
    ps = _psutil()
    if ps:
        try:
            vm = ps.virtual_memory()
            report["memory"] = f"{_gb(vm.total - vm.available)} used of {_gb(vm.total)} ({vm.percent:.0f}%)"
            if vm.percent >= 88:
                issues.append({"level": "warn", "what": f"Memory is nearly full ({vm.percent:.0f}% used).",
                               "fix": "Close apps and browser tabs you aren't using, or restart."})
        except Exception:
            pass
    elif MAC:
        ok, out = run(["memory_pressure"], timeout=8)
        m = re.search(r"free percentage:\s*(\d+)%", out) if ok else None
        if m:
            free = int(m.group(1))
            report["memory"] = f"{100 - free}% in use"
            if free < 12:
                issues.append({"level": "warn", "what": f"Memory is nearly full ({100 - free}% in use).",
                               "fix": "Close apps and browser tabs you aren't using, or restart."})


def _storage(report: dict, issues: list) -> None:
    path = os.path.expanduser("~")
    if WIN:
        path = os.environ.get("SystemDrive", "C:") + "\\"
    try:
        du = shutil.disk_usage(path)
    except Exception:
        return
    free_pct = 100 * du.free / du.total if du.total else 0
    report["storage"] = f"{_gb(du.free)} free of {_gb(du.total)} ({free_pct:.0f}% free)"
    if free_pct < 10 or du.free < 8e9:
        where = ("Apple menu > About This Mac > Storage > Manage" if MAC else "Settings > System > Storage" if WIN
                 else "your file manager")
        issues.append({"level": "warn", "what": f"Storage is almost full: {_gb(du.free)} free.",
                       "fix": f"Empty the Trash and Downloads, and remove big files you don't need ({where}). "
                              "I can find your largest recent files if you like."})


def _mac_battery(report: dict, issues: list) -> None:
    ok, out = run(["pmset", "-g", "batt"], timeout=5)
    m = re.search(r"(\d+)%;\s*([a-zA-Z ]+);", out) if ok else None
    if not m:
        return                                            # a desktop Mac: no battery
    state = m.group(2).strip()
    report["battery"] = f"{m.group(1)}% ({'charging' if state == 'charging' else 'charged' if 'charged' in state or 'finishing' in state else 'on battery'})"
    ok, out = run(["ioreg", "-r", "-c", "AppleSmartBattery"], timeout=6)
    if not ok:
        return

    def val(key):
        mm = re.search(r'"%s"\s*=\s*(\d+)' % key, out)
        return int(mm.group(1)) if mm else None
    cycles, design = val("CycleCount"), val("DesignCapacity")
    full = val("AppleRawMaxCapacity") or val("MaxCapacity")
    if cycles is not None:
        report["battery_cycles"] = cycles
    if design and full and full > 100:                    # MaxCapacity is a % on Apple silicon: then skip
        health = round(100 * full / design)
        report["battery_health"] = f"{health}% of its original capacity"
        if health < 80:
            issues.append({"level": "warn", "what": f"The battery holds {health}% of what it did when new"
                                                    + (f" ({cycles} charge cycles)" if cycles else "") + ".",
                           "fix": "It's worn: expect shorter battery life. A battery replacement brings it back."})
    if "PermanentFailureStatus" in out and re.search(r'"PermanentFailureStatus"\s*=\s*[1-9]', out):
        issues.append({"level": "warn", "what": "The battery reports a fault.",
                       "fix": "Have the battery checked (Apple or a repair shop)."})


def _battery(report: dict, issues: list) -> None:
    if MAC:
        return _mac_battery(report, issues)
    ps = _psutil()
    if ps:
        try:
            b = ps.sensors_battery()
            if b is not None:
                report["battery"] = f"{b.percent:.0f}% ({'charging' if b.power_plugged else 'on battery'})"
        except Exception:
            pass
    base = "/sys/class/power_supply"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.startswith("BAT"):
                continue

            def read(f):
                try:
                    return open(os.path.join(base, name, f)).read().strip()
                except OSError:
                    return ""
            full = read("energy_full") or read("charge_full")
            design = read("energy_full_design") or read("charge_full_design")
            if full.isdigit() and design.isdigit() and int(design):
                health = round(100 * int(full) / int(design))
                report["battery_health"] = f"{health}% of its original capacity"
                if health < 80:
                    issues.append({"level": "warn", "what": f"The battery holds {health}% of what it did when new.",
                                   "fix": "It's worn: expect shorter battery life. A new battery brings it back."})
            if read("cycle_count").isdigit():
                report["battery_cycles"] = int(read("cycle_count"))
            break


def _protection(report: dict, issues: list) -> None:
    found = {}
    if MAC:
        ok, out = run(["fdesetup", "status"], timeout=6)
        if ok:
            found["disk encryption (FileVault)"] = "on" if "is On" in out else "off"
        ok, out = run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"], timeout=6)
        if ok:
            found["firewall"] = "on" if ("enabled" in out.lower() and "disabled" not in out.lower()) else "off"
        ok, out = run(["spctl", "--status"], timeout=6)
        if out:
            found["Gatekeeper (app checks)"] = "on" if "enabled" in out else "off"
    elif WIN:
        ok, out = run(["powershell", "-NoProfile", "-Command",
                       "$s = Get-MpComputerStatus; \"$($s.AntivirusEnabled)|$($s.RealTimeProtectionEnabled)\""], timeout=15)
        if ok and "|" in out:
            av, rt = out.strip().split("|")[:2]
            found["Microsoft Defender antivirus"] = "on" if av.strip() == "True" and rt.strip() == "True" else "off"
        ok, out = run(["netsh", "advfirewall", "show", "allprofiles", "state"], timeout=10)
        if ok:
            states = re.findall(r"State\s+(ON|OFF)", out, re.I)
            if states:
                found["firewall"] = "on" if all(s.upper() == "ON" for s in states) else "off"
    if found:
        report["protection"] = found
    for name, state in found.items():
        if state == "off":
            fix = {"disk encryption (FileVault)": "Turn on FileVault (System Preferences > Security & Privacy > FileVault) "
                                                  "so nobody can read your files if the Mac is lost.",
                   "firewall": "Turn the firewall on (security settings).",
                   "Gatekeeper (app checks)": "Turn app checks back on: only open apps you trust.",
                   "Microsoft Defender antivirus": "Turn on real-time protection (Windows Security > Virus & threat protection)."}
            issues.append({"level": "tip", "what": f"{name[0].upper() + name[1:]} is off.", "fix": fix.get(name, "")})


def _updates(report: dict, issues: list) -> None:
    if MAC:
        ok, out = run(["softwareupdate", "-l"], timeout=60)
        names = re.findall(r"^\s*\*\s*(?:Label:\s*)?(.+)$", out, re.M) if out else []
        if names:
            report["updates"] = names[:8]
            issues.append({"level": "tip", "what": f"{len(names)} system update{'s' if len(names) > 1 else ''} waiting.",
                           "fix": "Install them in Software Update (save your work first: the Mac may restart)."})
        elif "No new software available" in out:
            report["updates"] = "none waiting"
    elif WIN:
        report["updates"] = "open Settings > Windows Update to check"


def _phone(report: dict, issues: list) -> None:
    from .. import device_info
    report["device"] = device_info.describe()
    try:
        st = os.statvfs(os.path.expanduser("~"))
        free, total = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
        report["storage"] = f"{_gb(free)} free of {_gb(total)}"
        if total and free / total < 0.1:
            issues.append({"level": "warn", "what": f"Storage is almost full: {_gb(free)} free.",
                           "fix": "Delete apps, videos and downloads you don't need (Settings > Storage)."})
    except Exception:
        pass
    if ANDROID:
        try:
            from java import jclass
            Intent, IntentFilter = jclass("android.content.Intent"), jclass("android.content.IntentFilter")
            ctx = jclass("com.chaquo.python.Python").getPlatform().getApplication()
            st = ctx.registerReceiver(None, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            level, scale = st.getIntExtra("level", -1), st.getIntExtra("scale", 100)
            if level >= 0:
                report["battery"] = f"{round(100 * level / max(scale, 1))}%"
        except Exception:
            pass


# ---- Camera and microphone (0.1.162): "why is my camera not working?" -- is one there at all, does the system say
# it has a problem, is camera access turned off for apps, which open apps usually hold it. Read-only, like the rest.
CALL_APPS = ("zoom", "teams", "facetime", "photo booth", "skype", "webex", "obs", "discord", "slack", "whatsapp",
             "meet", "loom", "snap camera", "camo", "messenger")


def _call_apps_open() -> List[str]:
    """Open apps that usually take the camera and microphone (video calls, recording)."""
    names = set()
    if MAC or sys.platform.startswith("linux"):
        ok, out = run(["ps", "-Ao", "comm"] if MAC else ["ps", "-eo", "comm"], timeout=6)
        procs = [os.path.basename(x.strip()).lower() for x in (out.splitlines()[1:] if ok else [])]
    else:
        ps = _psutil()
        procs = []
        if ps:
            try:
                procs = [(p.info.get("name") or "").lower() for p in ps.process_iter(["name"])]
            except Exception:
                procs = []
    for proc in procs:
        for app in CALL_APPS:
            if app.replace(" ", "") in proc.replace(" ", "").replace(".", "").replace("-", ""):
                names.add(app.title() if app not in ("obs",) else "OBS")
    return sorted(names)


def _mac_av_permission(kind: str) -> str:
    """Gink's own camera / microphone permission on a Mac (the built app only): allowed, denied, not asked yet."""
    try:
        from rubicon.objc import ObjCClass
        from rubicon.objc.runtime import load_library
        load_library("AVFoundation")
        media = "vide" if kind == "camera" else "soun"           # AVMediaTypeVideo / AVMediaTypeAudio
        state = int(ObjCClass("AVCaptureDevice").authorizationStatusForMediaType_(media))
        return {0: "not asked yet", 1: "restricted", 2: "denied", 3: "allowed"}.get(state, "")
    except Exception:
        return ""


def _devices(report: dict, issues: list, focus: str = "all") -> None:
    want_cam, want_mic = focus in ("all", "camera"), focus in ("all", "microphone")
    cams, mics, problem = None, None, []
    if MAC:
        if want_cam:
            ok, out = run(["system_profiler", "SPCameraDataType"], timeout=20)
            cams = [m.strip() for m in re.findall(r"^\s{4}(\S[^:\n]*):\s*$", out, re.M)] if ok else None
        if want_mic:
            ok, out = run(["system_profiler", "SPAudioDataType"], timeout=20)
            found = []
            for block in re.split(r"\n(?=\s{8}\S[^\n]*:\s*\n)", out if ok else ""):
                head = block.strip().splitlines()[0].rstrip(":").strip() if block.strip() else ""
                if head and (re.search(r"microphone|\bmic\b|input", head, re.I) or "Input Channels" in block
                             or "Default Input Device: Yes" in block):
                    found.append(head)
            mics = found or None             # nothing recognisable (older macOS lists them differently): don't guess
    elif WIN:
        script = ("$c = Get-PnpDevice -Class Camera,Image -PresentOnly -ErrorAction SilentlyContinue | "
                  "ForEach-Object { $_.FriendlyName + '|' + $_.Status };"
                  "$m = Get-PnpDevice -Class AudioEndpoint -PresentOnly -ErrorAction SilentlyContinue | "
                  "Where-Object { $_.FriendlyName -match 'Microphone|Mic|Input|Headset' } | ForEach-Object { $_.FriendlyName + '|' + $_.Status };"
                  "'CAM:' + ($c -join ';'); 'MIC:' + ($m -join ';');"
                  "$k = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore';"
                  "'CAMOK:' + (Get-ItemProperty -Path ($k + '\\webcam') -Name Value -ErrorAction SilentlyContinue).Value;"
                  "'MICOK:' + (Get-ItemProperty -Path ($k + '\\microphone') -Name Value -ErrorAction SilentlyContinue).Value")
        ok, out = run(["powershell", "-NoProfile", "-Command", script], timeout=25)
        lines = dict(line.split(":", 1) for line in out.splitlines() if ":" in line and line.split(":", 1)[0] in
                     ("CAM", "MIC", "CAMOK", "MICOK")) if ok else {}

        def parse(text):
            found = [x.split("|") for x in (text or "").split(";") if x.strip()]
            for name, *status in found:
                if status and status[0].strip().upper() not in ("OK", ""):
                    problem.append(f"{name.strip()} ({status[0].strip().lower()})")
            return [f[0].strip() for f in found]
        if want_cam and "CAM" in lines:
            cams = parse(lines["CAM"])
            if lines.get("CAMOK", "").strip().lower() == "deny":
                issues.append({"level": "warn", "what": "Camera access is turned off for apps.",
                               "fix": "Settings > Privacy & security > Camera: turn on Camera access (and for the app)."})
        if want_mic and "MIC" in lines:
            mics = parse(lines["MIC"])
            if lines.get("MICOK", "").strip().lower() == "deny":
                issues.append({"level": "warn", "what": "Microphone access is turned off for apps.",
                               "fix": "Settings > Privacy & security > Microphone: turn on Microphone access."})
    elif sys.platform.startswith("linux"):
        if want_cam:
            try:
                cams = sorted(n for n in os.listdir("/dev") if re.match(r"video\d+$", n))
            except OSError:
                cams = None
            if cams:
                ok, out = run(["fuser"] + [f"/dev/{n}" for n in cams], timeout=6)
                if ok and re.search(r"\d", out.split(":", 1)[-1] if ":" in out else out):
                    report["camera_in_use"] = "yes: another program has it open"
        if want_mic:
            ok, out = run(["arecord", "-l"], timeout=6)
            mics = re.findall(r"^card \d+: [^\[]*\[([^\]]+)\]", out, re.M) if ok else None
    if cams is not None and want_cam:
        report["cameras"] = cams or "none found"
        if not cams:
            issues.append({"level": "warn", "what": "No camera was found.",
                           "fix": "A camera that's plugged in: unplug it and plug it in again (another port). A built-in one: "
                                  "restart the computer; if it's still missing, it may need a repair."})
    if mics is not None and want_mic:
        report["microphones"] = mics or "none found"
        if not mics:
            issues.append({"level": "warn", "what": "No microphone was found.",
                           "fix": "Plug the headset or microphone in again, or choose it in the sound settings (Input)."})
    if problem:
        issues.append({"level": "warn", "what": "The system reports a problem with " + ", ".join(problem) + ".",
                       "fix": "Device Manager: right-click it, then Disable and Enable it again, or Update driver; then restart."})
    if MAC:
        for kind, wanted in (("camera", want_cam), ("microphone", want_mic)):
            state = _mac_av_permission(kind) if wanted else ""
            if state:
                report[f"gink_{kind}_permission"] = state
            if state == "denied":
                pane = "Camera" if kind == "camera" else "Microphone"
                issues.append({"level": "tip", "what": f"Gink isn't allowed to use the {kind}.",
                               "fix": f"System Settings > Privacy & Security > {pane}: turn on Gink."})
    holders = _call_apps_open() if (want_cam or want_mic) else []
    if holders:
        report["call_apps_open"] = holders
        issues.append({"level": "tip", "what": "Open apps that may be using the camera or microphone: " + ", ".join(holders) + ".",
                       "fix": "Quit the ones you aren't using (a camera often works in one app at a time), then try again."})
    if (want_cam or want_mic) and not (ANDROID or IOS):
        where = ("System Settings > Privacy & Security > Camera / Microphone" if MAC else
                 "Settings > Privacy & security > Camera / Microphone" if WIN else "the app's permissions")
        report["if_one_app_fails"] = f"If it works in one app but not another, that app needs permission: {where}."


def check_device(updates: bool = False, focus: str = "all") -> Dict:
    """Read-only health check of this device. -> {"ok", "message", "report", "issues"}
    focus: "all" (everything), or "camera" / "microphone" (the system basics and that device)."""
    report: Dict = {}
    issues: List[dict] = []
    focus = focus if focus in ("all", "camera", "microphone") else "all"
    if ANDROID or IOS:
        _phone(report, issues)
        if focus != "all":
            what = "Camera" if focus == "camera" else "Microphone"
            report["permissions"] = (f"Settings > Apps > the app > Permissions > {what}" if ANDROID else
                                     f"Settings > Privacy & Security > {what}")
            issues.append({"level": "tip", "what": f"Phones only let apps use the {focus} with permission.",
                           "fix": f"Check that the app has {what} permission ({report['permissions']}); close other apps "
                                  "that may be using it, then restart the phone if it's still not working."})
    else:
        steps = (_system, _uptime, _cpu_memory, _storage, _battery, _protection) if focus == "all" else (_system,)
        for step in steps:
            try:
                step(report, issues)
            except Exception:
                continue
        try:
            _devices(report, issues, focus)
        except Exception:
            pass
        if updates:
            try:
                _updates(report, issues)
            except Exception:
                pass
    if not report:
        return {"ok": False, "message": "I couldn't read this device's details."}
    order = {"warn": 0, "tip": 1}
    issues.sort(key=lambda i: order.get(i.get("level"), 2))
    lines = [f"{k.replace('_', ' ')}: {v if not isinstance(v, (list, dict)) else v}" for k, v in report.items()]
    lines.append("issues: " + ("; ".join(f"{i['what']} -> {i['fix']}" for i in issues) if issues else "none found"))
    return {"ok": True, "message": "\n".join(lines), "report": report, "issues": issues,
            "summary": "No problems found." if not issues else f"{len(issues)} thing{'s' if len(issues) > 1 else ''} to look at."}


def format_report(result: Dict) -> str:
    """The check as a short Markdown answer (used when there's no AI to explain it)."""
    if not result.get("ok"):
        return result.get("message") or "I couldn't check this device."
    r, issues = result.get("report", {}), result.get("issues", [])
    names = {"device": "Device", "system": "System", "since_restart": "Since the last restart",
             "processor_load": "Processor", "memory": "Memory", "storage": "Storage", "battery": "Battery",
             "battery_health": "Battery health", "battery_cycles": "Charge cycles", "updates": "Updates",
             "cameras": "Cameras", "camera_in_use": "Camera in use", "microphones": "Microphones",
             "gink_camera_permission": "Gink's camera permission", "gink_microphone_permission": "Gink's microphone permission",
             "call_apps_open": "Call apps open", "if_one_app_fails": "Tip"}
    out = ["**Your device check**", ""]
    for key, label in names.items():
        if key in r:
            v = r[key]
            out.append(f"- **{label}:** {', '.join(v) if isinstance(v, list) else v}")
    if r.get("protection"):
        out.append("- **Protection:** " + ", ".join(f"{k} {v}" for k, v in r["protection"].items()))
    if r.get("busiest_apps"):
        out.append("- **Busiest apps:** " + ", ".join(r["busiest_apps"][:3]))
    out.append("")
    if issues:
        out.append("**What to do**")
        out += [f"{n}. {i['what']} {i['fix']}" for n, i in enumerate(issues, 1)]
    else:
        out.append("Everything looks healthy.")
    return "\n".join(out)


def quick_summary() -> Optional[str]:
    try:
        return format_report(check_device())
    except Exception:
        return None
