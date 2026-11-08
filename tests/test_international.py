"""Gink is for everyone, everywhere: examples aren't about one country, and answers fit the user's own country
automatically -- from the device's time zone and region (no location lookup)."""
import os, re, sys, types
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
from test_genie import SCRIPT, SEEN      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")
USER_FACING = ["src/ginkassistant/ui/settings_page.py", "src/ginkassistant/ui/media_studio_screen.py",
               "src/ginkassistant/ui/login_screen.py", "src/ginkassistant/ui/settings_screen.py",
               "src/ginkassistant/services/web_app/auth.html", "src/ginkassistant/services/web_app/console.html",
               "src/ginkassistant/services/web_app/agents.html", "cli/README.md", "cli/gink/__init__.py",
               "sdk/js/README.md", "sdk/js/index.js"]


def test_no_single_country_examples():
    for f in USER_FACING:
        text = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert not re.search(r"Senegal|Dakar|\+221|H\u00f4pital Principal", text), f


def test_the_server_reads_the_device_place():
    from ginkassistant.services import backend_server as b
    req = types.SimpleNamespace(headers={"x-gink-tz": "America/Sao_Paulo", "x-gink-locale": "pt_BR"})
    assert b._client_place_from(req) == {"tz": "America/Sao_Paulo", "city": "Sao Paulo", "language": "pt", "region": "BR"}
    bad = types.SimpleNamespace(headers={"x-gink-tz": "../../etc/passwd", "x-gink-locale": "<script>"})
    assert b._client_place_from(bad) == {}
    note = b._place_note({"tz": "Asia/Tokyo", "region": "JP"})
    assert "Asia/Tokyo" in note and "region JP" in note and "currency" in note


def test_chat_fits_the_users_country(genie_srv, monkeypatch):
    b, c, h = genie_srv
    asked = []
    async def facts(text):
        asked.append(text)
        return ["Weather in Nairobi: 22°C"] if "Nairobi" in text else []
    monkeypatch.setattr(b, "_live_facts", facts)
    SCRIPT[:] = [{"content": "It's 22°C."}]
    r = c.post("/ai/openai/v1/chat/completions", headers=dict(h, **{"X-Gink-TZ": "Africa/Nairobi", "X-Gink-Locale": "en_KE"}),
               json={"messages": [{"role": "user", "content": "What's the weather like?"}]})
    assert r.status_code == 200
    system = " ".join(m["content"] for m in SEEN[-1]["messages"] if m["role"] == "system")
    assert "Africa/Nairobi" in system and "region KE" in system and "22°C" in system
    assert asked[-1].endswith("in Nairobi")                                        # no place said: where they are


def test_agents_and_genie_get_the_place_too(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "t")["key"]
    SCRIPT[:] = [{"content": "Done."}]
    c.post("/v1/interactions", headers={"Authorization": f"Bearer {key}", "X-Gink-TZ": "Europe/Berlin", "X-Gink-Locale": "de_DE"},
           json={"input": "Find solar news in my country"})
    assert "Europe/Berlin" in " ".join(m["content"] for m in SEEN[-1]["messages"] if m["role"] == "system")
    SCRIPT[:] = [{"content": "Hi."}]
    c.post("/genie/projects", headers=dict(h, **{"X-Gink-TZ": "Asia/Manila"}), json={"prompt": "Make a page"})
    assert "Asia/Manila" in SEEN[-1]["messages"][0]["content"]


def test_apps_sdks_and_cli_send_it(monkeypatch):
    from ginkassistant.services import device_region, api_client
    monkeypatch.setattr(device_region, "timezone_name", lambda: "America/Lima")
    monkeypatch.setattr(device_region, "region_locale", lambda: "es_PE")
    device_region._cache.clear()
    assert api_client.device_headers()["X-Gink-TZ"] == "America/Lima" and api_client.device_headers()["X-Gink-Locale"] == "es_PE"
    device_region._cache.clear()
    from gink import client as sdk
    monkeypatch.setenv("TZ", "Australia/Sydney")
    assert sdk.place_headers()["X-Gink-TZ"] == "Australia/Sydney"
    js = open(os.path.join(ROOT, "sdk", "js", "index.js"), encoding="utf-8").read()
    assert "...placeHeaders()" in js
    for page in ("webapp/bridge.js", "src/ginkassistant/services/web_app/genie.html", "src/ginkassistant/services/web_app/console.html"):
        assert 'h["X-Gink-TZ"] = tz' in open(os.path.join(ROOT, page), encoding="utf-8").read(), page


def test_weather_skill_uses_the_devices_city(monkeypatch):
    import asyncio
    from ginkassistant.services import skills, device_region
    got = []
    async def weather(city): got.append(city); return "ok"
    monkeypatch.setattr(skills, "_get_weather", weather)
    monkeypatch.setattr(device_region, "timezone_name", lambda: "America/New_York")
    asyncio.run(skills.try_skill("what's the weather"))
    assert got == ["New York"]
    monkeypatch.setattr(device_region, "timezone_name", lambda: "")
    assert "Which city" in asyncio.run(skills.try_skill("weather"))
