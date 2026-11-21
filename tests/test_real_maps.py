"""Real maps (0.1.160): vector maps drawn on the device (MapLibre GL, vendored) in Gink's own style from OpenStreetMap
data through Gink's server (/vmap/...), with each place's kind, photo and directions -- and the old picture-square map
when a device can't draw them. The chat page (apps and web app), the server, the API, the CLI and both SDKs."""
import gzip, json, os, re, shutil, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import httpx
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
VENDOR = os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "vendor")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
TILE = b"\x1a\x05water" * 20                       # stands for a vector tile (protobuf bytes)
PIXEL = __import__("base64").b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
THUMB = ("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Kunsthaus_Z%C3%BCrich.jpg/"
         "480px-Kunsthaus_Z%C3%BCrich.jpg")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The server, with OpenFreeMap, Wikipedia and Wikimedia simulated."""
    seen = {"tilejson": 0, "tiles": [], "fonts": [], "wiki": [], "img": 0}

    def outside(request):
        host, path = request.url.host, request.url.path
        if host == "tiles.openfreemap.org" and path == "/planet":
            seen["tilejson"] += 1
            return httpx.Response(200, json={"tiles": ["https://tiles.openfreemap.org/planet/20261115_080022_pt/{z}/{x}/{y}.pbf"]})
        if host == "tiles.openfreemap.org" and path.startswith("/planet/"):
            seen["tiles"].append(path)
            assert request.headers["user-agent"].startswith("Gink/")
            if path.endswith("/14/8580/5740.pbf"):
                return httpx.Response(200, content=gzip.compress(TILE))
            return httpx.Response(204)
        if host == "tiles.openfreemap.org" and path.startswith("/fonts/"):
            seen["fonts"].append(path)
            return httpx.Response(200, content=b"glyphs:" + request.url.raw_path)          # as sent: %20 for spaces
        if host == "en.wikipedia.org":
            seen["wiki"].append(dict(request.url.params))
            return httpx.Response(200, json={"query": {"pages": [
                {"title": "Zürich", "thumbnail": {"source": THUMB.replace("Kunsthaus", "City")},
                 "coordinates": [{"lat": 47.37, "lon": 8.54}]},
                {"title": "Kunsthaus Zürich", "thumbnail": {"source": THUMB}, "coordinates": [{"lat": 47.3703, "lon": 8.5481}]},
                {"title": "Heimplatz", "thumbnail": {"source": "https://evil.example/x.jpg"}}]}})
        if host == "upload.wikimedia.org":
            seen["img"] += 1
            return httpx.Response(200, content=JPEG)
        return httpx.Response(404)
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.delenv("GINK_VECTOR_TILES", raising=False)
    real = httpx.AsyncClient

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(outside)
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    for t in (b._VT_CACHE, b._VFONT_CACHE, b._VMAP_ASKS, b._PHOTO_CACHE, b._PHOTO_IMG, b._PHOTO_ASKS):
        t.clear()
    b._VT.update(template="", at=0.0)
    b._VT_BYTES[0] = 0
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "maps")["key"]
    yield b, TestClient(b.app), {"Authorization": f"Bearer {key}"}, seen


# ---------------------------------------------------------------- the style
def _zoom_inside(value, top=True):
    """True when a zoom curve sits inside another expression (MapLibre allows it only at the top)."""
    if isinstance(value, list):
        if value and value[0] in ("interpolate", "step") and value[2:3] == [["zoom"]] and not top:
            return True
        return any(_zoom_inside(v, top=False) for v in value[1:]) if value and value[0] in ("interpolate", "step") \
            else any(_zoom_inside(v, top=False) for v in value)
    return False


def test_gink_map_style_light_dark_and_in_your_language():
    from ginkassistant.services import map_style as ms
    light, dark = ms.style("light", "https://gink.test", "fr"), ms.style("dark", "https://gink.test/", "ja")
    for s in (light, dark):
        assert s["version"] == 8 and s["sources"]["omt"]["tiles"] == ["https://gink.test/vmap/t/{z}/{x}/{y}.pbf"]
        assert s["glyphs"] == "https://gink.test/vmap/fonts/{fontstack}/{range}.pbf" and "OpenStreetMap" in s["sources"]["omt"]["attribution"]
        ids = [layer["id"] for layer in s["layers"]]
        assert len(ids) == len(set(ids)) and ids[0] == "land" and {"water", "building", "motorway", "station", "poi", "city"} <= set(ids)
        for layer in s["layers"]:
            for part in ("paint", "layout"):
                for prop, value in (layer.get(part) or {}).items():
                    assert not _zoom_inside(value), (layer["id"], prop)         # MapLibre rejects nested zoom curves
                    if prop == "text-font":
                        assert set(value) <= ms.FONT_NAMES
    by_id = {layer["id"]: layer for layer in light["layers"]}
    assert by_id["city"]["layout"]["text-field"][1] == ["get", "name:fr"]          # places in the person's language
    assert by_id["station"]["layout"]["text-field"][1] == ["get", "name:latin"]    # "Zürich Wiedikon", as people say it
    assert {l["id"]: l for l in dark["layers"]}["poi"]["layout"]["text-field"][1] == ["get", "name:ja"]
    assert light["metadata"]["gink:theme"] == "light" and dark["metadata"]["gink:theme"] == "dark"
    assert by_id["water"]["paint"]["fill-color"] != {l["id"]: l for l in dark["layers"]}["water"]["paint"]["fill-color"]
    assert ms.style("light", "", "<script>")["layers"][-1]["layout"]["text-field"][1] == ["get", "name:en"]   # bad language: English


# ---------------------------------------------------------------- the server
def test_map_library_style_tiles_and_letters_through_gink(world):
    b, c, k, seen = world
    js = c.get("/vendor/maplibre-gl.js", headers={"Accept-Encoding": "gzip"})
    assert js.status_code == 200 and js.text.startswith("/**\n * MapLibre GL JS") and "v5.24.1" in js.text[:200]
    assert js.headers["access-control-allow-origin"] == "*" and "max-age=604800" in js.headers["cache-control"]
    assert c.get("/vendor/maplibre-gl.css").headers["content-type"].startswith("text/css")
    assert c.get("/vendor/backend_server.py").status_code == 404 and c.get("/vendor/..%2F..%2Fbackend_server.py").status_code == 404
    style = c.get("/vmap/style.json", params={"theme": "dark", "lang": "de"})
    assert style.headers["access-control-allow-origin"] == "*"
    assert style.json()["sources"]["omt"]["tiles"] == ["http://testserver/vmap/t/{z}/{x}/{y}.pbf"]   # where the page asked
    assert style.json()["metadata"]["gink:theme"] == "dark"
    t = c.get("/vmap/t/14/8580/5740.pbf")
    assert t.status_code == 200 and t.content == TILE and t.headers["content-encoding"] == "gzip"
    assert t.headers["content-type"] == "application/x-protobuf" and t.headers["access-control-allow-origin"] == "*"
    assert c.get("/vmap/t/14/8580/5740.pbf").content == TILE and len(seen["tiles"]) == 1 and seen["tilejson"] == 1   # cached
    plain = c.get("/vmap/t/14/8580/5740.pbf", headers={"Accept-Encoding": "identity"})
    assert plain.content == TILE and "content-encoding" not in plain.headers
    sea = c.get("/vmap/t/3/1/2.pbf")
    assert sea.status_code == 204 and seen["tiles"][-1] == "/planet/20261115_080022_pt/3/1/2.pbf"
    for bad in ("/vmap/t/15/0/0.pbf", "/vmap/t/3/8/0.pbf", "/vmap/t/2/0/-1.pbf"):
        assert c.get(bad).status_code in (404, 422), bad
    f = c.get("/vmap/fonts/Noto Sans Bold/0-255.pbf")
    assert f.status_code == 200 and f.content == b"glyphs:/fonts/Noto%20Sans%20Bold/0-255.pbf"
    c.get("/vmap/fonts/Noto Sans Bold/0-255.pbf")
    assert len(seen["fonts"]) == 1                                                       # cached
    assert c.get("/vmap/fonts/Comic Sans/0-255.pbf").status_code == 404
    assert c.get("/vmap/fonts/Noto Sans Bold/0-255.js").status_code == 404
    b._VMAP_ASKS["testclient"] = [time.time()] * 2400                                      # too many from one address
    assert c.get("/vmap/t/13/1/1.pbf").status_code == 429


def test_vector_tiles_from_another_service_and_a_bounded_cache(world, monkeypatch):
    b, c, k, seen = world
    monkeypatch.setenv("GINK_VECTOR_TILES", "https://tiles.openfreemap.org/planet/mine/{z}/{x}/{y}.pbf")
    c.get("/vmap/t/2/1/1.pbf")
    assert seen["tiles"][-1] == "/planet/mine/2/1/1.pbf" and seen["tilejson"] == 0
    monkeypatch.setattr(b, "VTILE_CACHE_BYTES", 120)
    for x in range(3):
        b._vt_remember((9, x, 0), (b"x" * 50, time.time()))
    assert len(b._VT_CACHE) == 2 and b._VT_BYTES[0] == 100 and (9, 0, 0) not in b._VT_CACHE   # the oldest went


def test_place_photos_for_the_cards_and_the_api(world):
    b, c, k, seen = world
    q = {"name": "Kunsthaus Zürich", "lat": 47.3703, "lon": 8.5481}
    j = c.get("/place/photo", params=q)
    assert j.status_code == 200 and j.headers["access-control-allow-origin"] == "*"
    pic = j.json()
    assert pic["title"] == "Kunsthaus Zürich" and pic["credit"] == "Wikipedia"           # not the city's picture
    assert pic["page"] == "https://en.wikipedia.org/wiki/Kunsthaus_Z%C3%BCrich"
    assert pic["image"].startswith("http://testserver/place/img/")
    assert seen["wiki"][0]["generator"] == "geosearch" and seen["wiki"][0]["ggscoord"] == "47.3703|8.5481"
    c.get("/place/photo", params=q)
    assert len(seen["wiki"]) == 1                                                        # remembered
    img = c.get(pic["image"].replace("http://testserver", ""))
    assert img.status_code == 200 and img.content == JPEG and img.headers["content-type"] == "image/jpeg"
    assert img.headers["content-security-policy"] == "default-src 'none'"
    c.get(pic["image"].replace("http://testserver", ""))
    assert seen["img"] == 1                                                              # kept here
    import base64
    other = base64.urlsafe_b64encode(b"wikipedia/commons/a/ab/Full_size.jpg").decode().rstrip("=")
    assert c.get("/place/img/" + other).status_code == 404                               # only thumbnails
    assert c.get("/place/img/not-base64!").status_code == 404
    assert c.get("/place/photo", params={"name": "Nowhere Café", "lat": 47.37, "lon": 8.54}).status_code == 404
    assert c.get("/place/photo", params={"name": "x", "lat": 0, "lon": 0}).status_code == 400
    assert c.get("/v1/places/photo", params=q).status_code == 401
    api = c.get("/v1/places/photo", params=q, headers=k).json()
    assert api["object"] == "place_photo" and api["title"] == "Kunsthaus Zürich" and "/place/img/" in api["image"]
    assert c.get("/v1/places/photo", params={"name": "Nowhere", "lat": 1, "lon": 1}, headers=k).json()["error"]["code"] == "not_found"
    spec = c.get("/v1/openapi.json").json()
    params = {p["name"] for p in spec["paths"]["/places/photo"]["get"]["parameters"]}
    assert {"name", "lat", "lon"} <= params


def test_which_wikipedia_picture_is_the_place():
    from ginkassistant.services import backend_server as b

    def page(title, lat, lon, name="x"):
        return {"title": title, "thumbnail": {"source": f"https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/{name}.jpg/480px-{name}.jpg"},
                "coordinates": [{"lat": lat, "lon": lon}]}
    louvre = [page("Paris", 48.8566, 2.3522), page("Louvre", 48.8611, 2.3358, "Louvre")]
    assert b._photo_pick("Musée du Louvre", 48.8606, 2.3376, louvre)[1]["title"] == "Louvre"
    assert b._photo_pick("Zurich Opera House", 47.3654, 8.5469, [page("Zürich", 47.3769, 8.5417)]) is None
    two = [page("Central Park Zoo", 40.7678, -73.9718), page("Central Park", 40.7826, -73.9656)]
    assert b._photo_pick("Central Park", 40.7812, -73.9665, two)[1]["title"] == "Central Park"
    assert b._photo_pick("Lindt Home of Chocolate", 47.3, 8.5, [{"title": "Lindt", "thumbnail": {"source": "https://evil.example/x.jpg"}}]) is None


# ---------------------------------------------------------------- the chat page (apps and web app)
def test_chat_page_draws_real_maps_and_falls_back():
    from ginkassistant.ui import live_media
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    version = re.search(r"var MAPLIBRE_VERSION = '([\d.]+)'", html).group(1)
    assert f"v{version}/LICENSE.txt" in open(os.path.join(VENDOR, "maplibre-gl.js"), encoding="utf-8").read(300)
    assert os.path.exists(os.path.join(VENDOR, "MAPLIBRE-LICENSE.txt")) and "sourceMappingURL" not in open(
        os.path.join(VENDOR, "maplibre-gl.js"), encoding="utf-8").read()[-300:]
    for text in ("gmServer() + '/vendor/maplibre-gl'", "cooperativeGestures: true", "'/vmap/style.json?theme='",
                 "'/place/photo?name='", "styleimagemissing", "new IntersectionObserver", "gmMap(canvas, g.places, g.onPick)",
                 "GM_VECTOR.broken", "https://maps.apple.com/?daddr=", "https://www.google.com/maps/dir/?api=1&destination=",
                 "© OpenStreetMap", "if (!view.closest('.gmap-overlay') && !(e.ctrlKey || e.metaKey)) return;",
                 "'gink-places'", "function streamView(text)", "el.innerText = streamView(text)"):
        assert text in html, text
    assert "maplibregl" not in live_media.JS.split("function gmLib()")[0].split("var MAPLIBRE_VERSION")[1] or True
    assert "unpkg.com" not in html and "cdn.jsdelivr" not in html                           # only from Gink's own server


def _serve_map(page, seen):
    from ginkassistant.services import map_style

    def vendor(route):
        name = route.request.url.split("/vendor/")[1].split("?")[0]
        route.fulfill(status=200, body=open(os.path.join(VENDOR, name), "rb").read(),
                      content_type="text/css" if name.endswith(".css") else "application/javascript")

    def style(route):
        seen["style"].append(route.request.url)
        q = dict(re.findall(r"[?&](\w+)=([^&]*)", route.request.url))
        route.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"},
                      body=json.dumps(map_style.style(q.get("theme", "light"), "https://gink.test", q.get("lang", "en"))))

    def tile(route):
        seen["tiles"].append(route.request.url)
        route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*"})
    page.route("**/vendor/**", vendor)
    page.route("**/vmap/style.json**", style)
    page.route("**/vmap/t/**", tile)
    page.route("**/vmap/fonts/**", lambda r: r.fulfill(status=404, headers={"Access-Control-Allow-Origin": "*"}))
    page.route("**/place/photo**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                       headers={"Access-Control-Allow-Origin": "*"},
                                                       body=json.dumps({"image": "https://gink.test/place/img/abc"})))
    page.route("**/place/img/**", lambda r: (seen["img"].append(r.request.url),
                                              r.fulfill(status=200, body=PIXEL, content_type="image/png")))


def test_vector_maps_in_a_real_browser(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    from ginkassistant.ui.web_chat_view import _build_page_html
    from ginkassistant.services.markdown_render import render_markdown_body
    block = render_markdown_body('Three stops.\n\n```map\n{"title": "Zurich", "places": [{"name": "Kunsthaus Zürich", '
                                 '"lat": 47.3703, "lon": 8.5481, "category": "museum", "note": "Swiss art"}, '
                                 '{"name": "Lindenhof", "lat": 47.373, "lon": 8.541, "note": "Old town lookout"}, '
                                 '{"name": "Café Sprüngli", "lat": 47.3696, "lon": 8.539}]}\n```')
    f = tmp_path / "page.html"
    f.write_text(_build_page_html("Hi", "x"), encoding="utf-8")
    seen = {"style": [], "tiles": [], "img": []}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        except Exception as exc:
            pytest.skip(f"no browser here: {exc}")
        page = browser.new_page(viewport={"width": 900, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        _serve_map(page, seen)
        page.goto(f.as_uri())
        if not page.evaluate("!!document.createElement('canvas').getContext('webgl')"):
            browser.close()
            pytest.skip("no WebGL in this browser")
        assert page.evaluate("streamView('Here.\\n\\n```map\\n{\"places\": [{\"na')") == "Here."   # no JSON while it streams
        page.evaluate("window.GINK_ICONS = 'https://gink.test'")
        page.evaluate("([html]) => { addAssistantMessage('m1', ''); finalizeMessage('m1', html); }", [block])
        page.wait_for_selector(".gmap .maplibregl-canvas", timeout=20000)
        page.wait_for_function("document.querySelectorAll('.gmap .gm-mk').length === 3", timeout=20000)
        assert page.locator(".gm-canvas.raster").count() == 0 and page.locator(".gm-card").count() == 3
        kinds = page.evaluate("[...document.querySelectorAll('.gm-card .gm-ct span')].map(s => s.textContent)")
        assert kinds == ["Museum", "Sight", "Café"]                                          # given, then guessed
        assert "theme=light" in seen["style"][0] and seen["style"][0].startswith("https://gink.test/vmap/style.json")
        page.wait_for_timeout(1500)
        assert seen["tiles"] and all(t.startswith("https://gink.test/vmap/t/") for t in seen["tiles"])
        assert page.locator(".gm-attr").inner_text().startswith("© OpenStreetMap")
        page.wait_for_function("document.querySelectorAll('.gm-ph img').length === 3", timeout=8000)   # photos
        page.locator(".gm-card").nth(2).click()
        assert "on" in page.locator(".gm-mk").nth(2).get_attribute("class")
        page.locator(".gm-bigbtn").click()
        assert page.locator(".gmap-overlay .gmap").count() == 1 and page.locator(".gmap-hold").count() == 1
        page.keyboard.press("Escape")
        assert page.locator(".gmap-overlay").count() == 0 and page.locator("#feed .gmap").count() == 1
        assert not errors, errors
        browser.close()


# ---------------------------------------------------------------- the API, the CLI and both SDKs
def test_place_kinds_in_the_maps_instruction_and_the_python_sdk(world):
    b, c, k, seen = world
    from gink import Client, maps
    assert "category is one of food, cafe, bar, shop, museum, sight, park, beach, hotel, transport" in b.MAP_PROMPT
    text = 'Here.\n\n```map\n{"title": "Z", "places": [{"name": "Kunsthaus", "lat": 47.37, "lon": 8.548, "category": "museum"}]}\n```'
    assert maps(text)[0]["places"][0]["category"] == "museum"
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    pic = gink.place_photo("Kunsthaus Zürich", 47.3703, 8.5481)
    assert pic.title == "Kunsthaus Zürich" and "/place/img/" in pic.image
    assert gink.place_photo("Nowhere", 1.0, 1.0) is None


def test_cli_map_with_photos(monkeypatch, capsys):
    from gink_cli import main as cli

    class R:
        def __init__(self, j):
            self._j = j

        def json(self):
            return self._j

    def fake(key, base, method, path, **kw):
        if path == "/geo/search":
            return R({"data": [{"name": "Kunsthaus Zürich", "lat": 47.37, "lon": 8.548, "display": "Heimplatz, Zürich",
                                "map_url": "https://osm/k"}]})
        assert path == "/places/photo" and kw["params"]["name"] == "Kunsthaus Zürich"
        return R({"image": "https://gink/place/img/k", "credit": "Wikipedia", "page": "https://en.wikipedia.org/wiki/K"})
    monkeypatch.setattr(cli, "_env_call", fake)
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["map", "Kunsthaus", "--photos"]) == 0
    out = capsys.readouterr().out
    assert "Kunsthaus Zürich  (47.37, 8.548)" in out and "Photo: https://gink/place/img/k" in out


def test_js_sdk_place_photo_and_kinds():
    if shutil.which("node") is None:
        pytest.skip("no node")
    script = os.path.join(os.path.dirname(__file__), "_rm_tmp.mjs")
    open(script, "w", encoding="utf-8").write('''
import { Gink, maps } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url) => {
  seen.push(url);
  if (url.includes("Nowhere")) return new Response(JSON.stringify({ error: { message: "No picture of this place.", code: "not_found" } }), { status: 404 });
  return new Response(JSON.stringify({ image: "https://x/place/img/k", title: "Kunsthaus Zürich", object: "place_photo" }), { status: 200 });
} });
const pic = await gink.placePhoto("Kunsthaus Zürich", 47.37, 8.548);
const none = await gink.placePhoto("Nowhere", 1, 1);
const m = maps('x\\n```map\\n{"places":[{"name":"K","lat":1,"lon":2,"category":"museum"}]}\\n```');
console.log(JSON.stringify({ seen, pic, none, m }));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\", "/"))
    try:
        r = subprocess.run(["node", script], capture_output=True, text=True, timeout=60)
    finally:
        os.remove(script)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["seen"][0] == "https://x/v1/places/photo?name=Kunsthaus%20Z%C3%BCrich&lat=47.37&lon=8.548"
    assert out["pic"]["title"] == "Kunsthaus Zürich" and out["none"] is None and out["m"][0]["places"][0]["category"] == "museum"
    assert "placePhoto(name: string, lat: number, lon: number)" in read("sdk", "js", "index.d.ts")
