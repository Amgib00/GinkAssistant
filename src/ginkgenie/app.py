"""
Gink Genie as an app: the Genie workspace (https://<Gink server>/genie) in its own window, signed in
with the same Gink account. Everything Genie does happens through the server, so the app stays small.

- A toolbar: Home, Back, Reload, Open in browser.
- The page is told it runs in the app (user agent "GinkGenieApp"), so it opens Preview and GitHub in
  the same window; with Toga 0.5+ those links are caught here and opened in the real browser instead.
- If the server is asleep (Render's free plan) or unreachable, a friendly page with Retry.
Server: GINK_SERVER_URL, else <app data>/server.txt (one line), else the public Gink server.
"""
import asyncio
import os
import urllib.request
import webbrowser

import toga
from toga.style import Pack

DEFAULT_SERVER = "https://gink-server.onrender.com"
APP_MARK = "GinkGenieApp/1"


def server_url(data_dir=None) -> str:
    url = os.environ.get("GINK_SERVER_URL", "").strip()
    if not url and data_dir:
        try:
            with open(os.path.join(str(data_dir), "server.txt"), encoding="utf-8") as f:
                url = f.read().strip()
        except OSError:
            pass
    url = url or DEFAULT_SERVER
    return url.rstrip("/") if url.startswith(("https://", "http://")) else DEFAULT_SERVER


def leaves_the_app(url: str, server: str) -> bool:
    """Pages that should open in the real browser: other sites (GitHub...) and project previews."""
    url = str(url or "")
    if url.startswith(("about:", "data:", "blob:")) or not url:
        return False
    if not url.startswith(server + "/") and url != server:
        return True
    return url.startswith(server + "/genie/p/")


def status_page(title: str, text: str, retry: bool) -> str:
    import html
    button = ('<button onclick="location.href=\'gink-genie://retry\'" style="font:inherit;font-weight:700;padding:10px 20px;'
              'border:0;border-radius:999px;background:#151D23;color:#fff;cursor:pointer">Retry</button>') if retry else ""
    return ("<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<body style='font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:90vh;margin:0;"
            "background:#F6F7F4;color:#151D23;text-align:center'><div style='max-width:420px;padding:20px'>"
            f"<h1 style='font-size:24px'>{html.escape(title)}</h1><p style='color:#5D6B64'>{html.escape(text)}</p>{button}</div></body>")


class GinkGenie(toga.App):
    def startup(self):
        try:
            data_dir = self.paths.data
        except Exception:
            data_dir = None
        self.server = server_url(data_dir)
        self.home = self.server + "/genie"
        self.showing_status = False
        try:                                       # Toga 0.5+: catch links that should leave the app
            self.web = toga.WebView(style=Pack(flex=1), on_navigation_starting=self.navigating, on_webview_load=self.loaded)
        except TypeError:                          # older Toga (Briefcase 0.3.15 on macOS 10.15): no such option
            self.web = toga.WebView(style=Pack(flex=1), on_webview_load=self.loaded)
        try:                                       # ADD our mark to the WebView's normal identity (never replace it)
            self.web.user_agent = self._user_agent()
        except Exception:
            pass
        group = toga.Group("Genie")
        self.commands.add(
            toga.Command(lambda w, **kw: self.go_home(), text="Home", tooltip="Back to your Genie projects", group=group, order=1),
            toga.Command(lambda w, **kw: self.back(), text="Back", tooltip="Previous page", group=group, order=2),
            toga.Command(lambda w, **kw: self.reload(), text="Reload", tooltip="Reload this page", group=group, order=3),
            toga.Command(lambda w, **kw: self.open_in_browser(), text="Open in browser",
                         tooltip="Downloads, passkeys and everything else work in your browser", group=group, order=4),
        )
        self.main_window = toga.MainWindow(title=self.formal_name, size=(1280, 820))     # room for files, editor and chat
        try:
            self.main_window.toolbar.add(*[c for c in self.commands if getattr(c, "group", None) == group])
        except Exception:
            pass
        self.main_window.content = self.web
        self.main_window.show()
        asyncio.ensure_future(self.connect())

    def _user_agent(self) -> str:
        try:
            base = self.web.user_agent or ""
        except Exception:
            base = ""
        return (base + " " + APP_MARK).strip() if APP_MARK not in base else base

    async def connect(self):
        """Wake the server first (free plans sleep), then open Genie -- or explain."""
        self.showing_status = True
        self.web.set_content(self.home, status_page("Opening Gink Genie\u2026", "Waking up the Gink server. The first time can take up to a minute.", False))
        ok = await asyncio.get_event_loop().run_in_executor(None, self._reachable)
        if ok:
            self.showing_status = False
            self.web.url = self.home
        else:
            self.web.set_content(self.home, status_page("Can't reach Gink", "Check your internet connection, then press Retry (or Reload).", True))

    def _reachable(self) -> bool:
        try:
            with urllib.request.urlopen(self.server + "/health", timeout=75) as r:
                return r.status == 200
        except Exception:
            return False

    def navigating(self, widget, url=None, **kwargs):
        url = url or ""
        if url.startswith("gink-genie://retry"):
            asyncio.ensure_future(self.connect())
            return False
        if leaves_the_app(url, self.server):
            webbrowser.open(url)
            return False
        return True

    def loaded(self, widget, **kwargs):
        pass

    def go_home(self):
        if self.showing_status:
            asyncio.ensure_future(self.connect())
        else:
            self.web.url = self.home

    def back(self):
        try:
            self.web.evaluate_javascript("history.back()")
        except Exception:
            pass

    def reload(self):
        if self.showing_status:                    # on the "can't reach" page: try again
            asyncio.ensure_future(self.connect())
            return
        try:
            self.web.evaluate_javascript("location.reload()")
        except Exception:
            self.web.url = self.web.url or self.home

    def open_in_browser(self):
        current = ""
        try:
            current = self.web.url or ""
        except Exception:
            pass
        webbrowser.open(current if current.startswith(self.server) else self.home)


def main():
    return GinkGenie("Gink Genie", "com.amgib.ginkgenie")
