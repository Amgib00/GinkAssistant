"""Maps in answers (by themselves, no button), voice messages (hold the mic; spoken answers) and screen view (Live
looks at your screen; "look at my screen" starts it) -- across the apps' and web app's chat page, Genie, the server,
the API (geo, audio, gink_maps), the CLI and both SDKs. Plus batches in the SDKs and CLI. (0.1.159)"""
import base64, json, os, re, shutil, subprocess, sys, types
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import httpx
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 40


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The server, with the outside world simulated: map tiles, place search, the AI, speech."""
    seen = {"tiles": 0, "geo": [], "chat": [], "stt": [], "tts": 0}

    def outside(request):
        host, path = request.url.host, request.url.path
        if host == "tile.openstreetmap.org":
            seen["tiles"] += 1
            assert request.headers["user-agent"].startswith("Gink/")
            return httpx.Response(200, content=PNG)
        if host == "nominatim.openstreetmap.org":
            seen["geo"].append(dict(request.url.params))
            return httpx.Response(200, json=[{"name": "Eiffel Tower", "display_name": "Eiffel Tower, Paris, France",
                                              "lat": "48.8582599", "lon": "2.2945006", "type": "attraction"}])
        if path.endswith("/audio/transcriptions"):
            seen["stt"].append(request.content)
            return httpx.Response(200, json={"text": "Where is the Eiffel Tower?", "language": "english"})
        if "generativelanguage" in host or "interactions" in path:
            seen["tts"] += 1
            return httpx.Response(200, json={"output_audio": {"data": base64.b64encode(WAV).decode(), "mime_type": "audio/wav"}})
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        seen["chat"].append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Here it is."}}]})
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    real = httpx.AsyncClient

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(outside)
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "pro"})
    for t in (b._TILE_CACHE, b._TILE_ASKS, b._GEO_CACHE, b._GEO_ASKS, b._stt_recent):   # no state from other tests
        t.clear()
    b._geo_gate["last"] = 0.0
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "maps")["key"]
    c = TestClient(b.app)
    yield b, c, {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}, \
        {"Authorization": f"Bearer {key}"}, seen
    b._groq_models.update(ids=set(), at=0.0)
    b._stt_recent.clear()


# ---------------------------------------------------------------- maps
def test_map_tiles_are_proxied_cached_and_limited(world):
    b, c, h, k, seen = world
    r = c.get("/tiles/3/4/2.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert r.headers["access-control-allow-origin"] == "*" and "max-age=604800" in r.headers["cache-control"]
    assert c.get("/tiles/3/4/2.png").status_code == 200 and seen["tiles"] == 1               # from the cache
    for bad in ("/tiles/20/0/0.png", "/tiles/3/8/0.png", "/tiles/3/0/-1.png"):
        assert c.get(bad).status_code in (404, 422), bad
    b._TILE_ASKS["testclient"] = [__import__("time").time()] * 900                          # too many from one address
    assert c.get("/tiles/3/1/1.png").status_code == 429


def test_place_search_for_pages_and_developers(world):
    b, c, h, k, seen = world
    j = c.get("/geo/search", params={"q": "Eiffel Tower", "limit": 1})
    assert j.headers["access-control-allow-origin"] == "*"
    assert j.json()["places"] == [{"name": "Eiffel Tower", "display": "Eiffel Tower, Paris, France", "lat": 48.85826,
                                   "lon": 2.294501, "type": "attraction"}]
    c.get("/geo/search", params={"q": "eiffel tower", "limit": 1})
    assert len(seen["geo"]) == 1 and seen["geo"][0]["format"] == "jsonv2"                   # cached, case-insensitive
    api = c.get("/v1/geo/search", params={"q": "Eiffel Tower", "limit": 1}, headers=k).json()
    assert api["data"][0]["object"] == "place" and api["data"][0]["map_url"].startswith("https://www.openstreetmap.org/?mlat=48.85826")
    assert c.get("/v1/geo/search", params={"q": "x"}, headers=k).json()["error"]["code"] == "missing_query"
    assert c.get("/v1/geo/search", params={"q": "Paris"}).status_code == 401


def test_the_same_maps_instruction_everywhere_and_gink_maps(world):
    b, c, h, k, seen = world
    from ginkassistant.services import groq_worker
    bridge = read("webapp", "bridge.js")
    js = json.loads(re.search(r"var MAP_PROMPT = (\".*?\");\n", bridge).group(1))
    assert b.MAP_PROMPT == groq_worker.MAP_PROMPT == js and "fenced code block with the language map" in js
    assert groq_worker.DEFAULT_SYSTEM_PROMPT.endswith(groq_worker.MAP_PROMPT) and "MAP_PROMPT) +" in bridge
    c.post("/v1/chat/completions", headers=k, json={"messages": [{"role": "user", "content": "Where is the Eiffel Tower?"}],
                                                    "gink_maps": True})
    sent = seen["chat"][-1]
    assert sent["messages"][0] == {"role": "system", "content": b.MAP_PROMPT} and "gink_maps" not in sent
    c.post("/v1/chat/completions", headers=k, json={"messages": [{"role": "user", "content": "Hi"}]})
    assert all(m.get("content") != b.MAP_PROMPT for m in seen["chat"][-1]["messages"])     # only when asked


def test_chat_page_draws_maps_by_itself():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    for text in ("window.upgradeMaps = function", "if (window.upgradeMaps) upgradeMaps(el);", "'/tiles/' + st.z",
                 "/geo/search?limit=1&q=", "OpenStreetMap</a> contributors", "gmFit(places"):
        assert text in html, text
    assert "Show map" not in html                                                         # no button: by itself


def test_maps_in_a_real_browser(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    from ginkassistant.ui.web_chat_view import _build_page_html
    from ginkassistant.services.markdown_render import render_markdown_body
    page_html = _build_page_html("Hi", "x").replace("__THEME__", "")
    block = render_markdown_body('Here they are.\n\n```map\n{"title": "Two museums", "places": [{"name": "Louvre", '
                                 '"lat": 48.8606, "lon": 2.3376}, {"name": "Orsay", "query": "Musée d\'Orsay, Paris"}]}\n```')
    f = tmp_path / "page.html"
    f.write_text(page_html, encoding="utf-8")
    tiles = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no browser here: {exc}")
        page = browser.new_page(viewport={"width": 900, "height": 800})
        page.route("**/tiles/**", lambda route: (tiles.append(route.request.url), route.fulfill(status=200, body=PNG, content_type="image/png")))
        page.route("**/geo/search**", lambda route: route.fulfill(status=200, content_type="application/json",
                                                                  body=json.dumps({"places": [{"lat": 48.86, "lon": 2.3266}]})))
        page.route("**/place/photo**", lambda route: route.fulfill(status=404, body="{}", content_type="application/json"))
        page.goto(f.as_uri())
        page.evaluate("window.GINK_ICONS = 'https://gink.test'; window.ginkVectorMaps = false")   # the picture-square map
        page.evaluate("([html]) => { addAssistantMessage('m1', ''); finalizeMessage('m1', html); }", [block])
        page.wait_for_selector(".gmap .gmap-pin", timeout=8000)
        assert page.locator(".gmap .gmap-pin").count() == 2 and page.locator(".gmap .gm-card").count() == 2
        assert page.locator(".code-block-label", has_text="map").count() == 0                # the block became the map
        assert tiles and all(t.startswith("https://gink.test/tiles/") for t in tiles)
        z0 = page.evaluate("document.querySelector('.gmap-view img.tile').src")
        page.locator(".gmap-zoom button").first.click()
        assert page.evaluate("document.querySelector('.gmap-view img.tile').src") != z0        # zoomed in: new squares
        page.locator(".gm-card").nth(1).click()                                                 # a card picks its place
        assert "on" in page.locator(".gmap-pin").nth(1).get_attribute("class")
        browser.close()


# ---------------------------------------------------------------- voice messages and the audio API
def test_voice_messages_in_any_format_and_the_audio_api(world):
    b, c, h, k, seen = world
    webm = b"\x1aE\xdf\xa3" + b"\x00" * 50
    assert b._audio_format("", webm) == "webm" and b._audio_format("note.m4a", b"") == "m4a"
    assert b._audio_format("", b"OggS....") == "ogg" and b._audio_format("", WAV) == "wav"
    j = c.post("/voice/transcribe", headers=h, json={"audio_b64": base64.b64encode(webm).decode(), "format": "webm"}).json()
    assert j["text"] == "Where is the Eiffel Tower?" and b'filename="speech.webm"' in seen["stt"][-1]
    assert b"audio/webm" in seen["stt"][-1]
    r = c.post("/v1/audio/transcriptions", headers=k, files={"file": ("hello.m4a", b"\x00\x00\x00\x18ftypM4A ")}, data={"language": "fr"})
    assert r.json()["text"] == "Where is the Eiffel Tower?" and b'filename="speech.m4a"' in seen["stt"][-1]
    assert c.post("/v1/audio/transcriptions", headers=k, json={"audio_b64": "!!"}).json()["error"]["code"] == "invalid_audio"
    speech = c.post("/v1/audio/speech", headers=k, json={"input": "Hello there"})
    assert speech.status_code == 200 and speech.headers["content-type"] == "audio/wav" and speech.content == WAV
    assert c.post("/v1/audio/speech", headers=k, json={"input": " "}).json()["error"]["code"] == "missing_input"


def test_voice_messages_on_the_page_the_apps_web_and_genie():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    for text in ("VM.timer = setTimeout(vmStart, 380)", "ginkEmit('voice_message', { action: 'start' })",
                 "window.markVoiceMessage = function (url, secs, text)", "e.stopImmediatePropagation()", "MediaRecorder"):
        assert text in html, text
    bridge = read("webapp", "bridge.js")
    assert 'window.ginkVoiceRecorder = "page"' in bridge and "voice_message: voiceMessage" in bridge
    assert "W.prefs.read_aloud || W.voiceReply" in bridge and '"/voice/transcribe", { audio_b64: v.data' in bridge
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert 'kind == "voice_message"' in main and "async def voice_message(" in main and "or spoken:" in main
    genie = read("src", "ginkassistant", "services", "web_app", "genie.html")
    assert 'id="gvoice"' in genie and 'api("/voice/transcribe"' in genie


# ---------------------------------------------------------------- screen view
def test_screen_view_everywhere(monkeypatch):
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    for text in ("md.getDisplayMedia({ video: true, audio: false })", "window.liveScreenFrame = function",
                 "ginkEmit('screen_view', { on: true })", "window.openScreenView = function", "LIVE.pendingQ = text",
                 "if (document.hidden && !screen) closeLive();"):
        assert text in html, text
    from ginkassistant.ui import main_screen
    js_re = re.search(r"window\.GINK_SCREEN_RE = /(.*?)/i;", read("src", "ginkassistant", "ui", "live_media.py")).group(1)
    assert js_re == main_screen.SCREEN_ASK.pattern                                       # the same words in the apps
    for yes in ("Can you look at my screen?", "what's on my screen", "help me with this error on my screen", "share my screen"):
        assert main_screen.SCREEN_ASK.search(yes), yes
    for no in ("my screen is cracked, where can I fix it?", "screen time tips"):
        assert not main_screen.SCREEN_ASK.search(no), no
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "SCREEN_ASK.search(message) and screen_view_supported()" in main and '"live-screen.jpg"' in main
    assert 'window.GINK_NATIVE_SCREEN = true' in main and 'kind == "screen_view"' in main
    assert "display-capture=(self)" in read("src", "ginkassistant", "services", "backend_server.py")
    bridge = read("webapp", "bridge.js")
    assert "GINK_SCREEN_RE.test(text)" in bridge and "openScreenView(text)" in bridge
    from ginkassistant.services.actions import computer as cc
    monkeypatch.setattr(cc, "run", lambda *a, **k: (False, "no"))
    monkeypatch.setattr(cc, "shutil", types.SimpleNamespace(which=lambda n: None, copy2=shutil.copy2))
    assert cc.ComputerControl().screen_image() in ("",) or cc.ComputerControl().screen_image().startswith("data:image/")


# ---------------------------------------------------------------- SDKs and CLI
def test_python_sdk_geo_maps_audio_and_batches(world, monkeypatch):
    b, c, h, k, seen = world
    from gink import Client, maps
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    assert gink.geo("Eiffel Tower")[0].map_url.startswith("https://www.openstreetmap.org/")
    text = 'Here.\n\n```map\n{"title": "Paris", "places": [{"name": "Louvre", "lat": 48.86, "lon": 2.33}, {"name": "x"}, 7]}\n```'
    assert maps(text) == gink.maps(text) == [{"title": "Paris", "places": [
        {"name": "Louvre", "lat": 48.86, "lon": 2.33, "map_url": "https://www.openstreetmap.org/?mlat=48.86&mlon=2.33#map=16/48.86/2.33"},
        {"name": "x"}]}]
    assert gink.audio.transcribe(b"\x1aE\xdf\xa3" + b"\x00" * 9, filename="note.webm") == "Where is the Eiffel Tower?"
    assert gink.audio.speech("Hello") == WAV
    calls = []

    async def fake_run(bid):
        calls.append(bid)
    monkeypatch.setattr(b, "_start_batch", lambda bid: calls.append(bid))
    batch = gink.batches.create(["Say hi", [{"role": "user", "content": "Say bye"}], {"custom_id": "mine", "body": {"messages": []}}],
                                name="greetings")
    assert batch.status == "queued" and batch.request_counts["total"] == 3 and calls == [batch.id]
    assert [x.id for x in gink.batches.list()] == [batch.id] and gink.batches.get(batch.id).name == "greetings"
    assert gink.batches.results(batch.id) == [] and gink.batches.cancel(batch.id).status == "cancelled"


def test_cli_map_say_transcribe_screen_and_batch(monkeypatch, capsys, tmp_path):
    from gink_cli import main as cli
    calls = []

    class R:
        def __init__(self, j=None, content=b"", text=""):
            self._j, self.content, self.text = j, content, text
        def json(self): return self._j

    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw))
        if path == "/geo/search":
            return R({"data": [{"name": "Louvre", "lat": 48.86, "lon": 2.33, "display": "Louvre, Paris", "map_url": "https://osm/l"}]})
        if path == "/audio/speech":
            return R(content=WAV)
        if path == "/audio/transcriptions":
            return R({"text": "bonjour"})
        if path == "/batches" and method == "POST":
            return R({"id": "batch_1", "status": "queued", "request_counts": {"total": 2, "completed": 0, "failed": 0}})
        return R({"data": []})
    monkeypatch.setattr(cli, "_env_call", fake)
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["map", "Louvre"]) == 0 and "Louvre  (48.86, 2.33)" in capsys.readouterr().out
    out = tmp_path / "hi.wav"
    assert cli.main(["say", "Hello", "-o", str(out)]) == 0 and out.read_bytes() == WAV
    rec = tmp_path / "note.m4a"
    rec.write_bytes(b"x")
    capsys.readouterr()
    assert cli.main(["transcribe", str(rec)]) == 0 and capsys.readouterr().out.strip() == "bonjour"
    assert calls[-1][2]["files"]["file"][0] == "note.m4a"
    prompts = tmp_path / "p.txt"
    prompts.write_text('Summarise the news\n{"custom_id": "t", "body": {"messages": [{"role": "user", "content": "Translate"}]}}\n')
    assert cli.main(["batch", str(prompts), "--name", "daily"]) == 0
    sent = calls[-1][2]["json"]
    assert sent["name"] == "daily" and [r["custom_id"] for r in sent["requests"]] == ["request-1", "t"]
    import gink.client as sdk
    monkeypatch.setattr(sdk, "screen_image", lambda: PNG)
    streamed = []
    monkeypatch.setattr(cli, "stream_answer", lambda key, base, messages: streamed.append(messages))
    assert cli.main(["screen", "what", "is", "this", "error?"]) == 0
    assert streamed[0][0]["content"][0]["text"] == "what is this error?"
    assert streamed[0][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_js_sdk_geo_maps_audio_and_batches():
    if shutil.which("node") is None:
        pytest.skip("no node")
    script = os.path.join(os.path.dirname(__file__), "_lm_tmp.mjs")
    open(script, "w", encoding="utf-8").write('''
import { Gink, maps } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url, init.body instanceof FormData ? "form" : init.body ? JSON.parse(init.body) : null]);
  if (url.endsWith("/audio/speech")) return new Response(new Uint8Array([82, 73, 70, 70]), { status: 200 });
  if (url.includes("/results")) return new Response('{"custom_id":"request-1","response":{}}\\n', { status: 200 });
  return new Response(JSON.stringify({ data: [{ name: "Louvre", lat: 48.86, lon: 2.33 }], text: "hi", id: "batch_1", status: "queued" }), { status: 200 });
} });
const geo = await gink.geo("Louvre");
const wav = new Uint8Array(await gink.audio.speech("Hello", { voice: "Male (Guy)" }));
const said = await gink.audio.transcribe(new Uint8Array([1, 2, 3]), { filename: "a.webm" });
await gink.batches.create(["Say hi"], { name: "n" });
const res = await gink.batches.results("batch_1");
const m = maps('x\\n```map\\n{"title":"T","places":[{"name":"Louvre","lat":48.86,"lon":2.33}]}\\n```');
console.log(JSON.stringify({ seen, geo, wav: Array.from(wav), said, res, m }));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\", "/"))
    try:
        r = subprocess.run(["node", script], capture_output=True, text=True, timeout=60)
    finally:
        os.remove(script)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["seen"][0][:2] == ["GET", "https://x/v1/geo/search?q=Louvre&limit=5"] and out["geo"][0]["name"] == "Louvre"
    assert out["seen"][1] == ["POST", "https://x/v1/audio/speech", {"input": "Hello", "voice": "Male (Guy)"}] and out["wav"] == [82, 73, 70, 70]
    assert out["seen"][2][2] == "form" and out["said"] == "hi"
    assert out["seen"][3][2] == {"requests": [{"custom_id": "request-1", "body": {"messages": [{"role": "user", "content": "Say hi"}]}}], "name": "n"}
    assert out["res"] == [{"custom_id": "request-1", "response": {}}]
    assert out["m"][0]["places"][0]["map_url"].startswith("https://www.openstreetmap.org/?mlat=48.86")
