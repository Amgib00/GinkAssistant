"""
Opening the links a person shares (0.1.161 pages; 0.1.164 any link): "summarise https://...", a Facebook reel, a
TikTok, a YouTube video, an X post, a PDF, a picture, a voice note on the web -- the server opens it itself and gives
the AI what it found, so the answer comes from the real thing, not a guess. Automatic for the apps and the web app
(backend_server._add_reading), for developers with "gink_web": "auto", for agents (read_page), and on its own
(/links/read, /v1/links/read).

What it reads (services/link_kinds.py knows the sites):
  * the official preview where there is one (oEmbed: YouTube, TikTok, X, Vimeo, Spotify, SoundCloud...; Facebook and
    Instagram with a Meta app token; Bluesky's public API), and the page's own preview (Open Graph, X cards, JSON-LD)
    -- the caption, who posted it, when, how long, its picture -- plus an ordinary page's text
  * a PDF's or a Word file's text; a picture (looked at); an audio or video file (listened to) -- see() and hear() are
    given by the server (its vision model, Whisper)
  * a reel's or a post's picture, looked at the same way, so Gink can say what it shows

Safe by design:
  * only http(s) on the usual ports; the address must be a public one (no localhost, private networks, cloud
    metadata) -- checked before every request and again after connecting, so a name can't switch to a private
    address; redirects followed by hand, each one checked the same way -- pictures and previews too
  * GET only, no cookies kept, sizes capped by kind (a page 2 MB, a PDF 15 MB, a picture 6 MB, audio/video 24 MB),
    pictures checked by their first bytes, time-limited
  * the words are data for the AI, between markers no page can fake, hidden text and invisible characters out, and a
    warning when a page tries to give the AI instructions (link_kinds: the shield)
"""
import asyncio
import base64
import html as html_module
import io
import ipaddress
import json
import re
import secrets
import socket
import time
from typing import Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote, urljoin, urlsplit

try:
    from . import link_kinds as lk
except ImportError:                                    # the server image: modules side by side
    import link_kinds as lk

MAX_BYTES = 2_000_000                # a page (enough for its head and text)
PDF_BYTES = 15_000_000
IMAGE_BYTES = 6_000_000
LOOK_BYTES = 2_900_000               # the vision model takes pictures up to 4 MB as base64
MEDIA_BYTES = 24_000_000             # Whisper takes up to 25 MB
MAX_CHARS = 9000                     # per link, for the AI
MAX_PAGES = 3                        # links per message
PDF_PAGES = 40
CACHE_SECONDS = 600
LINK_SECONDS = 30                    # one link, its picture looked at included (what's found by then is kept)
HEAR_SECONDS = 75                    # listening to an audio or video file, on top
UA = "Mozilla/5.0 (compatible; GinkReader/1.1; +https://amgib00.github.io/GinkAssistant/)"
ACCEPT = ("text/html,application/xhtml+xml,application/json;q=0.9,application/pdf;q=0.9,text/plain;q=0.8,"
          "image/*;q=0.7,video/*;q=0.5,audio/*;q=0.5,*/*;q=0.3")
_URL = re.compile(r"https?://[^\s<>()\[\]{}\"'`]+", re.I)
_SKIP_HOSTS = ("github.com", "www.github.com")            # repositories: services/code_reader.py reads those
_CACHE: Dict[str, tuple] = {}
SOCIAL = {s[0] for s in lk.SITES}
GENERIC_TITLES = {"facebook", "instagram", "threads", "linkedin", "x", "twitter", "tiktok", "youtube", "reddit", "log in",
                  "login", "sign in", "log into facebook", "error", "snapchat", "pinterest", "page not found", "just a moment...",
                  "attention required! | cloudflare"}

See = Callable[[str, str], Awaitable[str]]           # (picture as a data URL, what it is) -> what it shows
Hear = Callable[[bytes, str], Awaitable[str]]        # (audio or video bytes, format) -> what's said


def _generic_title(title: str, social: bool) -> bool:
    """A site's own name or its sign-in page ("Facebook - log in or sign up", "Login • Instagram"), not a post's title."""
    t = " ".join(title.lower().split())
    return t in GENERIC_TITLES or (social and len(t) < 60 and bool(re.search(r"\b(log ?in|sign ?in|sign up)\b", t)))


