"""
Live TV + YouTube, inside Gink.

* Channels open each broadcaster's permanent YouTube "live" address
  (youtube.com/@channel/live), which YouTube always points at the stream
  that's on air now. (The old version stored fixed video IDs, which break
  every time a channel restarts its stream.)
* Search box: any YouTube video or live stream ("jollof rice recipe",
  "Senegal match live"); results appear as buttons, the first one plays.
* "+ Add channel": paste a YouTube channel link or @handle, give it a name;
  saved in prefs so it's there next time.
* Say "watch Al Jazeera live" / "put on France 24" in the chat to jump here.

Uses the YouTube Data API when YOUTUBE_API_KEY is set (better live search),
otherwise free search (services/video_search.py).
"""

import asyncio
import re

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from ..services import prefs
from ..services.video_search import VideoSearch, video_id_from_url, watch_url
from .viewer_util import stop_webview
from .theme import ACCENT, BG_ELEVATED, BG_SURFACE, DANGER, ON_ACCENT, TEXT_MAIN, TEXT_MUTED

DEFAULT_CHANNELS = {
    "Al Jazeera English": "https://www.youtube.com/@aljazeeraenglish/live",
    "France 24 English": "https://www.youtube.com/@France24_en/live",
    "DW News": "https://www.youtube.com/@dwnews/live",
    "Africanews": "https://www.youtube.com/@africanews/live",
    "Sky News": "https://www.youtube.com/@SkyNews/live",
    "Euronews": "https://www.youtube.com/@euronews/live",
    "NASA": "https://www.youtube.com/@NASA/live",
}
# kept for older imports
LIVE_TV_CHANNELS = DEFAULT_CHANNELS


def channel_url(text: str):
    """'@handle', a channel link or a video link -> something playable."""
    t = (text or "").strip()
    if not t:
        return None
    vid = video_id_from_url(t)
    if vid:
        return watch_url(vid)
    m = re.match(r"^(?:https?://(?:www\.|m\.)?youtube\.com/)?(@[\w.\-]+|channel/[\w\-]+|c/[\w\-]+|user/[\w\-]+)", t)
    if m:
        return f"https://www.youtube.com/{m.group(1)}/live"
    return None


def all_channels(app) -> dict:
    custom = prefs.load(app).get("live_channels") or {}
    return {**DEFAULT_CHANNELS, **custom}


def match_channel(app, wanted: str):
    """'al jazeera' -> 'Al Jazeera English'."""
    w = re.sub(r"[^a-z0-9 ]", "", (wanted or "").lower()).strip()
    if not w:
        return None
    for name in all_channels(app):
        n = re.sub(r"[^a-z0-9 ]", "", name.lower())
        if w in n or n in w or w.replace(" ", "") in n.replace(" ", ""):
            return name
    return None


