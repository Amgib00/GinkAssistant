"""Real-time information through the server (developer API, web app): date always; live data when asked."""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx


def test_understanding_what_and_where():
    from ginkassistant.services.backend_server import _live_requests as r, _live_place as place
    assert r("What's the weather in Dakar today?") == [("weather", {"place": "Dakar", "day": "now"})]
    assert r("will it rain in freetown tomorrow") == [("weather", {"place": "freetown", "day": "tomorrow"})]
    assert place("weather for Saint-Louis, Senegal please") == "Saint-Louis, Senegal"
    assert r("what time is it in Tokyo?") == [("time", {"place": "Tokyo", "day": "now"})]
    assert r("how much is 100 dollars in cfa") == [("currency", {"amount": 100.0, "from": "USD", "to": "XOF"})]
    assert r("what's the bitcoin price?") == [("crypto", {"coin": "bitcoin"})]
    assert r("prayer times in Kano") == [("prayer", {"place": "Kano", "day": "today"})]
    assert r("what's the weather like?") == [] and r("write me a poem about rain") == []      # no place: nothing fetched
    assert r("tell me about the history of Rome") == []


def _server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "l.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b, live_info
    b._groq_models.update(ids=set(), at=0.0)
    asked = []
    async def weather(self, place=None, day="now"):
        asked.append(("weather", place, day))
        return {"ok": True, "message": f"Now in {place}: 31\u00b0C, sunny, humidity 60%."}
    monkeypatch.setattr(live_info.LiveInfo, "get_weather", weather)
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": "pro"})
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    ask = lambda text, **extra: c.post("/ai/openai/v1/chat/completions", headers=h,
                                       json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": text}], **extra})
    return b, ask, sent, asked


def test_the_ai_gets_live_weather_and_the_date(tmp_path, monkeypatch):
    b, ask, sent, asked = _server(tmp_path, monkeypatch)
    assert ask("What's the weather in Dakar today?").status_code == 200
    system = sent[-1]["messages"][0]
    assert system["role"] == "system" and "Current date and time:" in system["content"]
    assert "Now in Dakar: 31\u00b0C, sunny" in system["content"] and asked == [("weather", "Dakar", "now")]
    assert "don't claim you can't access real-time information" in system["content"]
    b._groq_models.update(ids=set(), at=0.0)


def test_developers_can_turn_it_off_and_no_city_means_ask(tmp_path, monkeypatch):
    b, ask, sent, asked = _server(tmp_path, monkeypatch)
    ask("What's the weather in Dakar?", gink_live=False)
    assert asked == [] and "gink_live" not in sent[-1]                       # not fetched, never sent to the AI service
    assert "Current date and time:" in sent[-1]["messages"][0]["content"]    # the date is always there
    ask("what's the weather like?")
    assert asked == [] and "ask which city or town" in sent[-1]["messages"][0]["content"]
    ask("Explain photosynthesis")
    assert "Live data" not in sent[-1]["messages"][0]["content"]
    b._groq_models.update(ids=set(), at=0.0)


def test_the_server_image_has_live_info():
    dockerfile = open(os.path.join(os.path.dirname(__file__), "..", "deploy", "Dockerfile")).read()
    assert "COPY src/ginkassistant/services/live_info.py ./live_info.py" in dockerfile


def test_every_route_decorator_sits_on_its_function():
    """Code inserted between "@app.post(...)" and its function moved the route to the wrong function
    (the chat route returned the live_info module). A decorator must be followed by a def or another decorator."""
    lines = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "backend_server.py"),
                 encoding="utf-8").read().splitlines()
    bad = [i + 1 for i, line in enumerate(lines) if line.startswith("@app.")
           and not (lines[i + 1].startswith(("def ", "async def ", "@")))]
    assert bad == [], f"route decorators not directly on their function, lines {bad}"
