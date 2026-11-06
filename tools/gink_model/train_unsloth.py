"""
Fine-tune Gink's own model: a LoRA on an Apache-2.0 Qwen3.5 model, from the Gink dataset.

Runs where there's an NVIDIA GPU -- Google Colab (free T4 is enough for 2B/4B), RunPod, Lambda...
The easiest way is the notebook next to this file (Gink_finetune_colab.ipynb), which runs this script.

    pip install unsloth                                   # Unsloth installs a matching TRL/transformers
    python tools/gink_dataset/generate.py && python tools/gink_dataset/validate.py
    python tools/gink_model/train_unsloth.py --base unsloth/Qwen3.5-4B --out gink-4b
    python tools/gink_model/train_unsloth.py --base unsloth/Qwen3.5-4B --out gink-4b --gguf q4_k_m
    python tools/gink_model/train_unsloth.py --data tools/gink_model/out/mix ...   # chat + Genie (build_mix.py)

What it does, and why:
  * bf16 LoRA (not 4-bit QLoRA): Unsloth advises against QLoRA for Qwen3.5.
  * The SAME chat template and tool definitions the model will see when Gink calls it, so tool calls
    come out in the format servers (vLLM, Fireworks, Together, llama.cpp) turn into OpenAI tool_calls.
  * It learns only Gink's replies (not the system prompt or the user's words).
  * "Thinking" is off: Gink's examples are direct answers; Qwen's reasoning mode isn't trained.
  * At the end: a quick score on the held-out eval set (never trained on), with the same rules as
    tools/gink_dataset/evaluate.py -- then the LoRA adapter, and optionally merged weights / GGUF.
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "gink_dataset", "out")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gink_dataset"))


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def for_template(messages):
    """Gink's dataset -> what HF chat templates expect: tool-call arguments as objects."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = dict(c["function"])
                if isinstance(fn.get("arguments"), str):
                    try:
                        fn["arguments"] = json.loads(fn["arguments"])
                    except ValueError:
                        pass
                calls.append({"type": "function", "function": fn})
            m["tool_calls"] = calls
            m["content"] = m.get("content") or ""
        out.append(m)
    return out


def render(tokenizer, messages, tools, add_generation_prompt=False):
    """The chat template with Gink's tools, thinking off when the template supports it."""
    kw = dict(tools=tools, tokenize=False, add_generation_prompt=add_generation_prompt)
    try:
        return tokenizer.apply_chat_template(for_template(messages), enable_thinking=False, **kw)
    except TypeError:
        return tokenizer.apply_chat_template(for_template(messages), **kw)


TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse_tool_calls(text):
    """Qwen writes <tool_call>{"name": ..., "arguments": {...}}</tool_call>."""
    calls = []
    for raw in TOOL_CALL.findall(text or ""):
        try:
            obj = json.loads(raw)
            calls.append({"name": obj.get("name", ""), "arguments": obj.get("arguments") or {}})
        except ValueError:
            continue
    return calls


def score(example, generated_text):
    """1 if the reply does what the example wants (same rules as evaluate.py), else 0."""
    from evaluate import same_args
    want = next((c for m in example["messages"] for c in m.get("tool_calls") or []), None)
    calls = parse_tool_calls(generated_text)
    if not want:
        return int(not calls)
    if not calls or calls[0]["name"] != want["function"]["name"]:
        return 0
    try:
        wanted = json.loads(want["function"]["arguments"])
    except ValueError:
        return 0
    got = calls[0]["arguments"] if isinstance(calls[0]["arguments"], dict) else {}
    return int(same_args(want["function"]["name"], wanted, got))


