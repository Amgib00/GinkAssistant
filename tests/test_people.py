"""People (0.1.154): like Photos on iPhone -- faces in photos shared with Gink are found and grouped ON THE DEVICE
(the face model runs in the page, in the apps and the web app), so people can be named and their photos found.
Gink's server only SENDS the model files; nothing anywhere receives a face. Off until turned on; never in a
healthcare workspace, a temporary chat, or for Live camera frames."""
import asyncio
import functools
import http.server
import json
import os
import shutil
import sys
import threading
import types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
FACES = os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "faces")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---------------------------------------------------------------- the server only sends the model
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "p.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    return b, TestClient(b.app)


def test_model_files_are_served_to_any_page(client):
    b, c = client
    r = c.get("/app/faces/face-api.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"] and r.text.startswith("/*")
    assert r.headers["access-control-allow-origin"] == "*" and "immutable" in r.headers["cache-control"]
    m = c.get("/app/faces/models/face_recognition_model-weights_manifest.json")
    assert m.status_code == 200 and m.json()[0]["paths"] == ["face_recognition_model.bin"]
    w = c.get("/app/faces/models/tiny_face_detector_model.bin")
    assert w.status_code == 200 and w.headers["content-type"] == "application/octet-stream" and len(w.content) > 100_000
    for bad in ("/app/faces/models/evil.js", "/app/faces/..%2Fgenie.html", "/app/faces/models/..%2F..%2Fgenie.html",
                "/app/faces/secret.txt"):
        assert c.get(bad).status_code == 404, bad
    assert "MIT License" in c.get("/app/faces/LICENSE").text


def test_nothing_on_the_server_takes_faces(client):
    b, c = client
    for route in b.app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", set()) or set()
        if "face" in path.lower() or "people" in path.lower():
            assert methods <= {"GET", "HEAD"}, (path, methods)                 # downloads only, never uploads
    assert os.path.getsize(os.path.join(FACES, "models", "face_recognition_model.bin")) > 6_000_000


# ---------------------------------------------------------------- the apps and the web app
def test_page_has_people(tmp_path):
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    for must in ("window.openPeople = function (name)", "window.peopleAuto = function (data, from)", "function peopleLook(item)",
                 "function peopleAllowed() { return PEOPLE.on && !CARE_MODE; }",
                 "peopleIntercept(text)", "indexedDB.open('gink-people', 1)", "ginkEmit('people_save'", "ginkEmit('people_pick', true)",
                 "PEOPLE_MATCH = 0.5", "PEOPLE_MAX = 400", "Turn on People"):
        assert must in html, must
    # 0.1.156: no People button -- it works by itself (asking opens it; the first shared photo brings a one-time offer)
    assert 'data-nav="people"' not in html and 'data-rail="people"' not in html
    for must in ("window.peoplePending = function (list)", "localStorage.getItem('gink-people-offered')",
                 "run: function () { ginkEmit('setting', {key: 'people_on', value: true}); }",
                 "if (PEOPLE_OPEN.test(String(text || '').trim())) { window.openPeople(); return true; }"):
        assert must in html, must


def test_apps_keep_people_on_the_device():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    for must in ('people_path = data_dir(app) / "people.json"', 'if kind == "people_save" and isinstance(value, str):',
                 "await web_chat.people_auto(data_url)", 'not str(a.name or "").startswith("live-")',
                 'if photos and not brain.history.is_temporary(current_session["id"]):', "if await people_on():",
                 "await web_chat.people_pending(photos)",
                 'return bool(prefs.load(app).get("people_on")) and not await in_healthcare_workspace()',
                 "await web_chat.people_set_on(False)      # never in a healthcare workspace", 'app.state.base_url.rstrip("/") + "/app/faces/"'):
        assert must in main, must
    bridge = read("webapp", "bridge.js")
    for must in ('peopleConfigure({ base: "/app/faces/", native: false })', "!/^live-/.test(a.name || \"\")",
                 "if (photos.length && !s.temporary && !W.care) {", "else if (typeof peoplePending === \"function\") peoplePending(photos);",
                 'peopleSetOn(!!W.prefs.people_on && !on)', 'name === "people_delete"'):
        assert must in bridge, must
    page = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "key: 'people_on'" in page and "action: 'people_delete'" in page and "Off in healthcare workspaces" in page


def test_settings_turn_people_on_and_delete(tmp_path, monkeypatch):
    from ginkassistant.services import prefs
    from ginkassistant.ui.settings_controller import SettingsController
    monkeypatch.setattr(prefs, "config_dir", lambda _app: tmp_path)
    app = types.SimpleNamespace()
    ctl = SettingsController.__new__(SettingsController)
    seen = []

    async def push(*a, **k): pass
    async def toast(text, kind=""): seen.append(text)
    async def changed(on): seen.append(("on", on))
    async def delete(): seen.append("deleted")
    ctl.app, ctl.web, ctl.push, ctl.apply_all = app, types.SimpleNamespace(settings_toast=toast), push, lambda: None
    ctl.on_people_change, ctl.on_people_delete = changed, delete
    assert prefs.load(app)["people_on"] is False                                       # off until turned on
    asyncio.run(ctl.on_setting("people_on", True))
    assert prefs.load(app)["people_on"] is True and ("on", True) in seen
    asyncio.run(ctl._a_people_delete(None))
    assert "deleted" in seen and "People data deleted from this device." in seen


