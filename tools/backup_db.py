"""
Download a copy of the Gink server's database (every account, synced chat and payment) --
server owner only.

    python tools/backup_db.py

Asks for the server address and your GINK_ADMIN_KEY (hidden as you type, so it isn't saved in
your Terminal history), then saves gink-backup-<date>.db in the current folder.
Find GINK_ADMIN_KEY in Render: gink-server -> Environment (Render generated it).

Keep the file private (it holds everyone's accounts), and never put it in the GitHub repo.
To restore it, see deploy/README.md, "Backups".
"""
import getpass
import json
import os
import re
import urllib.error
import urllib.request

server = input("Server [https://gink-server.onrender.com]: ").strip() or "https://gink-server.onrender.com"
key = getpass.getpass("GINK_ADMIN_KEY (hidden): ").strip()
req = urllib.request.Request(server.rstrip("/") + "/admin/backup", headers={"x-admin-key": key})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        found = re.search(r'filename="?([^";]+)"?', r.headers.get("Content-Disposition", ""))
        name = os.path.basename(found.group(1)) if found else "gink-backup.db"
        with open(name, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
    print(f"Saved {name} ({os.path.getsize(name) // 1024} KB). Keep it somewhere private.")
except urllib.error.HTTPError as e:
    try:
        print("Refused:", json.load(e).get("detail"))
    except Exception:
        print("Refused: HTTP", e.code)
except Exception as e:
    print("Couldn't reach the server:", e)
