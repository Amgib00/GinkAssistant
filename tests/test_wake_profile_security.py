"""Hey Gink everywhere, the profile synced to the web, Python 3.11+, and the security fixes."""
import io, os, pickle, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))


def test_hey_gink_falls_back_to_sounddevice_when_pyaudio_cannot():
    from ginkassistant.services import wake_word as w
    class Broken:
        def __call__(self, frame): raise ImportError("No module named 'pyaudio'")
        def terminate(self): pass
    class Works:
        def __call__(self, frame):
            class S:
                def read(self): return b"\0" * frame * 2
                def close(self): pass
            return S()
        def terminate(self): pass
    mic = w._AnyMic(Broken(), Works())
    assert len(mic(4000).read()) == 8000 and mic.using == "Works"
    try:
        w._AnyMic(Broken(), Broken())(4000)
        assert False
    except RuntimeError as e:
        assert "no microphone could be opened" in str(e) and "pyaudio" in str(e)      # the status line says why
    assert isinstance(w.WakeWordListener(engine=None, on_wake=lambda: None).open_stream, w._AnyMic)


def test_hey_gink_on_the_web_and_honest_about_it():
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    for part in ("function wakeStart()", "r.continuous = true", "startVoice();", "voice_start: function (v) {\n      wakeStop();",
                 "setTimeout(wakeStart, 800)", "Microphone blocked", 'document.visibilityState === "visible"'):
        assert part in bridge, part
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    assert "Chrome sends what it hears to Google, Safari to Apple" in page          # the web listens through the browser's service


def test_the_web_app_shares_the_profile_with_the_apps():
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    for part in ("function takeProfile(docs)", "push: { chats: push, profile: pushProfile }", "profileEdit(v.key, v.value)",
                 "profileNote() + memoryNote()", 'if (typeof sync === "function") sync();'):
        assert part in bridge, part


def test_python_311_or_newer():
    assert 'requires-python = ">=3.11"' in open(os.path.join(ROOT, "pyproject.toml")).read()
    assert '"3.11", "3.13"' in open(os.path.join(ROOT, ".github", "workflows", "tests.yml")).read()
    assert "FROM python:3.12-slim" in open(os.path.join(ROOT, "deploy", "Dockerfile")).read()


def test_a_tampered_song_database_cannot_run_code():
    from collections import defaultdict
    from ginkassistant.services import shazam_engine as se
    good = io.BytesIO(); pickle.dump({"db": defaultdict(list, {1: [("t", 2)]}), "song_info": {"t": {"title": "S"}}}, good)
    assert se._PlainDataUnpickler(io.BytesIO(good.getvalue())).load()["song_info"]["t"]["title"] == "S"
    class Evil:
        def __reduce__(self): return (os.system, ("echo hacked",))
    try:
        se._PlainDataUnpickler(io.BytesIO(pickle.dumps({"db": Evil()}))).load()
        assert False
    except pickle.UnpicklingError:
        pass


def test_news_feeds_cannot_attack_the_xml_reader():
    from ginkassistant.services.news import _parse_xml
    assert _parse_xml(b"<rss><item><title>Hi</title></item></rss>").find(".//title").text == "Hi"
    bomb = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss>&b;</rss>'
    try:
        import defusedxml  # noqa: F401
    except ImportError:
        return
    try:
        _parse_xml(bomb)
        assert False
    except Exception as e:
        assert type(e).__name__ == "EntitiesForbidden"