def build_live_tv_view(app: toga.App, on_back, initial_channel: str = None):
    channels = all_channels(app)
    search = VideoSearch()
    web_view = toga.WebView(style=Pack(flex=1))
    status = toga.Label("", style=Pack(margin_left=12, font_size=12, color=TEXT_MUTED, background_color=BG_SURFACE))
    results_box = toga.Box(style=Pack(direction=ROW, background_color=BG_SURFACE))
    results_row = toga.ScrollContainer(content=results_box, vertical=False,
                                       style=Pack(flex=1, height=46, background_color=BG_SURFACE))

    def play(url: str, label: str):
        web_view.url = url
        status.text = f"\u25cf {label}"

    def play_channel(name: str):
        url = all_channels(app).get(name)
        if url:
            play(url, name)

    selector = toga.Selection(items=list(channels.keys()), on_change=lambda w: play_channel(w.value),
                              style=Pack(width=210, color=TEXT_MAIN, background_color=BG_ELEVATED))

    # -- search ---------------------------------------------------------------
    query = toga.TextInput(placeholder="Search YouTube \u2014 a recipe, a match, a how-to\u2026",
                           style=Pack(flex=1, color=TEXT_MAIN, background_color=BG_ELEVATED))
    live_only = toga.Switch("Live only", style=Pack(margin_left=8, color=TEXT_MUTED, background_color=BG_SURFACE))

    def show_results(found):
        for child in list(results_box.children):
            results_box.remove(child)
        for v in found:
            label = (v["title"][:46] + "\u2026") if len(v["title"]) > 47 else v["title"]
            extra = f"  \u00b7 {v['duration']}" if v.get("duration") else ""
            results_box.add(toga.Button(f"\u25b6 {label}{extra}",
                                        on_press=lambda w, v=v: play(v["url"], v["title"]),
                                        style=Pack(margin=(4, 6, 6, 0), color=TEXT_MAIN, background_color=BG_ELEVATED)))
        if found and results_wrap not in screen.children:
            screen.insert(screen.children.index(web_view), results_wrap)
        elif not found and results_wrap in screen.children:
            screen.remove(results_wrap)

    async def do_search(widget):
        q = (query.value or "").strip()
        if not q:
            return
        status.text = "Searching\u2026"
        found = await search.search(q, n=8, live=bool(live_only.value))
        if not found:
            status.text = "Nothing found (or you're offline)."
            show_results([])
            return
        show_results(found)
        play(found[0]["url"], found[0]["title"])

    query.on_confirm = do_search
    search_btn = toga.Button("Search", on_press=do_search,
                             style=Pack(margin_left=6, color=ON_ACCENT, background_color=ACCENT, font_weight="bold"))

    # -- add channel ----------------------------------------------------------
    add_name = toga.TextInput(placeholder="Name, e.g. RTS S\u00e9n\u00e9gal",
                              style=Pack(width=180, color=TEXT_MAIN, background_color=BG_ELEVATED))
    add_link = toga.TextInput(placeholder="YouTube channel link or @handle",
                              style=Pack(flex=1, margin_left=6, color=TEXT_MAIN, background_color=BG_ELEVATED))
    add_msg = toga.Label("", style=Pack(margin_left=8, font_size=12, color=TEXT_MUTED, background_color=BG_SURFACE))

    def save_channel(widget):
        url = channel_url(add_link.value)
        name = (add_name.value or "").strip()
        if not url or not name:
            add_msg.text = "Enter a name and a YouTube channel link or @handle."
            add_msg.style.color = DANGER
            return
        custom = dict(prefs.load(app).get("live_channels") or {})
        custom[name] = url
        prefs.save(app, live_channels=custom)
        selector.items = list(all_channels(app).keys())
        selector.value = name
        if add_panel in screen.children:
            screen.remove(add_panel)
        add_msg.text = ""

    add_panel = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(0, 12, 8, 12),
                                    background_color=BG_SURFACE), children=[
        add_name, add_link,
        toga.Button("Save", on_press=save_channel,
                    style=Pack(margin_left=6, color=ON_ACCENT, background_color=ACCENT)),
        add_msg,
    ])

    def toggle_add(widget):
        if add_panel in screen.children:
            screen.remove(add_panel)
        else:
            screen.insert(1, add_panel)

    # -- layout ---------------------------------------------------------------
    btn = dict(color=TEXT_MUTED, background_color=BG_ELEVATED)
    top = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(10, 12, 6, 12), background_color=BG_SURFACE),
                   children=[
                       toga.Button("\u2190 Back", on_press=lambda w: (stop_webview(web_view), on_back()),
                                   style=Pack(width=86, **btn)),
                       toga.Label("\u25cf LIVE", style=Pack(margin=(0, 10, 0, 12), color=DANGER, font_weight="bold",
                                                           background_color=BG_SURFACE)),
                       selector,
                       toga.Button("+ Add channel", on_press=toggle_add, style=Pack(margin_left=6, **btn)),
                       status,
                   ])
    search_row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(0, 12, 6, 12),
                                     background_color=BG_SURFACE),
                          children=[query, live_only, search_btn])
    results_wrap = toga.Box(style=Pack(direction=ROW, margin=(0, 12), background_color=BG_SURFACE),
                            children=[results_row])

    screen = toga.Box(style=Pack(direction=COLUMN, flex=1, background_color=BG_SURFACE),
                      children=[top, search_row, web_view])
    start = match_channel(app, initial_channel) if initial_channel else None
    if initial_channel and not start:
        # not one of the channels -> search for it live
        query.value = initial_channel
        live_only.value = True
        try:
            asyncio.get_event_loop().create_task(do_search(None))
        except RuntimeError:
            pass
    else:
        start = start or next(iter(channels))
        selector.value = start
        play_channel(start)

    return screen
