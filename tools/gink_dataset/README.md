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
**Who writes the examples matters.** Training data may come from Gink's own templates, from people
(you, testers, native speakers), and from Apache-2.0 models (GPT-OSS, Qwen). It must not come from
Claude: Anthropic's terms don't allow using Claude's output to train other models. That's why Claude
builds the tools here but doesn't write the examples.

### More ways to ask: `paraphrase.py`
GPT-OSS rewrites each action request several ways (`GROQ_API_KEY`); rewrites that change a number, a
time, a day, a name or a currency -- or add a number -- are dropped automatically, so the tool call the
example teaches stays right. Kept rewrites go to `paraphrases.csv`: skim it, set `approved` to `no` for
anything odd, then run `generate.py` again. Rewrites are used for training only, never the held-out set.

### The whole world, not one country
`generate.py` makes the action examples twice: the original set (unchanged, so your rewrites and translations
still match), then the same actions with places, money, time zones and names from everywhere -- Tokyo, São
Paulo, Mumbai, Cairo, yen, rupees, reais... (`GINK_DATA_WORLD_PER_TOOL`, default 60 per tool). Run
`paraphrase.py` again: it only rewrites the new requests.

### Many languages: `translate.py`
GPT-OSS translates action examples, and Gink's short reply, into other languages:
`--languages es,pt,ar` or `--languages all` (22 widely used languages plus 15 African languages). Only
actions whose details stay the same in every language are translated (numbers, times, amounts, places,
app names); every number must survive, place and app names must stay, and the script must be right.
Widely used languages that pass are approved; Hausa, Yoruba, Wolof, Krio, Pidgin and the other
African languages are **drafts** until a native speaker corrects them and sets `approved` to `yes`.
Saved in `translations.csv`, used for training only.

`paraphrase.py --recheck` runs the latest checks again on rows you already have (no AI calls) -- for
example the remember / remind check added after the first review.

### Written by people: `examples_general.csv`
Questions that need **no tool** (so Gink doesn't call tools when it shouldn't), **safety** (declining
something dangerous kindly and saying why), **honesty** (it's an AI; it can be wrong; it doesn't know
what it can't know), and **teen**-appropriate answers. Columns: `language` (en/fr), `category`
(general, safety, honesty, teen), `user_message`, `gink_reply` (warm, short, how Gink should really
answer), `author`, then a **second** person checks it, writes their name in `reviewer` and sets
`approved` to `yes`. Aim for 300.

### Also
- More actions: copy a `gen_...` function in `generate.py`; `validate.py` checks the result.
- More languages: see `languages/README.md`.
- Aim for a few thousand examples before the first real training run, with plenty of
  variety in phrasing.

## Training
The plan and the scripts are in `tools/gink_model/` (start with `PLAN.md`): a free Colab pilot, hosted
training for the bigger model, and a ship / not-yet gate. In short:

### The short version
1. Rent a GPU (Google Colab, RunPod, Lambda...) and fine-tune a small open model with **LoRA**
   (Unsloth, TRL or Axolotl all read this JSONL "messages" format).
2. Measure it with `evaluate.py` against the **baseline** (today's `gink-crystal`). Ship it only
   if it's better at Gink's tasks, and still safe and honest.
3. Serve it (vLLM gives an OpenAI-style API your server can use as another provider), or
   convert it to GGUF for the desktop app's offline AI (llama.cpp).
