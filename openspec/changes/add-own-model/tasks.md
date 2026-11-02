## 1. Build
- [x] 1.1 tools/gink_model (plan, notebook, train / prepare / gate), evaluate.py --save
- [x] 1.2 Server routing (own provider, testers, no fallback, models list per account)
- [x] 1.3 Safety classifier off the retired Groq model
- [x] 1.4 Tests: tests/test_gink_model_tools.py, tests/test_own_model.py
- [x] 1.5 Growing the data: paraphrase.py (GPT-OSS rewrites, fact checks, paraphrases.csv), examples_general.csv
      (people-written, second-person approval), a held-out set chosen by content (stable as data grows),
      validate.py progress toward the targets; tests/test_grow_dataset.py
- [x] 1.6 Apps' model picker lists own models the server offers ("Gink 1", More models); the server can name
      the desktop offline model (GINK_OFFLINE_MODEL_URL in /info; model.json; chat templates);
      tests/test_own_model_picker.py, tests/test_offline_model.py

## 2. Owner
- [ ] 2.1 Pilot in Colab (Qwen3.5-4B); note the held-out score
- [ ] 2.2 Grow the dataset to 3,000+: run paraphrase.py and skim paraphrases.csv; people write
      examples_general.csv; native speakers fill languages/*.csv
- [ ] 2.3 Hosted 9B LoRA; set GINK_OWN_* with GINK_OWN_TESTERS = owner
- [ ] 2.4 gate.py says SHIP IT and a person read 30 answers; then launch (model picker)
