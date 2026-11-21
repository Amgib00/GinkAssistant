"""Gink Developer API client: managed agents (interactions), environments, chat, photos (see), images."""
import json
import os
import time
from typing import Iterator, Optional

import httpx

DEFAULT_BASE = "https://gink-server.onrender.com/v1"


def utc_offset() -> str:
    """The clock's offset from UTC, like "+01:00" (no time zone name, no region)."""
    from datetime import datetime
    off = datetime.now().astimezone().utcoffset()
    mins = int(off.total_seconds() // 60) if off else 0
    return f"{'+' if mins >= 0 else '-'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"


def place_headers(location: Optional[bool] = None) -> dict:
    """The computer's time zone and region (no location lookup): answers fit the user's own country.
    location=False (or GINK_LOCATION=off): like Settings > Privacy > "Location metadata" off -- only the clock's UTC
    offset is sent, so times stay right but no city or region is used."""
    if location is None:
        location = os.environ.get("GINK_LOCATION", "").strip().lower() not in ("off", "0", "false", "no")
    if not location:
        return {"X-Gink-Location": "off", "X-Gink-UTC-Offset": utc_offset()}
    import locale
    h, tz = {}, os.environ.get("TZ", "").lstrip(":")
    if "/" not in tz:
        try:
            link = os.path.realpath("/etc/localtime")
            tz = link.split("zoneinfo/", 1)[1] if "zoneinfo/" in link else ""
        except OSError:
            tz = ""
    if "/" in tz:
        h["X-Gink-TZ"] = tz[:64]
    try:
        loc = locale.getlocale()[0] or os.environ.get("LANG", "").split(".")[0]
    except ValueError:
        loc = os.environ.get("LANG", "").split(".")[0]
    if loc and "_" in loc:
        h["X-Gink-Locale"] = loc[:20]
    return h


def image_data_url(photo) -> str:
    """bytes, a file path or a data URL -> a data URL Gink can look at (JPEG, PNG, WebP or GIF)."""
    import base64
    if isinstance(photo, str) and photo.startswith("data:image/"):
        return photo
    raw = bytes(photo) if isinstance(photo, (bytes, bytearray)) else open(photo, "rb").read()
    mime = ("image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n"
            else "image/webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else "image/gif" if raw[:4] == b"GIF8" else "")
    if not mime:
        raise GinkAPIError("That isn't a JPEG, PNG, WebP or GIF photo.", 400, "invalid_image")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def sources(text: str, base_url: str = DEFAULT_BASE) -> list:
    """The sources listed under a web answer's "Sources" (gink-search), official ones first:
    [{"title", "url", "host", "official", "icon"}] -- icon is the site's real logo, served by Gink (<server>/icon/<host>)."""
    import re
    from urllib.parse import urlparse
    root = (base_url or DEFAULT_BASE).rstrip("/")
    root = root[:-3] if root.endswith("/v1") else root
    part = (text or "").split("**Sources**", 1)
    out = []
    for line in (part[1] if len(part) == 2 else "").splitlines():
        m = re.match(r"\s*[-*]\s*\[([^\]]*)\]\((https?://[^)\s]+)\)(.*)$", line)
        if not m:
            continue
        host = (urlparse(m.group(2)).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        out.append({"title": m.group(1).strip() or host, "url": m.group(2), "host": host,
                    "official": bool(re.search(r"\u00b7\s*official\s*$", m.group(3))), "icon": f"{root}/icon/{host}" if host else ""})
    return sorted(out, key=lambda s: 0 if s["official"] else 1)


def maps(text: str) -> list:
    """The maps in an answer (```map blocks: ask with gink_maps=True): [{"title", "places": [{"name", "query", "lat",
    "lon", "category", "note", "map_url"}]}] -- category is what kind of place (food, cafe, bar, shop, museum, sight,
    park, beach, hotel, transport, health, school, worship, other); map_url opens it on OpenStreetMap when its
    coordinates are known."""
    import json as _json
    import re
    out = []
    for block in re.findall(r"```map\s*\n(.*?)```", text or "", re.S):
        try:
            data = _json.loads(block)
        except ValueError:
            continue
        places = []
        for p in (data.get("places") or data.get("markers") or [])[:10] if isinstance(data, dict) else []:
            if not isinstance(p, dict) or not (p.get("name") or p.get("query")):
                continue
            place = {k: p.get(k) for k in ("name", "query", "lat", "lon", "category", "note") if p.get(k) not in (None, "")}
            if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float)):
                place["map_url"] = f"https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}#map=16/{p['lat']}/{p['lon']}"
            places.append(place)
        if places:
            out.append({"title": str(data.get("title") or ""), "places": places})
    return out


ARTIFACT_KINDS = {"html": "page", "htm": "page", "svg": "image", "mermaid": "diagram", "document": "document",
                  "markdown": "document", "md": "document"}
_EXT = {"python": "py", "javascript": "js", "typescript": "ts", "html": "html", "svg": "svg", "mermaid": "mmd",
        "document": "md", "markdown": "md", "md": "md", "css": "css", "json": "json", "bash": "sh", "shell": "sh",
        "sql": "sql", "java": "java", "kotlin": "kt", "swift": "swift", "go": "go", "rust": "rs", "ruby": "rb",
        "php": "php", "csharp": "cs", "cpp": "cpp", "c": "c", "yaml": "yaml", "toml": "toml", "dart": "dart"}


def artifacts(text: str) -> list:
    """The finished things in an answer (ask with gink_artifacts=True): each fenced block with a title, like
    ```html title="Pomodoro timer". [{"title", "language", "kind", "content", "filename", "version"}] -- kind is page,
    image (SVG), diagram (Mermaid), document (Markdown) or code; a later block with the same title is a new version
    of it (version 2, 3...)."""
    import re
    out, seen = [], {}
    for m in re.finditer(r"^([ \t]*)(```|~~~)[ \t]*([\w+#.\-]*)([^\n`]*)\n(.*?)\n?[ \t]*\2[ \t]*$", text or "", re.M | re.S):
        lang, info, body = m.group(3).lower(), m.group(4), m.group(5)
        t = re.search(r"""\btitle[ \t]*=[ \t]*(?:"([^"\n]{1,120})"|'([^'\n]{1,120})')""", info)
        if not t:
            continue
        title = (t.group(1) or t.group(2)).strip()
        key = re.sub(r"\s+", " ", title.lower())
        seen[key] = seen.get(key, 0) + 1
        ext = _EXT.get(lang, lang or "txt")
        base = title if re.search(r"\.[A-Za-z0-9]{1,6}$", title) else re.sub(r"[^\w.-]+", "-", title).strip("-").lower() + "." + ext
        out.append({"title": title, "language": lang, "kind": ARTIFACT_KINDS.get(lang, "code"), "content": body,
                    "filename": base or ("artifact." + ext), "version": seen[key]})
    return out


def schedules_in(text: str) -> list:
    """The schedules an answer offers (ask with gink_tasks=True): each ```schedule block, ready for
    client.tasks.create(**s) -- [{"title", "task", "every", "at", "day"?, "date"?}]."""
    import json as _json
    import re
    out = []
    for block in re.findall(r"```schedule[^\n]*\n(.*?)```", text or "", re.S):
        try:
            d = _json.loads(block)
        except ValueError:
            continue
        if not isinstance(d, dict) or not str(d.get("task") or "").strip():
            continue
        out.append({k: d[k] for k in ("title", "task", "every", "at", "day", "date") if d.get(k) not in (None, "")})
    return out


def screen_image() -> bytes:
    """A picture of this computer's screen (PNG bytes) for see(): macOS screencapture, Windows/Linux Pillow's
    ImageGrab, or a Linux screenshot tool. Nothing is kept."""
    import shutil
    import subprocess
    import sys as _sys
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".png", prefix="gink-screen-")
    os.close(fd)
    try:
        cmds = [["screencapture", "-x", "-C", path]] if _sys.platform == "darwin" else \
            [["gnome-screenshot", "-f", path], ["grim", path], ["import", "-window", "root", path]]
        for cmd in cmds:
            if shutil.which(cmd[0]) and subprocess.run(cmd, capture_output=True, timeout=20).returncode == 0 and os.path.getsize(path):
                return open(path, "rb").read()
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(path)
            return open(path, "rb").read()
        except Exception as exc:
            raise GinkAPIError("Couldn't take a picture of the screen here" + (
                " (allow Screen Recording for your terminal in System Settings > Privacy & Security)" if _sys.platform == "darwin"
                else " (install Pillow: pip install pillow)") + f": {type(exc).__name__}", 0, "no_screen")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class GinkAPIError(Exception):
    """The API said no; .status and .code say why (e.g. 429 daily_limit, 401 invalid_api_key)."""

    def __init__(self, message: str, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status, self.code = status, code


class _Obj(dict):
    """A dict you can also read with dots: interaction.output_text == interaction["output_text"]."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class Interaction(_Obj):
    pass


class Event(_Obj):
    """A live event: type is "step", "status" or "done"; data is its content (done: the whole Interaction)."""


def _saved_key() -> str:
    """The key `gink login` saved (the CLI's config), if any."""
    try:
        from gink_cli.main import load_config
        return load_config().get("api_key", "")
    except Exception:
        return ""


class Client:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 600,
                 http: Optional[httpx.Client] = None, location: Optional[bool] = None):
        """location=False: send no location metadata (city/region), only the clock's UTC offset (or GINK_LOCATION=off)."""
        self.location = location
        self.api_key = api_key or os.environ.get("GINK_API_KEY") or _saved_key()
        if not self.api_key:
            raise GinkAPIError("No API key: pass api_key=, set GINK_API_KEY, or run `gink login`.", 401, "invalid_api_key")
        self.base_url = (base_url or os.environ.get("GINK_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self._http = http or httpx.Client(timeout=timeout)
        self.interactions = _Interactions(self)
        self.environments = _Environments(self)
        self.schedules = _Schedules(self)
        self.tasks = _Tasks(self)
        self.memories = _Memories(self)
        self.workspace = _Workspace(self)
        self.webhooks = _Webhooks(self)
        self.audio = _Audio(self)
        self.batches = _Batches(self)

    # ---- plumbing
    def _headers(self) -> dict:
        return dict({"Authorization": f"Bearer {self.api_key}", "User-Agent": "gink-python"}, **place_headers(self.location))

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._http.request(method, self.base_url + path, headers=self._headers(), **kw)
        except httpx.HTTPError as exc:
            raise GinkAPIError(f"Couldn't reach Gink ({type(exc).__name__}).", 0, "network") from exc
        if r.status_code >= 400:
            try:
                err = r.json().get("error") or {}
                msg, code = err.get("message") or r.json().get("detail") or r.text, err.get("code", "")
            except ValueError:
                msg, code = r.text[:300], ""
            raise GinkAPIError(str(msg), r.status_code, code)
        return r

    # ---- chat (OpenAI-compatible) and images
    def _chat_data(self, message, model: str = "", system: str = "", **extra) -> dict:
        messages = message if isinstance(message, list) else (
            ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": str(message)}])
        body = dict({"messages": messages}, **({"model": model} if model else {}), **extra)
        return self.request("POST", "/chat/completions", json=body).json()

    def chat(self, message, model: str = "", system: str = "", **extra) -> str:
        """One answer. `message` is text or a full messages list. Live info (date, weather, rates...) is added by Gink.
        Gink's options, as keyword arguments: gink_web="auto" (read the pages linked in the question and search the
        web when the answer needs it -- like Gink's apps), gink_code=True (GitHub repositories in the question are
        read), gink_artifacts=True (finished things in titled blocks: artifacts()), gink_tasks=True ("every morning..."
        gets a ```schedule block: schedules_in()), gink_maps=True (```map blocks: maps())."""
        data = self._chat_data(message, model=model, system=system, **extra)
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    def search(self, question: str, with_sources: bool = False):
        """An answer from the web, with its sources listed (official ones first). with_sources=True:
        {"answer": text, "sources": [{"title", "url", "host", "official", "icon"}]} -- icon: the site's real logo."""
        data = self._chat_data(question, model="gink-search")
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        if not with_sources:
            return text
        found = sources(text, self.base_url)
        hosts = {s["url"]: s for s in found}
        for s in data.get("sources") or []:                       # the server's own list, when it sent one
            if isinstance(s, dict) and s.get("url") in hosts:
                hosts[s["url"]].update(official=bool(s.get("official")), icon=s.get("icon") or hosts[s["url"]]["icon"])
        return {"answer": text, "sources": sorted(found, key=lambda s: 0 if s["official"] else 1)}

    def sources(self, text: str) -> list:
        """The sources under an answer's "Sources", each with its site's real logo (see gink.sources)."""
        return sources(text, self.base_url)

    def maps(self, text: str) -> list:
        """The maps in an answer (ask with gink_maps=True): see gink.maps."""
        return maps(text)

    def artifacts(self, text: str) -> list:
        """The finished things in an answer (ask with gink_artifacts=True): see gink.artifacts."""
        return artifacts(text)

    def schedules_in(self, text: str) -> list:
        """The schedules an answer offers (ask with gink_tasks=True): see gink.schedules_in."""
        return schedules_in(text)

    def geo(self, query: str, limit: int = 5) -> list:
        """Places by name or address (OpenStreetMap): [{"name", "display", "lat", "lon", "type", "map_url"}]."""
        r = self.request("GET", "/geo/search", params={"q": query, "limit": int(limit)})
        return [_Obj(p) for p in r.json().get("data", [])]

    def place_photo(self, name: str, lat: float, lon: float):
        """A picture of a place, like the ones on Gink's map cards (Wikipedia's, for the article about it):
        {"image", "title", "page", "credit"} -- or None when there's no picture of it."""
        try:
            return _Obj(self.request("GET", "/places/photo", params={"name": name, "lat": lat, "lon": lon}).json())
        except GinkAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def see_screen(self, question: str = "", model: str = "", **extra) -> str:
        """Like Live screen view: an answer about what's on this computer's screen right now (Gink Pro)."""
        return self.see(screen_image(), question or "What's on my screen?", model=model, **extra)

    def see(self, photo, question: str = "", model: str = "", **extra) -> str:
        """An answer about a photo -- like the Live camera: Gink works out what it needs (reads text, finds what's
        wrong, solves sums...) and is careful with anything about health. photo: bytes, a file path or a data URL
        (JPEG, PNG, WebP or GIF). Looking at photos is part of Gink Pro."""
        content = [{"type": "text", "text": (question or "").strip() or "What's this?"},
                   {"type": "image_url", "image_url": {"url": image_data_url(photo)}}]
        return self.chat([{"role": "user", "content": content}], model=model, **extra)

    def image(self, prompt: str = "", idea: str = "", subject: str = "", style: str = "", aspect_ratio: str = "",
              photo=None) -> bytes:
        """An image (PNG/JPEG bytes). idea: a ready-made look (see image_ideas()), its subject = subject or prompt;
        style: "3d", "photo"... or your own words; aspect_ratio: "1:1", "16:9", "9:16", "4:3", "3:4";
        photo: bytes or a file path, to start from someone's own photo (use photos of people who agreed)."""
        import base64
        body = {"prompt": prompt}
        if idea:
            body.update(idea=idea, subject=subject or prompt)
        if style:
            body["style"] = style
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if photo is not None:
            raw = photo if isinstance(photo, (bytes, bytearray)) else open(photo, "rb").read()
            body["photo"] = base64.b64encode(bytes(raw)).decode("ascii")
        data = self.request("POST", "/images/generations", json=body).json()
        return base64.b64decode(data["data"][0]["b64_json"])

    def image_ideas(self) -> dict:
        """{"styles": [...], "ideas": [{"id": "statue", "title", "example_subject", ...}]} -- Media Studio's looks."""
        return self.request("GET", "/images/ideas").json()

    def status(self) -> dict:
        """Is Gink working right now? {"status": "ok" | "degraded" | "down" | "notice", "message", "components"}."""
        base = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        return self._http.get(base + "/status", headers={"User-Agent": "gink-python"}).json()

    def export_account(self) -> bytes:
        """Everything Gink's server keeps for this account, as a ZIP (bytes). At most once every 10 minutes."""
        return self.request("GET", "/account/export.zip").content

    def models(self) -> list:
        return [m["id"] for m in self.request("GET", "/models").json().get("data", [])]


class _Interactions:
    def __init__(self, client: Client):
        self.c = client

    def create(self, input: str, agent: str = "gink-agent", environment: str = "remote", previous_interaction_id: str = "",
               background: bool = False, stream: bool = False, max_steps: int = 30, tools: Optional[list] = None,
               webhook_url: str = "", notify_email: bool = False):
        """Run the managed agent. Returns an Interaction -- or, with stream=True, an iterator of live Events."""
        body = {"agent": agent, "input": input, "max_steps": max_steps, "background": bool(background), "stream": bool(stream)}
        if previous_interaction_id:
            body["previous_interaction_id"] = previous_interaction_id
        if environment and not previous_interaction_id:
            body["environment"] = environment
        if tools is not None:
            body["tools"] = list(tools)
        if webhook_url:
            body["webhook_url"] = webhook_url
        if notify_email:
            body["notify_email"] = True
        if stream:
            return self._stream(body)
        return Interaction(self.c.request("POST", "/interactions", json=body).json())

    def _stream(self, body) -> Iterator[Event]:
        try:
            with self.c._http.stream("POST", self.c.base_url + "/interactions", headers=self.c._headers(), json=body) as r:
                if r.status_code >= 400:
                    r.read()
                    raise GinkAPIError(r.text[:300], r.status_code)
                kind = ""
                for line in r.iter_lines():
                    if line.startswith("event: "):
                        kind = line[7:].strip()
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        yield Event(type=kind, data=Interaction(data) if kind == "done" else _Obj(data))
        except httpx.HTTPError as exc:
            raise GinkAPIError(f"Couldn't reach Gink ({type(exc).__name__}).", 0, "network") from exc

    def get(self, interaction_id: str) -> Interaction:
        return Interaction(self.c.request("GET", f"/interactions/{interaction_id}").json())

    def cancel(self, interaction_id: str) -> Interaction:
        return Interaction(self.c.request("POST", f"/interactions/{interaction_id}/cancel").json())

    def wait(self, interaction_id: str, every: float = 1.5, timeout: float = 1800) -> Interaction:
        """For background interactions: check until it's no longer running."""
        end = time.time() + timeout
        while True:
            it = self.get(interaction_id)
            if it.status != "running" or time.time() > end:
                return it
            time.sleep(every)


class Environment(_Obj):
    """A persistent workspace (a Gink Genie project). env.files, env.upload(path, data), env.download(path)."""

    def __init__(self, data: dict, client: Client):
        super().__init__(data)
        self._c = client

    def upload(self, path: str, data) -> "Environment":
        content = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        self.update(self._c.request("PUT", f"/environments/{self['id']}/files/{path}", content=content).json())
        return self

    def download(self, path: str) -> bytes:
        return self._c.request("GET", f"/environments/{self['id']}/files/{path}").content

    def check(self) -> _Obj:
        """The whole environment checked (nothing runs): .ok, .problems, .missing, .broken, .fix_request --
        give fix_request to client.interactions.create(input=..., environment=env.id) to fix them all."""
        return _Obj(self._c.request("GET", f"/environments/{self['id']}/check").json())

    def refresh(self) -> "Environment":
        self.update(self._c.request("GET", f"/environments/{self['id']}").json())
        return self

    def delete(self) -> None:
        self._c.request("DELETE", f"/environments/{self['id']}")


class _Environments:
    def __init__(self, client: Client):
        self.c = client

    def create(self, name: str = "Agent environment") -> Environment:
        return Environment(self.c.request("POST", "/environments", json={"name": name}).json(), self.c)

    def list(self) -> list:
        return [Environment(e, self.c) for e in self.c.request("GET", "/environments").json().get("data", [])]

    def get(self, environment_id: str) -> Environment:
        return Environment(self.c.request("GET", f"/environments/{environment_id}").json(), self.c)


class _Schedules:
    """Scheduled agents: client.schedules.create(input="Update report.md with today's news", every="daily", at="08:00")."""

    def __init__(self, client: Client):
        self.c = client

    def create(self, input: str, every: str = "daily", at: str = "08:00", timezone: str = "", environment: str = "remote",
               tools: Optional[list] = None, webhook_url: str = "", notify_email: bool = False) -> _Obj:
        body = {"input": input, "every": every, "at": at, "environment": environment}
        if webhook_url:
            body["webhook_url"] = webhook_url
        if notify_email:
            body["notify_email"] = True
        if timezone:
            body["timezone"] = timezone
        if tools is not None:
            body["tools"] = list(tools)
        return _Obj(self.c.request("POST", "/schedules", json=body).json())

    def list(self) -> list:
        return [_Obj(s) for s in self.c.request("GET", "/schedules").json().get("data", [])]

    def run(self, schedule_id: str) -> _Obj:
        return _Obj(self.c.request("POST", f"/schedules/{schedule_id}/run").json())

    def pause(self, schedule_id: str) -> _Obj:
        return _Obj(self.c.request("PATCH", f"/schedules/{schedule_id}", json={"enabled": False}).json())

    def resume(self, schedule_id: str) -> _Obj:
        return _Obj(self.c.request("PATCH", f"/schedules/{schedule_id}", json={"enabled": True}).json())

    def delete(self, schedule_id: str) -> None:
        self.c.request("DELETE", f"/schedules/{schedule_id}")


class _Tasks:
    """Scheduled tasks for your account: at its time Gink does the task by itself (searching the web as it needs) and
    the result lands in the task's own chat in your Gink apps -- and by email with notify_email=True.

        task = client.tasks.create("Give me the three biggest news stories, with sources", every="daily", at="08:00")
        client.tasks.run(task.id).text            # now, and wait for the result
        client.tasks.get(task.id).results         # [{"text", "created"}], newest last

    every: once (date="YYYY-MM-DD"), hourly (Gink Pro), daily, weekdays, weekly (day="monday"), monthly (day=1..31).
    The time is your computer's time zone unless you pass timezone="Europe/Paris"."""

    def __init__(self, client: Client):
        self.c = client

    def create(self, task: str, every: str = "daily", at: str = "08:00", title: str = "", day=None, date: str = "",
               timezone: str = "", notify_email: bool = False) -> _Obj:
        body = {"task": task, "every": every, "at": at}
        for k, v in (("title", title), ("day", day), ("date", date), ("timezone", timezone)):
            if v not in (None, ""):
                body[k] = v
        if notify_email:
            body["notify_email"] = True
        return _Obj(self.c.request("POST", "/tasks", json=body).json())

    def list(self) -> list:
        return [_Obj(t) for t in self.c.request("GET", "/tasks").json().get("data", [])]

    def get(self, task_id: str, results: int = 5) -> _Obj:
        return _Obj(self.c.request("GET", f"/tasks/{task_id}", params={"results": int(results)}).json())

    def update(self, task_id: str, **fields) -> _Obj:
        """Change a task: title, task, every, at, day, date, timezone, notify_email, enabled."""
        return _Obj(self.c.request("PATCH", f"/tasks/{task_id}", json=fields).json())

    def pause(self, task_id: str) -> _Obj:
        return self.update(task_id, enabled=False)

    def resume(self, task_id: str) -> _Obj:
        return self.update(task_id, enabled=True)

    def run(self, task_id: str, wait: bool = True) -> _Obj:
        """Run it now. wait=True: {"status", "text", "task"} once it's done (a minute or so)."""
        return _Obj(self.c.request("POST", f"/tasks/{task_id}/run", json={"wait": bool(wait)}).json())

    def delete(self, task_id: str) -> None:
        self.c.request("DELETE", f"/tasks/{task_id}")


class _Webhooks:
    """The secret Gink signs webhooks with (Gink-Signature header). Keep it on your server."""

    def __init__(self, client: Client):
        self.c = client

    def secret(self) -> str:
        return self.c.request("GET", "/webhooks/secret").json()["secret"]

    def rotate(self) -> str:
        return self.c.request("POST", "/webhooks/secret/rotate").json()["secret"]


def verify_webhook(body: bytes, signature: str, secret: str, tolerance: int = 300) -> dict:
    """Check a webhook really came from Gink, then return its JSON. `body`: the raw request body (bytes, exactly as
    received); `signature`: the Gink-Signature header. Raises GinkAPIError if it doesn't match or is too old."""
    import hashlib
    import hmac
    parts = dict(p.split("=", 1) for p in str(signature or "").split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        raise GinkAPIError("Bad Gink-Signature header.", 400, "bad_signature")
    if abs(time.time() - ts) > tolerance:
        raise GinkAPIError("The webhook is too old (or the clocks differ).", 400, "stale_signature")
    raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode()
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + bytes(raw), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts.get("v1", "")):
        raise GinkAPIError("The webhook's signature doesn't match.", 400, "bad_signature")
    return json.loads(raw)


class _Memories:
    """What Gink remembers about you -- the same memories as your apps and the web app.
    client.memories.add("I live in Nairobi") -- a single fact said again (a new city, a new number) replaces the old one."""

    def __init__(self, client: Client):
        self.c = client

    def list(self) -> list:
        return [_Obj(m) for m in self.c.request("GET", "/memories").json().get("data", [])]

    def add(self, text: str) -> _Obj:
        return _Obj(self.c.request("POST", "/memories", json={"text": text}).json())

    def forget(self, memory_id: str) -> None:
        self.c.request("DELETE", f"/memories/{memory_id}")

    def suggest(self, text: str, sensitive: bool = False):
        """A lasting fact in `text` worth offering to remember ("I live in Nairobi"), or None. Saves nothing.
        sensitive=True also considers health, religion and other sensitive topics (never for teens' accounts)."""
        return self.c.request("POST", "/memories/suggest", json={"text": text, "sensitive": bool(sensitive)}).json().get("fact")

    def generate(self, messages: list, save: bool = True, sensitive: bool = False) -> list:
        """"Generate memory from chats": the lasting facts in a conversation (a messages list, like chat's), picked by
        Gink's AI -- at most 5, saved to memory unless save=False. Returns the saved memories (or, with save=False,
        [{"text"}])."""
        body = {"messages": list(messages), "save": bool(save), "sensitive": bool(sensitive)}
        return [_Obj(m) for m in self.c.request("POST", "/memories/generate", json=body).json().get("data", [])]

    def import_prompt(self) -> str:
        """What to ask your other AI assistant so it lists what it remembers about you (then use import_text)."""
        return self.c.request("GET", "/memories/import-prompt").json().get("prompt", "")

    def import_text(self, text: str, sensitive: bool = False) -> _Obj:
        """"Import memory from other AI providers": another assistant's answer to import_prompt(), one fact per line,
        added to memory. {"data": [saved memories], "skipped", "skipped_sensitive", "memory_full"}."""
        return _Obj(self.c.request("POST", "/memories/import", json={"text": str(text), "sensitive": bool(sensitive)}).json())


class _Batches:
    """Many chat requests at once, answered in the background (up to 100):
    batch = client.batches.create(["Summarise ...", "Translate ..."]); client.batches.wait(batch.id); client.batches.results(batch.id)"""

    def __init__(self, client: Client):
        self.c = client

    def create(self, requests: list, name: str = "", model: str = "") -> _Obj:
        """requests: prompts (strings), message lists, or {"custom_id", "body": {chat request}} items."""
        items = []
        for i, r in enumerate(requests):
            if isinstance(r, dict) and "body" in r:
                items.append({"custom_id": str(r.get("custom_id") or f"request-{i + 1}"), "body": r["body"]})
                continue
            messages = r if isinstance(r, list) else [{"role": "user", "content": str(r)}]
            items.append({"custom_id": f"request-{i + 1}", "body": dict({"messages": messages}, **({"model": model} if model else {}))})
        body = {"requests": items}
        if name:
            body["name"] = name
        return _Obj(self.c.request("POST", "/batches", json=body).json())

    def get(self, batch_id: str) -> _Obj:
        return _Obj(self.c.request("GET", f"/batches/{batch_id}").json())

    def list(self) -> list:
        return [_Obj(b) for b in self.c.request("GET", "/batches").json().get("data", [])]

    def cancel(self, batch_id: str) -> _Obj:
        return _Obj(self.c.request("POST", f"/batches/{batch_id}/cancel").json())

    def results(self, batch_id: str) -> list:
        """[{"custom_id", "response" | "error"}], one per request (JSON Lines on the server)."""
        import json as _json
        text = self.c.request("GET", f"/batches/{batch_id}/results").text
        return [_Obj(_json.loads(line)) for line in text.splitlines() if line.strip()]

    def wait(self, batch_id: str, every: float = 2.0, timeout: float = 3600) -> _Obj:
        start = time.time()
        while True:
            b = self.get(batch_id)
            if b["status"] in ("completed", "failed", "cancelled", "expired") or time.time() - start > timeout:
                return b
            time.sleep(every)


class _Audio:
    """Voice messages in your own app: client.audio.transcribe("note.m4a") and client.audio.speech("Hello")."""

    def __init__(self, client: Client):
        self.c = client

    def transcribe(self, audio, filename: str = "", language: str = "") -> str:
        """Speech to text in any language. audio: a file path or bytes (WAV, WebM, OGG, M4A/MP4, MP3, FLAC)."""
        if isinstance(audio, (bytes, bytearray)):
            raw, name = bytes(audio), filename or "speech.wav"
        else:
            raw, name = open(str(audio), "rb").read(), filename or os.path.basename(str(audio))
        data = {"language": language} if language else {}
        r = self.c.request("POST", "/audio/transcriptions", files={"file": (name, raw)}, data=data)
        return r.json().get("text", "")

    def speech(self, text: str, voice: str = "", speed: str = "") -> bytes:
        """Gink's natural voice: WAV bytes (voice: e.g. "Female (Jenny)"; speed: "slow" or "fast")."""
        body = {"input": text}
        if voice:
            body["voice"] = voice
        if speed:
            body["speed"] = speed
        return self.c.request("POST", "/audio/speech", json=body).content


class _Workspace:
    """Your workspace (a hospital, school or business). Admins of one in healthcare mode also get its safety report:
    counts only -- patient details removed or stopped, photos checked -- never words."""

    def __init__(self, client: Client):
        self.c = client

    def get(self) -> _Obj:
        """{"workspace": {"id", "name", "healthcare", "patient_details": "remove" | "stop"} or None, "role", "status"}"""
        return _Obj(self.c.request("GET", "/workspace").json())

    def safety(self, days: int = 30) -> _Obj:
        """{"totals": {"patient_details_removed", "patient_details_stopped", "photo_checked"}, "by_day", "by_person",
        "by_feature"} for the last `days` days (admins only)."""
        return _Obj(self.c.request("GET", "/workspace/safety", params={"days": int(days)}).json())
