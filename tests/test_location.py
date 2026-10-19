"""Settings -> Location: city, approximate location, and the 'Use location in answers' switch."""
import asyncio, os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest
from ginkassistant.services import prefs
from ginkassistant.services.live_info import LiveInfo


@pytest.fixture
def app(tmp_path, monkeypatch):
    a = types.SimpleNamespace()
    monkeypatch.setattr(prefs, "config_dir", lambda _app: tmp_path)
    return a


def test_city_respects_the_switch(app):
    prefs.save(app, city="Dakar")
    assert prefs.city(app) == "Dakar"
    prefs.save(app, use_location=False)
    assert prefs.city(app) == ""


def test_no_estimated_location_when_off():
    live = LiveInfo(); calls = []
    async def fake_get(url, **k):
        calls.append(url); return {"success": True, "city": "Dakar", "country": "Senegal", "latitude": 14.7, "longitude": -17.4}
    live._get = fake_get
    live.allowed_fn = lambda: False
    assert asyncio.run(live.where(None)) is None and calls == []          # nothing looked up
    live.allowed_fn = lambda: True
    place = asyncio.run(live.where(None))
    assert place["name"] == "Dakar" and place["source"] == "approximate" and len(calls) == 1


def test_settings_location_text_and_detect(app, monkeypatch):
    from ginkassistant.ui.settings_controller import SettingsController
    live = LiveInfo()
    async def fake_get(url, **k):
        return {"success": True, "city": "Thiès", "country": "Senegal", "latitude": 14.8, "longitude": -16.9}
    live._get = fake_get
    app.task_runner = types.SimpleNamespace(live=live)
    ctl = SettingsController.__new__(SettingsController); ctl.app = app
    toasts = []
    async def toast(t): toasts.append(t)
    async def push(): pass
    ctl.web = types.SimpleNamespace(settings_toast=toast); ctl.push = push
    assert ctl._location_text().startswith("Not set")
    asyncio.run(ctl._a_detect_location(None))
    assert prefs.city(app) == "Thiès" and "Thiès, Senegal" in toasts[-1]
    assert ctl._location_text() == "Thiès \u00b7 set by you"
    prefs.save(app, city="")
    assert ctl._location_text() == "Thiès, Senegal \u00b7 estimated from your IP address"
    prefs.save(app, use_location=False)
    assert ctl._location_text().startswith("Off")


def test_location_panel_has_the_new_rows():
    from ginkassistant.ui import web_chat_view as w
    h = w._build_page_html("Hi", "")
    for bit in ("'Your area'", "detect_location", "use_location", "About this location"):
        assert bit in h
    assert h.count("{id: 'location'") == 1
