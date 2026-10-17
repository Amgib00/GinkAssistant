# Gink in West African languages

These sheets are for **native speakers**. A model trained on mistakes learns the mistakes,
so nothing here is machine-written.

1. Open a sheet (`wolof.csv`, `krio.csv`, `pidgin.csv`) in Excel, Numbers or Google Sheets.
2. For each row: write how a real person would ask the `prompt_idea` in that language
   (`user_message`), then how Gink should answer, warm and short (`gink_reply`).
3. A **second** native speaker checks it, writes their name in `reviewer` and sets
   `approved` to `yes`. Only approved rows are used for training.
4. Add as many new rows as you like: everyday life, family, markets, transport, school, health.

Save as CSV (UTF-8) with the same columns. Run `python tools/gink_dataset/generate.py` to include them.
