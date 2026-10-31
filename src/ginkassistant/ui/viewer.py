"""
The viewer: watch a video or read a web guide WITHOUT leaving the chat.

* Computer: opens as a panel to the right of the chat, so you can follow
  Gink's written steps while the video plays. "Wider"/"Narrower" changes
  the split; the X closes it (and stops the video).
* Phone: opens full screen with a Back button (no room side by side).
* "Open in browser" hands the page to your normal browser / YouTube app.

YouTube is opened as a normal watch page, not an embedded player: embeds
inside an app page are often refused by YouTube ("Video unavailable",
error 153) because the page has no real web address. The watch page always
plays.
"""

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from ..services.actions.platform_info import is_mobile
from .viewer_util import stop_webview
from .theme import BG_ELEVATED, BG_SURFACE, BORDER, TEXT_MAIN, TEXT_MUTED

WIDTHS = (420, 560, 720)


class Viewer:
    def __init__(self, app: toga.App, host_box: toga.Box, open_external=None, on_close=None):
        self.app = app
        self.host = host_box                  # the main screen's root row
        self.open_external = open_external    # callable(url) -> opens in the system browser
        self.on_close = on_close
        self.url = ""
        self.mobile = is_mobile()
        self._width_i = 1
        self._previous_content = None

        self.title = toga.Label("", style=Pack(flex=1, font_weight="bold", color=TEXT_MAIN,
                                               background_color=BG_SURFACE, margin_left=6))
        btn = dict(margin_left=6, color=TEXT_MUTED, background_color=BG_ELEVATED)
        self.back_btn = toga.Button("\u2190 Back", on_press=lambda w: self.close(), style=Pack(**btn))
        self.size_btn = toga.Button("\u2194 Wider", on_press=self._toggle_width, style=Pack(**btn))
        self.ext_btn = toga.Button("Open in browser \u2197", on_press=self._external, style=Pack(**btn))
        self.close_btn = toga.Button("\u2715", on_press=lambda w: self.close(), style=Pack(width=36, **btn))
        # the close button comes FIRST: a long title can never push it out of sight (it did, with a long URL)
        bar_children = ([self.back_btn, self.title, self.ext_btn] if self.mobile
                        else [self.close_btn, self.title, self.size_btn, self.ext_btn])
        bar = toga.Box(children=bar_children,
                       style=Pack(direction=ROW, align_items=CENTER, margin=(8, 10), background_color=BG_SURFACE))
        self.web = toga.WebView(style=Pack(flex=1), on_webview_load=self._loaded)
        # skeleton screen: grey lines in the shape of a page while it loads (instead of a blank area)
        bars = []
        for w, h, gap in ((None, 150, 0), (260, 14, 16), (None, 12, 10), (None, 12, 8), (200, 12, 8), (None, 90, 18), (240, 14, 16), (None, 12, 10)):
            st = dict(height=h, margin=(gap, 16, 0, 16), background_color=BORDER)
            if w:
                st["width"] = w
            bars.append(toga.Box(style=Pack(**st)))
        self.skeleton = toga.Box(children=bars, style=Pack(direction=COLUMN, flex=1, background_color=BG_SURFACE))
        style = Pack(direction=COLUMN, flex=1, background_color=BG_SURFACE) if self.mobile else \
            Pack(direction=COLUMN, width=WIDTHS[self._width_i], background_color=BG_SURFACE)
        self.view = toga.Box(children=[bar, self.skeleton, self.web], style=style)
        self._loading(False)
        if not self.mobile:
            # thin divider so the panel reads as separate from the chat
            self.divider = toga.Box(style=Pack(width=1, background_color=BORDER))

    @property
    def is_open(self) -> bool:
        if self.mobile:
            return self.app.main_window.content is self.view
        return self.view in self.host.children

    @staticmethod
    def short_title(url: str, title: str = "") -> str:
        """A short bar title: the page's title, else the site's name ("YouTube"), never a long address."""
        if title and not title.startswith(("http://", "https://")):
            return title if len(title) <= 40 else title[:39] + "\u2026"
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        for pre in ("www.", "m.", "music."):
            host = host[len(pre):] if host.startswith(pre) else host
        known = {"youtube.com": "YouTube", "youtu.be": "YouTube", "spotify.com": "Spotify", "google.com": "Google",
                 "wikipedia.org": "Wikipedia"}
        for k, v in known.items():
            if host == k or host.endswith("." + k):
                return v
        return host or "Web page"

    def _loading(self, on: bool):
        """Skeleton while loading. The page view stays in the window (so it keeps loading), just squeezed."""
        self.skeleton.style.display = "pack" if on else "none"
        self.web.style.flex = 0 if on else 1
        self.web.style.height = 1 if on else 1
        if not on:
            try:
                del self.web.style.height
            except Exception:
                pass

    def _loaded(self, widget=None, **kw):
        self._loading(False)

    def show(self, url: str, title: str = ""):
        self.url = url
        self.title.text = self.short_title(url, title)
        self._loading(True)
        self.web.url = url
        try:                                               # some systems never report "loaded": stop waiting anyway
            import asyncio
            asyncio.get_event_loop().call_later(6, self._loading, False)
        except Exception:
            self._loading(False)
        if self.is_open:
            return
        if self.mobile:
            self._previous_content = self.app.main_window.content
            self.app.main_window.content = self.view
        else:
            self.host.add(self.divider)
            self.host.add(self.view)

    def close(self):
        if not self.is_open:
            return
        try:
            stop_webview(self.web)                 # stops playback
        except Exception:
            pass
        if self.mobile:
            if self._previous_content is not None:
                self.app.main_window.content = self._previous_content
        else:
            self.host.remove(self.view)
            self.host.remove(self.divider)
        if self.on_close:
            self.on_close()

    def _toggle_width(self, widget):
        self._width_i = (self._width_i + 1) % len(WIDTHS)
        self.view.style.width = WIDTHS[self._width_i]
        nxt = WIDTHS[(self._width_i + 1) % len(WIDTHS)]
        widget.text = "\u2194 Wider" if nxt > WIDTHS[self._width_i] else "\u2194 Narrower"

    def _external(self, widget):
        if self.url and self.open_external:
            self.open_external(self.url)
