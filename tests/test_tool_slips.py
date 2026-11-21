"""Tool slips (0.1.162): "Tool choice is none, but model called a tool" never reaches anyone. Groq answers 400
"tool_use_failed" (before the answer, or as an "error" event inside a streamed one) when a model calls a tool it wasn't
given; the server asks again -- as plain text, then on another model -- and the apps' chats can hand the request to
their own tools instead ({"gink_status": "use_tools"})."""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx

IDS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
SLIP = {"error": {"message": "Tool choice is none, but model called a tool", "type": "invalid_request_error",
                  "code": "tool_use_failed", "failed_generation": "{\"name\": \"python\"}"}}


def sse(*events):
    return "".join("data: " + (e if isinstance(e, str) else json.dumps(e)) + "\n\n" for e in events)


def piece(text):
    return {"choices": [{"index": 0, "delta": {"content": text}}]}


def server(monkeypatch, tmp_path, answers):
    """answers: a list, one per call to Groq: (status, json) or ("sse", text)."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []

    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i} for i in IDS]})
        sent.append(json.loads(request.content))
        kind, what = answers.pop(0) if answers else (200, {"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        if kind == "sse":
            return httpx.Response(200, text=what, headers={"content-type": "text/event-stream"})
        return httpx.Response(kind, json=what)
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
    return b, c, h, sent


def ask(c, h, extra_headers=None, **body):
    body = {"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": "can you run some check for why my camera is not working"}], **body}
    return c.post("/ai/openai/v1/chat/completions", headers={**h, **(extra_headers or {})}, json=body)


def test_a_slip_before_the_answer_is_asked_again_as_plain_text(tmp_path, monkeypatch):
    b, c, h, sent = server(monkeypatch, tmp_path, [(400, SLIP), (200, {"choices": [{"message": {"role": "assistant", "content": "Here's what to check."}}]})])
    r = ask(c, h)
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Here's what to check."
    assert len(sent) == 2 and "tools" not in sent[1]
    assert any(m["role"] == "system" and m["content"] == b.PLAIN_TEXT_NOTE for m in sent[1]["messages"])
    assert b._health["tool_slips"] >= 1
    b._groq_models.update(ids=set(), at=0.0)


def test_streamed_slips_are_asked_again_and_never_reach_the_app(tmp_path, monkeypatch):
    # before the stream starts (HTTP 400), then inside it (an "error" event before any words)
    b, c, h, sent = server(monkeypatch, tmp_path, [(400, SLIP), ("sse", sse({"choices": [{"index": 0, "delta": {"role": "assistant"}}]}, SLIP)),
                                                   ("sse", sse(piece("Close other apps "), piece("that use the camera."), "[DONE]"))])
    r = ask(c, h, stream=True)
    assert r.status_code == 200 and "Close other apps that use the camera." in "".join(
        json.loads(l[6:])["choices"][0]["delta"].get("content", "") for l in r.text.splitlines()
        if l.startswith("data: {") and json.loads(l[6:]).get("choices"))
    assert "tool_use_failed" not in r.text and "Tool choice is none" not in r.text
    assert len(sent) == 3 and sent[2]["model"] != sent[0]["model"]              # the second slip: another model
    b._groq_models.update(ids=set(), at=0.0)


def test_an_error_after_words_ends_with_a_sentence_for_people_and_as_is_for_developers(tmp_path, monkeypatch):
    stream = sse(piece("First part. "), {"error": {"message": "Internal error", "code": "internal"}})
    b, c, h, sent = server(monkeypatch, tmp_path, [("sse", stream), ("sse", stream)])
    r = ask(c, h, stream=True)
    assert "First part." in r.text and "stopped early" in r.text and '"error"' not in r.text and r.text.rstrip().endswith("[DONE]")
    key = b._create_api_key("ib@example.com", "k")["key"]
    r = c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
               json={"stream": True, "gink_web": False, "messages": [{"role": "user", "content": "hi"}]})
    assert '"Internal error"' in r.text and "stopped early" not in r.text          # developers: OpenAI-style, unchanged
    b._groq_models.update(ids=set(), at=0.0)


def test_the_apps_chats_can_hand_a_request_to_their_tools(tmp_path, monkeypatch):
    call = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                                                               "function": {"name": "gink_use_tools", "arguments": ""}}]}}]}
    b, c, h, sent = server(monkeypatch, tmp_path, [("sse", sse(call, "[DONE]")), ("sse", sse(SLIP)), (400, SLIP)])
    acts = {"X-Gink-Actions": "1", "X-Gink-Turn": "t1"}
    r = ask(c, h, acts, stream=True)
    assert '"gink_status": "use_tools"' in r.text and "tool_calls" not in r.text
    assert sent[0]["tools"] == [b.HANDOFF_TOOL] and sent[0]["tool_choice"] == "auto"
    assert sent[0]["messages"][0] == {"role": "system", "content": b.HANDOFF_NOTE}
    assert '"gink_status": "use_tools"' in ask(c, h, acts, stream=True).text           # a slip: it wanted to act
    assert ask(c, h, acts).json()["gink"] == {"use_tools": True}                        # not streamed: the same
    assert len(sent) == 3                                                               # handed over, not asked again
    # not for photos, the agent's own steps or developers
    photo = [{"role": "user", "content": [{"type": "text", "text": "fix this"},
                                          {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]}]
    ask(c, h, acts, messages=photo)
    assert "tools" not in sent[-1]
    ask(c, h, {**acts, "X-Gink-Agent": "1"})
    assert "tools" not in sent[-1]
    b._groq_models.update(ids=set(), at=0.0)


def test_requests_with_tools_get_one_more_try_with_a_note(tmp_path, monkeypatch):
    tools = [{"type": "function", "function": {"name": "calculate", "parameters": {"type": "object", "properties": {}}}}]
    b, c, h, sent = server(monkeypatch, tmp_path, [(400, {"error": {"message": "tool call validation failed: attempted to call "
                                                                            "tool 'python' which was not in request.tools",
                                                                 "code": "tool_use_failed"}}),
                                                   (200, {"choices": [{"message": {"role": "assistant", "content": "42"}}]})])
    r = ask(c, h, tools=tools, tool_choice="auto")
    assert r.json()["choices"][0]["message"]["content"] == "42"
    assert sent[1]["tools"] == tools and sent[1]["messages"][-1] == {"role": "system", "content": b.TOOL_RETRY_NOTE}
    b._groq_models.update(ids=set(), at=0.0)


def test_gink_s_own_loops_ask_again_too(tmp_path, monkeypatch):
    import asyncio
    b, c, h, sent = server(monkeypatch, tmp_path, [(400, SLIP), (200, {"choices": [{"message": {"content": "Done."}}]})])

    async def go():
        async with httpx.AsyncClient() as client:
            return await b._groq_post(client, f"{b.GROQ_BASE}/chat/completions", {"model": "openai/gpt-oss-120b",
                                      "messages": [{"role": "user", "content": "x"}]}, {})
    r, body = asyncio.run(go())
    assert r.status_code == 200 and "tools" not in body and len(sent) == 2
    # the helpers: what a slip looks like, and plain text keeps what the tools found
    assert b._tool_slip(json.dumps(SLIP)) and not b._tool_slip('{"error": {"message": "Rate limit reached"}}')
    plain = b._without_tools({"model": "m", "tools": [1], "tool_choice": "none", "messages": [
        {"role": "system", "content": "S"}, {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "web_search", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "RESULT"}]})
    assert "tools" not in plain and "tool_choice" not in plain
    assert [m["role"] for m in plain["messages"]] == ["system", "system", "user", "assistant", "user"]
    assert "web_search" in plain["messages"][3]["content"] and "RESULT" in plain["messages"][4]["content"]
    assert b._without_tools(plain)["messages"] == plain["messages"]                    # once is enough
    b._groq_models.update(ids=set(), at=0.0)
