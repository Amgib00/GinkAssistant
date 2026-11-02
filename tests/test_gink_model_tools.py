"""tools/gink_model: the fine-tuning pipeline's pieces that run without a GPU."""
import json, os, subprocess, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "gink_model"))
sys.path.insert(0, os.path.join(ROOT, "tools", "gink_dataset"))
import pytest
import train_unsloth as tu
import prepare_hosted as ph
import gate


@pytest.fixture(scope="module")
def data():
    out = os.path.join(ROOT, "tools", "gink_dataset", "out")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gink_dataset", "generate.py")], check=True,
                   capture_output=True)
    rows = [json.loads(l) for l in open(os.path.join(out, "eval.jsonl"), encoding="utf-8")]
    yield out, rows
    import shutil
    shutil.rmtree(out, ignore_errors=True)                     # generated: never published


def test_template_input_has_object_arguments(data):
    _, rows = data
    ex = next(r for r in rows if any(m.get("tool_calls") for m in r["messages"]))
    fixed = tu.for_template(ex["messages"])
    call = next(m for m in fixed if m.get("tool_calls"))["tool_calls"][0]
    assert isinstance(call["function"]["arguments"], dict) and call["type"] == "function"
    assert isinstance(next(m for m in ex["messages"] if m.get("tool_calls"))["tool_calls"][0]["function"]["arguments"], str)


def test_render_turns_thinking_off_when_it_can():
    seen = {}

    class New:
        def apply_chat_template(self, messages, enable_thinking=True, **kw):
            seen.update(thinking=enable_thinking, tools=kw.get("tools")); return "x"

    class Old:
        def apply_chat_template(self, messages, **kw):
            seen.update(old=True); return "y"
    assert tu.render(New(), [], ["t"]) == "x" and seen["thinking"] is False and seen["tools"] == ["t"]
    assert tu.render(Old(), [], []) == "y" and seen["old"]


def test_scoring_reads_qwen_tool_calls(data):
    _, rows = data
    ex = next(r for r in rows if any(m.get("tool_calls") for m in r["messages"]))
    want = next(c for m in ex["messages"] for c in m.get("tool_calls") or [])
    name, args = want["function"]["name"], json.loads(want["function"]["arguments"])
    good = f'<tool_call>\n{json.dumps({"name": name, "arguments": args})}\n</tool_call><|im_end|>'
    assert tu.parse_tool_calls(good)[0]["name"] == name and tu.score(ex, good) == 1
    assert tu.score(ex, "Sure, done!") == 0                                   # said it, didn't do it
    wrong = dict(args, **{k: ("1999-01-01 00:00" if isinstance(v, str) else 12345) for k, v in args.items()
                          if k not in ("text", "label", "title", "content", "fact", "body", "prompt", "notes", "query")})
    if wrong != args:
        assert tu.score(ex, f'<tool_call>{json.dumps({"name": name, "arguments": wrong})}</tool_call>') == 0
    chat = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "Who are you?"},
                         {"role": "assistant", "content": "I'm Gink, an AI assistant."}]}
    assert tu.score(chat, "I'm Gink, an AI assistant.") == 1                    # no tool wanted, none used
    assert tu.parse_tool_calls("<tool_call>{broken</tool_call>") == []


def test_hosted_files_and_cost(data, tmp_path, capsys):
    out, _ = data
    totals = ph.main(["--data", out, "--out", str(tmp_path), "--epochs", "3", "--price-per-million", "1.5"])
    first = json.loads(open(tmp_path / "hosted_train.jsonl", encoding="utf-8").readline())
    assert set(first) == {"messages", "tools"} and len(first["tools"]) >= 10
    for m in first["messages"]:
        for c in m.get("tool_calls") or []:
            assert isinstance(c["function"]["arguments"], str)                 # OpenAI format
    n, tokens, exact = totals["train"]
    assert n > 500 and tokens > 100_000 and not exact
    printed = capsys.readouterr().out
    assert "Cost at $1.5/M" in printed and f"{n} conversations" in printed


def test_gate():
    base = {"model": "gink-crystal", "score": 0.80, "per_tool": {"set_alarm": [9, 10], "remember": [8, 10]}}
    better = {"model": "gink-1", "score": 0.86, "per_tool": {"set_alarm": [10, 10], "remember": [8, 10]}}
    regress = {"model": "gink-1", "score": 0.85, "per_tool": {"set_alarm": [10, 10], "remember": [5, 10]}}
    worse = {"model": "gink-1", "score": 0.70, "per_tool": {"set_alarm": [7, 10], "remember": [7, 10]}}
    assert gate.decide(base, better) == (True, [])
    ok, why = gate.decide(base, regress)
    assert not ok and "remember" in why[0]                                     # one action clearly worse
    assert not gate.decide(base, worse)[0]
    assert not gate.decide(base, better, margin=0.10)[0]                      # must be 10 points better


def test_evaluate_can_save(monkeypatch, data, tmp_path):
    import evaluate as ev
    _, rows = data
    monkeypatch.setattr(ev, "ask", lambda *a, **k: {"content": "ok"})
    ev.evaluate("http://x", "k", "gink-test", rows[:5], [], out=lambda *a: None)
    assert ev.evaluate.last["model"] == "gink-test" and ev.evaluate.last["total"] == 5


def test_notebook_runs_the_real_scripts():
    nb = json.load(open(os.path.join(ROOT, "tools", "gink_model", "Gink_finetune_colab.ipynb"), encoding="utf-8"))
    src = "".join("".join(c["source"]) for c in nb["cells"])
    for path in ("tools/gink_dataset/generate.py", "tools/gink_dataset/validate.py", "tools/gink_model/train_unsloth.py"):
        assert path in src and os.path.exists(os.path.join(ROOT, path))
    assert "Qwen3.5-4B" in src and nb["metadata"]["accelerator"] == "GPU"
