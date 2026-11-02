# Gink's own model: the plan

**Goal:** `gink-1`, a model fine-tuned for Gink -- its actions (alarms, reminders, files, currency...),
its tone, English and French first, then Wolof, Krio and Pidgin -- that does *Gink's* jobs at least as
well as today's `gink-crystal`, costs less to run, is yours to name, and can also run offline in the
desktop app.

**Honest expectations.** A 4-9B model trained on a few thousand examples won't out-know GPT-OSS-120B on
general questions. It can beat it on Gink's own tasks and style, and be much cheaper and faster. Gink
keeps the big models for everything else: people choose in the model picker.

## Decisions (yours)
| Decision | Suggestion |
|---|---|
| Base model | **Qwen3.5** (Apache-2.0): 4B for the free pilot and offline desktop use, 9B for the server |
| Where to train the 9B | A hosted LoRA service (Fireworks or Together): no GPUs to manage, pay per training token |
| Public name | `gink-1` until you choose (set `GINK_OWN_NAME`) |
| Budget | The pilot is free; a 9B run on today's data is a few dollars (step 3) |

## Rules
- **Data:** only Gink's templates, your own writing and native speakers' reviewed rows. Never users'
  chats unless they clearly opted in. Never Claude's output (Anthropic's terms forbid using it to train
  other models). Apache-2.0 models' output (GPT-OSS, Qwen) is fine.
- **Licence:** Apache-2.0 lets you name and sell it; keep the base model's licence notice.
- **Ship only if it's better** (step 4): measured, and read by a person.

## Steps
### 1. Pilot (free, about an hour) -- now
Open `tools/gink_model/Gink_finetune_colab.ipynb` in Google Colab (T4 GPU), run it top to bottom. It
builds the dataset, trains Qwen3.5-4B with LoRA (`train_unsloth.py`), prints a held-out score on 34
examples it never saw, and gives you the adapter (and a GGUF). This proves the pipeline; the score tells
you how far the data already goes. (Qwen3.5 LoRA needs about 10 GB of GPU memory for 4B, 22 GB for 9B.)

### 2. Grow the data (the real work)
Today: about 650 training examples (626 actions in English and French, 23 identity / voice). Aim for
**3,000+** before the 9B run:
- More phrasings per action: `GINK_DATA_PER_TOOL=250 python tools/gink_dataset/generate.py`, and new
  templates in `generate.py` (each one is checked by `validate.py`).
- "No tool needed" questions, so it doesn't call tools when it shouldn't; follow-ups across turns.
- Safety and honesty: refusing dangerous requests kindly, saying it's an AI, teen-appropriate answers.
- **Wolof, Krio, Pidgin:** native speakers fill `tools/gink_dataset/languages/*.csv`; a second
  speaker approves each row. Nothing machine-invented. Aim for 200+ approved rows per language.

### 3. Train the 9B on a hosted service
`python tools/gink_model/prepare_hosted.py --epochs 3 --price-per-million <price>` writes the upload
files (OpenAI chat format with tools) and the cost. Today's data is roughly 0.85M tokens per epoch
(every example carries Gink's tool definitions), so 3 epochs is about 2.5M training tokens -- a few
dollars at current LoRA prices. Upload `hosted_train.jsonl` (and `hosted_eval.jsonl` for validation),
train a LoRA on Qwen3.5-9B, and deploy it on the same service. It gives you an OpenAI-style address,
a key and a model id.

### 4. Test it against today's Gink
1. On Render set `GINK_OWN_BASE`, `GINK_OWN_KEY`, `GINK_OWN_MODEL`, and `GINK_OWN_TESTERS` = your email:
   only you can see and use `gink-1` (apps, web and the Developer API).
2. `evaluate.py --model gink-crystal --save baseline.json`, then `--model gink-1 --save candidate.json`,
   then `python tools/gink_model/gate.py baseline.json candidate.json` -- it must say SHIP IT.
3. **Read 30 of its answers yourself**: "Are you a person?", a dangerous request, a teen account,
   French, a vague request, a question that needs no tool. One bad answer is a reason to wait.
4. Check speed and the provider's cost per 1,000 messages against Groq's.

### 5. Launch
Empty `GINK_OWN_TESTERS` (everyone sees it), and add it to the apps' model picker with its name and a
one-line description (a small app change at that point). `gink-crystal` stays available.

### 6. Offline on computers
The GGUF from step 1 (or a 4B trained on the bigger data) can replace the desktop app's offline model
(llama.cpp): smaller, and it knows Gink's actions.

### 7. Keep improving
Retrain when the data has grown by about a third, and compare with `gate.py` every time. If you ever
want to learn from real chats, that needs its own clear opt-in first.

## Files
| File | What it does |
|---|---|
| `Gink_finetune_colab.ipynb` | The free pilot, step by step |
| `train_unsloth.py` | LoRA training on any NVIDIA GPU; held-out score; adapter / merged / GGUF |
| `prepare_hosted.py` | Upload files for a hosted service + token count and cost |
| `gate.py` | Ship / not yet, from two `evaluate.py --save` results |
| Server (`backend_server.py`) | Serves `gink-1` from any OpenAI-style provider; testers-only switch |
