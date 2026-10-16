"""iOS: every Gink module must import with ONLY the iOS requirements installed.

Python on iOS reports sys.platform == "ios". Packages with compiled code that have
no iOS build (numpy, psutil, pydantic-core, shazamio, PyAudio, primp/duckduckgo-search,
vosk...) and the desktop voice tools aren't in the iOS requirements, so importing them
must never be needed to start the app.
"""
import os, subprocess, sys, textwrap

NOT_ON_IOS = ["pygame", "edge_tts", "speech_recognition", "pyaudio", "sounddevice", "llama_cpp", "librosa", "scipy",
              "numba", "pyttsx3", "fastapi", "uvicorn", "google.genai", "pydantic_core", "numpy", "psutil", "shazamio",
              "duckduckgo_search", "primp", "nltk", "vosk", "pvporcupine", "lxml", "jiter", "regex"]

SCRIPT = textwrap.dedent(f"""
    import sys, os, importlib, pkgutil
    os.environ["TOGA_BACKEND"] = "toga_dummy"
    BLOCK = {NOT_ON_IOS!r}
    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if any(name == b or name.startswith(b + ".") for b in BLOCK):
                raise ModuleNotFoundError(f"No module named '{{name}}' (not installed on iOS)")
            return None
    sys.meta_path.insert(0, Blocker())
    for b in BLOCK:
        sys.modules.pop(b, None)
    import toga                                        # imported before the switch (it's the toga-iOS backend on a phone)
    # Python 3.13's webbrowser has an iPhone branch that loads Apple's ObjC runtime -- present on a
    # real iPhone, absent on this Linux test machine -- so load it (and toga.app, which uses it) first.
    import webbrowser, toga.app                        # noqa: E401
    import platform; platform.uname()                  # 3.13: platform.system() asks iOS for its version -- cache it first
    sys.platform = "ios"                               # what Python reports on iPhone / iPad
    sys.path.insert(0, {os.path.join(os.path.dirname(__file__), "..", "src")!r})
    import ginkassistant
    from ginkassistant.services import platform_utils
    assert platform_utils.is_ios() and platform_utils.is_mobile()
    failed = []
    for mod in pkgutil.walk_packages(ginkassistant.__path__, "ginkassistant."):
        if mod.name.endswith("backend_server"):
            continue
        try:
            importlib.import_module(mod.name)
        except Exception as e:
            failed.append(f"{{mod.name}}: {{type(e).__name__}}: {{e}}")
    print("FAILED:" + "|".join(failed) if failed else "ALL_OK")
""")


def test_every_module_imports_on_ios():
    out = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=120)
    assert "ALL_OK" in out.stdout, out.stdout[-3000:] + out.stderr[-3000:]
