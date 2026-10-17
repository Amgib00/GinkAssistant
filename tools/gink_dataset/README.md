# The Gink dataset: the first step to Gink's own model

A fine-tuned model is only as good as its examples. This folder builds them, checks them, and
measures any model against them.

```bash
python tools/gink_dataset/generate.py     # -> out/train.jsonl, out/eval.jsonl, out/tools.json
python tools/gink_dataset/validate.py     # must say "0 with problems" before any training
python tools/gink_dataset/evaluate.py --base-url https://gink-server.onrender.com/v1 --model gink-crystal
```

## What's in it
| Part | Source | Why it's trustworthy |
|---|---|---|
| **Actions**: 11 everyday tasks with Gink's real tools, English + French | `generate.py` templates | Each example states its own date and time; the right arguments are *computed* from it |
| **Identity and tone** | `examples_identity.jsonl` (hand-written) | Honest about being an AI built on open models |
| **Voice style** | `examples_voice.jsonl` (hand-written) | Short, natural spoken answers |
| **Wolof, Krio, Pidgin** | `languages/*.csv`, filled in by **native speakers** | Only rows a second speaker approved are used |

`out/` is generated: it isn't stored on GitHub, and `generate.py` rebuilds it identically.

## Rules that protect you
- **Never train on users' chats** unless they clearly agreed to it first.
- **Don't generate training data with Claude**: Anthropic's terms don't allow using its output to
  build competing models. Gink's own templates, your writing, and Apache-2.0 models (GPT-OSS, Qwen)
  are fine.
- **Choose an Apache-2.0 base model** (Qwen or GPT-OSS) so you can name it Gink and use it
  commercially; keep its licence notice. Llama requires "Llama" in derived models' names.

## Growing it
- More actions: copy a `gen_...` function in `generate.py`; `validate.py` checks the result.
- More languages: see `languages/README.md`.
- Aim for a few thousand examples before the first real training run, with plenty of
  variety in phrasing.

## Training (when the data is ready)
1. Rent a GPU (Google Colab, RunPod, Lambda...) and fine-tune a small open model with **LoRA**
   (Unsloth, TRL or Axolotl all read this JSONL "messages" format).
2. Measure it with `evaluate.py` against the **baseline** (today's `gink-crystal`). Ship it only
   if it's better at Gink's tasks, and still safe and honest.
3. Serve it (vLLM gives an OpenAI-style API your server can use as another provider), or
   convert it to GGUF for the desktop app's offline AI (llama.cpp).