def accepts(cls, new: str, old: str) -> str:
    """The keyword this library version takes (TRL renames arguments between releases)."""
    import inspect
    try:
        return new if new in inspect.signature(cls.__init__).parameters else old
    except (TypeError, ValueError):
        return old


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="unsloth/Qwen3.5-4B", help="an Apache-2.0 base, e.g. unsloth/Qwen3.5-2B, -4B, -9B")
    ap.add_argument("--data", default=DATA, help="folder with train.jsonl, eval.jsonl, tools.json")
    ap.add_argument("--out", default="gink-model")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--eval-limit", type=int, default=34, help="how many held-out examples to score at the end")
    ap.add_argument("--merged", action="store_true", help="also save merged 16-bit weights (for vLLM / providers)")
    ap.add_argument("--gguf", default="", help="also save GGUF for llama.cpp, e.g. q4_k_m")
    a = ap.parse_args()

    train_rows = load_jsonl(os.path.join(a.data, "train.jsonl"))
    eval_rows = load_jsonl(os.path.join(a.data, "eval.jsonl"))
    tools = json.load(open(os.path.join(a.data, "tools.json"), encoding="utf-8"))
    print(f"Training on {len(train_rows)} examples, scoring on {len(eval_rows)} held-out ones.")

    from unsloth import FastLanguageModel                      # noqa: imported here: GPU machines only
    model, tokenizer = FastLanguageModel.from_pretrained(model_name=a.base, max_seq_length=a.max_len,
                                                         load_in_4bit=False, dtype=None)
    model = FastLanguageModel.get_peft_model(
        model, r=a.rank, lora_alpha=a.rank, lora_dropout=0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=2026)

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    texts = [render(tokenizer, r["messages"], r.get("tools") or tools) for r in train_rows]   # a line's own tools (build_mix.py)
    longest = max(len(tokenizer(t)["input_ids"]) for t in texts[:50])
    print(f"Example length: up to ~{longest} tokens (max {a.max_len}).")
    cfg = dict(dataset_text_field="text", per_device_train_batch_size=a.batch,
               gradient_accumulation_steps=a.accum, warmup_steps=5, num_train_epochs=a.epochs,
               learning_rate=a.lr, logging_steps=10, optim="adamw_8bit", weight_decay=0.01,
               lr_scheduler_type="linear", seed=2026, output_dir=os.path.join(a.out, "checkpoints"), report_to="none")
    cfg[accepts(SFTConfig, "max_length", "max_seq_length")] = a.max_len        # TRL renamed it
    trainer = SFTTrainer(model=model, train_dataset=Dataset.from_dict({"text": texts}), args=SFTConfig(**cfg),
                         **{accepts(SFTTrainer, "processing_class", "tokenizer"): tokenizer})
    try:                                                      # learn Gink's replies only
        from unsloth.chat_templates import train_on_responses_only
        trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\n",
                                          response_part="<|im_start|>assistant\n")
    except Exception as exc:
        print(f"(training on whole conversations: {exc})")
    trainer.train()

    FastLanguageModel.for_inference(model)
    rows = eval_rows[:a.eval_limit]
    good = 0
    for ex in rows:
        prompt = render(tokenizer, ex["messages"][:2], ex.get("tools") or tools, add_generation_prompt=True)
        ids = tokenizer(prompt, return_tensors="pt").to(model.device)
        out = model.generate(**ids, max_new_tokens=300, do_sample=False)
        text = tokenizer.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=False)
        good += score(ex, text)
    print(f"\nHeld-out score: {good}/{len(rows)} ({100 * good / max(1, len(rows)):.0f}%). "
          "Compare with today's model: python tools/gink_dataset/evaluate.py --model gink-crystal ...")

    model.save_pretrained(os.path.join(a.out, "lora"))
    tokenizer.save_pretrained(os.path.join(a.out, "lora"))
    print(f"Saved the LoRA adapter: {a.out}/lora")
    if a.merged:
        model.save_pretrained_merged(os.path.join(a.out, "merged"), tokenizer, save_method="merged_16bit")
        print(f"Saved merged weights: {a.out}/merged")
    if a.gguf:
        model.save_pretrained_gguf(os.path.join(a.out, "gguf"), tokenizer, quantization_method=a.gguf)
        print(f"Saved GGUF: {a.out}/gguf")
    with open(os.path.join(a.out, "GINK_MODEL.json"), "w", encoding="utf-8") as f:
        json.dump({"base": a.base, "examples": len(train_rows), "epochs": a.epochs, "lr": a.lr, "rank": a.rank,
                   "heldout_score": good / max(1, len(rows)), "license": "Apache-2.0 (base model); keep its NOTICE"},
                  f, indent=2)


if __name__ == "__main__":
    random.seed(2026)
    main()
