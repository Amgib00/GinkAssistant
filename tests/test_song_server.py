"""Song recognition for phones: the app records ~8 s, the server asks Shazam (POST /media/song)."""
import asyncio, io, os, struct, sys, types, wave
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import pytest

pytest.importorskip("fastapi")


def wav_bytes(seconds=0.5, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(struct.pack("<h", 1000) * int(seconds * rate))
    return buf.getvalue()


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("GINK_SONG_DAILY", "2")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    mode = {"v": "match", "seen": []}

    class Shazam:
        async def recognize(self, path):
            mode["seen"].append(open(path, "rb").read()[:4]); mode.setdefault("paths", []).append(path)
            if mode["v"] == "down":
                raise RuntimeError("shazam unreachable")
            if mode["v"] == "none":
                return {"matches": []}
            return {"track": {"title": "Pon de Replay", "subtitle": "Rihanna", "url": "https://shazam.example/t/1"}}
    monkeypatch.setitem(sys.modules, "shazamio", types.SimpleNamespace(Shazam=Shazam))
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@x.co", "I")["token"]}
    return b, c, h, mode


def post(c, h, audio):
    import base64
    return c.post("/media/song", headers=h, json={"audio_b64": base64.b64encode(audio).decode(), "format": "wav"})


def test_needs_sign_in(server):
    _, c, _, _ = server
    assert post(c, {}, wav_bytes()).status_code == 401


def test_recognises_and_forgets_the_recording(server, tmp_path):
    _, c, h, mode = server
    r = post(c, h, wav_bytes())
    assert r.status_code == 200 and r.json() == {"match": True, "title": "Pon de Replay", "artist": "Rihanna",
                                                  "url": "https://shazam.example/t/1"}
    assert mode["seen"] == [b"RIFF"] and not os.path.exists(mode["paths"][0])     # the recording is forgotten


def test_no_match(server):
    _, c, h, mode = server
    mode["v"] = "none"
    assert post(c, h, wav_bytes()).json() == {"match": False}


def test_only_short_wav_recordings(server):
    _, c, h, _ = server
    assert post(c, h, b"ID3" + b"\0" * 5000).status_code == 422                 # an mp3
    assert post(c, h, wav_bytes(seconds=0.001)).status_code == 422             # nearly empty
    assert c.post("/media/song", headers=h, json={"audio_b64": "not base64!!"}).status_code == 400


def test_daily_limit_and_refund_when_shazam_fails(server):
    _, c, h, mode = server
    mode["v"] = "down"
    r = post(c, h, wav_bytes())
    assert r.status_code == 502 and "didn\u2019t answer" in r.json()["detail"]       # refunded
    mode["v"] = "match"
    assert post(c, h, wav_bytes()).status_code == 200
    assert post(c, h, wav_bytes()).status_code == 200
    r = post(c, h, wav_bytes())
    assert r.status_code == 429 and "2 songs" in r.json()["detail"]


def test_server_without_shazamio(server, monkeypatch):
    _, c, h, _ = server
    monkeypatch.setitem(sys.modules, "shazamio", None)                           # import fails
    r = post(c, h, wav_bytes())
    assert r.status_code == 503 and "isn\u2019t set up" in r.json()["detail"]


# ---------------------------------------------------------------- the app side
def test_phone_records_and_asks_the_server(monkeypatch):
    from ginkassistant.services import song_recognition as sr, platform_utils
    import ginkassistant.services.android_voice as av
    monkeypatch.setattr(platform_utils, "is_android", lambda: True)
    monkeypatch.setattr(sr, "HAS_SHAZAMIO", False)
    made = {}

    async def fake_record(seconds, rate):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
        open(path, "wb").write(wav_bytes()); made["path"] = path
        assert (seconds, rate) == (sr.SAMPLE_SECONDS, 16000)
        return path
    monkeypatch.setattr(av, "record_wav", fake_record)
    sent = {}

    class Api:
        def __init__(self, base): sent["base"] = base
        async def identify_song(self, token, audio):
            sent.update(token=token, audio=audio[:4]); return {"match": True, "title": "Dibi Dibi Rek", "artist": "Ismaël Lô"}
    import ginkassistant.services.api_client as api
    monkeypatch.setattr(api, "ApiClient", Api)
    monkeypatch.setitem(sr.server, "fn", lambda: ("https://gink-server.onrender.com", "tok"))
    song = asyncio.run(sr.identify_ambient_song())
    assert song == {"title": "Dibi Dibi Rek", "artist": "Ismaël Lô", "url": None}
    assert sent == {"base": "https://gink-server.onrender.com", "token": "tok", "audio": b"RIFF"}
    assert not os.path.exists(made["path"])                                      # the recording is deleted


def test_phone_says_why_it_cant(monkeypatch):
    from ginkassistant.services import song_recognition as sr, platform_utils
    import ginkassistant.services.android_voice as av
    monkeypatch.setattr(platform_utils, "is_android", lambda: True)
    monkeypatch.setattr(sr, "HAS_SHAZAMIO", False)

    async def no_mic(seconds, rate):
        raise av.VoiceProblem("Gink needs the microphone", code=9)
    monkeypatch.setattr(av, "record_wav", no_mic)
    with pytest.raises(sr.SongProblem, match="needs the microphone"):
        asyncio.run(sr.identify_ambient_song())

    async def ok(seconds, rate):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".wav"); os.close(fd); open(path, "wb").write(wav_bytes()); return path
    monkeypatch.setattr(av, "record_wav", ok)
    monkeypatch.setitem(sr.server, "fn", lambda: ("https://x", None))
    with pytest.raises(sr.SongProblem, match="Sign in"):
        asyncio.run(sr.identify_ambient_song())


def test_android_recording_makes_a_wav(monkeypatch, tmp_path):
    """AudioRecord on a simulated phone -> 16 kHz mono .wav with the recorded samples."""
    import fake_android
    from ginkassistant.services import android_voice as av
    monkeypatch.setitem(sys.modules, "java", fake_android.java)
    reads = []

    class AudioRecord:
        STATE_INITIALIZED = 1
        @staticmethod
        def getMinBufferSize(rate, ch, enc): return 1280
        def __init__(self, *a): self.args = a
        def getState(self): return 1
        def startRecording(self): pass
        def read(self, buf, off, n):
            for i in range(n):
                buf[off + i] = 7
            reads.append(n); return n
        def stop(self): pass
        def release(self): reads.append("released")

    classes = dict(fake_android.CLASSES)
    classes.update({"android.media.AudioRecord": AudioRecord,
                    "android.media.AudioFormat": types.SimpleNamespace(CHANNEL_IN_MONO=16, ENCODING_PCM_16BIT=2),
                    "android.media.MediaRecorder$AudioSource": types.SimpleNamespace(MIC=1)})
    java = types.ModuleType("java")
    java.jclass = lambda name: classes[name]
    java.dynamic_proxy, java.jbyte = (lambda i: object), "byte"
    java.jarray = lambda t: (lambda n: bytearray(n))
    monkeypatch.setitem(sys.modules, "java", java)
    fake_android.reset()
    path = asyncio.run(av.record_wav(0.5, 16000))
    with wave.open(path) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 8000)
        assert w.readframes(2) == b"\x07\x07\x07\x07"
    os.remove(path)
    assert reads[-1] == "released" and max(r for r in reads if r != "released") <= 8192
