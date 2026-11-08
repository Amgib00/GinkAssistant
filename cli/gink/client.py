"""Gink Developer API client: managed agents (interactions), environments, chat, images."""
import json
import os
import time
from typing import Iterator, Optional

import httpx

DEFAULT_BASE = "https://gink-server.onrender.com/v1"


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
                 http: Optional[httpx.Client] = None):
        self.api_key = api_key or os.environ.get("GINK_API_KEY") or _saved_key()
        if not self.api_key:
            raise GinkAPIError("No API key: pass api_key=, set GINK_API_KEY, or run `gink login`.", 401, "invalid_api_key")
        self.base_url = (base_url or os.environ.get("GINK_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self._http = http or httpx.Client(timeout=timeout)
        self.interactions = _Interactions(self)
        self.environments = _Environments(self)

    # ---- plumbing
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "User-Agent": "gink-python"}

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
    def chat(self, message, model: str = "", system: str = "", **extra) -> str:
        """One answer. `message` is text or a full messages list. Live info (date, weather, rates...) is added by Gink."""
        messages = message if isinstance(message, list) else (
            ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": str(message)}])
        body = dict({"messages": messages}, **({"model": model} if model else {}), **extra)
        data = self.request("POST", "/chat/completions", json=body).json()
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    def search(self, question: str) -> str:
        """An answer from the web, with its sources listed."""
        return self.chat(question, model="gink-search")

    def image(self, prompt: str) -> bytes:
        import base64
        data = self.request("POST", "/images/generations", json={"prompt": prompt}).json()
        return base64.b64decode(data["data"][0]["b64_json"])

    def models(self) -> list:
        return [m["id"] for m in self.request("GET", "/models").json().get("data", [])]


class _Interactions:
    def __init__(self, client: Client):
        self.c = client

    def create(self, input: str, agent: str = "gink-agent", environment: str = "remote", previous_interaction_id: str = "",
               background: bool = False, stream: bool = False, max_steps: int = 15, tools: Optional[list] = None):
        """Run the managed agent. Returns an Interaction -- or, with stream=True, an iterator of live Events."""
        body = {"agent": agent, "input": input, "max_steps": max_steps, "background": bool(background), "stream": bool(stream)}
        if previous_interaction_id:
            body["previous_interaction_id"] = previous_interaction_id
        if environment and not previous_interaction_id:
            body["environment"] = environment
        if tools is not None:
            body["tools"] = list(tools)
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
