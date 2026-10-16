"""Image creation (server), file creation, profile + instructions, languages."""
import asyncio, base64, io, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import httpx
import pytest

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-final").decode()
THOUGHT = base64.b64encode(b"\x89PNG\r\n\x1a\nthought").decode()


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("GINK_FREE_IMAGES", "2")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    calls, mode = [], {"v": "ok"}
    real = httpx.AsyncClient

    def google(req):
        calls.append({"url": str(req.url), "key": req.headers.get("x-goog-api-key"), "body": json.loads(req.content)})
        if mode["v"] == "down":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        if mode["v"] == "refused":
            return httpx.Response(400, json={"error": {"message": "Request blocked by safety policy"}})
        # shape from Google's Interactions docs: thought step + model_output step
        return httpx.Response(200, json={"id": "int-1", "steps": [
            {"type": "thought", "summary": [{"type": "image", "data": THOUGHT, "mime_type": "image/png"}]},
            {"type": "model_output", "content": [{"type": "text", "text": "Here you go"},
                                                 {"type": "image", "data": PNG, "mime_type": "image/png"}]}]})

    class Routed(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", httpx.MockTransport(google)); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Routed)
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@x.co", "I")["token"]}
    return b, c, h, calls, mode


def test_image_endpoint_limits_and_refunds(media):
    b, c, h, calls, mode = media
    r = c.post("/media/image", json={"prompt": "a sunset over Dakar", "aspect_ratio": "16:9", "style": "watercolour"}, headers=h)
    assert r.status_code == 200 and base64.b64decode(r.json()["image_b64"]).endswith(b"fake-final")   # not the thought image
    sent = calls[-1]
    assert sent["url"].endswith("/v1beta/interactions") and sent["key"] == "g-key"
    assert sent["body"]["model"] == "gemini-nano-banana-2.1"
    assert sent["body"]["response_format"] == {"type": "image", "mime_type": "image/png", "aspect_ratio": "16:9", "image_size": "1K"}
    assert "watercolour" in sent["body"]["input"][0]["text"]
    mode["v"] = "down"
    assert c.post("/media/image", json={"prompt": "x"}, headers=h).status_code == 502
    mode["v"] = "refused"
    r = c.post("/media/image", json={"prompt": "x"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "refused"
    assert c.get("/ai/usage", headers=h).json()["images_used"] == 1          # failures were refunded
    mode["v"] = "ok"
    assert c.post("/media/image", json={"prompt": "two"}, headers=h).status_code == 200
    r = c.post("/media/image", json={"prompt": "three"}, headers=h)
    assert r.status_code == 429 and "Gink Pro" in r.json()["error"]["message"]
    assert c.post("/media/image", json={"prompt": "x"}).status_code == 401
    assert c.post("/media/image", json={"prompt": "  "}, headers=h).status_code == 422


def test_agent_creates_files(tmp_path):
    from ginkassistant.services.actions import DeviceActions, TaskStore, ToolRunner
    r = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    r.files_dir = str(tmp_path / "files")
    out = r._t_create_file("pdf", "Exam plan", "# Exam plan\n- Maths\n- Physics")
    assert out["ok"] and out["file"] == "Exam plan.pdf" and "(gink://file/Exam%20plan.pdf)" in out["message"]
    assert open(out["path"], "rb").read(5) == b"%PDF-"
    out = r._t_create_file("excel", "Budget", rows=[["Item", "Cost"], ["Rent", "150000"]])
    assert out["file"] == "Budget.xlsx"
    assert r._t_create_file("pptx", "x", "y")["ok"] is False
    assert r._t_create_file("csv", "Empty", "no table here")["ok"] is False
    async def fake_maker(prompt, aspect):
        from ginkassistant.services.file_maker import save_image
        return save_image(r.files_dir, prompt, b"\x89PNG", "image/png")
    r.image_maker = fake_maker
    img = asyncio.run(r._t_create_image("a red bicycle", "1:1"))
    assert img["ok"] and img["file"] == "a red bicycle.png"


def test_profile_prompt_photo_and_sync(tmp_path):
    from ginkassistant.services.profile import ProfileStore
    from PIL import Image
    p = ProfileStore(str(tmp_path / "a.json"))
    p.update(full_name="Ibrahim A Kargbo", nickname="Ibrahim", work="Student", instructions="Keep answers short.")
    assert p.call_name() == "Ibrahim"
    note = p.as_prompt()
    assert "Ibrahim A Kargbo" in note and "Call them Ibrahim" in note and "Student" in note and "Keep answers short." in note
    p.update(work="Astronaut")                                   # not an allowed option -> ignored
    assert p.get()["work"] == "Student"
    buf = io.BytesIO(); Image.new("RGB", (900, 600), (0, 120, 0)).save(buf, "PNG")
    url = p.set_photo(buf.getvalue())
    assert url.startswith("data:image/jpeg;base64,")
    assert Image.open(io.BytesIO(base64.b64decode(url.split(",")[1]))).size == (256, 256)   # square, small
    with pytest.raises(ValueError):
        p.set_photo(b"not an image")
    other = ProfileStore(str(tmp_path / "b.json"))
    assert other.apply_remote(p.changes_since(0)) == 1 and other.call_name() == "Ibrahim" and other.get()["photo"] == url
    assert other.apply_remote(p.changes_since(0)) == 0          # nothing newer


def test_languages():
    from ginkassistant.services import languages as L
    assert len(L.LANGUAGES) > 120 and L.normalise("fr") == "fr" and L.normalise("en") == "en-US"
    assert L.normalise("klingon") == "auto" and L.reply_note("auto") == ""
    assert "French (France)" in L.reply_note("fr") and L.label("wo").endswith("experimental")
    assert len({c for c, *_ in L.LANGUAGES}) == len(L.LANGUAGES)                 # no duplicate codes


def test_settings_profile_actions(tmp_path, monkeypatch):
    from test_main_screen import GinkAssistantApp
    import ginkassistant.app as app_mod
    from ginkassistant.services.profile import ProfileStore
    from ginkassistant.ui.settings_controller import SettingsController
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    for attr in ("data", "config"):
        monkeypatch.setattr(type(app.paths), attr, property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    app.profile = ProfileStore(str(tmp_path / "profile.json"))
    toasts, pushed, changed = [], [], []

    class Web:
        async def settings_toast(self, t, kind=""): toasts.append((t, kind))
        async def set_settings_state(self, st): pushed.append(st)
        async def set_appearance(self, *a): pass
        async def set_keyboard_prefs(self, p): self.__dict__.setdefault('kb', []).append(p)
        async def set_voice_config(self, c): self.__dict__.setdefault('vc', []).append(c)

    class Brain:
        preferred_model = "m"; memory_provider = None; reply_language_note = None
    brain = Brain()
    sc = SettingsController(app, Web(), brain, {"value": "Female (Jenny)"}, type("A", (), {"voice_key": ""})(),
                            email="ib@x.co", display_name="Ib", models_fn=lambda: [], push_models=None, open_pro=None,
                            on_log_out=None, refresh_sidebar=None, clear_all_chats=None, brief_now=None,
                            sync_fn=None, open_url=None)
    sc.on_profile_change = lambda: changed.append(1)
    async def go():
        await sc.on_setting("nickname", "Ibra")
        await sc.on_setting("reply_language", "fr")
        await sc.on_action("save_instructions", "Use simple words.")
        await sc.on_action("set_photo", "data:text/html;base64,PGI+")            # not a photo
    asyncio.run(go())
    assert app.profile.call_name() == "Ibra" and changed
    note = brain.memory_provider() + brain.reply_language_note()
    assert "Call them Ibra" in note and "Use simple words." in note and "French (France)" in note
    assert app.task_runner.profile_note() and toasts[-1][1] == "err"
    assert pushed[-1]["values"]["reply_language"] == "fr" and pushed[-1]["values"]["nickname"] == "Ibra"
