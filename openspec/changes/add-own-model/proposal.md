## Why

Gink runs on other companies' models. A model fine-tuned for Gink's actions, tone and languages can be
cheaper, faster, named by Gink, and run offline -- if it's measured to be at least as good first.

## What Changes

- tools/gink_model: PLAN.md (pilot -> more data -> hosted 9B -> test -> launch), a free Colab notebook,
  train_unsloth.py (bf16 LoRA on Apache-2.0 Qwen3.5, held-out score, adapter / merged / GGUF),
  prepare_hosted.py (upload files + cost), gate.py (ship / not yet); evaluate.py --save.
- Server: serves the own model from any OpenAI-style provider (GINK_OWN_BASE/KEY/MODEL), under
  GINK_OWN_NAME (default gink-1), only for GINK_OWN_TESTERS while testing; no silent fallback to
  another model; no automatic web search swap; teen safety and limits apply as for every model.
- Fix: the teen safety classifier used llama-3.1-8b-instant, which Groq retired on 16 Aug 2026 (every
  check would have failed and no notice would ever be sent). Now GPT-OSS 20B with low reasoning effort.

Out of scope: the training itself (owner's runs), adding it to the apps' model picker (at launch).

## Impact

- New spec: own-model. Server only; the apps already list whatever /models returns for the account.
