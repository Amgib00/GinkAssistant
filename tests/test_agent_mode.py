"""Agent mode: multi-step tasks with a live checklist, and approvals before sensitive actions."""
import asyncio, json, os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.services.actions import agent as ag


def call(i, name, **args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def make(script):
    """A TaskAgent whose AI follows `script` (a list of messages), with a recording runner."""
    executed = []
    async def execute(name, args):
        executed.append(name)
        return {"ok": True, "message": {"set_alarm": "Alarm set for 06:00", "compose_message": "Message ready for Awa",
                                         "lock_screen": "Screen locked"}.get(name, "done")}
    runner = types.SimpleNamespace(execute=execute, memory=None, live=types.SimpleNamespace(city_fn=lambda: "Dakar"),
                                   use_memory=False, reply_language_note=lambda: "", profile_note=lambda: "")
    a = ag.TaskAgent(runner, api_key="test")
    seen = []
    async def chat(messages, use_tools=True):
        seen.append(messages[-1])
        return script.pop(0) if script else {"content": ""}
    a._chat = chat
    return a, executed, seen


def recorder():
    steps, asked = [], []
    async def on_step(i, label, state): steps.append((i, state))
    return steps, asked, on_step


def test_multi_step_with_approval():
    script = [{"content": "", "tool_calls": [call(1, "set_alarm", time="06:00"),
                                             call(2, "compose_message", channel="whatsapp", to="Awa", body="Running late")]},
              {"content": "Your alarm is set and the message to Awa is ready."}]
    a, executed, _ = make(script)
    steps, asked, on_step = recorder()
    async def confirm(tool, args, label): asked.append(label); return True
    r = asyncio.run(a.run("Plan my morning and tell Awa I'm late", on_step=on_step, confirm=confirm))
    assert executed == ["set_alarm", "compose_message"]
    assert asked == ["Send a WhatsApp message to Awa: \u201cRunning late\u201d"]          # only the message asks
    assert steps == [(0, "running"), (0, "done"), (1, "asking"), (1, "running"), (1, "done")]
    assert "message to Awa" in r.text


def test_declined_step_is_not_done_and_is_reported():
    script = [{"content": "", "tool_calls": [call(1, "compose_message", channel="sms", to="Awa", body="hi")]}, {"content": ""}]
    a, executed, seen = make(script)
    steps, asked, on_step = recorder()
    async def confirm(tool, args, label): return False
    r = asyncio.run(a.run("Text Awa hi", on_step=on_step, confirm=confirm))
    assert executed == [] and steps[-1] == (0, "skipped")
    assert seen[-1]["role"] == "tool" and "didn't allow" in seen[-1]["content"]            # the AI is told
    assert "Not done" in r.text and "text message to Awa" in r.text                         # and so is the user


def test_direct_versus_chained_sensitive_steps():
    a, executed, _ = make([{"content": "", "tool_calls": [call(1, "lock_screen")]}, {"content": "Locked."}])
    asked = []
    async def confirm(tool, args, label): asked.append(tool); return True
    asyncio.run(a.run("Please make my screen locked now", confirm=confirm))
    assert executed == ["lock_screen"] and asked == []                  # asked for directly: no question
    a, executed, _ = make([{"content": "", "tool_calls": [call(1, "set_dark_mode", mode="dark")]},
                           {"content": "", "tool_calls": [call(2, "lock_screen")]}, {"content": "Done."}])
    asyncio.run(a.run("Get my computer ready for the night", confirm=confirm))
    assert asked == ["lock_screen"]                                    # Gink's own idea mid-task: asks


def test_voice_turns_unchanged():
    a, executed, _ = make([{"content": "", "tool_calls": [call(1, "compose_message", to="Awa", body="hi")]}, {"content": "Ready."}])
    r = asyncio.run(a.run("Message Awa hi"))
    assert executed == ["compose_message"] and r.text == "Ready."


def test_more_rounds_for_real_tasks():
    assert ag.MAX_ROUNDS >= 12
