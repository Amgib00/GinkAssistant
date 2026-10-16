"""
Finds videos for Gink to show you -- how-to guides, explainers, recipes,
live channels.

Tried in order, first one that works wins:
  1. YouTube Data API v3 -- if YOUTUBE_API_KEY is set in .env (free from
     Google Cloud: enable "YouTube Data API v3", Credentials -> API key).
     Most accurate, includes durations and view counts. Free quota is
     ~100 searches/day.
  2. YouTube's own search results page (no key needed).
  3. DuckDuckGo video search (no key needed).

Each result: {"id", "title", "channel", "duration", "views", "url", "thumb", "source"}.
"""

import asyncio
import json
import os
import re
from typing import List, Optional

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
YT_ID = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})")


def video_id_from_url(url: str) -> Optional[str]:
    m = YT_ID.search(url or "")
    return m.group(1) if m else None


def watch_url(video_id: str, start: int = 0) -> str:
    return f"https://www.youtube.com/watch?v={video_id}" + (f"&t={int(start)}s" if start else "")


def _iso_duration(d: str) -> str:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return ""
    days, h, mi, s = (int(x or 0) for x in m.groups())
    h += days * 24
    return f"{h}:{mi:02d}:{s:02d}" if h else f"{mi}:{s:02d}"


def _short_views(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + suf + " views"
    return f"{n} views"


def _item(vid, title, channel="", duration="", views="", source=""):
    return {"id": vid, "title": (title or "").strip(), "channel": (channel or "").strip(),
            "duration": duration or "", "views": views or "", "url": watch_url(vid),
            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "source": source}


class VideoSearch:
    def __init__(self, api_key: Optional[str] = None, http_client=None):
        self.api_key = api_key if api_key is not None else os.environ.get("YOUTUBE_API_KEY", "").strip()
        self._http = http_client
        self.last_source = ""

    async def _get(self, url, params=None, headers=None):
        if self._http:
            return await self._http.get(url, params=params, headers=headers)
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            return await c.get(url, params=params, headers=headers)

    # -- 1. official API -----------------------------------------------------
    async def _api(self, query: str, n: int, live: bool) -> List[dict]:
        params = {"part": "snippet", "q": query, "type": "video", "maxResults": n,
                  "videoEmbeddable": "true", "safeSearch": "moderate", "key": self.api_key}
        if live:
            params["eventType"] = "live"
        r = await self._get("https://www.googleapis.com/youtube/v3/search", params)
        if r.status_code != 200:
            raise RuntimeError(f"YouTube API error {r.status_code}")
        items = r.json().get("items", [])
        ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
        details = {}
        if ids:
            d = await self._get("https://www.googleapis.com/youtube/v3/videos",
                                {"part": "contentDetails,statistics", "id": ",".join(ids), "key": self.api_key})
            if d.status_code == 200:
                details = {v["id"]: v for v in d.json().get("items", [])}
        out = []
        for i in items:
            vid = i["id"].get("videoId")
            if not vid:
                continue
            sn, det = i["snippet"], details.get(vid, {})
            dur = "LIVE" if live or sn.get("liveBroadcastContent") == "live" else \
                _iso_duration(det.get("contentDetails", {}).get("duration", ""))
            out.append(_item(vid, _unescape(sn.get("title")), sn.get("channelTitle"), dur,
                             _short_views(det.get("statistics", {}).get("viewCount")), "youtube-api"))
        return out

    # -- 2. YouTube results page ---------------------------------------------
    async def _page(self, query: str, n: int, live: bool) -> List[dict]:
        params = {"search_query": query}
        if live:
            params["sp"] = "EgJAAQ%3D%3D"                 # "Live" filter
        r = await self._get("https://www.youtube.com/results", params,
                            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                     "Cookie": "CONSENT=YES+1; SOCS=CAI"})
        m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", r.text, re.S) or \
            re.search(r'window\["ytInitialData"\]\s*=\s*(\{.*?\});', r.text, re.S)
        if not m:
            raise RuntimeError("results page format changed")
        data = json.loads(m.group(1))
        out = []

        def walk(node):
            if len(out) >= n:
                return
            if isinstance(node, dict):
                vr = node.get("videoRenderer")
                if isinstance(vr, dict) and vr.get("videoId"):
                    title = "".join(x.get("text", "") for x in vr.get("title", {}).get("runs", []))
                    channel = "".join(x.get("text", "") for x in vr.get("ownerText", {}).get("runs", []))
                    dur = vr.get("lengthText", {}).get("simpleText", "")
                    badges = json.dumps(vr.get("badges", []))
                    if not dur and ("LIVE" in badges or live):
                        dur = "LIVE"
                    views = vr.get("viewCountText", {}).get("simpleText", "") or \
                        "".join(x.get("text", "") for x in vr.get("viewCountText", {}).get("runs", []))
                    out.append(_item(vr["videoId"], title, channel, dur, views, "youtube"))
                    return
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(data)
        return out

    # -- 3. DuckDuckGo ---------------------------------------------------------
    async def _ddg(self, query: str, n: int, live: bool) -> List[dict]:
        def run():
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            return list(DDGS().videos(query + (" live" if live else ""), max_results=n * 3))
        rows = await asyncio.get_event_loop().run_in_executor(None, run)
        out = []
        for r in rows:
            vid = video_id_from_url(r.get("content", "")) or video_id_from_url(r.get("embed_url", ""))
            if vid and vid not in [o["id"] for o in out]:
                stats = r.get("statistics") or {}
                out.append(_item(vid, r.get("title"), r.get("uploader") or r.get("publisher"),
                                 r.get("duration", ""), _short_views(stats.get("viewCount")), "duckduckgo"))
            if len(out) >= n:
                break
        return out

    async def search(self, query: str, n: int = 3, live: bool = False) -> List[dict]:
        """Best-effort: returns [] only if every source failed."""
        query = (query or "").strip()
        if not query:
            return []
        sources = ([("youtube-api", self._api)] if self.api_key else []) + \
                  [("youtube", self._page), ("duckduckgo", self._ddg)]
        for name, fn in sources:
            try:
                res = await fn(query, n, live)
                if res:
                    self.last_source = name
                    return res[:n]
            except Exception:
                continue
        self.last_source = ""
        return []


def _unescape(s: str) -> str:
    import html
    return html.unescape(s or "")


def video_markdown(videos: List[dict]) -> str:
    """Video links in a form the chat page turns into playable cards
    (and that still read fine as plain links in history)."""
    lines = []
    for v in videos:
        meta = " \u00b7 ".join(x for x in (v.get("channel"), v.get("duration"), v.get("views")) if x)
        label = v["title"].replace("[", "(").replace("]", ")")
        sep = " \u2014 " + meta if meta else ""
        lines.append(f"[\u25b6 {label}{sep}]({v['url']})")
    return "\n\n".join(lines)
