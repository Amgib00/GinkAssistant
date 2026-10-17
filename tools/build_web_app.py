"""
Builds Gink on the web:  src/ginkassistant/services/web_app/index.html

    python tools/build_web_app.py

= the app's own chat page (ui/web_chat_view.py: sidebar, composer, Settings, themes)
+ the sign-in screen (webapp/signin.html) + the browser bridge (webapp/bridge.js).
The server serves it at /app (backend_server.py). Run this after changing the chat
page or webapp/*; tests/test_web_app.py fails if the built file is out of date.
"""
import base64
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "index.html")
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")


def build_html():
    from ginkassistant.ui.web_chat_view import _build_page_html
    page = _build_page_html("Hi, what\u2019s on your mind?", "")
    icon = "data:image/png;base64," + base64.b64encode(
        open(os.path.join(ROOT, "icons", "ginkassistant-128.png"), "rb").read()).decode()
    signin = open(os.path.join(ROOT, "webapp", "signin.html"), encoding="utf-8").read().replace("__ICON__", icon)
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    head = ('<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Gink</title><link rel="icon" href="{icon}"><meta name="theme-color" content="#151D23">')
    page = page.replace("<head>", "<head>" + head, 1) if "<head>" in page else head + page
    i = page.rindex("</body>")
    return ("<!-- Built by tools/build_web_app.py -- edit webapp/* or the app's chat page, not this file. -->\n"
            + page[:i] + signin + "\n<script>\n" + bridge + "\n</script>\n" + page[i:])


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    html = build_html()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {os.path.relpath(OUT, ROOT)} ({len(html) // 1024} KB)")
