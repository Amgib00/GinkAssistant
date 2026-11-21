"""requirements.txt (running Gink with `python -m ginkassistant`) must install exactly what
pyproject.toml gives the built desktop apps, on every desktop platform. It had drifted: Apple Silicon
Macs got a different numba/llvmlite and cryptography, and three minimum versions disagreed.

One difference is fine (0.1.162): a minimum (>=) that's NEWER in requirements.txt. Dependabot raises
requirements.txt's minimums by itself but can't reach pyproject.toml's Briefcase lists, so its pull requests
always failed here; the newest version is installed either way. Pins (==), caps (<) and older minimums still fail."""
import os
import tomllib
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEV_ONLY = {"briefcase", "pytest", "toga-dummy"}            # tools for building / testing, not the app


def _env(sp, machine, py):
    system = {"darwin": "Darwin", "win32": "Windows", "linux": "Linux"}[sp]
    return {"sys_platform": sp, "platform_system": system, "platform_machine": machine, "python_version": py,
            "python_full_version": py + ".0", "os_name": "nt" if sp == "win32" else "posix",
            "implementation_name": "cpython", "platform_python_implementation": "CPython",
            "platform_release": "19.6.0" if sp == "darwin" else ""}


def _resolve(reqs, env):
    out = {}
    for r in reqs:
        if r.marker and not r.marker.evaluate(env):
            continue
        out[canonicalize_name(r.name)] = str(r.specifier)
    return out


def _agree(want: str, have: str) -> bool:
    """The same versions -- or both only a minimum, requirements.txt's the same or newer (Dependabot's raise)."""
    if want == have:
        return True
    w, h = list(SpecifierSet(want)), list(SpecifierSet(have))
    return (len(w) == len(h) == 1 and w[0].operator == h[0].operator == ">="
            and Version(h[0].version) >= Version(w[0].version))


def test_a_newer_minimum_is_fine_but_nothing_else():
    assert _agree(">=0.162.0", ">=0.163.2") and _agree("==2.13.4", "==2.13.4")
    assert not _agree(">=0.163.2", ">=0.162.0")                       # older than the apps': no
    assert not _agree("==2.13.4", "==2.13.5") and not _agree("<49,>=46", ">=46") and not _agree(">=1", ">=2,<3")


def test_requirements_txt_matches_pyproject():
    app = tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))["tool"]["briefcase"]["app"]["ginkassistant"]
    lines = [l.split("#")[0].strip() for l in open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8")]
    txt = [Requirement(l) for l in lines if l]
    cases = [("darwin", m, py) for m in ("x86_64", "arm64") for py in ("3.11", "3.12", "3.13")] + \
            [("win32", "AMD64", py) for py in ("3.11", "3.13")] + [("linux", "x86_64", py) for py in ("3.11", "3.13")]
    section = {"darwin": "macOS", "win32": "windows", "linux": "linux"}
    problems = []
    for sp, machine, py in cases:
        env = _env(sp, machine, py)
        want = _resolve([Requirement(r) for r in app.get("requires", []) + app[section[sp]].get("requires", [])], env)
        have = {k: v for k, v in _resolve(txt, env).items() if k not in DEV_ONLY}
        where = f"{sp} {machine} Python {py}"
        for name in sorted(set(want) - set(have)):
            problems.append(f"{where}: requirements.txt lacks {name}")
        for name in sorted(set(have) - set(want)):
            problems.append(f"{where}: requirements.txt has {name}, pyproject doesn't")
        for name in sorted(set(want) & set(have)):
            if not _agree(want[name], have[name]):
                problems.append(f"{where}: {name} is '{want[name]}' in pyproject, '{have[name]}' in requirements.txt")
    assert problems == [], "\n".join(problems)