# ---------------------------------------------------------------- the real model, in a real browser
def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


@pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")
def test_people_runs_and_groups_in_a_browser(tmp_path):
    from ginkassistant.ui.web_chat_view import _build_page_html
    (tmp_path / "p.html").write_text(_build_page_html("Hi", "x"), encoding="utf-8")
    shutil.copytree(FACES, tmp_path / "faces")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    import base64
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (480, 360), (200, 210, 220)); ImageDraw.Draw(im).ellipse((160, 80, 320, 280), fill=(230, 190, 160))
    buf = io.BytesIO(); im.save(buf, "JPEG"); photo = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    try:
        with _browser()() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"no Chromium here ({type(exc).__name__})")
            page = browser.new_page()
            page.goto(base + "/p.html")
            page.evaluate("() => { window.__ev = []; window.ginkEmit = function (t, v) { window.__ev.push([t, v]); }; }")
            page.evaluate("(b) => { peopleSetOn(true); peopleConfigure({base: b + '/faces/', native: true}); openPeople(); }", base)
            page.evaluate("(d) => peopleAddPhotos([{name: 'x.jpg', data: d}])", photo)
            page.wait_for_function("() => /Done|couldn/.test((document.querySelector('#people-back .pp-progress') || {}).textContent || '')",
                                   timeout=180000)
            assert page.evaluate("() => document.querySelector('#people-back .pp-progress').textContent") == "Done: 0 faces in 1 photo."
            assert page.evaluate("() => [faceapi.nets.tinyFaceDetector.isLoaded, faceapi.nets.faceLandmark68Net.isLoaded, "
                                 "faceapi.nets.faceRecognitionNet.isLoaded]") == [True, True, True]
            size = page.evaluate("""async (d) => { const im = new Image(); im.src = d; await im.decode();
                const c = document.createElement('canvas'); c.width = c.height = 150; c.getContext('2d').drawImage(im, 0, 0, 150, 150);
                return (await faceapi.computeFaceDescriptor(c)).length; }""", photo)
            assert size == 128                                                         # the face "fingerprint" network runs here
            groups = page.evaluate("""() => {
                const r = (s) => { let x = s; return () => (x = (x * 9301 + 49297) % 233280) / 233280; };
                const ra = r(1), rb = r(7), A = Array.from({length: 128}, () => ra() * .2), B = Array.from({length: 128}, () => rb() * .2 + .1);
                const jit = (v, rnd) => v.map((x) => x + (rnd() - .5) * .02), j = r(3), out = [];
                for (let i = 0; i < 4; i++) out.push(peopleAssign({id: 'a' + i, photo: 'x', d: jit(A, j)}).id);
                for (let i = 0; i < 3; i++) out.push(peopleAssign({id: 'b' + i, photo: 'x', d: jit(B, j)}).id);
                return out; }""")
            assert len(set(groups[:4])) == 1 and len(set(groups[4:])) == 1 and groups[0] != groups[4]
            # naming saves on the device (the app's file) -- and "photos of Awa" opens People instead of asking the AI
            page.evaluate("""() => { const p = Object.values(PEOPLE.people)[0];
                PEOPLE.faces.a0 = {id: 'a0', photo: 'ph', crop: '', d: p.c, person: p.id}; PEOPLE.photos.ph = {id: 'ph', thumb: '', added: 1};
                openPeople(); PEOPLE.view = 'person'; PEOPLE.person = p.id; window.peopleLoad({photos: PEOPLE.photos, faces: PEOPLE.faces,
                people: PEOPLE.people}); }""")
            page.evaluate("() => { const p = Object.values(PEOPLE.people)[0]; p.name = 'Awa'; }")
            assert page.evaluate("() => peopleIntercept('show me photos of Awa')") is True
            assert page.evaluate("() => peopleIntercept('show me photos of the beach')") is False
            page.evaluate("() => { const i = document.querySelector('.pp-name-in'); i.value = 'Awa Ndiaye'; i.dispatchEvent(new Event('change')); }")
            page.wait_for_function("() => window.__ev.some(e => e[0] === 'people_save')", timeout=10000)
            saved = json.loads(page.evaluate("() => window.__ev.filter(e => e[0] === 'people_save').pop()[1]"))
            assert any(p["name"] == "Awa Ndiaye" for p in saved["people"].values())
            # a healthcare workspace: nothing is looked at or kept
            page.evaluate("() => { setCareMode(true); window.__ev = []; PEOPLE.queue = []; }")
            page.evaluate("(d) => peopleAuto(d, 'chat')", photo)
            assert page.evaluate("() => PEOPLE.queue.length + (PEOPLE.busy ? 1 : 0)") == 0
            assert "Off in healthcare workspaces" in page.evaluate("() => { openPeople(); return document.querySelector('#people-back').textContent; }")
            browser.close()
    finally:
        server.shutdown()
