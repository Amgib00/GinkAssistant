"""
Gink dataset -> a file for a hosted fine-tuning service (Fireworks, Together, ...), and what it costs.

    python tools/gink_dataset/generate.py && python tools/gink_dataset/validate.py
    python tools/gink_model/prepare_hosted.py --epochs 3 --price-per-million 1.5

Writes tools/gink_model/out/hosted_train.jsonl and hosted_eval.jsonl: one conversation per line in the
OpenAI chat format ({"messages": [...], "tools": [...]}, tool-call arguments as JSON strings), which
hosted LoRA services accept for tool-calling fine-tunes -- check your provider's current format page
before uploading. No user data is in it: only Gink's own templates and hand-written examples.

The token count is exact with --tokenizer (needs `pip install transformers`), otherwise an estimate
(about 3.6 characters per token). Training cost = tokens x epochs x the provider's price per million
training tokens, which you look up on their pricing page (prices change).
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "gink_dataset", "out")


def to_hosted(example: dict, tools: list) -> dict:
    msgs = []
    for m in example["messages"]:
        m = {k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_call_id", "name")}
        for c in m.get("tool_calls") or []:
            if not isinstance(c["function"].get("arguments"), str):
                c["function"]["arguments"] = json.dumps(c["function"]["arguments"], ensure_ascii=False)
        msgs.append(m)
    return {"messages": msgs, "tools": tools}


def count_tokens(rows, tokenizer_name: str = "") -> tuple:
    """(tokens, exact?)"""
    if tokenizer_name:
        try:
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(tokenizer_name)
            total = 0
            for r in rows:
                total += len(tok.apply_chat_template(r["messages"], tools=r["tools"], tokenize=True))
            return total, True
        except Exception as exc:
            print(f"(exact count unavailable: {exc}; estimating)")
    return int(sum(len(json.dumps(r, ensure_ascii=False)) for r in rows) / 3.6), False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--price-per-million", type=float, default=0.0, help="the provider's LoRA training price per 1M tokens")
    ap.add_argument("--tokenizer", default="", help="e.g. Qwen/Qwen3.5-9B for an exact count")
    a = ap.parse_args(argv)
    tools = json.load(open(os.path.join(a.data, "tools.json"), encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    totals = {}
    for split in ("train", "eval"):
        rows = [to_hosted(r, r.get("tools") or tools) for r in (json.loads(l) for l in
                open(os.path.join(a.data, f"{split}.jsonl"), encoding="utf-8") if l.strip())]   # a line's own tools if it has them
        path = os.path.join(a.out, f"hosted_{split}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        totals[split] = (len(rows), *count_tokens(rows, a.tokenizer))
        print(f"{split}: {len(rows)} conversations -> {path}")
    n, tokens, exact = totals["train"]
    trained = tokens * a.epochs
    print(f"\nTraining tokens: {'' if exact else '~'}{tokens:,} per epoch x {a.epochs:g} epochs = {'' if exact else '~'}{trained:,.0f}")
    if a.price_per_million:
        print(f"Cost at ${a.price_per_million}/M training tokens: about ${trained / 1e6 * a.price_per_million:,.2f}")
    else:
        print("Add --price-per-million <the provider's LoRA training price> for a cost estimate.")
    return totals


if __name__ == "__main__":
    main()
