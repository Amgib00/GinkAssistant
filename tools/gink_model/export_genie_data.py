"""
Download the Gink Genie sessions people chose to share (Settings > Privacy > Help improve Gink) as
training examples for Gink's coding model -- server owner only.

    python tools/gink_model/export_genie_data.py

Asks for the server and your GINK_ADMIN_KEY (hidden), saves genie_training.jsonl here: one request per
line in the OpenAI chat format with Genie's tools, ready for prepare_hosted-style uploads or
train_unsloth.py (--data with this file as train.jsonl and Genie's tools as tools.json).
Keys were removed and private files left out on the server, but keep the file private anyway, never
put it in the GitHub repo, and delete it when you're done training.
"""
import getpass
import json
import os
import ssl
import urllib.error
import urllib.request

try:
    import certifi
    CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CONTEXT = ssl.create_default_context()

server = input("Server [https://gink-server.onrender.com]: ").strip() or "https://gink-server.onrender.com"
key = getpass.getpass("GINK_ADMIN_KEY (hidden): ").strip()
req = urllib.request.Request(server.rstrip("/") + "/admin/training/genie.jsonl",
                             headers={"x-admin-key": key, "User-Agent": "GinkExport/1.0"})
try:
    with urllib.request.urlopen(req, timeout=300, context=CONTEXT) as r, open("genie_training.jsonl", "wb") as f:
        n = 0
        for line in r:
            f.write(line)
            n += 1
    print(f"Saved genie_training.jsonl ({n} examples, {os.path.getsize('genie_training.jsonl') // 1024} KB). Keep it private.")
except urllib.error.HTTPError as e:
    try:
        print("Refused:", json.load(e).get("detail"))
    except Exception:
        print("Refused: HTTP", e.code)
except Exception as e:
    print("Couldn't reach the server:", e)
