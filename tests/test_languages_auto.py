"""Automatic language: replies in the user's language; voice in any language via Whisper on the server."""
import base64, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


def test_same_as_my_message_is_an_explicit_instruction():
    from ginkassistant.services import languages
    note = languages.reply_note("auto")
    assert "same language the user writes in" in note and "Wolof to Wolof" in note
    assert "Always reply in French" in languages.reply_note("fr")


def test_automatic_speech_language_is_the_default():
    from ginkassistant.services import prefs, voice_profiles, voice_bridge
    assert prefs.DEFAULTS["speech_lang"] == "auto" and "auto" in voice_profiles.SPEECH_LANG_CODES
    assert voice_profiles.SPEECH_LANGS[0][0] == "auto" and voice_bridge.listen_language[0] == "auto"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "v.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []
    state = {"first_gone": False}
    def handler(request):
        body = request.content
        model = "whisper-large-v3-turbo" if b"whisper-large-v3-turbo" in body else "whisper-large-v3"
        sent.append({"path": request.url.path, "model": model, "has_file": b'filename="speech.wav"' in body})
        if state["first_gone"] and model == "whisper-large-v3-turbo":
            return httpx.Response(404, json={"error": {"message": "The model whisper-large-v3-turbo does not exist"}})
        return httpx.Response(200, json={"text": " Bonjour Gink, quel temps fait-il ? ", "language": "french"})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._stt_recent.clear()
    c = TestClient(b.app)
    return b, c, {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}, sent, state


WAV = base64.b64encode(b"RIFF....WAVEfmt " + b"\x00" * 200).decode()


def test_whisper_transcribes_and_detects_the_language(srv):
    b, c, h, sent, state = srv
    r = c.post("/voice/transcribe", headers=h, json={"audio_b64": WAV}).json()
    assert r == {"text": "Bonjour Gink, quel temps fait-il ?", "language": "french"}
    assert sent[-1]["path"].endswith("/audio/transcriptions") and sent[-1]["model"] == "whisper-large-v3-turbo" and sent[-1]["has_file"]


def test_falls_back_when_a_speech_model_is_retired(srv):
    b, c, h, sent, state = srv
    state["first_gone"] = True
    assert c.post("/voice/transcribe", headers=h, json={"audio_b64": WAV}).json()["text"].startswith("Bonjour")
    assert [s["model"] for s in sent] == ["whisper-large-v3-turbo", "whisper-large-v3"]


def test_limits(srv):
    b, c, h, sent, state = srv
    assert c.post("/voice/transcribe", json={"audio_b64": WAV}).status_code == 401
    assert c.post("/voice/transcribe", headers=h, json={"audio_b64": "not base64!"}).status_code == 422
    assert c.post("/voice/transcribe", headers=h, json={"audio_b64": base64.b64encode(b"x" * 4_000_001).decode()}).status_code == 422
    codes = [c.post("/voice/transcribe", headers=h, json={"audio_b64": WAV}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_the_apps_use_the_server_then_fall_back(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    calls = []
    def post(url, json=None, headers=None, timeout=None):
        calls.append(url); return httpx.Response(200, json={"text": "Na gode Gink", "language": "hausa"})
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setitem(vb.cloud, "base_url_fn", lambda: "https://gink-server.onrender.com")
    monkeypatch.setitem(vb.cloud, "token_fn", lambda: "tok")
    assert vb._transcribe_any_language(b"wav") == "Na gode Gink" and vb.last_heard_language[0] == "hausa"
    assert calls == ["https://gink-server.onrender.com/voice/transcribe"]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    assert vb._transcribe_any_language(b"wav") is None                               # -> Google instead
    monkeypatch.setitem(vb.cloud, "token_fn", lambda: None)
    assert vb._transcribe_any_language(b"wav") is None                               # signed out -> Google
    monkeypatch.setattr(vb, "_device_language", lambda: "fr-SN")
    assert vb._google_language() == "fr-SN"                                          # in the device's language
