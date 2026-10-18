"""'A newer Gink is out': version comparison, the right installer per device, daily checks, Later, server endpoint."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import httpx, pytest
from ginkassistant.services import updates

ASSETS = {n: "https://dl.example.com/" + n for n in ("Gink-mac-arm64.dmg", "Gink-mac-x86_64.dmg", "Gink-windows-x64.msi",
                                                   "Gink-linux-amd64.deb", "Gink-android.apk")}


def test_version_comparison():
    vt = updates.version_tuple
    assert vt("v0.10.0") > vt("0.9.9") and vt("v1.0") == vt("1.0.0") and vt("0.2.0") > vt("0.1.0") and vt("v0.1.0") == vt("0.1.0")
    assert vt("0.2.0-beta") == (0, 2, 0)


@pytest.mark.parametrize("plat, machine, android, expect", [
    ("darwin", "arm64", False, "Gink-mac-arm64.dmg"), ("darwin", "x86_64", False, "Gink-mac-x86_64.dmg"),
    ("win32", "AMD64", False, "Gink-windows-x64.msi"), ("linux", "x86_64", False, "Gink-linux-amd64.deb"),
    ("linux", "aarch64", True, "Gink-android.apk")])
def test_the_right_installer_for_each_device(monkeypatch, plat, machine, android, expect):
    from ginkassistant.services import platform_utils
    monkeypatch.setattr(updates.sys, "platform", plat); monkeypatch.setattr(updates.platform, "machine", lambda: machine)
    monkeypatch.setattr(updates.platform, "system", lambda: {"darwin": "Darwin", "win32": "Windows"}.get(plat, "Linux"))
    monkeypatch.setattr(platform_utils, "is_android", lambda: android)
    assert updates.asset_name() == expect


def test_no_installer_offered_on_iphone(monkeypatch):
    from ginkassistant.services import platform_utils
    monkeypatch.setattr(platform_utils, "is_android", lambda: False)
    monkeypatch.setattr(updates.sys, "platform", "ios")
    assert updates.asset_name() is None


class FakeHttp:
    def __init__(self, version): self.version, self.calls = version, 0
    async def get(self, url):
        self.calls += 1
        return httpx.Response(200, json={"version": self.version, "page": "https://example.com/rel", "assets": ASSETS})


def test_daily_check_offer_and_later(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "asset_name", lambda: "Gink-windows-x64.msi")
    state, http = str(tmp_path / "u.json"), FakeHttp("v0.2.0")
    offer = asyncio.run(updates.check("https://srv", "0.1.0", state, http=http, now=1000))
    assert offer == {"version": "v0.2.0", "url": ASSETS["Gink-windows-x64.msi"]} and http.calls == 1
    asyncio.run(updates.check("https://srv", "0.1.0", state, http=http, now=1000 + 3600))
    assert http.calls == 1                                                      # not again within a day
    updates.dismiss(state, "v0.2.0")
    assert asyncio.run(updates.check("https://srv", "0.1.0", state, http=http, now=1000 + 7200)) is None      # Later
    http.version = "v0.3.0"
    assert asyncio.run(updates.check("https://srv", "0.1.0", state, http=http, now=1000 + 90000))["version"] == "v0.3.0"
    assert asyncio.run(updates.check("https://srv", "0.3.0", state, http=http, now=1000 + 90001)) is None    # up to date


def test_offline_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "asset_name", lambda: "Gink-linux-amd64.deb")
    class Offline:
        async def get(self, url): raise httpx.ConnectError("offline")
    assert asyncio.run(updates.check("https://srv", "0.1.0", str(tmp_path / "u.json"), http=Offline())) is None


def test_server_endpoint_reports_the_latest_release(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "v.db"))
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"tag_name": "v0.2.0", "html_url": "https://github.com/x/y/releases/tag/v0.2.0",
                                         "published_at": "2026-10-20T10:00:00Z",
                                         "assets": [{"name": n, "browser_download_url": u} for n, u in ASSETS.items()]})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._release_cache.update(data={"version": None}, at=0.0)
    c = TestClient(b.app)
    j = c.get("/app/version").json()
    assert j["version"] == "v0.2.0" and j["assets"]["Gink-android.apk"] == ASSETS["Gink-android.apk"]
    c.get("/app/version")
    assert len(calls) == 1 and "releases/latest" in calls[0]                    # cached for an hour


def test_the_notice_is_on_the_chat_page():
    from ginkassistant.ui import web_chat_view as w
    h = w._build_page_html("Hi", "")
    assert 'id="update-bar"' in h and "function showUpdate" in h and "ginkEmit('update_get')" in h
