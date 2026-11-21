"""
What device Gink is running on, in a few words for the AI: "a MacBook Pro (a laptop) with macOS 12.7, Intel Core i5,
8 GB of memory". The apps tell the AI (groq_worker adds prompt_note() to the system prompt), so "which device am I
using?" gets a real answer and advice fits the machine -- before 0.1.160 Gink said it couldn't know, and asked
which operating system the person's laptop runs while running on it.

Worked out once, in the background (system_profiler takes a second or two on a Mac); until then the quick facts
(operating system and version) are used. Nothing here leaves the device except inside the conversation with the AI.
"""
import os
import platform
import subprocess
import sys
import threading

_cache: dict = {}
_lock = threading.Lock()


def _run(cmd, timeout=6) -> str:
    try:
        kwargs = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kwargs).stdout.strip()
    except Exception:
        return ""


def _gb(n) -> str:
    try:
        return f"{round(int(n) / 1024 ** 3)} GB"
    except Exception:
        return ""


def _has_battery() -> bool:
    try:
        import psutil
        return psutil.sensors_battery() is not None
    except Exception:
        return False


def _mac() -> dict:
    info = {"os": "macOS " + (platform.mac_ver()[0] or _run(["sw_vers", "-productVersion"]))}
    for line in _run(["system_profiler", "SPHardwareDataType"], timeout=12).splitlines():
        key, _, value = line.strip().partition(":")
        value = value.strip()
        if key == "Model Name":
            info["model"] = value
        elif key in ("Chip", "Processor Name") and value:
            info["chip"] = value
        elif key == "Memory":
            info["memory"] = value
        elif key == "Model Identifier":
            info["identifier"] = value
    if "model" not in info:
        info["model"] = _run(["sysctl", "-n", "hw.model"]) or "Mac"
    if "memory" not in info:
        info["memory"] = _gb(_run(["sysctl", "-n", "hw.memsize"]))
    if "chip" not in info:
        info["chip"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    info["laptop"] = "book" in info.get("model", "").lower() or _has_battery()
    return info


def _windows() -> dict:
    ver = sys.getwindowsversion()
    name = "Windows 11" if ver.major == 10 and ver.build >= 22000 else f"Windows {platform.release()}"
    info = {"os": f"{name} (build {ver.build})"}
    out = _run(["powershell", "-NoProfile", "-Command",
                "$c = Get-CimInstance Win32_ComputerSystem; \"$($c.Manufacturer)|$($c.Model)|$($c.TotalPhysicalMemory)\""])
    if out.count("|") == 2:
        maker, model, mem = out.split("|")
        info["model"] = f"{maker.strip()} {model.strip()}".strip()
        info["memory"] = _gb(mem)
    info["chip"] = platform.processor()
    info["laptop"] = _has_battery()
    return info


def _linux() -> dict:
    info = {"os": "Linux"}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    info["os"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    try:
        vendor = open("/sys/class/dmi/id/sys_vendor", encoding="utf-8").read().strip()
        product = open("/sys/class/dmi/id/product_name", encoding="utf-8").read().strip()
        info["model"] = f"{vendor} {product}".strip()
    except OSError:
        pass
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemTotal:"):
                info["memory"] = f"{round(int(line.split()[1]) / 1024 ** 2)} GB"
    except OSError:
        pass
    info["laptop"] = any(n.startswith("BAT") for n in os.listdir("/sys/class/power_supply")) \
        if os.path.isdir("/sys/class/power_supply") else False
    return info


def _android() -> dict:
    try:
        from java import jclass                       # Chaquopy
        build, version = jclass("android.os.Build"), jclass("android.os.Build$VERSION")
        maker = str(build.MANUFACTURER or "").strip()
        model = str(build.MODEL or "").strip()
        if maker and not model.lower().startswith(maker.lower()):
            model = f"{maker.title()} {model}"
        return {"os": f"Android {version.RELEASE}", "model": model, "phone": True}
    except Exception:
        return {"os": "Android", "phone": True}


def _ios() -> dict:
    try:
        from rubicon.objc import ObjCClass
        dev = ObjCClass("UIDevice").currentDevice
        return {"os": f"{dev.systemName} {dev.systemVersion}", "model": str(dev.model), "phone": True}
    except Exception:
        return {"os": "iOS", "phone": True}


def details() -> dict:
    """{"os", "model", "chip", "memory", "laptop" | "phone"} for this device (cached after the first time)."""
    with _lock:
        if _cache:
            return dict(_cache)
    try:
        if hasattr(sys, "getandroidapilevel"):
            info = _android()
        elif sys.platform == "ios":
            info = _ios()
        elif sys.platform == "darwin":
            info = _mac()
        elif sys.platform.startswith("win"):
            info = _windows()
        else:
            info = _linux()
    except Exception:
        info = {"os": platform.system() or "this device"}
    info = {k: v for k, v in info.items() if v not in ("", None)}
    with _lock:
        _cache.clear()
        _cache.update(info)
    return dict(info)


def warm_up() -> None:
    """Work it out in the background at startup, so the first answer doesn't wait for it."""
    threading.Thread(target=details, daemon=True).start()


def describe(info: dict = None) -> str:
    """'a MacBook Pro (a laptop) with macOS 12.7.6, Intel Core i5, 8 GB of memory'"""
    info = info if info is not None else (dict(_cache) if _cache else {"os": _quick_os()})
    kind = " (a phone or tablet)" if info.get("phone") else " (a laptop)" if info.get("laptop") else ""
    model = info.get("model") or ("phone" if info.get("phone") else "computer")
    extras = ", ".join(x for x in (info.get("chip", ""), f"{info['memory']} of memory" if info.get("memory") else "") if x)
    article = "an" if model[:1].lower() in "aeiou" else "a"
    return f"{article} {model}{kind} with {info.get('os', 'an unknown system')}" + (f", {extras}" if extras else "")


def _quick_os() -> str:
    if hasattr(sys, "getandroidapilevel"):
        return "Android"
    if sys.platform == "darwin":
        return "macOS " + (platform.mac_ver()[0] or "")
    if sys.platform.startswith("win"):
        return "Windows " + platform.release()
    return platform.system() or "an unknown system"


def prompt_note() -> str:
    """The sentence for the AI's instructions (apps only: the web app describes the browser instead)."""
    try:
        here = describe()
    except Exception:
        return ""
    computer = not (_cache.get("phone") or hasattr(sys, "getandroidapilevel") or sys.platform == "ios")
    note = (f" You're running in the Gink app on the person's own device: {here}. If they ask which device, computer "
            "or system they're using, tell them -- never say you can't know, and never ask which operating system they use.")
    if computer:
        note += (" When they ask you to check their computer (a health check, why it's slow, storage, battery, security), "
                 "run the device_check tool and explain what it found -- don't hand them steps to do it themselves.")
    return note
