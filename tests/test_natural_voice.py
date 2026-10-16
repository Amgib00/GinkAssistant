"""Natural voices: sentence streaming, fallbacks, stop, and the server's Gemini TTS call."""
import asyncio, base64, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import pytest


def test_sentence_splitting():
    from ginkassistant.services.voice_bridge import split_sentences
    done, rest = split_sentences("Sure! Dr. Diallo said the rate is 3.5 percent, e.g. for loans. And then")
    assert done == ["Sure! Dr. Diallo said the rate is 3.5 percent, e.g. for loans."] and rest.strip() == "And then"
    done, rest = split_sentences("Hi. Yes. That works well for me. ", final=True)
    assert done == ["Hi. Yes. That works well for me."] and rest == ""          # short bits joined, not choppy
    assert split_sentences("Half a sente")[0] == []


def test_queue_starts_early_falls_back_and_stops(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    events, synth_at, played = [], [], []
    vb.on_speaking = events.append
    async def no_cloud(t, k): return None
    async def no_edge(t, k): return None
    monkeypatch.setattr(vb, "_cloud_wav", no_cloud, raising=False)
    monkeypatch.setattr(vb, "_edge_mp3", no_edge, raising=False)
    real_synth = vb._synth_sentence
    async def spy_synth(t, k):
        synth_at.append(t); return await real_synth(t, k)
    async def fake_play(item, amp):
        played.append(item); await asyncio.sleep(0.05)
    monkeypatch.setattr(vb, "_synth_sentence", spy_synth)
    monkeypatch.setattr(vb, "_play_item", fake_play)

    async def stream():
        q = vb.SpeechQueue("ezinne")
        q.feed("Good morning! Today in Dakar it's sunny ")
        q.feed("and about 31 degrees. ")
        await asyncio.sleep(0.03)
        early = list(synth_at)                         # before the reply is finished
        q.feed("Take water if you go out, it's hot.")
        q.finish()
        await q.wait()
        return early
    early = asyncio.run(stream())
    assert early == ["Good morning! Today in Dakar it's sunny and about 31 degrees."]
    assert [p[0] for p in played] == ["system", "system"]                      # both engines down -> own voice
    assert events == [True, False]

    async def stopped():
        q = vb.SpeechQueue("ezinne")
        q.feed("One sentence that is long enough. Another sentence that is long enough. ")
        await asyncio.sleep(0.01)
        vb.stop_speaking()
        await asyncio.wait_for(q.wait(), 2)            # ends promptly, never hangs
    played.clear()
    asyncio.run(stopped())
    assert len(played) <= 1
    vb.on_speaking = None


def test_engine_order_prefers_natural_voice(monkeypatch, tmp_path):
    from ginkassistant.services import voice_bridge as vb
    calls = []
    async def cloud(t, k): calls.append("cloud"); return str(tmp_path / "a.wav")
    async def edge(t, k): calls.append("edge"); return str(tmp_path / "b.mp3")
    monkeypatch.setattr(vb, "_cloud_wav", cloud, raising=False)
    monkeypatch.setattr(vb, "_edge_mp3", edge, raising=False)
    item = asyncio.run(vb._synth_sentence("Hello there, how are you?", "sonia"))
    assert item == ("file", str(tmp_path / "a.wav")) and calls == ["cloud"]


@pytest.fixture
def tts(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("GINK_FREE_VOICE_CHARS", "100")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._regional_voice_cache.clear()
    calls, mode = [], {"v": "ok"}
    WAV = base64.b64encode(b"RIFF....WAVEfmt fake").decode()
    real = httpx.AsyncClient

    def google(req):
        if req.url.path.endswith("/voices"):
            calls.append({"voices": dict(req.url.params)})
            return httpx.Response(200, json={"voices": [{"id": "voice_ng_conversational_f1", "display_name": "Adaeze"}]})
        calls.append({"key": req.headers.get("x-goog-api-key"), "body": json.loads(req.content)})
        if mode["v"] == "down":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json={"steps": [{"type": "model_output", "content": [{"type": "audio", "data": WAV, "mime_type": "audio/wav"}]}]})

    class Routed(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", httpx.MockTransport(google)); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Routed)
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@x.co", "I")["token"]}
    return b, c, h, calls, mode


def test_server_tts_request_voices_and_allowance(tts):
    b, c, h, calls, mode = tts
    r = c.post("/voice/speak", json={"text": "Hi, I'm Jenny. How are you?", "persona": "Female (Jenny)", "speed": "slow"}, headers=h)
    assert r.status_code == 200 and r.json()["mime_type"] == "audio/wav"
    body = calls[-1]["body"]
    assert calls[-1]["key"] == "g-key" and body["model"] == "gemini-3.8-flash-lite-tts"
    part = body["input"][0]["content"][0]
    assert part["text"] == "Hi, I'm Jenny. How are you?"                      # verbatim, no stage directions
    assert part["annotations"] == [{"type": "speech_metadata", "style": "warm, relaxed and conversational, speaking slowly"}]
    assert body["generation_config"] == {"speech_config": [{"voice": "Sulafat"}]} and body["response_format"] == {"type": "audio"}
    # Nigerian voice: looked up by region in Google's voice library, then cached
    c.post("/voice/speak", json={"text": "Good morning!", "persona": "ezinne"}, headers=h)
    c.post("/voice/speak", json={"text": "How was your day?", "persona": "ezinne"}, headers=h)
    lookups = [x for x in calls if "voices" in x]
    assert len(lookups) == 1 and lookups[0]["voices"]["region_code"] == "NG" and lookups[0]["voices"]["context"] == "Conversational"
    assert calls[-1]["body"]["generation_config"]["speech_config"] == [{"voice": "voice_ng_conversational_f1"}]
    # failures are refunded; the daily allowance is enforced
    mode["v"] = "down"
    used_before = c.get("/ai/usage", headers=h).status_code
    assert c.post("/voice/speak", json={"text": "x" * 20, "persona": "abeo"}, headers=h).status_code == 502
    mode["v"] = "ok"
    r = c.post("/voice/speak", json={"text": "y" * 80, "persona": "abeo"}, headers=h)
    assert r.status_code == 429 and "standard voice" in r.json()["error"]["message"]
    assert c.post("/voice/speak", json={"text": "hi"}).status_code == 401


def test_failure_reasons_are_reported(tts, monkeypatch, capsys):
    """Google refuses (e.g. model not available for the key) -> the exact reason reaches the app."""
    b, c, h, calls, mode = tts
    import httpx as _h
    def refuse(req):
        return _h.Response(403, json={"error": {"message": "Text-to-speech requires a paid plan for this API key."}})
    real = _h.AsyncClient.__mro__[1]
    class Refusing(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", _h.MockTransport(refuse)); super().__init__(*a, **k)
    monkeypatch.setattr(_h, "AsyncClient", Refusing)
    r = c.post("/voice/speak", json={"text": "Hello there!", "persona": "Male (Guy)"}, headers=h)
    err = r.json()["error"]
    assert r.status_code == 502 and "Google 403" in err["detail"] and "paid plan" in err["detail"]
    assert "Natural voice: Google answered 403" in capsys.readouterr().out          # in the server's log


def test_app_side_reasons(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    vb.cloud["base_url_fn"], vb.cloud["token_fn"] = (lambda: "http://t"), (lambda: None)
    assert asyncio.run(vb.test_natural_voice("Male (Guy)")) == "not signed in to the Gink server (sign out and in again)"
    import httpx as _h
    real = _h.AsyncClient
    class Missing(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", _h.MockTransport(lambda req: _h.Response(
                503, json={"error": {"message": "Natural voices aren't set up on this server yet (GEMINI_API_KEY is missing)."}})))
            super().__init__(*a, **k)
    monkeypatch.setattr(_h, "AsyncClient", Missing)
    vb.cloud["token_fn"] = lambda: "tok"
    assert "GEMINI_API_KEY is missing" in asyncio.run(vb.test_natural_voice("Male (Guy)"))
    class Old(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", _h.MockTransport(lambda req: _h.Response(404, json={"detail": "Not Found"})))
            super().__init__(*a, **k)
    monkeypatch.setattr(_h, "AsyncClient", Old)
    assert "older than the app" in asyncio.run(vb.test_natural_voice("Male (Guy)"))
    vb.cloud["base_url_fn"] = vb.cloud["token_fn"] = None


def test_google_free_tier_limit_pauses_calls(tts, monkeypatch):
    b, c, h, calls, mode = tts
    b._tts_cooldown.update(until=0.0, reason="")
    import httpx as _h
    hits = []
    def limited(req):
        hits.append(1)
        return _h.Response(429, json={"error": {"message": "Rate limit exceeded for model gemini-3.8-flash-lite-tts "
                                                           "(limit: 3 requests per minute on Free Tier). Please retry in 50s or upgrade your tier."}})
    real = _h.AsyncClient.__mro__[1]
    class Limited(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", _h.MockTransport(limited)); super().__init__(*a, **k)
    monkeypatch.setattr(_h, "AsyncClient", Limited)
    r = c.post("/voice/speak", json={"text": "Hello there!", "persona": "Male (Guy)"}, headers=h)
    err = r.json()["error"]
    assert r.status_code == 503 and err["code"] == "voice_busy" and err["retry_after"] == 50
    assert "Free Tier" in err["detail"] and "enable billing" in err["detail"] and "50 seconds" in err["detail"]
    r2 = c.post("/voice/speak", json={"text": "Still there?", "persona": "Male (Guy)"}, headers=h)
    assert r2.status_code == 503 and len(hits) == 1                  # Google isn't called again during the wait
    b._tts_cooldown.update(until=0.0, reason="")


def test_app_waits_as_long_as_google_says(monkeypatch):
    import time as _t
    from ginkassistant.services import voice_bridge as vb
    import httpx as _h
    real = _h.AsyncClient
    class Busy(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", _h.MockTransport(lambda req: _h.Response(503, json={"error": {
                "code": "voice_busy", "retry_after": 3600, "detail": "Google's Free Tier limit for voices was reached \u2014 back in about 60 minutes"}})))
            super().__init__(*a, **k)
    monkeypatch.setattr(_h, "AsyncClient", Busy)
    vb.cloud["base_url_fn"], vb.cloud["token_fn"] = (lambda: "http://t"), (lambda: "tok")
    reason = asyncio.run(vb.test_natural_voice("Male (Guy)"))
    assert "Free Tier" in reason and "60 minutes" in reason
    assert asyncio.run(vb._cloud_wav("Hi there!", "Male (Guy)")) is None   # no new request while waiting
    vb.cloud["base_url_fn"] = vb.cloud["token_fn"] = None


def test_long_answer_needs_few_voice_requests(monkeypatch):
    from ginkassistant.services import voice_bridge as vb
    requests = []
    async def synth(t, k):
        requests.append(t); await asyncio.sleep(0.02); return ("system", t)
    async def play(item, amp):
        await asyncio.sleep(0.05)
    monkeypatch.setattr(vb, "_synth_sentence", synth)
    monkeypatch.setattr(vb, "_play_item", play)
    answer = " ".join(f"This is sentence number {i} of a fairly long spoken answer." for i in range(1, 13))
    async def go():
        q = vb.SpeechQueue("Male (Guy)")
        q.feed(answer)
        q.finish()
        await q.wait()
    asyncio.run(go())
    assert len(requests) <= 3 and requests[0].startswith("This is sentence number 1") and len(requests[0]) < 80
    assert " ".join(requests) == answer                                   # nothing lost or reordered
