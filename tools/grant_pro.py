"""
Give an existing Gink account Pro (for testing, gifts or support) -- server owner only.

    python tools/grant_pro.py

Asks for the server address, your GINK_ADMIN_KEY (hidden as you type, so it isn't saved
in your Terminal history), the account's email and the number of days.
Find GINK_ADMIN_KEY in Render: gink-server -> Environment (Render generated it).
"""
import getpass
import json
import urllib.error
import urllib.request

server = input("Server [https://gink-server.onrender.com]: ").strip() or "https://gink-server.onrender.com"
key = getpass.getpass("GINK_ADMIN_KEY (hidden): ").strip()
email = input("Account email: ").strip()
days = input("Days of Pro [30]: ").strip() or "30"
req = urllib.request.Request(server.rstrip("/") + "/admin/grant-pro", method="POST",
                             data=json.dumps({"email": email, "days": int(days)}).encode(),
                             headers={"Content-Type": "application/json", "x-admin-key": key})
try:
    with urllib.request.urlopen(req, timeout=90) as r:          # a sleeping free-plan server needs time to wake
        out = json.load(r)
    print(f"Done: {out['email']} has Gink Pro until {out['pro_until_date']}.")
except urllib.error.HTTPError as e:
    try:
        print("Refused:", json.load(e).get("detail"))
    except Exception:
        print("Refused: HTTP", e.code)
except Exception as e:
    print("Couldn't reach the server:", e)
