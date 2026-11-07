"""Media Studio "Use a photo": the photo goes to the image service with the idea, is never stored by the
server, and only real JPEG/PNG/WebP under 6 MB is accepted."""
import asyncio, base64, io, json, os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest
from PIL import Image


def jpeg(size=(40, 30)):
    out = io.BytesIO(); Image.new("RGB", size, (200, 120, 40)).save(out, "JPEG"); return out.getvalue()


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    sent = []
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 40).decode()

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
    h = {"Authorization": "Bearer " + b._token_response("ib@x.co", "Ib")["token"]}
    return b, TestClient(b.app), h, sent


def test_photo_goes_with_the_idea(srv):
    b, c, h, sent = srv
    photo = jpeg()
    r = c.post("/media/image", headers=h, json={"prompt": "a marble statue of me", "aspect_ratio": "3:4",
                                                "photo_b64": base64.b64encode(photo).decode()})
    assert r.status_code == 200, r.text
    inp = sent[-1]["input"]
    assert inp[0]["type"] == "text" and inp[0]["text"].startswith(b.PHOTO_INSTRUCTION) and "marble statue" in inp[0]["text"]
    assert inp[1] == {"type": "image", "data": base64.b64encode(photo).decode(), "mime_type": "image/jpeg"}
    c.post("/media/image", headers=h, json={"prompt": "a sunset"})
    assert len(sent[-1]["input"]) == 1 and not sent[-1]["input"][0]["text"].startswith(b.PHOTO_INSTRUCTION)


def test_only_real_photos(srv):
    b, c, h, sent = srv
    for bad in (b"not a photo at all", b"GIF89a" + b"0" * 30):
        r = c.post("/media/image", headers=h, json={"prompt": "x", "photo_b64": base64.b64encode(bad).decode()})
        assert r.status_code == 422
    assert c.post("/media/image", headers=h, json={"prompt": "x", "photo_b64": "%%%"}).status_code == 422
    assert sent == []                                                          # nothing sent, nothing counted


def test_app_shrinks_and_sends_the_photo(monkeypatch):
    from ginkassistant.services import image_service as isv, api_client
    big = jpeg((4000, 3000))
    small = isv.shrink_photo(big)
    assert max(Image.open(io.BytesIO(small)).size) == 1536 and len(small) < len(big)
    seen = {}

    class Api:
        def __init__(self, base): pass
        async def generate_image(self, token, prompt, aspect, style, photo=None):
            seen.update(photo=photo); return {"image_b64": base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode()}
    monkeypatch.setattr(isv, "ApiClient", Api)
    monkeypatch.setattr(isv, "save_image", lambda d, n, raw, mime: types.SimpleNamespace(name="a.png"))
    svc = isv.ImageService("/tmp/gink-photo-test", lambda: "https://x", lambda: "tok")
    asyncio.run(svc.create("statue of me", "3:4", "photo", small))
    assert seen["photo"] == small


def test_media_studio_page_and_handler(monkeypatch):
    from ginkassistant.ui import media_studio_screen as ms
    assert 'id="add-photo"' in ms.PAGE and "people who agreed" in ms.PAGE and "ginkEmit('photo'" in ms.PAGE
    studio = ms.MediaStudio.__new__(ms.MediaStudio)
    studio.photo, studio.app = None, types.SimpleNamespace()
    calls, made = [], {}
    async def call(*a): calls.append(a)
    studio.call = call

    class Images:
        async def create(self, prompt, aspect, style, photo=None): made.update(photo=photo)
    studio.images = Images()
    async def nothing(): pass
    studio.refresh_gallery = studio.refresh_usage = nothing
    asyncio.run(studio.handle({"type": "photo", "value": {"data": base64.b64encode(jpeg()).decode(), "mime": "image/jpeg"}}))
    assert studio.photo and studio.photo[:3] == b"\xff\xd8\xff"
    asyncio.run(studio.handle({"type": "create", "value": {"prompt": "me as an elf", "style": "photo", "aspect": "3:4"}}))
    assert made["photo"] == studio.photo
    asyncio.run(studio.handle({"type": "photo", "value": None}))
    assert studio.photo is None
