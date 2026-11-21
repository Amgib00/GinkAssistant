"""Automatic tools (0.1.162): the chat's AI can hand a request to Gink's own tools by itself, a camera or microphone
that isn't working gets a real check, and no answer ever ends in "[error] ..." or a spinner that never stops."""
import asyncio
import json
import os
import sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def sse(*events):
    return "".join("data: " + (e if isinstance(e, str) else json.dumps(e)) + "\n\n" for e in events)


def piece(text):
    return {"id": "x", "object": "chat.completion.chunk", "created": 1, "model": "m",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}


SLIP = {"error": {"message": "Tool choice is none, but model called a tool", "type": "invalid_request_error",
                  "code": "tool_use_failed"}}


def brain_on(tmp_path, answers):
    """A real GroqBrain talking straight to a simulated Groq (your own key): answers, one per request, are
    ("sse", text) or (status, json). -> (brain, the requests it sent)"""
    from groq import AsyncGroq
    from ginkassistant.services.groq_worker import GroqBrain
    from test_sync_attach_memory_briefing import _Hist
    sent = []

    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}]})
        sent.append({"body": json.loads(request.content), "headers": dict(request.headers)})
        kind, what = answers.pop(0)
        if kind == "sse":
            return httpx.Response(200, text=what, headers={"content-type": "text/event-stream"})
        return httpx.Response(kind, json=what)
    brain = GroqBrain.__new__(GroqBrain)
    brain.history, brain.session_id, brain.active_models = _Hist(tmp_path / "h.db"), "s", ["openai/gpt-oss-120b"]
    brain.preferred_model, brain.memory_provider, brain.city_fn, brain.api_key = "openai/gpt-oss-120b", None, None, "k"
    brain.app = None
    brain.client = AsyncGroq(api_key="k", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(groq)))
    return brain, sent


def test_an_answer_that_stops_ends_with_a_sentence_and_a_slip_is_asked_again(tmp_path):
    from ginkassistant.services import tool_slips
    brain, sent = brain_on(tmp_path, [("sse", sse(piece("The first half"), SLIP))])
    shown = []

    async def on_token(t):
        shown.append(t)
    reply = asyncio.run(brain.ask("explain it", on_token=on_token))
    assert reply.startswith("The first half") and reply.endswith(tool_slips.STOPPED_EARLY) and "[error]" not in reply
    assert "".join(shown) == reply                                         # what's on screen is what's saved
    # nothing said yet: once more without tools, as plain text
    brain, sent = brain_on(tmp_path, [("sse", sse(SLIP)), ("sse", sse(piece("Close the other camera apps."), "[DONE]"))])
    assert asyncio.run(brain.ask("can you run some check for why my camera is not working")) == "Close the other camera apps."
    assert any(m.get("content") == tool_slips.PLAIN_TEXT_NOTE for m in sent[1]["body"]["messages"])
    # a slip before the answer (HTTP 400) and again: a plain sentence, never the error
    brain, sent = brain_on(tmp_path, [(400, SLIP), (400, SLIP)])
    assert asyncio.run(brain.ask("hi")) == tool_slips.NO_ANSWER


def test_the_ai_can_hand_a_request_to_gink_s_tools(tmp_path):
    from ginkassistant.services.groq_worker import UseTools
    handoff = sse({"id": "gink-handoff", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": [],
                   "gink_status": "use_tools"}, "[DONE]")
    brain, sent = brain_on(tmp_path, [("sse", handoff), ("sse", handoff)])
    brain.actions_ok = True
    with pytest.raises(UseTools):
        asyncio.run(brain.ask("the light by my screen stays off in calls"))
    assert sent[0]["headers"].get("x-gink-actions") == "1"
    brain.actions_ok = False                                               # not allowed (photos, no agent): just text
    asyncio.run(brain.ask("hello"))
    assert "x-gink-actions" not in sent[1]["headers"]