def find_links(text: str, limit: int = MAX_PAGES) -> List[str]:
    """The web addresses in a message (trailing punctuation removed), at most `limit`, without repeats."""
    out = []
    for m in _URL.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?)»”’'\"")
        host = (urlsplit(url).hostname or "").lower()
        if not host or host in _SKIP_HOSTS or url in out:
            continue
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _resolve(host: str) -> List[str]:
    """Every address the name points to (tests replace this)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})


def public_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not (addr.is_multicast or addr.is_reserved or addr.is_loopback or addr.is_link_local)


async def allowed(url: str) -> Optional[str]:
    """None when the address may be fetched; otherwise why not."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "that isn't a web address"
    if parts.scheme not in ("http", "https"):
        return "only web pages (http or https) can be read"
    if parts.username or parts.password:
        return "addresses with a name and password in them aren't opened"
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost", ".lan", ".home")):
        return "that address is on a private network"
    if port not in (None, 80, 443, 8080, 8443):
        return "that port isn't a web page's"
    try:
        ips = [host] if _is_ip(host) else await asyncio.get_running_loop().run_in_executor(None, _resolve, host)
    except Exception:
        return "that site couldn't be found"
    if not ips or not all(public_address(ip) for ip in ips):
        return "that address is on a private network"
    return None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


_DROP = ("script", "style", "noscript", "svg", "template", "iframe", "object", "canvas", "nav", "footer", "aside")
_BLOCK = re.compile(r"</?(p|div|section|article|main|header|li|ul|ol|h[1-6]|br|tr|table|blockquote|pre|dd|dt|figcaption|form)"
                    r"\b[^<>]*>", re.I)


def html_to_text(raw: str) -> tuple:
    """(title, readable text) from a page: scripts, menus, footers and hidden parts out (words hidden from people are
    often meant for AI); the <main>/<article> part when there is one. One pass each, whatever the page holds."""
    raw = raw[:MAX_BYTES]
    title = lk.page_title(raw)
    body = lk.drop_elements(lk.drop_comments(raw), _DROP, hidden=True)
    main = lk.first_element(body)
    if len(main) > 500:
        body = main
    body = _BLOCK.sub("\n", body)
    text = html_module.unescape(lk._ANY_TAG.sub(" ", body))
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out, last = [], ""
    for line in lines:
        if line and line != last:
            out.append(line)
            last = line
    return lk.safe_text(title), lk.safe_text("\n".join(out))[:MAX_CHARS]


def _peer_ip(response) -> str:
    try:
        stream = response.extensions.get("network_stream")
        addr = stream.get_extra_info("server_addr") if stream else None
        return str(addr[0]) if addr else ""
    except Exception:
        return ""


def _limit_for(kind: str) -> int:
    """How much of a response may be read, by its type (0: not something Gink opens)."""
    if any(k in kind for k in ("text/html", "application/xhtml", "text/plain", "application/json", "text/markdown",
                               "application/xml", "text/xml", "application/ld+json", "+json", "+xml")) or not kind:
        return MAX_BYTES
    if "application/pdf" in kind:
        return PDF_BYTES
    if "wordprocessingml" in kind:
        return PDF_BYTES
    if kind.startswith("image/"):
        return IMAGE_BYTES
    if kind.startswith(("audio/", "video/")) or "application/ogg" in kind:
        return MEDIA_BYTES
    return 0


async def get(client, url: str, accept: str = ACCEPT) -> dict:
    """One GET through the safety checks: {"url", "type", "data", "whole"} or {"url", "error"} -- every redirect
    checked again, the peer's address too, the size capped by the type."""
    current = url
    for _ in range(5):
        why = await allowed(current)
        if why:
            return {"url": current, "error": why}
        async with client.stream("GET", current, headers={"User-Agent": UA, "Accept": accept,
                                                         "Accept-Language": "en,fr;q=0.8,*;q=0.5"}) as r:
            peer = _peer_ip(r)
            if peer and not public_address(peer):              # the name switched to a private address
                return {"url": current, "error": "that address is on a private network"}
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                current = urljoin(current, r.headers["location"])
                continue
            kind = r.headers.get("content-type", "").lower().strip()
            if r.status_code != 200:
                return {"url": current, "type": kind, "error": f"the site answered {r.status_code}"}
            limit = _limit_for(kind)
            if not limit:
                return {"url": current, "type": kind, "error": "that isn't something Gink can open (" + kind.split(";")[0] + ")"}
            size = r.headers.get("content-length", "")
            if size.isdigit() and int(size) > limit and limit != MAX_BYTES:
                return {"url": current, "type": kind, "error": f"it's too big to open here ({int(size) // 1_000_000} MB)"}
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) >= limit:
                    break
            data, whole = bytes(buf[:limit]), len(buf) < limit
            if not whole and limit != MAX_BYTES:
                return {"url": current, "type": kind, "error": "it's too big to open here"}
            return {"url": current, "type": kind, "data": data, "whole": whole, "encoding": r.encoding}
    return {"url": current, "error": "too many redirects"}


