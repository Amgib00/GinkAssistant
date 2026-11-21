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


def check_device(updates: bool = False) -> Dict:
    """Read-only health check of this device. -> {"ok", "message", "report", "issues"}"""
    report: Dict = {}
    issues: List[dict] = []
    if ANDROID or IOS:
        _phone(report, issues)
    else:
        for step in (_system, _uptime, _cpu_memory, _storage, _battery, _protection):
            try:
                step(report, issues)
            except Exception:
                continue
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
             "battery_health": "Battery health", "battery_cycles": "Charge cycles", "updates": "Updates"}
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
