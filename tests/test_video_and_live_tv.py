"""Video search (API / YouTube page / DuckDuckGo), video cards, viewer, Live TV."""
import asyncio, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import toga

YT_DATA = {"contents": {"twoColumnSearchResultsRenderer": {"primaryContents": {"sectionListRenderer": {"contents": [
    {"itemSectionRenderer": {"contents": [
        {"adSlotRenderer": {}},
        {"videoRenderer": {"videoId": "AAAAAAAAAAA", "title": {"runs": [{"text": "How to Change a Car Tyre"}]},
                           "ownerText": {"runs": [{"text": "AutoFix"}]}, "lengthText": {"simpleText": "8:42"},
                           "viewCountText": {"simpleText": "1,203,442 views"}}},
        {"videoRenderer": {"videoId": "BBBBBBBBBBB", "title": {"runs": [{"text": "Spare tyre "}, {"text": "in 5 minutes"}]},
                           "ownerText": {"runs": [{"text": "DIY Dad"}]}, "lengthText": {"simpleText": "5:10"}}},
    ]}}]}}}}}


def page_handler(request):
    url = str(request.url)
    if "youtube.com/results" in url:
        return httpx.Response(200, text="<html><script>var ytInitialData = " + json.dumps(YT_DATA) + ";</script></html>")
    if "googleapis.com/youtube/v3/search" in url:
        return httpx.Response(200, json={"items": [{"id": {"videoId": "CCCCCCCCCCC"}, "snippet": {
            "title": "Jollof Rice &amp; Chicken", "channelTitle": "Chef Ama", "liveBroadcastContent": "none"}}]})
    if "googleapis.com/youtube/v3/videos" in url:
        return httpx.Response(200, json={"items": [{"id": "CCCCCCCCCCC", "contentDetails": {"duration": "PT1H2M5S"},
                                                    "statistics": {"viewCount": "2540000"}}]})
    return httpx.Response(404)


def vs(api_key="", handler=page_handler):
    from ginkassistant.services.video_search import VideoSearch
    return VideoSearch(api_key=api_key, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_search_sources_and_fallbacks(monkeypatch):
    from ginkassistant.services import video_search as m
    s = vs()
    found = asyncio.run(s.search("change a tyre", n=3))
    assert [v["id"] for v in found] == ["AAAAAAAAAAA", "BBBBBBBBBBB"] and s.last_source == "youtube"
    assert found[0]["duration"] == "8:42" and found[1]["title"] == "Spare tyre in 5 minutes"
    api = vs(api_key="KEY")
    v = asyncio.run(api.search("jollof rice"))[0]
    assert api.last_source == "youtube-api" and v["title"] == "Jollof Rice & Chicken"
    assert v["duration"] == "1:02:05" and v["views"] == "2.5M views"
    # YouTube page fails -> DuckDuckGo
    broken = vs(handler=lambda r: httpx.Response(500))
    async def fake_ddg(self, q, n, live):
        return [m._item("DDDDDDDDDDD", "From DDG", "Someone", "3:00", "", "duckduckgo")]
    monkeypatch.setattr(m.VideoSearch, "_ddg", fake_ddg)
    assert asyncio.run(broken.search("x"))[0]["id"] == "DDDDDDDDDDD" and broken.last_source == "duckduckgo"
    async def no_ddg(self, q, n, live): raise RuntimeError("rate limited")
    monkeypatch.setattr(m.VideoSearch, "_ddg", no_ddg)
    assert asyncio.run(broken.search("x")) == []


def test_helpers():
    from ginkassistant.services.video_search import video_id_from_url, video_markdown, _item
    assert video_id_from_url("https://youtu.be/AAAAAAAAAAA?t=3") == "AAAAAAAAAAA"
    assert video_id_from_url("https://www.youtube.com/shorts/BBBBBBBBBBB") == "BBBBBBBBBBB"
    md = video_markdown([_item("AAAAAAAAAAA", "Fix [it] fast", "AutoFix", "8:42", "1M views")])
    assert md == "[\u25b6 Fix (it) fast \u2014 AutoFix \u00b7 8:42 \u00b7 1M views](https://www.youtube.com/watch?v=AAAAAAAAAAA)"


def test_agent_finds_videos(tmp_path):
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    runner.videos = vs()
    r = asyncio.run(TaskAgent(runner, api_key="").run("show me a video on how to change a tyre"))
    assert not r.used_ai and "watch?v=AAAAAAAAAAA" in r.text and r.text.count("[\u25b6 ") == 2


def test_live_tv_channels(tmp_path, monkeypatch):
    from ginkassistant.ui import toga_live_tv as tv
    assert tv.channel_url("@RTS1Senegal") == "https://www.youtube.com/@RTS1Senegal/live"
    assert tv.channel_url("https://www.youtube.com/@dwnews") == "https://www.youtube.com/@dwnews/live"
    assert tv.channel_url("https://youtu.be/AAAAAAAAAAA") == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert tv.channel_url("hello") is None
    app = toga.App("t", "org.t")
    monkeypatch.setattr(type(app.paths), "config", property(lambda self: tmp_path), raising=False)
    assert tv.match_channel(app, "al jazeera") == "Al Jazeera English"
    assert tv.match_channel(app, "france 24") == "France 24 English"
    screen = tv.build_live_tv_view(app, on_back=lambda: None, initial_channel="dw")
    web = [c for c in screen.children if isinstance(c, toga.WebView)][0]
    assert web.url == "https://www.youtube.com/@dwnews/live"
    from ginkassistant.services import prefs
    prefs.save(app, live_channels={"RTS": "https://www.youtube.com/@RTS1Senegal/live"})
    assert tv.match_channel(app, "rts") == "RTS"


def test_viewer_beside_chat(tmp_path):
    from ginkassistant.ui.viewer import Viewer
    app = toga.App("t", "org.t")
    app.main_window = toga.MainWindow()
    chat = toga.WebView()
    host = toga.Box(children=[chat])
    app.main_window.content = host
    opened = []
    v = Viewer(app, host, open_external=opened.append)
    v.show("https://www.youtube.com/watch?v=AAAAAAAAAAA", "How to change a tyre")
    assert v.is_open and host.children[0] is chat and len(host.children) == 3       # chat | divider | viewer
    assert v.web.url.endswith("AAAAAAAAAAA") and v.title.text == "How to change a tyre"
    v.show("https://www.youtube.com/watch?v=BBBBBBBBBBB", "Next")                     # reuses the panel
    assert len(host.children) == 3 and v.web.url.endswith("BBBBBBBBBBB")
    v._external(None)
    assert opened == ["https://www.youtube.com/watch?v=BBBBBBBBBBB"]
    v.close()
    assert not v.is_open and host.children == [chat]
