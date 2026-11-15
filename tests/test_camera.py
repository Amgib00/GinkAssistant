"""Camera across the suite: Camera opens Live (no modes to choose); where Live can't run, the platform takes the photo
-- the system camera in the apps, the browser's on the web. What Gink does with a photo is the server's job
(services/vision_rules.py: tests/test_photos_agents_care.py)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_the_camera_is_automatic_and_careful():
    """No modes to choose: Camera opens Live, and Gink works out what the picture needs -- carefully with health."""
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert 'data-act="camera"' in html and "function openCamera() { openLive(); }" in html
    assert "cam-sheet" not in html and "CAM_MODES" not in html and "live-modes" not in html     # no mode buttons
    assert "CAM_AUTO" not in html and "CAM_CARE" not in html            # the rules live on the server, not in your chat
    assert "patient records" in html and "patient details" in html                            # said in Live itself
    assert "ginkEmit('camera', 'auto')" in html                                               # the photo fallback


def test_apps_take_the_photo_with_the_system_camera():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "async def take_photo(mode" in main and "await camera.take_photo()" in main and 'kind == "camera"' in main
    assert "camera.request_permission()" in main and "return await pick_files()" in main        # no camera: choose a photo
    project = read("pyproject.toml")
    assert project.count('camera = "Gink uses the camera when you choose Camera') == 2            # macOS + iOS
    assert '"android.permission.CAMERA"' in project


def test_web_app_camera_and_permission(tmp_path, monkeypatch):
    bridge = read("webapp", "bridge.js")
    assert "camera: function ()" in bridge and "getUserMedia" in bridge and 'setAttribute("capture", "environment")' in bridge
    assert "Take photo" in bridge and "t.stop()" in bridge                                      # the camera is switched off after
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "c.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    r = TestClient(b.app).get("/app")
    assert "camera=(self)" in r.headers.get("permissions-policy", "")