def test_the_agent_asks_again_after_a_slip_and_answers_last_without_tools(tmp_path):
    from ginkassistant.services import tool_slips
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner
    bodies = []

    def ai(request):
        body = json.loads(request.content); bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(400, json=SLIP)
        if body.get("tools"):
            return httpx.Response(200, json={"choices": [{"message": {"content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "calculate", "arguments": "{\"expression\": \"6*7\"}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "It's 42."}}]})
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    agent = TaskAgent(runner, api_key="k", http_client=httpx.AsyncClient(transport=httpx.MockTransport(ai)))
    agent.base_url = "http://t/v1/chat/completions"

    async def last_word():
        return await agent._chat([{"role": "user", "content": "6*7?"},
                                  {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "calculate"}}]},
                                  {"role": "tool", "tool_call_id": "1", "content": "42"}], use_tools=False)
    msg = asyncio.run(last_word())
    assert msg["content"] == "It's 42." and len(bodies) == 2                  # the slip, then the same request once more
    assert "tools" not in bodies[1] and not any(m.get("role") == "tool" for m in bodies[1]["messages"])
    assert any(m.get("content") == tool_slips.PLAIN_TEXT_NOTE for m in bodies[1]["messages"])
    bodies.clear()                                                          # the next call is the first again: a slip
    r = asyncio.run(agent.run("what is six times seven, roughly, in words"))
    assert r.text == "It's 42." and bodies[1]["messages"][-1] == {"role": "system", "content": tool_slips.TOOL_RETRY_NOTE}


def test_camera_and_microphone_problems_go_to_the_tools_and_get_a_real_check(monkeypatch):
    from ginkassistant.services.actions import agent, health
    from ginkassistant.services.actions.tools import TOOL_SPECS
    for text in ("can you run some check for why my camera is not working", "my microphone isn't working",
                 "why won't my wifi connect", "my bluetooth keeps disconnecting", "troubleshoot my printer"):
        assert agent.looks_like_action(text), text
    for text in ("why is the sky blue", "how does a camera work", "write a poem about screens"):
        assert not agent.looks_like_action(text), text
    spec = next(t for t in TOOL_SPECS if t["function"]["name"] == "device_check")["function"]
    assert spec["parameters"]["properties"]["focus"]["enum"] == ["all", "camera", "microphone"]
    assert 'focus "camera" or "microphone"' in agent._system_prompt()
    # Linux: the cameras the system has, and the apps that usually hold one
    monkeypatch.setattr(health, "MAC", False); monkeypatch.setattr(health, "WIN", False)
    monkeypatch.setattr(health, "ANDROID", False); monkeypatch.setattr(health, "IOS", False)
    monkeypatch.setattr(health.sys, "platform", "linux")
    monkeypatch.setattr(health.os, "listdir", lambda d: ["video0", "null"] if d == "/dev" else [])
    runs = []

    def fake_run(cmd, timeout=20):
        runs.append(cmd[0])
        if cmd[0] == "ps":
            return True, "COMMAND\nzoom\nbash\n"
        return False, ""
    monkeypatch.setattr(health, "run", fake_run)
    r = health.check_device(focus="camera")
    assert r["ok"] and r["report"]["cameras"] == ["video0"] and r["report"]["call_apps_open"] == ["Zoom"]
    assert any("Zoom" in i["what"] for i in r["issues"]) and "permission" in r["report"]["if_one_app_fails"]
    assert "storage" not in r["report"]                                     # a camera check, not the whole device
    monkeypatch.setattr(health.os, "listdir", lambda d: [])
    r = health.check_device(focus="camera")
    assert r["report"]["cameras"] == "none found" and r["issues"][0]["what"] == "No camera was found."
    assert "Cameras" in health.format_report(r)


def test_the_chat_never_shows_raw_errors_and_hands_requests_to_the_agent():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert 'f"[error]' not in main and 'reply = "[error]' not in main             # no raw error text anywhere
    assert "except UseTools:" in main and "agent_reply = await with_tools()" in main
    assert "brain.actions_ok = not images and" in main and "friendly_problem(exc)" in main
    from ginkassistant.services import tool_slips
    assert tool_slips.friendly(RuntimeError("Groq 400: Tool choice is none, but model called a tool")) == tool_slips.NO_ANSWER
    assert tool_slips.friendly(RuntimeError("All connection attempts failed")) == tool_slips.OFFLINE
    assert "[error]" not in tool_slips.friendly(ValueError("boom"))


def test_the_server_and_the_apps_agree_on_what_a_slip_is():
    from ginkassistant.services import backend_server as b, tool_slips
    assert b.TOOL_SLIP_WORDS == tool_slips.TOOL_SLIP_WORDS and b.PLAIN_TEXT_NOTE == tool_slips.PLAIN_TEXT_NOTE
    assert b.TOOL_RETRY_NOTE == tool_slips.TOOL_RETRY_NOTE and b.NO_ANSWER == tool_slips.NO_ANSWER
    assert b.STOPPED_EARLY == tool_slips.STOPPED_EARLY


def _chat_screen(tmp_path, monkeypatch, ask):
    """The real main screen (Toga dummy) with GroqBrain.ask replaced by `ask`: returns (send, js calls, app)."""
    import toga  # noqa: F401
    import ginkassistant.app as app_mod
    from ginkassistant.app import GinkAssistantApp
    from ginkassistant.ui import main_screen, web_chat_view
    from ginkassistant.services.groq_worker import GroqBrain
    monkeypatch.setattr(app_mod, "is_desktop", lambda: False)
    app = GinkAssistantApp("Gink", "com.amgib.ginkassistant")
    monkeypatch.setattr(type(app.paths), "data", property(lambda self: tmp_path), raising=False)
    app._setup_task_system()
    queued, calls = [], []

    async def poll(self):
        return queued.pop(0) if queued else []

    async def js(self, script):
        calls.append(script)

    async def quiet(*a, **k):
        return None
    monkeypatch.setattr(web_chat_view.WebChatFeed, "_js", js)
    monkeypatch.setattr(web_chat_view.WebChatFeed, "poll", poll)
    monkeypatch.setattr(main_screen.voice_bridge, "speak", quiet)
    monkeypatch.setattr(GroqBrain, "ask", ask)
    return queued, calls, app, main_screen


def test_a_hand_off_runs_the_agent_in_the_same_reply_and_errors_end_the_row(tmp_path, monkeypatch):
    from ginkassistant.services.groq_worker import UseTools
    from ginkassistant.services.actions.agent import AgentReply, TaskAgent
    from ginkassistant.services import tool_slips
    seen = {}

    async def ask(self, query, **k):
        seen["actions_ok"] = self.actions_ok
        if "boom" in query:
            raise RuntimeError("Tool choice is none, but model called a tool")
        raise UseTools()

    async def run(self, text, **k):
        seen["agent"] = text
        return AgentReply("Your camera is in use by Zoom: quit Zoom and try again.",
                          [{"tool": "device_check", "args": {"focus": "camera"}, "result": {"ok": True}}])
    monkeypatch.setattr(TaskAgent, "run", run)
    queued, calls, app, main_screen = _chat_screen(tmp_path, monkeypatch, ask)

    async def go():
        main_screen.build_main_screen(app, "ibrahim.kargbo@example.com")
        app.task_agent.api_key = "k"                                        # the agent can reach the AI
        queued.append([{"type": "send", "value": "the light by my screen stays off in calls"}])
        for _ in range(40):
            await asyncio.sleep(0.05)
        queued.append([{"type": "send", "value": "boom"}])
        for _ in range(40):
            await asyncio.sleep(0.05)
    asyncio.run(go())
    assert seen["agent"] == "the light by my screen stays off in calls"     # the AI handed it over: the agent did it
    finals = [c for c in calls if c.startswith("finalizeMessage(")]
    assert len(finals) == 2 and "quit Zoom" in finals[0]                    # the agent's answer, in the same row
    assert "tripped over" in finals[1] and tool_slips.NO_ANSWER.startswith("The AI service tripped over")
    assert not any("[error]" in c for c in calls)                           # never the raw error
