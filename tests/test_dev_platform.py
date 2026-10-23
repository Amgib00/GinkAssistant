"""Developer platform: request logging (no contents), overview/metrics/logs/usage, OpenAI-style batches."""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


@pytest.fixture
def plat(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "d.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        body = json.loads(request.content)
        said = body["messages"][-1]["content"]
        if "FAIL" in said:
            return httpx.Response(400, json={"error": {"message": "bad input"}})
        usage = {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}
        if body.get("stream"):
            frames = [{"choices": [{"index": 0, "delta": {"content": "Hi"}}]},
                      {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "x_groq": {"usage": usage}}]
            return httpx.Response(200, text="".join("data: " + json.dumps(f) + "\n\n" for f in frames) + "data: [DONE]\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Answer to: " + said}}], "usage": usage})
    real = httpx.AsyncClient
    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._batch_tasks.clear()
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "pro"})
    c = TestClient(b.app)
    sess = {"Authorization": "Bearer " + b._token_response("dev@example.com", "Dev")["token"]}
    key = c.post("/account/api-keys", headers=sess, json={"name": "backend"}).json()["key"]
    return b, c, sess, {"Authorization": "Bearer " + key}


def chat(c, api, text, **kw):
    return c.post("/v1/chat/completions", headers=api, json={"model": "gink-crystal", "messages": [{"role": "user", "content": text}], **kw})


def test_requests_are_logged_without_contents(plat):
    b, c, sess, api = plat
    assert chat(c, api, "secret plans for Friday").status_code == 200
    with c.stream("POST", "/v1/chat/completions", headers=api, json={"messages": [{"role": "user", "content": "hi"}], "stream": True}) as r:
        list(r.iter_lines())
    assert chat(c, api, "FAIL please").status_code >= 400
    logs = c.get("/dev/logs", headers=sess).json()["logs"]
    assert [l["stream"] for l in logs] == [False, True, False]
    assert logs[2]["prompt_tokens"] == 12 and logs[2]["completion_tokens"] == 5 and logs[2]["key"] == "backend"
    assert logs[1]["prompt_tokens"] == 12                                               # tokens from the stream too
    assert logs[0]["status"] >= 400
    dump = json.dumps(logs) + str(b._dev_db(lambda con: con.execute("SELECT * FROM api_requests").fetchall()))
    assert "secret plans" not in dump                                                   # never the contents


def test_overview_metrics_and_usage(plat):
    b, c, sess, api = plat
    for t in ("a", "b", "FAIL"):
        chat(c, api, t)
    o = c.get("/dev/overview", headers=sess).json()
    assert o["today"]["requests"] == 3 and o["today"]["errors"] == 1 and o["today"]["tokens"] == 34 and o["active_keys"] == 1
    assert o["base_url"].endswith("/v1") and o["daily_limit"] == 500
    m = c.get("/dev/metrics?days=7", headers=sess).json()
    assert len(m["days"]) == 7 and m["days"][-1]["requests"] == 3 and m["days"][-1]["errors"] == 1
    assert m["models"][0] == {"model": "gink-crystal", "requests": 3}
    u = c.get("/dev/usage", headers=sess).json()["keys"][0]
    assert u["name"] == "backend" and u["today"]["requests"] == 3 and u["month"]["tokens"] == 34


def wait_done(c, path, headers, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        r = c.get(path, headers=headers).json()
        if r["status"] in ("completed", "cancelled"):
            return r
        time.sleep(0.1)
    raise AssertionError("batch didn't finish: " + json.dumps(r))


def test_batch_runs_and_returns_results(plat):
    b, c, sess, api = plat
    reqs = [{"custom_id": f"q{i}", "body": {"messages": [{"role": "user", "content": t}]}} for i, t in enumerate(["one", "two", "FAIL"])]
    created = c.post("/v1/batches", headers=api, json={"requests": reqs, "name": "test run"}).json()
    assert created["status"] in ("queued", "running") and created["request_counts"]["total"] == 3
    done = wait_done(c, f"/v1/batches/{created['id']}", api)
    assert done["status"] == "completed" and done["request_counts"] == {"total": 3, "completed": 2, "failed": 1}
    lines = [json.loads(l) for l in c.get(f"/v1/batches/{created['id']}/results", headers=api).text.splitlines()]
    by = {l["custom_id"]: l for l in lines}
    assert by["q0"]["response"]["choices"][0]["message"]["content"] == "Answer to: one" and by["q2"]["status"] >= 400
    assert [x["id"] for x in c.get("/dev/batches", headers=sess).json()["data"]] == [created["id"]]   # in the console too
    assert any(l["endpoint"] == "batch" for l in c.get("/dev/logs", headers=sess).json()["logs"])


def test_batch_validation_privacy_and_cancel(plat, monkeypatch):
    b, c, sess, api = plat
    too_many = [{"custom_id": str(i), "body": {"messages": []}} for i in range(101)]
    assert c.post("/v1/batches", headers=api, json={"requests": too_many}).status_code == 422
    assert c.post("/v1/batches", headers=api, json={"requests": [{"custom_id": "x", "body": {}}]}).status_code == 422
    other = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    bid = c.post("/dev/batches", headers=sess, json={"requests": [{"custom_id": "a", "body": {"messages": [{"role": "user", "content": "x"}]}}]}).json()["id"]
    assert c.get(f"/dev/batches/{bid}/results", headers=other).status_code == 404
    assert c.post(f"/dev/batches/{bid}/cancel", headers=other).status_code == 404
    paused = {"go": False}
    real = b.ai_chat
    async def slow(req):
        import asyncio
        while not paused["go"]:
            await asyncio.sleep(0.05)
        return await real(req)
    monkeypatch.setattr(b, "ai_chat", slow)
    bid2 = c.post("/dev/batches", headers=sess, json={"requests": [{"custom_id": "s", "body": {"messages": [{"role": "user", "content": "x"}]}}]}).json()["id"]
    assert c.post(f"/dev/batches/{bid2}/cancel", headers=sess).json()["status"] == "cancelled"
    paused["go"] = True


def test_batch_resumes_after_a_restart(plat):
    b, c, sess, api = plat
    body = {"messages": [{"role": "user", "content": "after restart"}]}
    b._dev_db(lambda con: con.execute("INSERT INTO batches (id, email, key_id, name, status, created, total, requests) "
                                      "VALUES ('batch_x', 'dev@example.com', NULL, NULL, 'running', ?, 1, ?)",
                                      (time.time(), json.dumps([{"custom_id": "r1", "body": body}]))))
    from fastapi.testclient import TestClient
    with TestClient(b.app) as restarted:                                         # a server start runs start-up hooks
        done = wait_done(restarted, "/v1/batches/batch_x", api)
    assert done["request_counts"]["completed"] == 1
