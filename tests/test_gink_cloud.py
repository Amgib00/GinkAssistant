"""Gink Cloud: the app's real brain/agent -> the real server proxy -> (simulated) Groq."""
import asyncio, json, os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import pytest

REAL_CLIENT = httpx.AsyncClient
SERVER_KEY = "gsk_server_secret"


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("GROQ_API_KEY", SERVER_KEY)
    monkeypatch.setenv("GINK_FREE_DAILY", "2")
    monkeypatch.setenv("GINK_PRO_DAILY", "50")
    from ginkassistant.services import backend_server as b
    b._models_cache.update(at=0, data=None)
    seen = []

    def groq(request):
        seen.append({"auth": request.headers.get("authorization"), "path": request.url.path,
                     "body": json.loads(request.content or b"{}")})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b-versatile"},
                                                      {"id": "meta-llama/llama-4-scout-17b-16e-instruct"}]})
        body = json.loads(request.content)
        if body.get("stream"):
            chunks = "".join(f"data: {json.dumps({'choices': [{'index': 0, 'delta': {'content': t}}]})}\n\n"
                             for t in ("Hel", "lo!")) + "data: [DONE]\n\n"
            return httpx.Response(200, text=chunks, headers={"content-type": "text/event-stream"})
        n = sum(1 for m in body["messages"] if m["role"] == "tool")
        if body.get("tools") and n == 0:     # agent round 1: ask for a tool
            return httpx.Response(200, json={"choices": [{"message": {"content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "calculate",
                                                              "arguments": "{\"expression\": \"6*7\"}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "It's 42."}}]})

    import ginkassistant.services.groq_worker  # noqa: F401  (load groq before swapping httpx.AsyncClient)

    class Routed(REAL_CLIENT):
        """The SERVER's outgoing calls (no transport given) go to the simulated Groq."""
        def __init__(self, *a, **k):
            k.setdefault("transport", httpx.MockTransport(groq))
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Routed)
    tok = lambda email: b._token_response(email, "I")["token"]
    to_server = lambda: Routed(transport=httpx.ASGITransport(app=b.app), base_url="http://t")
    return b, seen, tok, to_server


def _brain(tmp_path, token, to_server):
    from ginkassistant.services.groq_worker import GroqBrain
    from test_sync_attach_memory_briefing import _Hist
    brain = GroqBrain.__new__(GroqBrain)
    brain.history, brain.session_id, brain.active_models = _Hist(tmp_path / "h.db"), "s", []
    brain.preferred_model, brain.memory_provider, brain.city_fn, brain.api_key, brain.client = \
        "llama-3.3-70b-versatile", None, None, "", None
    assert brain.use_cloud("http://t", token, http_client=to_server())
    return brain


def test_chat_streams_through_server_and_key_stays_there(cloud, tmp_path):
    b, seen, tok, to_server = cloud
    brain = _brain(tmp_path, tok("ib@x.co"), to_server)
    tokens = []
    async def on_token(t): tokens.append(t)
    reply = asyncio.run(brain.ask("hi", on_token=on_token))
    assert reply == "Hello!" and tokens == ["Hel", "lo!"]
    upstream = [s for s in seen if s["path"].endswith("/chat/completions")][-1]
    assert upstream["auth"] == f"Bearer {SERVER_KEY}"                         # server's key, server-side only
    assert upstream["body"]["max_tokens"] == 1024 and len(upstream["body"]["user"]) == 32   # free cap, hashed id
    assert "ib@x.co" not in json.dumps(upstream["body"])


def test_free_daily_limit_then_upgrade_link(cloud, tmp_path):
    b, seen, tok, to_server = cloud
    brain = _brain(tmp_path, tok("free@x.co"), to_server)
    assert asyncio.run(brain.ask("one")) == "Hello!"
    assert asyncio.run(brain.ask("two")) == "Hello!"
    third = asyncio.run(brain.ask("three"))
    assert "today's 2 free messages" in third and "(gink://pro)" in third
    usage = b._usage_for("free@x.co")
    assert usage["used"] == 2 and usage["limit"] == 2 and usage["plan"] == "free"


def test_agent_steps_count_once_and_photos_need_pro(cloud, tmp_path):
    b, seen, tok, to_server = cloud
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    agent = TaskAgent(runner, api_key=tok("agent@x.co"), http_client=to_server())
    agent.base_url = "http://t/ai/openai/v1/chat/completions"
    r = asyncio.run(agent.run("what is six times seven, roughly, in words"))
    assert r.text == "It's 42." and r.actions[0]["tool"] == "calculate"
    assert b._usage_for("agent@x.co")["used"] == 1                        # 2 AI rounds, 1 message
    # photos: refused on Free, allowed on Pro
    from ginkassistant.services import attachments as a
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (20, 20)).save(buf, "PNG")
    img = a.load_bytes(buf.getvalue(), "x.png")
    brain = _brain(tmp_path, tok("pic@x.co"), to_server)
    msg = asyncio.run(brain.ask("what is this?", attachments=[img]))
    assert "part of Gink Pro" in msg and "gink://pro" in msg
    with b._db_lock:
        con = b._billing_db(); con.execute("UPDATE users SET pro_until=? WHERE email=?", (9e9, "pic@x.co")); con.commit(); con.close()
    assert asyncio.run(brain.ask("what is this?", attachments=[img])) == "Hello!"
    assert seen[-1]["body"]["max_tokens"] == 4096 and seen[-1]["body"]["model"].startswith("meta-llama/llama-4")


def test_auth_and_configuration(cloud, monkeypatch):
    b, seen, tok, to_server = cloud
    async def go():
        async with to_server() as c:
            r1 = await c.post("/ai/openai/v1/chat/completions", json={"model": "x", "messages": []})
            r2 = await c.post("/ai/openai/v1/chat/completions", json={"model": "x", "messages": []},
                              headers={"Authorization": "Bearer gsk_someones_real_groq_key"})
            monkeypatch.delenv("GROQ_API_KEY")
            r3 = await c.post("/ai/openai/v1/chat/completions", json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
                              headers={"Authorization": "Bearer " + tok("a@x.co")})
            return r1, r2, r3
    r1, r2, r3 = asyncio.run(go())
    assert r1.status_code == 401 and r2.status_code == 401                # only Gink session tokens work
    assert r3.status_code == 503 and r3.json()["error"]["code"] == "not_configured"
