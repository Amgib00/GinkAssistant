"""
How good is a model at Gink's actions? Scores it on the held-out eval set (never trained on).

    python tools/gink_dataset/evaluate.py --base-url https://gink-server.onrender.com/v1 \\
        --model gink-crystal            # API key: asked for (hidden), or GINK_EVAL_KEY

Works with any OpenAI-style endpoint: your Gink Developer API (today's models, as a baseline),
or your own fine-tuned model served with vLLM / llama.cpp. A Gink model is worth shipping
only if it beats the baseline here.
Each action example scores 1 when the model calls the RIGHT tool with the RIGHT arguments
(times and dates exact; free text compared loosely). Examples without a tool score 1 when
the model answers without calling one.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOOSE = {"text", "label", "title", "content", "fact", "body", "prompt", "notes", "query"}   # free wording


def same_args(tool, want, got):
    for k, v in want.items():
        if k not in got:
            return False
        if k in LOOSE:
            a, b = str(v).lower(), str(got[k]).lower()
            if tool == "create_file" and k == "content":
                continue                                       # any good content is fine
            if not (a in b or b in a or len(set(a.split()) & set(b.split())) >= max(1, len(a.split()) // 2)):
                return False
        elif isinstance(v, str) and isinstance(got[k], str):
            if v.strip().lower() != got[k].strip().lower():
                return False
        elif isinstance(v, (int, float)) and isinstance(got[k], (int, float)):
            if abs(v - got[k]) > 1e-6:
                return False
        elif v != got[k]:
            return False
    return True


def ask(base_url, key, model, messages, tools):
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 600}
    if tools:
        body.update(tools=tools, tool_choice="auto")
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]


def evaluate(base_url, key, model, rows, tools, out=print):
    per_tool, score = {}, 0
    for i, ex in enumerate(rows, 1):
        msgs = ex["messages"]
        want = next((c for m in msgs for c in m.get("tool_calls") or []), None)
        prompt = [m for m in msgs[:2]]                                      # system + user, as a real turn starts
        try:
            reply = ask(base_url, key, model, prompt, tools)
        except Exception as e:
            out(f"  {i}: request failed ({e})"); reply = {}
        calls = reply.get("tool_calls") or []
        name = want["function"]["name"] if want else "(no tool)"
        if want:
            ok = bool(calls) and calls[0]["function"]["name"] == name
            if ok:
                try:
                    ok = same_args(name, json.loads(want["function"]["arguments"]), json.loads(calls[0]["function"].get("arguments") or "{}"))
                except ValueError:
                    ok = False
        else:
            ok = not calls
        score += ok
        t = per_tool.setdefault(name, [0, 0]); t[0] += ok; t[1] += 1
    out(f"\n{model}: {score}/{len(rows)} correct ({100 * score / max(1, len(rows)):.0f}%)")
    for name, (good, n) in sorted(per_tool.items()):
        out(f"  {name:18} {good}/{n}")
    return score / max(1, len(rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--file", default=os.path.join(HERE, "out", "eval.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    key = os.environ.get("GINK_EVAL_KEY") or getpass.getpass("API key (hidden): ")
    rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    rows = rows[:a.limit] if a.limit else rows
    tools = json.load(open(os.path.join(os.path.dirname(a.file), "tools.json"), encoding="utf-8"))
    evaluate(a.base_url, key, a.model, rows, tools)


if __name__ == "__main__":
    main()
