"""Android voice (services/android_voice.py) on a simulated Android: listening, permission, speaking, "Hey Gink"."""
import asyncio, base64, os, subprocess, sys, textwrap
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest
import fake_android
sys.modules["java"] = fake_android.java
from ginkassistant.services import android_voice as av
S = fake_android.STATE


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_listening_text_partials_levels_and_language():
    fake_android.reset(script=[("text", "Bonjour Gink, quel temps fait-il")])
    partials, levels = [], []
    text = run(av.listen("fr-SN", on_amplitude=levels.append, on_partial=partials.append))
    assert text == "Bonjour Gink, quel temps fait-il" and partials and levels and 0 < levels[0] <= 1
    assert S["recognizers"][0].intent.extras["lang"] == "fr-SN"
    fake_android.reset(script=[("text", "hi")])
    run(av.listen("auto"))
    assert "lang" not in S["recognizers"][0].intent.extras                      # automatic: the phone decides


def test_microphone_permission_asked_and_refused(monkeypatch):
    fake_android.reset(granted=False, grant_on_request=True, script=[("text", "hello")])
    assert run(av.listen("")) == "hello" and S["requested"] == 1                # asked once, then allowed
    fake_android.reset(granted=False)
    orig = av.ensure_mic_permission
    monkeypatch.setattr(av, "ensure_mic_permission", lambda timeout=45.0: orig(timeout=0.3))
    with pytest.raises(av.VoiceProblem, match="needs the microphone"):
        run(av.listen(""))


def test_silence_and_errors():
    fake_android.reset(script=[("error", 7)])
    assert run(av.listen("")) == ""                                              # nothing understood
    fake_android.reset(script=[("error", 2)])
    with pytest.raises(av.VoiceProblem, match="no network"):
        run(av.listen(""))
    fake_android.reset(available=False)
    with pytest.raises(av.VoiceProblem, match="no speech recognition service"):
        run(av.listen(""))


def test_speaking_natural_voice_then_phone_voice(monkeypatch):
    fake_android.reset()
    wav = b"RIFF-natural-voice"
    real = httpx.AsyncClient
    class Natural(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(lambda r: httpx.Response(200, json={"audio_b64": base64.b64encode(wav).decode()}))
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Natural)
    assert run(av.speak("Hello Ibrahim", "ezinne", "https://srv", "tok")) == "natural" and S["played"] == [wav]
    class Down(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(lambda r: httpx.Response(503, json={}))
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Down)
    assert run(av.speak("Hello again", "ezinne", "https://srv", "tok")) == "phone" and S["tts_spoken"] == ["Hello again"]


def test_wake_phrase_as_phones_write_it():
    for said in ("hey gink", "Hey, Ginc what's up", "okay gink", "hi gink", "a gink set an alarm"):
        assert av.WAKE_RE.search(said), said
    for said in ("ginger tea", "hey king", "making it"):
        assert not av.WAKE_RE.search(said), said


def test_hey_gink_listener():
    fake_android.reset(script=[("text", "good morning everyone"), ("error", 7), ("text", "Hey Gink what's the weather in Dakar"),
                               ("hang", None)])
    woke = []
    async def scenario():
        lst = av.AndroidWakeListener(lambda: woke.append(True), pause_between=0.01)
        lst.start()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if woke:
                break
        lst.pause()                                   # Gink takes the microphone
        await asyncio.sleep(0.05)
        assert lst._session is None and lst._released.is_set()
        lst.stop()
        return lst
    lst = run(scenario())
    assert woke == [True] and lst.detections == 1
    assert lst.heard_after_wake == "what's the weather in Dakar"                 # the question said with it
    assert lst.engine.last_heard == "Hey Gink what's the weather in Dakar"


def test_voice_bridge_uses_android_voice_on_a_phone():
    """The real voice layer, imported as on Android (Chaquopy present), sends listening to android_voice."""
    here = os.path.dirname(os.path.abspath(__file__))
    script = textwrap.dedent(f"""
        import asyncio, os, sys
        sys.path[:0] = [{here!r}, {os.path.join(here, '..', 'src')!r}]
        import fake_android; sys.modules["java"] = fake_android.java
        sys.getandroidapilevel = lambda: 31                       # what Chaquopy's Python has
        fake_android.reset(script=[("text", "Na gode Gink")])
        from ginkassistant.services import voice_bridge as vb
        print("TEXT=" + asyncio.new_event_loop().run_until_complete(vb.listen()))
    """)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert "TEXT=Na gode Gink" in out.stdout, out.stdout[-1500:] + out.stderr[-1500:]
