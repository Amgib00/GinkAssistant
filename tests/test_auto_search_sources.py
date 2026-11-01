"""Gink searches by itself when an answer needs the web; official sources first; the Sources button."""
import json, os, sys
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
