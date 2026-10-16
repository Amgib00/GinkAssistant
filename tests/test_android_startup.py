"""Regression test for "installs but won't open" on Android.

Simulates Chaquopy: sys.getandroidapilevel exists and the desktop-only
libraries (not in the Android requirements) can't be imported. Then every
Gink module is imported in a fresh interpreter. Before the fix this failed
with: ModuleNotFoundError: No module named 'pygame' (voice_bridge.py).
"""
import os, subprocess, sys, textwrap

# Everything NOT in pyproject's Android requirements (universal + android sections)
DESKTOP_ONLY = ["pygame", "edge_tts", "speech_recognition", "pyaudio", "sounddevice", "llama_cpp",
                "librosa", "scipy", "numba", "pyttsx3", "fastapi", "uvicorn", "google.genai", "pydantic_core",
                "numpy", "shazamio", "duckduckgo_search", "ddgs", "primp", "nltk", "vosk", "pvporcupine",
                "pillow_heif", "jwt", "tzlocal"]

SCRIPT = textwrap.dedent(f"""
    import sys, os, importlib, pkgutil
    os.environ["TOGA_BACKEND"] = "toga_dummy"
    sys.getandroidapilevel = lambda: 34            # what Chaquopy provides
    BLOCK = {DESKTOP_ONLY!r}
    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if any(name == b or name.startswith(b + ".") for b in BLOCK):
                raise ModuleNotFoundError(f"No module named '{{name}}' (not installed on Android)")
            return None
    sys.meta_path.insert(0, Blocker())
    for b in BLOCK:
        sys.modules.pop(b, None)
    sys.path.insert(0, {os.path.join(os.path.dirname(__file__), "..", "src")!r})
    import ginkassistant
    from ginkassistant.services import platform_utils
    assert platform_utils.is_android() and platform_utils.is_mobile()
    failed = []
    for mod in pkgutil.walk_packages(ginkassistant.__path__, "ginkassistant."):
        if mod.name.endswith("backend_server"):      # server-only, never imported on phones (lazy in app.py)
            continue
        try:
            importlib.import_module(mod.name)
        except Exception as e:
            failed.append(f"{{mod.name}}: {{type(e).__name__}}: {{e}}")
    from ginkassistant.services import voice_bridge
    assert voice_bridge._is_android()
    print("FAILED:" + "|".join(failed) if failed else "ALL_OK")
""")


def test_every_module_imports_on_android():
    out = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=120)
    assert "ALL_OK" in out.stdout, out.stdout[-3000:] + out.stderr[-3000:]
