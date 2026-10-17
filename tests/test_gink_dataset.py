"""The Gink dataset: generated examples pass the validator, and the validator catches mistakes."""
import copy, json, os, subprocess, sys
HERE = os.path.dirname(__file__)
DS = os.path.join(HERE, "..", "tools", "gink_dataset")
sys.path.insert(0, DS); sys.path.insert(0, os.path.join(HERE, "..", "src"))
import validate as v


def test_generated_dataset_is_valid(tmp_path):
    env = {**os.environ, "GINK_DATA_PER_TOOL": "15"}
    out = subprocess.run([sys.executable, os.path.join(DS, "generate.py")], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    res = subprocess.run([sys.executable, os.path.join(DS, "validate.py")], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0 and "0 with problems" in res.stdout, res.stdout[-800:]


def test_validator_catches_wrong_formats_and_logic():
    base = {"messages": [
        {"role": "system", "content": "You are Gink. It is now Saturday 17 October 2026, 08:15 (Africa/Dakar)."},
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "set_alarm", "arguments": "{\"time\": \"07:00\"}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "content": "Done."}]}
    assert v.check_example(base) == []
    def with_call(name, args):
        ex = copy.deepcopy(base); ex["messages"][2]["tool_calls"][0]["function"] = {"name": name, "arguments": json.dumps(args)}; return ex
    assert v.check_example(with_call("set_alarm", {"time": "7am"}))                                   # not HH:MM
    assert v.check_example(with_call("add_reminder", {"text": "x", "when": "2026-10-16 09:00"}))       # before "now"
    assert v.check_example(with_call("add_reminder", {"text": "x", "when": "tomorrow 9"}))            # not YYYY-MM-DD HH:MM
    assert v.check_example(with_call("media_control", {"action": "louder"}))                          # not an allowed value
    assert v.check_example(with_call("set_timer", {"seconds": "600"}))                                # wrong type
    assert v.check_example(with_call("set_alarm", {"time": "07:00", "snooze": 5}))                    # invented argument
    assert v.check_example(with_call("add_reminder", {"text": "x", "when": "2026-10-18 09:00"})) == []
