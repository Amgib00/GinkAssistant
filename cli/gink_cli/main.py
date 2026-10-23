"""
gink -- Gink in your terminal (the Gink Developer API, OpenAI-compatible).

    gink "question"                 one answer, streamed
    gink                            a chat (type /help inside)
    cat file | gink "summarise"     send a file's text with the question
    gink -s "question"              search the web (answers list their sources)
    gink --image "prompt" -o x.png  make an image
    gink login | logout | models | version
"""
import argparse
import base64
import getpass
import json
import os
import sys
import time

from . import __version__

DEFAULT_BASE = "https://gink-server.onrender.com/v1"
MAX_PIPED_CHARS = 200_000


class GinkError(Exception):
    pass


# ---------------------------------------------------------------- settings
def config_path() -> str:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(root, "gink", "config.json")


def load_config() -> dict:
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)      # only you can read your key
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def settings():
    cfg = load_config()
    key = os.environ.get("GINK_API_KEY") or cfg.get("api_key") or ""
    base = (os.environ.get("GINK_BASE_URL") or cfg.get("base_url") or DEFAULT_BASE).rstrip("/")
    return key, base


# ---------------------------------------------------------------- talking to Gink
def _client(key: str, timeout: float = 120):
    import httpx
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=30),
                        headers={"Authorization": f"Bearer {key}", "User-Agent": f"gink-cli/{__version__}"})


def _explain(r) -> GinkError:
    try:
        body = r.json()
        msg = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else body.get("detail")
    except Exception:
        msg = ""
    if r.status_code == 401:
        return GinkError("Your API key isn't valid (or was revoked). Run: gink login")
    if r.status_code == 429:
        wait = r.headers.get("retry-after")
        return GinkError((msg or "Limit reached.") + (f" Try again in {wait} seconds." if wait else ""))
    return GinkError(msg or f"The Gink server answered {r.status_code}.")


def _network(exc) -> GinkError:
    import httpx
    if isinstance(exc, httpx.TimeoutException):
        return GinkError("The Gink server didn't answer in time. If it was asleep it can take up to a minute "
                         "to wake up \u2014 please try again.")
    return GinkError(f"Can't reach the Gink server ({type(exc).__name__}). Check your connection.")


def need_key(key: str):
    if not key:
        raise GinkError("No API key yet. Create one in Gink (Settings > Developers), then run: gink login")


def list_models(key: str, base: str) -> list:
    need_key(key)
    import httpx
    try:
        with _client(key, 90) as c:
            r = c.get(base + "/models")
    except httpx.HTTPError as exc:
        raise _network(exc)
    if r.status_code != 200:
        raise _explain(r)
    return [m["id"] for m in r.json().get("data", [])]


def stream_answer(key: str, base: str, messages: list, model: str = "", out=None) -> str:
    """Send the chat; print the answer as it arrives; return the full text."""
    need_key(key)
    import httpx
    out = out or sys.stdout
    body = {"messages": messages, "stream": True}
    if model:
        body["model"] = model
    text = []
    try:
        with _client(key) as c, c.stream("POST", base + "/chat/completions", json=body) as r:
            if r.status_code != 200:
                r.read()
                raise _explain(r)
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise GinkError(chunk["error"].get("message") or "The AI service had a problem.")
                piece = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                if piece:
                    text.append(piece)
                    out.write(piece)
                    out.flush()
    except httpx.HTTPError as exc:
        raise _network(exc)
    out.write("\n")
    out.flush()
    return "".join(text)


