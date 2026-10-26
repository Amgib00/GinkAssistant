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
