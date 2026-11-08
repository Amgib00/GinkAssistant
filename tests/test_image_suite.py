"""Image looks across the whole suite: Media Studio's Ideas and styles mean the same in the apps, the web
app, the API, the SDKs and the CLI; a photo can be the starting point everywhere."""
import base64, io, json, os, subprocess, shutil, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import httpx, pytest
from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..")


def jpeg():
    out = io.BytesIO(); Image.new("RGB", (20, 20), (9, 9, 9)).save(out, "JPEG"); return out.getvalue()


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "img.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    sent = []
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 30).decode()

    def gemini(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"outputs": [{"type": "image", "data": png, "mime_type": "image/png"}],
                                         "output_image": {"data": png, "mime_type": "image/png"}})
    from httpx import _client

    class Mock(_client.AsyncClient):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(gemini); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    b._upsert_user("ib@x.co", "Ib", None, "password")
    key = b._create_api_key("ib@x.co", "img")["key"]
    return b, TestClient(b.app), {"Authorization": f"Bearer {key}"}, sent


def test_the_same_ideas_everywhere(srv):
    b, c, k, sent = srv
    from ginkassistant.services import image_ideas
    from ginkassistant.ui import media_studio_screen
    cat = c.get("/v1/images/ideas").json()
    assert [i["id"] for i in cat["ideas"]] == [i[0] for i in media_studio_screen.IDEAS] == [i[0] for i in image_ideas.IDEAS]
    assert c.get("/media/ideas").json() == cat and {"3d", "photo", "anime"} <= {s["id"] for s in cat["styles"]}


def test_api_idea_style_size_and_photo(srv):
    b, c, k, sent = srv
    r = c.post("/v1/images/generations", headers=k, json={"idea": "statue", "subject": "my grandmother", "photo": base64.b64encode(jpeg()).decode()})
    assert r.status_code == 200, r.text
    body = sent[-1]
    assert "my grandmother as a white marble statue" in body["input"][0]["text"] and body["input"][0]["text"].startswith(b.PHOTO_INSTRUCTION)
    assert body["input"][1]["mime_type"] == "image/jpeg" and body["response_format"]["aspect_ratio"] == "3:4"
    c.post("/v1/images/generations", headers=k, json={"prompt": "a lighthouse", "style": "3d", "size": "1792x1024"})
    assert "3D render, soft studio lighting" in sent[-1]["input"][0]["text"] and sent[-1]["response_format"]["aspect_ratio"] == "16:9"
    c.post("/v1/images/generations", headers=k, json={"prompt": "a lighthouse", "style": "in the style of a woodcut"})
    assert "woodcut" in sent[-1]["input"][0]["text"]                                       # own words kept
    assert c.post("/v1/images/generations", headers=k, json={"idea": "nope"}).status_code == 422


def test_web_app_starts_from_an_attached_photo():
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "function photoOf(atts)" in bridge and "body.photo_b64 = photo" in bridge
    assert "IMAGE_RE.test(text) && (!atts.length || photoOf(atts))" in bridge


def test_python_sdk_and_cli(monkeypatch, tmp_path, capsys):
    from gink import Client
    sent = {}

    class R:
        status_code = 200
        def json(self): return {"data": [{"b64_json": base64.b64encode(b"PNG").decode()}]}
    gink = Client(api_key="k", base_url="https://x/v1", http=types.SimpleNamespace(
        request=lambda method, url, headers, json=None, **kw: sent.update(url=url, body=json) or R()))
    photo = tmp_path / "me.jpg"; photo.write_bytes(jpeg())
    assert gink.image("my dog", idea="figurine", style="3d", photo=str(photo)) == b"PNG"
    assert sent["body"]["idea"] == "figurine" and sent["body"]["subject"] == "my dog" and sent["body"]["photo"]
    from gink_cli import main as m
    body = {}

    class C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json): body.update(json); return R()
    monkeypatch.setattr(m, "_client", lambda key, t: C())
    out = m.make_image("k", "https://x/v1", "my cat", str(tmp_path / "x.png"), idea="statue", aspect="3:4", photo=str(photo))
    assert open(out, "rb").read() == b"PNG" and body["idea"] == "statue" and body["aspect_ratio"] == "3:4" and body["photo"]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_image_options(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink } from "%s";
let seen;
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen = { url, body: JSON.parse(init.body) };
  return new Response(JSON.stringify({ data: [{ b64_json: "UE5H" }] }), { status: 200 }); } });
const bytes = await gink.image("my dog", { idea: "chibi", photo: new Uint8Array([1, 2, 3]) });
console.log(JSON.stringify({ seen, out: Array.from(bytes) }));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["seen"]["url"] == "https://x/v1/images/generations" and j["seen"]["body"]["idea"] == "chibi"
    assert j["seen"]["body"]["photo"] == "AQID" and j["out"] == [80, 78, 71]
