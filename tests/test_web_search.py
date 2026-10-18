"""Web search: GPT-OSS + Groq's browser_search; clean answers with sources; daily allowance."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest

ANSWER = "Senegal's new bridge opened on 12 October 2026 【1†L3-L5】. It links Dakar and Thiès 【2†L1-L2】."
TOOLS_RAN = [{"type": "search", "search_results": {"results": [
    {"title": "Bridge opens", "url": "https://news.example.com/bridge", "content": "..."},
    {"title": "Dakar–Thiès link", "url": "https://example.org/link", "content": "..."}]}}]


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "w.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        body = json.loads(request.content); sent.append(body)
        if body.get("stream"):
            pieces = ["Senegal's new bridge opened ", "on 12 October 2026 【1", "†L3-L5】. It links ", "Dakar and Thiès 【2†L1-L2】."]
            frames = [{"choices": [{"index": 0, "delta": {"role": "assistant"}}]}]
            frames += [{"choices": [{"index": 0, "delta": {"content": p}}]} for p in pieces]
            frames += [{"choices": [{"index": 0, "delta": {"executed_tools": TOOLS_RAN}}]},
                       {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
            sse = "".join("data: " + json.dumps(f) + "\n\n" for f in frames) + "data: [DONE]\n\n"
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": ANSWER, "executed_tools": TOOLS_RAN}}]})
    real = httpx.AsyncClient

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "free"})
    c = TestClient(b.app)
    return b, c, {"Authorization": "Bearer " + b._token_response("u@x.co", "U")["token"]}, sent


def ask(c, h, **body):
    return c.post("/ai/openai/v1/chat/completions", headers=h, json={"messages": [{"role": "user", "content": "bridge news"}], **body})


def test_search_requests_use_browser_search(srv):
    b, c, h, sent = srv
    my_tools = [{"type": "function", "function": {"name": "set_alarm", "parameters": {}}}]
    for request in ({"model": "gink-search"}, {"model": "gink-crystal", "gink_web": True, "tools": my_tools}):
        assert ask(c, h, **request).status_code == 200
        s = sent[-1]
        assert s["model"] == "openai/gpt-oss-120b" and s["tools"] == [{"type": "browser_search"}]
        assert s["tool_choice"] == "required" and s["reasoning_effort"] == "low" and "gink_web" not in s
    assert ask(c, h, model="gink-crystal").status_code == 200 and "tools" not in sent[-1]     # normal chat: no search


def test_answers_are_clean_and_list_their_sources(srv):
    b, c, h, sent = srv
    text = ask(c, h, model="gink-search").json()["choices"][0]["message"]["content"]
    assert "【" not in text and "on 12 October 2026. It links Dakar and Thiès." in text
    assert "**Sources**" in text and "[Bridge opens](https://news.example.com/bridge)" in text


def test_streamed_answers_are_clean_even_when_a_mark_is_split(srv):
    b, c, h, sent = srv
    with c.stream("POST", "/ai/openai/v1/chat/completions", headers=h,
                  json={"model": "gink-search", "stream": True, "messages": [{"role": "user", "content": "bridge news"}]}) as r:
        frames = [l[5:].strip() for l in r.iter_lines() if l.startswith("data:")]
    assert frames[-1] == "[DONE]"
    chunks = [json.loads(f) for f in frames[:-1]]
    text = "".join(ch["choices"][0]["delta"].get("content") or "" for ch in chunks)
    assert "【" not in text and "†" not in text and "on 12 October 2026. It links Dakar and Thiès." in text
    assert text.endswith("- [Dakar–Thiès link](https://example.org/link)") and "**Sources**" in text
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_daily_search_allowance(srv, monkeypatch):
    b, c, h, sent = srv
    monkeypatch.setenv("GINK_FREE_SEARCH_DAILY", "2")
    assert [ask(c, h, model="gink-search").status_code for _ in range(2)] == [200, 200]
    r = ask(c, h, model="gink-search")
    assert r.status_code == 429 and "web searches" in r.json()["error"]["message"]
    assert ask(c, h, model="gink-crystal").status_code == 200                                   # chat still works


def test_web_search_endpoint_for_the_apps(srv):
    b, c, h, sent = srv
    assert c.post("/web/search", json={"query": "bridge"}).status_code == 401
    j = c.post("/web/search", headers=h, json={"query": "Senegal bridge"}).json()
    assert "【" not in j["answer"] and j["sources"][0]["url"] == "https://news.example.com/bridge"
    assert sent[-1]["tools"] == [{"type": "browser_search"}]


def test_gink_search_is_in_the_model_list(srv):
    b, c, h, sent = srv
    ids = [m["id"] for m in c.get("/ai/openai/v1/models", headers=h).json()["data"]]
    assert "gink-search" in ids


def test_desktop_tool_asks_the_server_first_then_falls_back():
    from ginkassistant.services.actions.tools import ToolRunner
    runner = ToolRunner.__new__(ToolRunner); runner._http = None
    async def server(q): return {"ok": True, "answer": "From the web: " + q, "sources": []}
    runner.web_researcher = server
    assert asyncio.run(runner._t_web_search("bridge"))["answer"] == "From the web: bridge"
    async def unavailable(q): return None
    runner.web_researcher = unavailable
    calls = []
    class FakeClient:
        async def get(self, url, params=None):
            calls.append(url); return httpx.Response(200, json={}, request=httpx.Request("GET", url))
        async def aclose(self): pass
    runner._http = FakeClient()
    asyncio.run(runner._t_web_search("bridge"))
    assert any("duckduckgo" in u for u in calls)                                                 # the old lookup still works