def make_image(key: str, base: str, prompt: str, path: str) -> str:
    need_key(key)
    import httpx
    try:
        with _client(key, 180) as c:
            r = c.post(base + "/images/generations", json={"prompt": prompt})
    except httpx.HTTPError as exc:
        raise _network(exc)
    if r.status_code != 200:
        raise _explain(r)
    data = r.json()["data"][0]["b64_json"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    return path


# ---------------------------------------------------------------- the commands
def with_piped_text(question: str, piped: str) -> str:
    if not piped:
        return question
    if len(piped) > MAX_PIPED_CHARS:
        piped = piped[:MAX_PIPED_CHARS] + "\n[... cut: only the first 200,000 characters were sent]"
    return (f'<attached_file name="input">\n{piped}\n</attached_file>\n\n'
            + (question or "Please read this and summarise the important points."))


def chat(key: str, base: str, model: str, system: str = "") -> int:
    """An interactive chat. /help for commands; Ctrl+C stops an answer, Ctrl+D (or /exit) leaves."""
    need_key(key)
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    you = "\033[1;32myou \u203a\033[0m " if color else "you > "
    history = [{"role": "system", "content": system}] if system else []
    print(f"Gink chat \u00b7 {model or 'default model'} \u00b7 /help for commands, /exit to leave")
    while True:
        try:
            line = input(you).strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0
        if not line:
            continue
        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            if cmd in ("exit", "quit", "q"):
                return 0
            if cmd == "new":
                history = history[:1] if system else []
                print("New chat.")
            elif cmd == "model":
                model = arg.strip()
                print(f"Model: {model or 'default'}")
            elif cmd == "search":
                model = "gink-search" if arg.strip() != "off" else ""
                print("Web search on." if model == "gink-search" else "Web search off.")
            elif cmd == "models":
                try:
                    print("\n".join(list_models(key, base)))
                except GinkError as exc:
                    print(f"gink: {exc}")
            else:
                print("/new  start over  \u00b7  /model NAME  \u00b7  /models  \u00b7  /search on|off  \u00b7  /exit")
            continue
        history.append({"role": "user", "content": line})
        try:
            answer = stream_answer(key, base, history[-30:], model)
            history.append({"role": "assistant", "content": answer})
        except KeyboardInterrupt:
            print("\n(stopped)")
            history.pop()
        except GinkError as exc:
            print(f"gink: {exc}")
            history.pop()


def login(base: str) -> int:
    print("Paste your Gink API key (Gink > Settings > Developers > Create key). It starts with gink_live_")
    key = getpass.getpass("API key: ").strip()
    if not key.startswith("gink_live_"):
        print("gink: that doesn't look like a Gink API key (it should start with gink_live_).")
        return 1
    models = list_models(key, base)                      # check it works before saving it
    cfg = load_config()
    cfg["api_key"] = key
    if base != DEFAULT_BASE:
        cfg["base_url"] = base
    save_config(cfg)
    print(f"Signed in. {len(models)} models available. Try: gink \"hello\"")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    key, base = settings()
    try:
        if argv[:1] == ["login"]:
            return login(base)
        if argv[:1] == ["logout"]:
            cfg = load_config()
            cfg.pop("api_key", None)
            save_config(cfg)
            print("Signed out: your API key was removed from this computer.")
            return 0
        if argv[:1] == ["models"]:
            print("\n".join(list_models(key, base)))
            return 0
        if argv[:1] in (["version"], ["--version"]):
            print(f"gink {__version__}")
            return 0

        ap = argparse.ArgumentParser(prog="gink", description="Gink in your terminal.",
                                     epilog="Also: gink login | logout | models | version")
        ap.add_argument("question", nargs="*", help="what to ask (leave out for a chat)")
        ap.add_argument("-m", "--model", default="", help="a model from 'gink models' (default: your account's)")
        ap.add_argument("-s", "--search", action="store_true", help="search the web; answers list their sources")
        ap.add_argument("--system", default="", help="instructions for Gink in this conversation")
        ap.add_argument("--image", metavar="PROMPT", help="make an image instead of answering")
        ap.add_argument("-o", "--output", default="", help="where to save the image (default gink-image-<time>.png)")
        a = ap.parse_args(argv)
        model = "gink-search" if a.search else a.model

        if a.image:
            path = make_image(key, base, a.image, a.output or f"gink-image-{int(time.time())}.png")
            print(f"Saved {path}")
            return 0
        question = " ".join(a.question).strip()
        piped = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        if not question and not piped:
            return chat(key, base, model, a.system)
        messages = ([{"role": "system", "content": a.system}] if a.system else []) + \
                   [{"role": "user", "content": with_piped_text(question, piped)}]
        stream_answer(key, base, messages, model)
        return 0
    except GinkError as exc:
        print(f"gink: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n(stopped)", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