async def get_json(client, url: str) -> Optional[dict]:
    got = await get(client, url, "application/json")
    if got.get("error") or not got.get("data"):
        return None
    try:
        data = json.loads(got["data"].decode("utf-8", "replace"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _decode(got: dict) -> str:
    return got["data"].decode(got.get("encoding") or "utf-8", errors="replace")


def picture_type(data: bytes) -> str:
    """The picture's type from its first bytes ("" when it isn't one the AI can look at)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def pdf_text(data: bytes) -> tuple:
    """(text, pages) of a PDF's first pages."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", 0
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        parts = []
        for i, page in enumerate(reader.pages[:PDF_PAGES]):
            t = (page.extract_text() or "").strip()
            if t:
                parts.append(f"[Page {i + 1}] {t}")
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
        return lk.safe_text("\n".join(parts))[:MAX_CHARS], len(reader.pages)
    except Exception:
        return "", 0


def docx_text(data: bytes) -> str:
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.getinfo("word/document.xml").file_size > 20_000_000:       # a "zip bomb": not opened
                return ""
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    text = html_module.unescape(lk._ANY_TAG.sub("", xml))
    return lk.safe_text(re.sub(r"\n{3,}", "\n\n", text).strip())[:MAX_CHARS]


def _merge(info: dict, found: dict, keep: bool = True) -> None:
    """Add what a source found: keep=True never replaces what an earlier (better) source said."""
    for k, v in (found or {}).items():
        if v and (not keep or not info.get(k)):
            info[k] = v


async def _bluesky(client, who: str, post: str) -> dict:
    api = "https://public.api.bsky.app/xrpc/"
    did = who
    if not who.startswith("did:"):
        got = await get_json(client, api + "com.atproto.identity.resolveHandle?handle=" + quote(who, safe=""))
        did = (got or {}).get("did") or ""
        if not did.startswith("did:"):
            return {}
    thread = await get_json(client, api + "app.bsky.feed.getPostThread?depth=0&parentHeight=0&uri=" +
                            quote(f"at://{did}/app.bsky.feed.post/{post}", safe=""))
    return lk.from_bluesky(thread or {})


async def _youtube_api(client, video_id: str, key: str) -> dict:
    """YouTube's Data API (official; YOUTUBE_API_KEY on the server): the whole description, length, counts."""
    data = await get_json(client, "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&id="
                          + quote(video_id, safe="") + "&key=" + quote(key, safe=""))
    item = ((data or {}).get("items") or [{}])[0]
    snip, stats = item.get("snippet") or {}, item.get("statistics") or {}
    out = {"title": lk._clean(snip.get("title"), 300), "author": lk._clean(snip.get("channelTitle"), 200),
           "text": lk._clean(snip.get("description"), 5000), "date": str(snip.get("publishedAt") or "")[:10],
           "seconds": lk.iso_seconds((item.get("contentDetails") or {}).get("duration")),
           "stats": {k: int(stats[f]) for k, f in (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount"))
                     if str(stats.get(f) or "").isdigit()}}
    return {k: v for k, v in out.items() if v}


def youtube_id(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.endswith("youtu.be"):
        return parts.path.strip("/").split("/")[0][:11]
    m = re.search(r"(?:[?&]v=|/shorts/|/embed/|/live/)([\w-]{11})", url)
    return m.group(1) if m else ""


async def fetch_link(url: str, see: Optional[See] = None, hear: Optional[Hear] = None, keys: Optional[dict] = None) -> dict:
    """Everything Gink can open of one link: {"url", "site", "kind", "title", "author", "date", "seconds", "stats",
    "text", "body", "image", "seen", "heard", "note"} -- or with "error". Cached for 10 minutes."""
    keys = keys or {}
    key = url + ("|see" if see else "") + ("|hear" if hear else "")
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return dict(hit[1])
    try:
        info = await asyncio.wait_for(_open(url, see, hear, keys), LINK_SECONDS + HEAR_SECONDS + 10)   # a last guard
    except asyncio.TimeoutError:
        info = {"url": url, **_site_fields(url), "error": "it took too long to open"}
    except Exception as exc:
        info = {"url": url, **_site_fields(url), "error": "it couldn't be opened (" + type(exc).__name__ + ")"}
    info = {k: v for k, v in info.items() if v not in (None, "", {}, [])}
    _CACHE[key] = (time.time(), info)
    while len(_CACHE) > 300:
        _CACHE.pop(next(iter(_CACHE)))
    return dict(info)


def cached(url: str, see: bool = False, hear: bool = False) -> bool:
    """Opened in the last 10 minutes (the same way): opening it again costs nothing."""
    hit = _CACHE.get(url + ("|see" if see else "") + ("|hear" if hear else ""))
    return bool(hit and time.time() - hit[0] < CACHE_SECONDS)


def _site_fields(url: str) -> dict:
    site = lk.site_of(url)
    return {"site": site["name"], "kind": site["kind"]}


async def _within(job, seconds: float):
    """The job's result, or None when it fails or takes longer than `seconds` -- so one slow part (a picture, the
    vision model) never loses what the others found."""
    if job is None:
        return None
    if seconds < 1:
        if hasattr(job, "close"):
            job.close()                                    # a coroutine: never started
        elif hasattr(job, "cancel"):
            job.cancel()
        return None
    try:
        return await asyncio.wait_for(job, seconds)
    except Exception:
        return None


async def _open(url: str, see: Optional[See], hear: Optional[Hear], keys: dict) -> dict:
    import httpx
    site = lk.site_of(url)
    info: dict = {"url": url, "site": site["name"], "kind": site["kind"]}
    official_url = site["oembed"] or lk.meta_oembed(url, keys.get("meta", ""), keys.get("meta_version") or "v22.0")
    picture, media, media_type = b"", b"", ""
    started = time.monotonic()

    def left() -> float:
        return LINK_SECONDS - (time.monotonic() - started)
    async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=6), follow_redirects=False) as client:
        parts = lk.bluesky_parts(url)
        vid = youtube_id(url) if site["name"] == "YouTube" and keys.get("youtube") else ""
        page, official, bsky, ytapi = await asyncio.gather(
            _within(get(client, url), 18), _within(get_json(client, official_url) if official_url else None, 12),
            _within(_bluesky(client, *parts) if parts else None, 12),
            _within(_youtube_api(client, vid, keys["youtube"]) if vid else None, 12))
        if page is None:
            page = {"url": url, "error": "it took too long to open"}
        for found in (ytapi, bsky):
            if isinstance(found, dict):
                _merge(info, found)
        if isinstance(official, dict):
            _merge(info, lk.from_oembed(official))
            info["official"] = True
        if isinstance(page, dict) and page.get("data") is not None:
            kind = page.get("type", "")
            info["url"] = page.get("url") or url                 # where a short link led
            if page["url"] != url and site["name"] != lk.site_of(page["url"])["name"]:
                site = lk.site_of(page["url"])                    # a short link to another site (bit.ly -> facebook)
                info["site"], info["kind"] = site["name"], site["kind"]
            if "html" in kind or "xhtml" in kind or (not kind and page["data"][:200].lstrip().lower().startswith((b"<!doctype", b"<html"))):
                raw = _decode(page)
                if info.get("kind") in ("picture", "video", "audio", "PDF") and site["name"] not in SOCIAL:
                    info["kind"] = "page"                         # ".../photo.jpg" that is really a page
                meta = lk.page_meta(raw)
                found = lk.preview(meta, lk.page_ld(raw))
                if _generic_title(str(found.get("title", "")), site["name"] in SOCIAL):
                    found.pop("title")                            # "Facebook", "Log in": not the post's title
                title, text = html_to_text(raw)
                _merge(info, {k: v for k, v in found.items() if k not in ("site", "type")})
                if not info.get("title") and title and site["name"] not in SOCIAL:
                    info["title"] = title
                desc = str(info.get("text") or "")
                if site["name"] not in SOCIAL and text and (not desc or desc not in text or len(text) > len(desc) + 40):
                    info["body"] = text                          # an ordinary page: its words
                if str(found.get("type", "")).startswith("video") and info.get("kind") in ("page", "post"):
                    info["kind"] = "video"
                if found.get("site") and site["name"] not in SOCIAL:
                    info["site"] = found["site"]
                if lk.walled(site["name"], found, text) and not info.get("official"):
                    info["note"] = (f"{site['name'] or 'The site'} only showed its sign-in page to Gink, so only the link "
                                    "itself is known -- not its caption or picture.")
                if not official_url and meta.get("oembed"):     # the page names its own official preview
                    found = await _within(get_json(client, urljoin(info["url"], meta["oembed"])), min(8, left() - 6))
                    if found:
                        _merge(info, lk.from_oembed(found))
                        info["official"] = True
            elif "application/pdf" in kind or page["data"][:5] == b"%PDF-":
                info["kind"] = "PDF"                            # read beside the server's work, within the time left
                got = await _within(asyncio.get_running_loop().run_in_executor(None, pdf_text, page["data"]),
                                    min(15, left() - 2))
                info["body"], info["pages"] = got or ("", 0)
                if not info["body"]:
                    info["note"] = "This PDF has no text Gink can read (it may be a scan, locked, or too slow to read)."
            elif "wordprocessingml" in kind:
                info["kind"] = "Word document"
                info["body"] = await _within(asyncio.get_running_loop().run_in_executor(None, docx_text, page["data"]),
                                             min(10, left() - 2)) or ""
            elif kind.startswith("image/"):
                info["kind"], picture = "picture", page["data"]
            elif kind.startswith(("audio/", "video/")) or "application/ogg" in kind:
                info["kind"], media, media_type = ("video" if kind.startswith("video/") else "audio"), page["data"], kind
            else:
                info["body"] = lk.safe_text(_decode(page))[:MAX_CHARS]
            if not info.get("official") and info["url"] != url and lk.site_of(info["url"])["oembed"]:
                found = await _within(get_json(client, lk.site_of(info["url"])["oembed"]), min(8, left() - 6))   # a short link
                if found:
                    _merge(info, lk.from_oembed(found))
                    info["official"] = True
        elif isinstance(page, dict) and page.get("error") and not any(info.get(k) for k in ("text", "title")):
            info["error"] = page["error"]
        if info.get("image"):
            info["image"] = urljoin(info.get("url") or url, str(info["image"]))
        # what its picture shows -- a reel's cover, a post's photo, the picture itself
        if see and (picture or info.get("image")) and left() > 4:
            if not picture:
                got = await _within(get(client, str(info["image"]), "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8"),
                                    min(8, left() - 4))
                picture = (got or {}).get("data") or b""
            mime = picture_type(picture) if len(picture) <= LOOK_BYTES else ""
            seen = await _within(see(f"data:{mime};base64," + base64.b64encode(picture).decode(), lk.a_kind(info)),
                                 min(20, left())) if mime else None
            if seen:
                info["seen"] = lk.safe_text(str(seen))[:1500]
    if media and hear:
        heard = await _within(hear(media, media_type), HEAR_SECONDS)
        if heard:
            info["heard"] = lk.safe_text(str(heard))[:MAX_CHARS]
    if info.get("kind") == "picture" and not info.get("seen"):
        info.setdefault("note", "This is a picture; Gink couldn't look at it here. Attached to the chat, Gink can.")
    if media and not info.get("heard"):
        info.setdefault("note", f"This is {lk.a_kind(info)} file ({media_type.split(';')[0] or 'unknown type'}); Gink "
                                "couldn't listen to it here. Attached to the chat, Gink can watch or listen to it.")
    if info.get("kind") in lk.VIDEO_KINDS and not info.get("heard") and info.get("site") in SOCIAL and not media:
        info.setdefault("note", f"Only the {info['kind']}'s preview could be opened (its caption and picture): "
                                f"{info.get('site') or 'the site'} doesn't let other apps play its videos. With the video "
                                "file attached to the chat, Gink watches the whole thing.")
    for k in ("text", "body", "title", "author"):
        if info.get(k):
            info[k] = lk.safe_text(str(info[k]))
    if not any(info.get(k) for k in ("text", "body", "title", "seen", "heard", "error", "note")):
        info["error"] = "it had nothing Gink could read"
    return info


async def read_links(text: str = "", see: Optional[See] = None, hear: Optional[Hear] = None, keys: Optional[dict] = None,
                     links: Optional[List[str]] = None) -> List[dict]:
    """Every link in a message (or the given ones), opened at the same time."""
    links = links if links is not None else find_links(text)
    if not links:
        return []
    return list(await asyncio.gather(*(fetch_link(u, see, hear, keys) for u in links[:MAX_PAGES])))


def context_note(pages: List[dict], today: str = "", earlier: bool = False, code: str = "", budget: int = 12000) -> str:
    """The system note with everything Gink opened (data between markers, never instructions)."""
    return lk.context_note(pages, code or secrets.token_hex(4), today, earlier, budget)


def opened(info: dict) -> bool:
    """Something of the link could be read or seen (not only its address)."""
    return any(info.get(k) for k in ("text", "body", "title", "seen", "heard", "transcript"))


async def fetch_page(url: str) -> dict:
    """An ordinary page's {"url", "title", "text"} or {"url", "error"} (0.1.161's shape)."""
    info = await fetch_link(url)
    if info.get("error"):
        return {"url": info.get("url") or url, "error": info["error"]}
    return {"url": info.get("url") or url, "title": info.get("title", ""),
            "text": info.get("body") or info.get("text") or ""}
