"""
One training file from several sources, for a model that does both Gink's chat actions and Genie's
coding work.

    python tools/gink_dataset/generate.py
    python tools/gink_model/export_genie_data.py                 # the opted-in Genie sessions (owner)
    python tools/gink_model/build_mix.py --genie genie_training.jsonl --genie-share 0.4
    python tools/gink_model/train_unsloth.py --data tools/gink_model/out/mix --base unsloth/Qwen3.5-9B ...

Every line keeps its own tools (chat examples get Gink's tools, Genie examples Genie's), so one model
learns both. --genie-share caps how much of the mix is Genie's (so coding doesn't crowd out Gink's
actions and languages, or the other way round). Exact duplicates are dropped; lines that aren't a valid
conversation (roles, tool calls with JSON arguments, tool results answering a call) are skipped and
counted. The held-out chat examples are copied as they are for scoring.
"""
import argparse
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "gink_dataset", "out")


def valid(row) -> bool:
    msgs = row.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 2:
        return False
    open_calls = set()
    for m in msgs:
        role = m.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            return False
        for c in m.get("tool_calls") or []:
            try:
                json.loads(c["function"]["arguments"]) if isinstance(c["function"]["arguments"], str) else None
            except (KeyError, TypeError, ValueError):
                return False
            open_calls.add(c.get("id"))
        if role == "tool" and m.get("tool_call_id") not in open_calls:
            return False
    return any(m.get("role") == "assistant" for m in msgs)


def load(path, tools=None):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                if tools is not None and "tools" not in row:
                    row["tools"] = tools
                out.append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=DATA, help="the chat dataset (train.jsonl, eval.jsonl, tools.json)")
    ap.add_argument("--genie", default="", help="Genie sessions (export_genie_data.py)")
    ap.add_argument("--genie-share", type=float, default=0.4, help="at most this share of the mix is Genie's")
    ap.add_argument("--extra", action="append", default=[], help="more JSONL files with their own tools")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "mix"))
    a = ap.parse_args(argv)
    tools = json.load(open(os.path.join(a.data, "tools.json"), encoding="utf-8"))
    chat = load(os.path.join(a.data, "train.jsonl"), tools)
    genie = load(a.genie) if a.genie else []
    extra = [r for p in a.extra for r in load(p)]
    rnd = random.Random(2026)
    if genie and a.genie_share < 1:
        cap = int(a.genie_share / max(1e-9, 1 - a.genie_share) * (len(chat) + len(extra)))
        if len(genie) > cap:
            rnd.shuffle(genie)
            genie = genie[:cap]
    rows, seen, skipped, dupes = [], set(), 0, 0
    for row in chat + genie + extra:
        if not valid(row):
            skipped += 1
            continue
        key = hashlib.sha256(json.dumps(row["messages"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        rows.append({"messages": row["messages"], "tools": row.get("tools") or tools})
    rnd.shuffle(rows)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "train.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    held = load(os.path.join(a.data, "eval.jsonl"))
    with open(os.path.join(a.out, "eval.jsonl"), "w", encoding="utf-8") as f:
        for r in held:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(tools, open(os.path.join(a.out, "tools.json"), "w", encoding="utf-8"))
    n_genie = sum(1 for r in rows if r["tools"] is not tools and any(t["function"]["name"] == "write_file" for t in r["tools"]))
    print(f"{len(rows)} conversations -> {a.out}/train.jsonl  (Genie {n_genie}, chat and others {len(rows) - n_genie}; "
          f"{dupes} duplicates and {skipped} invalid lines left out)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
