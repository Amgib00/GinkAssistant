"""Gink searches by itself when an answer needs the web; official sources first; the Sources button."""
import json
import os
import sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import httpx


def test_what_needs_a_search():
    from ginkassistant.services.backend_server import _needs_search as n
    for t in ("Who won the AFCON final?", "latest iPhone price in Senegal", "who is the president of Ghana",
              "search for cheap flights Dakar to Paris", "check orange.sn for the new plans", "what happened yesterday in Lagos"):
        assert n(t), t
    for t in ("write a poem about the news", "What's the weather in Dakar?", "explain photosynthesis", "hello", "translate this: latest news"):
        assert not n(t), t


def test_official_sources_come_first():
    from ginkassistant.services.backend_server import _rank_sources, _sources_md
    src = [{"url": "https://www.bbc.com/a", "title": "BBC"}, {"url": "https://www.who.int/b", "title": "WHO"},
           {"url": "https://www.gouv.sn/c", "title": "Gouvernement du S\u00e9n\u00e9gal"}]
    assert [s["title"] for s in _rank_sources(src)] == ["WHO", "Gouvernement du S\u00e9n\u00e9gal", "BBC"]
    md = _sources_md(src)
    assert md.index("WHO") < md.index("BBC") and "(https://www.who.int/b) \u00b7 official" in md and "bbc.com/a) \u00b7" not in md


def _server(tmp_path, monkeypatch, plan="free"):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": plan})
    return b, TestClient(b.app), sent


def test_apps_search_by_themselves_and_answer_anyway_over_the_limit(tmp_path, monkeypatch):
    b, c, sent = _server(tmp_path, monkeypatch)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    ask = lambda text, **x: c.post("/ai/openai/v1/chat/completions", headers=h,
                                   json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": text}], **x})
    assert ask("Who won the election in Ghana?").status_code == 200
    assert sent[-1]["tools"] == [{"type": "browser_search"}] and sent[-1]["model"] == b.SEARCH_MODEL
    assert "Prefer official and primary sources" in sent[-1]["messages"][0]["content"]
    ask("Who won the election in Ghana?", gink_web=False)
    assert "tools" not in sent[-1] and "gink_web" not in sent[-1]                    # turned off: no search
    ask("Explain photosynthesis")
    assert "tools" not in sent[-1]
    monkeypatch.setenv("GINK_FREE_SEARCH_DAILY", "0")                                 # today's searches used up
    assert ask("latest news in Dakar").status_code == 200 and "tools" not in sent[-1]  # answered anyway, without searching
    assert sent[-1]["model"] == "openai/gpt-oss-20b"
    b._groq_models.update(ids=set(), at=0.0)


def test_the_developer_api_decides_for_itself(tmp_path, monkeypatch):
    b, c, sent = _server(tmp_path, monkeypatch, plan="pro")
    h = {"Authorization": "Bearer " + b._token_response("dev@example.com", "D")["token"]}
    key = c.post("/account/api-keys", headers=h, json={}).json().get("key", "")
    assert key.startswith(b.API_KEY_PREFIX)
    r = c.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key},
               json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "latest news in Dakar"}]})
    assert r.status_code == 200 and "tools" not in sent[-1]                          # no automatic search for API keys
    b._groq_models.update(ids=set(), at=0.0)


def test_the_page_turns_the_list_into_a_sources_button():
    extras = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "chat_extras.py"), encoding="utf-8").read()
    assert "window.upgradeSources" in extras and "o.textContent = 'Official'" in extras
    assert "if (window.upgradeSources) upgradeSources(el);" in open(os.path.join(ROOT, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()


def test_streamed_searches_say_searching_first(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "st.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        return httpx.Response(200, text='data: {"choices":[{"index":0,"delta":{"content":"Mahama."}}]}\n\ndata: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "free"})
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    body = {"model": "openai/gpt-oss-20b", "stream": True, "messages": [{"role": "user", "content": "who is the president of Ghana"}]}
    with TestClient(b.app).stream("POST", "/ai/openai/v1/chat/completions", headers=h, json=body) as r:
        lines = [l for l in r.iter_lines() if l.startswith("data: ")]
    first = json.loads(lines[0][6:])
    assert first["gink_status"] == "searching" and first["choices"] == []     # no text: apps and web app skip it as text
    assert any("Mahama." in l for l in lines)
    worker = open(os.path.join(ROOT, "src", "ginkassistant", "services", "groq_worker.py"), encoding="utf-8").read()
    assert 'getattr(chunk, "gink_status", None)' in worker and "save_user, on_status=on_status)" in worker
    assert 'if (d.gink_status === "searching") setSpinLabel(aid' in open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    b._groq_models.update(ids=set(), at=0.0)


def test_the_apps_brain_shows_searching_and_still_answers(tmp_path):
    """Runs the real GroqBrain.ask (cloud path): a status piece first, then the answer.
    (on_status once reached the stream reader without being passed in: every app answer would have crashed.)"""
    import asyncio
    import types
    os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
    from groq.types.chat import ChatCompletionChunk
    from ginkassistant.services import groq_worker
    app = types.SimpleNamespace(paths=types.SimpleNamespace(data=tmp_path, config=tmp_path, cache=tmp_path, app=tmp_path),
                                formal_name="Gink", app_name="ginkassistant")
    brain = groq_worker.GroqBrain(app, session_id="t")
    chunk = lambda **kw: ChatCompletionChunk.model_validate({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m", **kw})
    class Stream:
        def __init__(self):
            self.items = [chunk(choices=[], gink_status="searching"),
                          chunk(choices=[{"index": 0, "delta": {"content": "Mahama."}, "finish_reason": None}])]
        def __aiter__(self): return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)
    async def create(**kw): return Stream()
    async def models_list(): return types.SimpleNamespace(data=[types.SimpleNamespace(id="openai/gpt-oss-120b")])
    brain.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)),
                                         models=types.SimpleNamespace(list=models_list))
    brain.api_key = "session-token"
    statuses, tokens = [], []
    async def on_token(t): tokens.append(t)
    reply = asyncio.run(brain.ask("who is the president of Ghana", on_token=on_token, on_status=statuses.append))
    assert reply == "Mahama." and tokens == ["Mahama."] and statuses == ["Searching the web\u2026"]


def test_developer_streams_get_no_status_piece(tmp_path, monkeypatch):
    """Developers' code often reads choices[0] of every piece: the status piece is only for Gink's own clients."""
    b, c, sent = _server(tmp_path, monkeypatch, plan="pro")
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        return httpx.Response(200, text='data: {"choices":[{"index":0,"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
                              headers={"content-type": "text/event-stream"})
    real = httpx.AsyncClient.__mro__[1]
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    h = {"Authorization": "Bearer " + b._token_response("dev2@example.com", "D")["token"]}
    key = c.post("/account/api-keys", headers=h, json={}).json()["key"]
    with c.stream("POST", "/v1/chat/completions", headers={"Authorization": "Bearer " + key},
                  json={"model": "gink-search", "stream": True, "messages": [{"role": "user", "content": "latest news"}]}) as r:
        pieces = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: {")]
    assert pieces and all(p.get("choices") for p in pieces) and not any("gink_status" in p for p in pieces)
    b._groq_models.update(ids=set(), at=0.0)
