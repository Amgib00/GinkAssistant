"""Hey Gink: the microphone permission is declared everywhere; Android keeps listening through hiccups."""
import asyncio, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from ginkassistant.services import android_voice as av


def test_microphone_permission_is_declared_on_every_platform():
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    assert not re.search(r"^\[tool\.briefcase\.app\.[a-z]+\.[A-Za-z]+\.permissions\]", text, re.M), \
        "Briefcase ignores 'permissions' (plural): the Mac app had no microphone, so Hey Gink heard nothing"
    try:
        import tomllib                     # Python 3.11+
    except ImportError:                    # Python 3.10 (the Catalina Mac): the same parser, as a package
        import tomli as tomllib
    app = tomllib.loads(text)["tool"]["briefcase"]["app"]["ginkassistant"]
    assert app["macOS"]["permission"]["microphone"] and app["iOS"]["permission"]["microphone"]
    assert "android.permission.RECORD_AUDIO" in app["android"]["permission"]


def _run_listener(monkeypatch, script):
    """Run AndroidWakeListener against a fake recognizer that follows `script` (text or error codes)."""
    calls, woke = [], []
    class FakeSession:
        def __init__(self, language, prefer_offline=True):
            calls.append(prefer_offline)
        async def run(self, timeout=12):
            step = script.pop(0) if script else None
            if step is None:
                listener.running = False; return ""
            if isinstance(step, int):
                raise av.VoiceProblem(av.ERRORS.get(step, "x"), code=step)
            return step
        def close(self): pass
    async def allowed(): return True
    real_sleep = asyncio.sleep
    monkeypatch.setattr(av, "_Session", FakeSession)
    monkeypatch.setattr(av, "ensure_mic_permission", allowed)
    monkeypatch.setattr(av.asyncio, "sleep", lambda s: real_sleep(0))
    listener = av.AndroidWakeListener(lambda: woke.append(listener.heard_after_wake), language="en-US")
    async def go():
        listener.start(); await listener._task
    asyncio.run(go())
    return listener, calls, woke


def test_android_keeps_listening_when_the_recognizer_is_busy(monkeypatch):
    listener, calls, woke = _run_listener(monkeypatch, [8] * 7 + ["hey gink what's the weather"])
    assert woke == ["what's the weather"] and listener.error == ""          # it kept going, and it woke up


def test_android_goes_online_when_offline_language_is_missing(monkeypatch):
    listener, calls, woke = _run_listener(monkeypatch, [13, "hey gink"])
    assert calls[:2] == [True, False] and len(woke) == 1 and listener.prefer_offline is False


def test_android_stops_and_says_why_without_permission(monkeypatch):
    listener, calls, woke = _run_listener(monkeypatch, [9, "hey gink"])
    assert not listener.running and "permission" in listener.error and woke == []
