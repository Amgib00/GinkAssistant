"""Claude's native Messages API with prompt caching: OpenAI <-> Claude translation (requests,
answers, tool calls, streaming) and the full path through the server."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest
from ginkassistant.services import backend_server as b

AGENT_TOOLS = [{"type": "function", "function": {"name": "set_alarm", "description": "Set an alarm",
                "parameters": {"type": "object", "properties": {"time": {"type": "string"}}, "required": ["time"]}}}]


def test_request_translation():
    body = {"model": "claude-sonnet-5-5", "max_tokens": 500, "temperature": 1.7, "stream": True, "tools": AGENT_TOOLS,
            "messages": [{"role": "system", "content": "You are Gink."}, {"role": "system", "content": "Be brief."},
                         {"role": "user", "content": [{"type": "text", "text": "What is this?"},
                                                      {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
                         {"role": "user", "content": "And wake me at 6"},
                         {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function",
                          "function": {"name": "set_alarm", "arguments": "{\"time\": \"06:00\"}"}}]},
                         {"role": "tool", "tool_call_id": "call_1", "content": "Alarm set for 06:00"}]}
    c = b._to_claude(body)
    assert c["cache_control"] == {"type": "ephemeral"}                      # automatic prompt caching
    assert c["system"] == "You are Gink.\n\nBe brief." and c["temperature"] == 1.0 and c["stream"] is True
    roles = [m["role"] for m in c["messages"]]
    assert roles == ["user", "assistant", "user"]                            # same-role turns merged
    first = c["messages"][0]["content"]
    assert first[1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    assert first[2] == {"type": "text", "text": "And wake me at 6"}
    assert c["messages"][1]["content"] == [{"type": "tool_use", "id": "call_1", "name": "set_alarm", "input": {"time": "06:00"}}]
    assert c["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "call_1", "content": "Alarm set for 06:00"}
    assert c["tools"][0]["name"] == "set_alarm" and c["tools"][0]["input_schema"]["required"] == ["time"]
    assert c["tool_choice"] == {"type": "auto"}
    assert b._to_claude({**body, "tool_choice": "required"})["tool_choice"] == {"type": "any"}


def test_answer_translation():
    resp = {"id": "msg_1", "stop_reason": "tool_use",
            "content": [{"type": "text", "text": "Setting it."}, {"type": "tool_use", "id": "toolu_1", "name": "set_alarm", "input": {"time": "06:00"}}],
            "usage": {"input_tokens": 20, "cache_read_input_tokens": 1800, "cache_creation_input_tokens": 0, "output_tokens": 30}}
    o = b._from_claude(resp, "claude-sonnet-5-5")
    msg = o["choices"][0]["message"]
    assert msg["content"] == "Setting it." and o["choices"][0]["finish_reason"] == "tool_calls"
    assert msg["tool_calls"][0]["function"] == {"name": "set_alarm", "arguments": "{\"time\": \"06:00\"}"}
    assert o["usage"]["prompt_tokens"] == 1820 and o["usage"]["prompt_tokens_details"]["cached_tokens"] == 1800


def _events():
    return [{"type": "message_start", "message": {"id": "msg_9"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Sure, "}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "setting it."}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_7", "name": "set_alarm", "input": {}}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"time\": "}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "\"06:00\"}"}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 12}},
            {"type": "message_stop"}]


def _parse(lines):
    text, args, name, finish, done = "", "", None, None, False
    for raw in lines:
        payload = raw.decode()[6:].strip()
        if payload == "[DONE]":
            done = True; continue
        ch = json.loads(payload)["choices"][0]
        d = ch["delta"]
        text += d.get("content") or ""
        for tc in d.get("tool_calls") or []:
            name = tc.get("function", {}).get("name") or name
            args += tc.get("function", {}).get("arguments") or ""
        finish = ch["finish_reason"] or finish
    return text, name, args, finish, done


def test_stream_translation():
    t = b._ClaudeStream("claude-sonnet-5-5")
    out = [line for ev in _events() for line in t.event(ev)]
    text, name, args, finish, done = _parse(out)
    assert text == "Sure, setting it." and name == "set_alarm" and json.loads(args) == {"time": "06:00"}
    assert finish == "tool_calls" and done


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "n.db"))
    monkeypatch.setenv("GROQ_API_KEY", "g"); monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    seen = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5-5"}, {"id": "openai/gpt-oss-120b"}]})
        if request.url.path.endswith("/chat/completions"):                    # the compatibility route
            seen.append({"compat": True})
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        assert request.url.path.endswith("/v1/messages"), request.url.path
        req = json.loads(request.content); seen.append({"body": req, "key": request.headers.get("x-api-key"),
                                                        "version": request.headers.get("anthropic-version")})
        if req.get("stream"):
            sse = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in _events())
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"id": "msg_2", "stop_reason": "end_turn", "content": [{"type": "text", "text": "Hello!"}],
                                         "usage": {"input_tokens": 5, "output_tokens": 2, "cache_read_input_tokens": 1500}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler),
                                                                    **{x: y for x, y in k.items() if x != "transport"}))
    from fastapi.testclient import TestClient
    b._claude_models.update(ids=set(), at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "pro"})
    c = TestClient(b.app)
    return c, {"Authorization": "Bearer " + b._token_response("pro@x.co", "P")["token"]}, seen


def test_through_the_server_non_streaming(server):
    c, h, seen = server
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "gink-frost", "messages": [
        {"role": "system", "content": "You are Gink."}, {"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Hello!"
    assert r.json()["usage"]["prompt_tokens_details"]["cached_tokens"] == 1500
    sent = seen[-1]
    assert sent["key"] == "anthropic-secret" and sent["version"] == "2023-06-01"
    assert sent["body"]["cache_control"] == {"type": "ephemeral"} and sent["body"]["system"] == "You are Gink."


def test_through_the_server_streaming_with_a_tool_call(server):
    c, h, seen = server
    with c.stream("POST", "/ai/openai/v1/chat/completions", headers=h, json={"model": "claude-sonnet-5-5", "stream": True,
                  "tools": AGENT_TOOLS, "messages": [{"role": "user", "content": "wake me at 6"}]}) as r:
        lines = [l.encode() for l in r.iter_lines() if l.startswith("data:")]
    text, name, args, finish, done = _parse(lines)
    assert text == "Sure, setting it." and name == "set_alarm" and json.loads(args) == {"time": "06:00"} and finish == "tool_calls" and done
    assert seen[-1]["body"]["tools"][0]["name"] == "set_alarm"


def test_compat_mode_still_available(server, monkeypatch):
    c, h, seen = server
    monkeypatch.setenv("GINK_CLAUDE_MODE", "compat")
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "claude-sonnet-5-5", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and seen[-1] == {"compat": True}
