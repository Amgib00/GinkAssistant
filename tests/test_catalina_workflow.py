"""The Catalina Mac build (.github/workflows/macos-catalina.yml): the recipe that makes an app for
macOS 10.15 on GitHub's Mac. Its inline scripts are run here on a copy of the project."""
import os
import re
import shutil
import subprocess
import sys
import tomllib
import yaml

def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


ROOT = os.path.join(os.path.dirname(__file__), "..")
WF = yaml.safe_load(_read_text(os.path.join(ROOT, ".github", "workflows", "macos-catalina.yml")))
JOB = WF["jobs"]["catalina"]
STEPS = {s.get("name", s.get("uses")): s for s in JOB["steps"]}


def step(prefix):
    return next(s for n, s in STEPS.items() if n and n.startswith(prefix))


def inline_python(run: str) -> str:
    m = re.search(r"python - <<'PY'[^\n]*\n(.*?)\n\s*PY\n", run, re.S)
    lines = m.group(1).splitlines()
    pad = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    return "\n".join(l[pad:] for l in lines)


def test_recipe():
    assert JOB["runs-on"] == "macos-15-intel" and JOB["env"]["MACOSX_DEPLOYMENT_TARGET"] == "10.15"
    assert STEPS["actions/setup-python@v7"]["with"]["python-version"] == "3.11"
    assert '"briefcase==0.3.15"' in step("Tools")["run"]
    build = step("Build the app")
    assert build["env"]["PIP_NO_INDEX"] == "1" and build["env"]["PIP_ONLY_BINARY"] == ":all:"
    names = [s.get("name", "") for s in JOB["steps"]]
    assert names.index(next(n for n in names if n.startswith("Check every program"))) < \
        names.index(next(n for n in names if n.startswith("Package")))      # nothing ships unchecked
    assert "tools/check_mac_min_os.py \"$APP\" --max 10.15 --arch x86_64" in step("Check every program")["run"]
    fetch = step("Fetch every other package")["run"]
    for v in ("10_9", "10_15"):
        assert v in fetch
    assert "--only-binary=:all:" in fetch and "--find-links \"$WHEELS\"" in fetch


def test_requirements_script(tmp_path):
    shutil.copy(os.path.join(ROOT, "pyproject.toml"), tmp_path / "pyproject.toml")
    out = subprocess.run([sys.executable, "-c", inline_python(step("Fetch every other package")["run"])],
                         cwd=tmp_path, capture_output=True, text=True, check=True).stdout.split()
    assert "cryptography<49" in out and not any(r.startswith("cryptography>=49") for r in out)   # Intel Macs
    assert "toga-cocoa" in out and "certifi" in out
    assert not any(r.lower().startswith(("pyaudio", "llama-cpp-python")) for r in out)            # built from source


def test_only_gink_is_built(tmp_path):
    shutil.copy(os.path.join(ROOT, "pyproject.toml"), tmp_path / "pyproject.toml")
    subprocess.run([sys.executable, "-c", inline_python(step("Only the Gink app")["run"])], cwd=tmp_path, check=True)
    after = tomllib.loads(_read_text(tmp_path / "pyproject.toml"))
    before = tomllib.loads(_read_text(os.path.join(ROOT, "pyproject.toml")))
    assert list(after["tool"]["briefcase"]["app"]) == ["ginkassistant"]
    assert after["tool"]["briefcase"]["app"]["ginkassistant"] == before["tool"]["briefcase"]["app"]["ginkassistant"]
    assert after["project"] == before["project"]
