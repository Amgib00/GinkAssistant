"""When the AI provider refuses: the app says why; the server logs why (never the messages)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


def _err(status, body):
    import groq                                   # the app's AI client (its errors are groq's)
    resp = httpx.Response(status, request=httpx.Request("POST", "https://x/v1/chat/completions"), json=body)
    return groq.APIStatusError("refused", response=resp, body=body)


def test_the_app_says_the_real_reason():
    from ginkassistant.services.groq_worker import _problem_message, _limit_message
    limit = _err(429, {"error": {"message": "Rate limit reached for model openai/gpt-oss-120b: tokens per day (TPD)", "code": "rate_limit_exceeded"}})
    assert _limit_message(limit) == "" and _problem_message(limit).startswith("The AI service has reached its limit for now")
    assert "tokens per day" in _problem_message(limit)
    bad = _err(400, {"error": {"message": "The model `x` does not exist"}})
    assert _problem_message(bad) == "The AI service couldn't answer (error 400: The model `x` does not exist)."
    assert "error 503" in _problem_message(_err(503, {}))
    assert "The AI service had a problem" not in _problem_message(bad)


def test_the_server_logs_refusals_without_the_messages(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "e.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        return httpx.Response(429, headers={"retry-after": "120"},
                              json={"error": {"message": "Rate limit reached: tokens per day", "code": "rate_limit_exceeded"}})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "pro"})
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    r = c.post("/ai/openai/v1/chat/completions", headers=h,
               json={"model": "openai/gpt-oss-120b", "stream": True, "messages": [{"role": "user", "content": "MY SECRET QUESTION"}]})
    assert r.status_code == 429 and r.headers.get("retry-after") == "120" and "tokens per day" in r.json()["error"]["message"]
    out = capsys.readouterr().out
    assert "[gink] AI provider refused: HTTP 429 model=openai/gpt-oss-120b" in out and "tokens per day" in out
    assert "MY SECRET QUESTION" not in out                                                  # never the person's messages
    b._groq_models.update(ids=set(), at=0.0)


IDS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile",
       "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"]


def _server(monkeypatch, tmp_path, answers):
    """Groq simulated per model: answers[model] = status (200 answers 'hi from MODEL')."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "f.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i} for i in IDS]})
        body = json.loads(request.content); sent.append(body)
        status = answers.get(body["model"], 429)
        if status == 200:
            return httpx.Response(200, text='data: {"choices":[{"index":0,"delta":{"content":"hi from ' + body["model"] + '"}}]}\n\ndata: [DONE]\n\n',
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(status, json={"error": {"message": f"refused {status}", "code": "rate_limit_exceeded" if status == 429 else "x"}})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "pro"})
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    ask = lambda **extra: c.post("/ai/openai/v1/chat/completions", headers=h,
                                 json={"model": "openai/gpt-oss-120b", "stream": True, "messages": [{"role": "user", "content": "hi"}], **extra})
    return b, ask, sent


def test_another_model_answers_when_one_is_at_its_limit(tmp_path, monkeypatch, capsys):
    b, ask, sent = _server(monkeypatch, tmp_path, {"openai/gpt-oss-20b": 200})
    r = ask()
    assert r.status_code == 200 and "hi from openai/gpt-oss-20b" in r.text and r.headers["x-gink-model"] == "openai/gpt-oss-20b"
    assert "-> trying openai/gpt-oss-20b" in capsys.readouterr().out
    b._groq_models.update(ids=set(), at=0.0)


def test_non_gpt_oss_models_dont_get_reasoning_settings(tmp_path, monkeypatch):
    b, ask, sent = _server(monkeypatch, tmp_path, {"llama-3.3-70b-versatile": 200})
    r = ask(reasoning_effort="medium")
    assert "hi from llama-3.3-70b-versatile" in r.text
    assert [s["model"] for s in sent] == IDS[:4] and "reasoning_effort" not in sent[-1] and sent[0]["reasoning_effort"] == "medium"
    b._groq_models.update(ids=set(), at=0.0)


def test_at_most_four_tries_then_the_real_reason(tmp_path, monkeypatch):
    b, ask, sent = _server(monkeypatch, tmp_path, {})
    r = ask()
    assert r.status_code == 429 and len(sent) == 4 and "refused 429" in r.json()["error"]["message"]
    b._groq_models.update(ids=set(), at=0.0)


def test_no_retries_for_other_errors_photos_or_search_rules(tmp_path, monkeypatch):
    b, ask, sent = _server(monkeypatch, tmp_path, {"openai/gpt-oss-120b": 400})
    assert ask().status_code == 400 and len(sent) == 1                                  # a bad request isn't a limit
    sent.clear()
    tools = [{"type": "browser_search"}]
    assert [m for m in b._next_models({"messages": [], "tools": tools}, ["openai/gpt-oss-120b"])] == ["openai/gpt-oss-20b"]
    photo = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}]}
    assert b._next_models(photo, ["x"]) == []
    b._groq_models.update(ids=set(), at=0.0)
