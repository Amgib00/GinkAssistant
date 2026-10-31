"""Tests run the same everywhere: never with the developer's real .env (server address, AI keys...).

app.py loads the project's .env when imported. On the owner's Mac that made tests use the real Render
address and even call the real AI ("Wake Up Reminder"). GitHub has no .env, so this matches it."""
import dotenv
import dotenv.main

_no_dotenv = lambda *a, **k: False
dotenv.load_dotenv = _no_dotenv
dotenv.main.load_dotenv = _no_dotenv
