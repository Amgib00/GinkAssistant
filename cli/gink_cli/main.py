"""
gink -- Gink in your terminal (the Gink Developer API, OpenAI-compatible).

    gink "question"                 one answer, streamed
    gink                            a chat (type /help inside)
    cat file | gink "summarise"     send a file's text with the question
    gink -s "question"              search the web (answers list their sources)
    gink --save-artifacts [DIR] "make a pomodoro timer page"   the finished things in the answer, saved as files
    gink --schedule "every morning at 8, the top news"        make the scheduled tasks the answer offers
                                    (links in a question are read and the web searched when needed: --no-auto turns it off)
    gink see PHOTO ["question"]     about a photo: Gink reads it, finds what's wrong, solves it... (Gink Pro)
    gink --image "prompt" -o x.png  make an image
    gink agent "task"               a managed agent does it in a workspace that persists (--env ID, --continue)
    gink env list | new NAME | files ID | check ID [--fix] | pull ID [DIR] | push ID DIR | rm ID
    gink tasks add "task" --every daily --at 08:00 [--day monday] [--date 2026-12-24] [--email]
    gink tasks | show ID | run ID | pause ID | resume ID | rm ID
                                    scheduled tasks: Gink does it at its time; the result is in its chat in your apps
    gink schedule add "task" --every daily --at 08:00 [--env ID] | list | run ID | pause ID | resume ID | rm ID
                                    scheduled agents (the time is your computer's time zone)
    gink export [FILE]              everything Gink's server keeps for you, as a ZIP
    gink remember "fact" | memories | forget ID   what Gink remembers about you
    gink memories prompt            what to ask your other AI assistant, to bring its memory to Gink
    gink memories import FILE|-     add what it answered (one fact per line; --sensitive keeps health, religion...)
    gink memories generate TEXT|-   the lasting facts in a conversation, remembered (--dry-run: only show them)
    gink --no-location ...          no location metadata (city/region): only the clock's UTC offset (or GINK_LOCATION=off)
    gink batch FILE [--name N]      many requests at once (one prompt per line); gink batches | batch results ID
    gink map PLACE [--photos]       find a place by name or address (with an OpenStreetMap link; --photos: a picture)
    gink say "text" [-o file.wav]   Gink's natural voice, saved as audio
    gink transcribe RECORDING       a voice message as text (any language)
    gink screen ["question"]        what's on this computer's screen (like Live screen view; Gink Pro)
    gink workspace [safety --days 30]   your workspace; admins: healthcare mode's safety report (counts only)
    gink status                     is Gink working right now?
    gink webhook secret             the secret Gink signs webhooks with (schedule add --webhook URL)
    gink ideas                      ready-made image looks: gink --image "my dog" --idea statue --photo dog.jpg
                                    the agents' workspaces (the same projects as Gink Genie)
    gink login                      sign in through your browser -- a passkey works (Face ID, Touch ID, Windows Hello)
                                    (or: gink login --key to paste a key)
    gink logout | models | version
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
    try:
        from gink.client import place_headers           # the computer's time zone + region: local answers
        place = place_headers()
    except Exception:
        place = {}
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=30),
                        headers=dict({"Authorization": f"Bearer {key}", "User-Agent": f"gink-cli/{__version__}"}, **place))


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
        raise GinkError("You're not signed in yet. Run: gink login")


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


def stream_answer(key: str, base: str, messages: list, model: str = "", out=None, extra: dict = None) -> str:
    """Send the chat; print the answer as it arrives; return the full text. extra: Gink's own options
    (gink_web, gink_code, gink_artifacts, gink_tasks)."""
    need_key(key)
    import httpx
    out = out or sys.stdout
    body = dict({"messages": messages, "stream": True}, **(extra or {}))
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


def make_image(key: str, base: str, prompt: str, path: str, idea: str = "", style: str = "", aspect: str = "",
               photo: str = "") -> str:
    """An image; optionally a ready-made idea (gink ideas), a style ("3d"...), a shape ("3:4") and a photo to start from."""
    need_key(key)
    import httpx
    body = {"prompt": prompt}
    if idea:
        body.update(idea=idea, subject=prompt)
    if style:
        body["style"] = style
    if aspect:
        body["aspect_ratio"] = aspect
    if photo:
        try:
            with open(photo, "rb") as f:
                body["photo"] = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            raise GinkError(f"can't read the photo {photo}")
    try:
        with _client(key, 180) as c:
            r = c.post(base + "/images/generations", json=body)
    except httpx.HTTPError as exc:
        raise _network(exc)
    if r.status_code != 200:
        raise _explain(r)
    data = r.json()["data"][0]["b64_json"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    return path


def run_agent(key: str, base: str, task: str, env: str = "remote", previous: str = "", max_steps: int = 30) -> dict:
    """A managed agent (POST /v1/interactions): runs in the background while we show its steps."""
    need_key(key)
    import httpx
    body = {"agent": "gink-agent", "input": task, "environment": env or "remote", "background": True, "max_steps": max_steps}
    if previous:
        body["previous_interaction_id"] = previous
        body.pop("environment")
    try:
        with _client(key, 60) as c:
            r = c.post(base + "/interactions", json=body)
            if r.status_code != 200:
                raise _explain(r)
            it, shown = r.json(), 0
            while it["status"] == "running":
                time.sleep(1.5)
                r = c.get(f"{base}/interactions/{it['id']}")
                if r.status_code != 200:
                    raise _explain(r)
                it = r.json()
                for step in it.get("steps", [])[shown:]:
                    if step.get("tool") == "plan":                 # the agent's plan, as it changes
                        marks = {"done": "\u2713", "doing": "\u25d0", "todo": "\u25cb"}      # (no backslash in f-strings: 3.11)
                        print("  \u2022 plan: " + "  ".join(marks.get(p.get("status"), marks["todo"]) + " " + str(p.get("title"))
                                                          for p in step.get("plan", [])), file=sys.stderr)
                        continue
                    what = step.get("query") or step.get("path") or (
                        str(step.get("result") or "")[:140] if step.get("tool") == "check" else "")   # "2 problems found -- fixing"
                    print(f"  \u2022 {step.get('tool')} {what}".rstrip(), file=sys.stderr)
                shown = len(it.get("steps", []))
    except httpx.HTTPError as exc:
        raise _network(exc)
    return it


def _env_call(key: str, base: str, method: str, path: str, **kw):
    need_key(key)
    import httpx
    try:
        with _client(key, 120) as c:
            r = c.request(method, base + path, **kw)
    except httpx.HTTPError as exc:
        raise _network(exc)
    if r.status_code != 200:
        raise _explain(r)
    return r


def env_command(key: str, base: str, args: list) -> int:
    """gink env ...: list, create, look into, download, upload, delete environments (Genie projects)."""
    what = args[0] if args else "list"
    if what == "list":
        for e in _env_call(key, base, "GET", "/environments").json()["data"]:
            print(f"{e['id']}  {e['name']}  ({len(e['files'])} files)")
        return 0
    if what == "new":
        e = _env_call(key, base, "POST", "/environments", json={"name": " ".join(args[1:]) or "Agent environment"}).json()
        print(e["id"])
        return 0
    if len(args) < 2:
        raise GinkError("say which environment (its id from 'gink env list')")
    env = args[1]
    if what == "check":                                    # the whole project; --fix asks an agent to fix it all
        r = _env_call(key, base, "GET", f"/environments/{env}/check").json()
        if r["ok"]:
            print(f"All good: {r['files']} files checked.")
            return 0
        print(f"{len(r['problems'])} problem" + ("s" if len(r["problems"]) != 1 else "") + f" in {r['files']} files:")
        for p in r["problems"]:
            print(f"  - {p}")
        if "--fix" in args[2:]:
            print("Fixing them all...")
            run_agent(key, base, r["fix_request"], env, max_steps=30)        # shows each step as it happens
            after = _env_call(key, base, "GET", f"/environments/{env}/check").json()
            print("All fixed." if after["ok"] else f"{len(after['problems'])} still left: gink env check {env} --fix")
            return 0 if after["ok"] else 1
        print(f"Fix them all: gink env check {env} --fix")
        return 1
    if what == "files":
        for f in _env_call(key, base, "GET", f"/environments/{env}").json()["files"]:
            print(f"{f['size']:>9}  {f['path']}")
        return 0
    if what == "pull":
        target = args[2] if len(args) > 2 else env
        files = _env_call(key, base, "GET", f"/environments/{env}").json()["files"]
        for f in files:
            dest = os.path.normpath(os.path.join(target, f["path"]))
            if not dest.startswith(os.path.normpath(target)):
                continue                                   # never write outside the folder
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "wb") as out:
                out.write(_env_call(key, base, "GET", f"/environments/{env}/files/{f['path']}").content)
        print(f"Downloaded {len(files)} files to {target}/")
        return 0
    if what == "push":
        if len(args) < 3 or not os.path.isdir(args[2]):
            raise GinkError("gink env push ID FOLDER")
        n = 0
        for root, dirs, names in os.walk(args[2]):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv", "venv")]
            for name in names:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, args[2]).replace(os.sep, "/")
                with open(path, "rb") as f:
                    _env_call(key, base, "PUT", f"/environments/{env}/files/{rel}", content=f.read())
                n += 1
        print(f"Uploaded {n} files to {env}")
        return 0
    if what == "rm":
        _env_call(key, base, "DELETE", f"/environments/{env}")
        print(f"Deleted {env}")
        return 0
    raise GinkError("gink env list | new NAME | files ID | check ID [--fix] | pull ID [DIR] | push ID DIR | rm ID")


def schedule_command(key: str, base: str, args: list) -> int:
    """gink schedule add|list|run|pause|resume|rm: agents that run hourly, daily or weekly."""
    what = args[0] if args else "list"
    if what == "add":
        ap = argparse.ArgumentParser(prog="gink schedule add")
        ap.add_argument("task", nargs="+")
        ap.add_argument("--every", default="daily", choices=["hourly", "daily", "weekdays", "weekly"])
        ap.add_argument("--at", default="08:00", help="24-hour time, in your computer's time zone")
        ap.add_argument("--env", default="remote")
        ap.add_argument("--webhook", default="", help="https address Gink notifies after each run (signed)")
        ap.add_argument("--email", action="store_true", help="email me the result of each run")
        b = ap.parse_args(args[1:])
        body = {"input": " ".join(b.task), "every": b.every, "at": b.at, "environment": b.env}
        if b.webhook:
            body["webhook_url"] = b.webhook
        if b.email:
            body["notify_email"] = True
        s = _env_call(key, base, "POST", "/schedules", json=body).json()
        print(f"{s['id']}  {s['every']} at {s['at']} ({s['timezone']})  next: {time.strftime('%a %d %b %H:%M', time.localtime(s['next_run']))}")
        print(f"Workspace: {s['environment']}  (see the results in Gink Genie, or: gink env files {s['environment']})")
        return 0
    if what == "list":
        rows = _env_call(key, base, "GET", "/schedules").json()["data"]
        for s in rows:
            state = "on " if s["enabled"] else "off"
            print(f"{s['id']}  {state} {s['every']:<6} {s['at']}  {s['input'][:60]}")
        if not rows:
            print("No schedules. Add one: gink schedule add \"Update report.md with today's news\" --every daily --at 08:00")
        return 0
    if len(args) < 2:
        raise GinkError("say which schedule (its id from 'gink schedule list')")
    sid = args[1]
    if what == "run":
        r = _env_call(key, base, "POST", f"/schedules/{sid}/run").json()
        print(f"Started {r['interaction_id']}. Follow it on the console's Agents page, or open its workspace in Gink Genie.")
        return 0
    if what in ("pause", "resume"):
        _env_call(key, base, "PATCH", f"/schedules/{sid}", json={"enabled": what == "resume"})
        print(("Resumed " if what == "resume" else "Paused ") + sid)
        return 0
    if what == "rm":
        _env_call(key, base, "DELETE", f"/schedules/{sid}")
        print(f"Deleted {sid}")
        return 0
    raise GinkError("gink schedule add | list | run ID | pause ID | resume ID | rm ID")


def _when(t: dict) -> str:
    nxt = time.strftime("%a %d %b %H:%M", time.localtime(t["next_run"])) if t.get("next_run") else ""
    return t.get("when", "") + (f" ({t.get('timezone')})" if t.get("timezone") else "") + (f"  next: {nxt}" if nxt else "")


def tasks_command(key: str, base: str, args: list) -> int:
    """gink tasks add|list|show|run|pause|resume|rm: scheduled tasks -- the result lands in the task's chat."""
    what = args[0] if args else "list"
    if what == "add":
        ap = argparse.ArgumentParser(prog="gink tasks add")
        ap.add_argument("task", nargs="+")
        ap.add_argument("--every", default="daily", choices=["once", "hourly", "daily", "weekdays", "weekly", "monthly"])
        ap.add_argument("--at", default="08:00", help="the time, in your computer's time zone (08:00, 8am, 17:30)")
        ap.add_argument("--day", default="", help="weekly: monday ... sunday; monthly: 1-31")
        ap.add_argument("--date", default="", help="once: YYYY-MM-DD")
        ap.add_argument("--title", default="")
        ap.add_argument("--email", action="store_true", help="email me each result")
        b = ap.parse_args(args[1:])
        body = {"task": " ".join(b.task), "every": b.every, "at": b.at}
        for k in ("day", "date", "title"):
            if getattr(b, k):
                body[k] = getattr(b, k)
        if b.email:
            body["notify_email"] = True
        t = _env_call(key, base, "POST", "/tasks", json=body).json()
        print(f"{t['id']}  “{t['title']}”  {_when(t)}")
        print("Each result arrives in its own chat in your Gink apps (and the web app). See them here: gink tasks show " + t["id"])
        return 0
    if what == "list":
        j = _env_call(key, base, "GET", "/tasks").json()
        for t in j["data"]:
            state = "on " if t["enabled"] else "off"
            print(f"{t['id']}  {state} {t['title'][:40]:<40}  {_when(t)}")
        lim = j.get("limits") or {}
        if not j["data"]:
            print("No scheduled tasks. Add one: gink tasks add \"Give me the top three news stories\" --every daily --at 08:00")
        elif lim.get("max"):
            print(f"\n{lim.get('used', len(j['data']))} of {lim['max']} tasks on your plan.")
        return 0
    if len(args) < 2:
        raise GinkError("say which task (its id from 'gink tasks')")
    tid = args[1]
    if what == "show":
        t = _env_call(key, base, "GET", f"/tasks/{tid}", params={"results": 3}).json()
        print(f"“{t['title']}”  {_when(t)}\n{t['task']}\n")
        for r in t.get("results") or []:
            print(time.strftime("%a %d %b %H:%M", time.localtime(r["created"])) if r.get("created") else "")
            print(r["text"] + "\n")
        if not t.get("results"):
            print("No results yet.")
        return 0
    if what == "run":
        print("Running it now (this takes a minute or so)…", file=sys.stderr)
        r = _env_call(key, base, "POST", f"/tasks/{tid}/run", json={"wait": True}).json()
        if r.get("text"):
            print(r["text"])
            return 0
        print(f"gink: {r.get('status')}: {r.get('note') or ''}", file=sys.stderr)
        return 1
    if what in ("pause", "resume"):
        _env_call(key, base, "PATCH", f"/tasks/{tid}", json={"enabled": what == "resume"})
        print(("Resumed " if what == "resume" else "Paused ") + tid)
        return 0
    if what == "rm":
        _env_call(key, base, "DELETE", f"/tasks/{tid}")
        print(f"Deleted {tid} (its chat and results stay in your apps)")
        return 0
    raise GinkError("gink tasks add | list | show ID | run ID | pause ID | resume ID | rm ID")


def save_artifacts(text: str, folder: str) -> list:
    """The answer's finished things (titled blocks) as files in `folder`; a newer version of the same one replaces it."""
    from gink.client import artifacts
    os.makedirs(folder or ".", exist_ok=True)
    saved = []
    for a in artifacts(text):
        name = os.path.basename(a["filename"]) or "artifact.txt"
        path = os.path.join(folder or ".", name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(a["content"] + ("" if a["content"].endswith("\n") else "\n"))
        if path not in saved:
            saved.append(path)
    return saved


def show_agent_result(it: dict) -> int:
    if it.get("output_text"):
        print(it["output_text"])
    if it.get("files_changed"):
        print(f"\nFiles changed: {', '.join(it['files_changed'])}", file=sys.stderr)
    print(f"Environment: {it.get('environment')}   Interaction: {it.get('id')}   "
          f"(continue with: gink agent --continue {it.get('id')} \"...\")", file=sys.stderr)
    if it.get("status") not in ("completed",):
        print(f"gink: {it.get('status')}: {(it.get('error') or {}).get('message', '')}", file=sys.stderr)
        return 1
    return 0


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


def device_login(base: str, open_browser: bool = True, sleep=time.sleep, say=print) -> str:
    """Sign in through the browser: show a code, the person approves it at /device, we get a key."""
    import socket
    import httpx
    root = base[:-3] if base.endswith("/v1") else base
    client = f"gink CLI on {socket.gethostname()[:40]}"
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(root + "/auth/device/start", json={"client": client})
            if r.status_code != 200:
                raise _explain(r)
            d = r.json()
            say(f"To sign in, open  {d['verification_uri']}  and enter:  {d['user_code']}")
            if open_browser:
                try:
                    import webbrowser
                    webbrowser.open(d["verification_uri_complete"])
                except Exception:
                    pass
            say("Waiting for you to approve in the browser\u2026  (Ctrl+C to cancel)")
            say("(Signing in there with a passkey works too: Face ID, Touch ID, Windows Hello or your phone.)")
            deadline = time.time() + int(d.get("expires_in", 600))
            while time.time() < deadline:
                sleep(int(d.get("interval", 5)))
                p = c.post(root + "/auth/device/poll", json={"device_code": d["device_code"]}).json()
                if p.get("status") == "approved":
                    return p["api_key"]
                if p.get("status") == "denied":
                    raise GinkError("The sign-in was denied in the browser.")
                if p.get("status") == "expired":
                    break
    except httpx.HTTPError as exc:
        raise _network(exc)
    raise GinkError("The code expired. Run gink login again.")


def login(base: str, paste_key: bool = False) -> int:
    if not paste_key:
        key = device_login(base)
        cfg = load_config()
        cfg["api_key"] = key
        if base != DEFAULT_BASE:
            cfg["base_url"] = base
        save_config(cfg)
        print("\u2713 Signed in. Try: gink \"hello\"")
        return 0
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
    if "--no-location" in argv:                        # like Settings > Privacy > "Location metadata" off
        argv = [a for a in argv if a != "--no-location"]
        os.environ["GINK_LOCATION"] = "off"
    key, base = settings()
    try:
        if argv[:1] == ["login"]:
            return login(base, paste_key="--key" in argv)
        if argv[:1] == ["logout"]:
            cfg = load_config()
            cfg.pop("api_key", None)
            save_config(cfg)
            print("Signed out: your API key was removed from this computer.")
            return 0
        if argv[:1] == ["models"]:
            print("\n".join(list_models(key, base)))
            return 0
        if argv[:1] == ["agent"]:
            ag = argparse.ArgumentParser(prog="gink agent", description="A managed agent with a workspace that persists.")
            ag.add_argument("task", nargs="+", help="what the agent should do")
            ag.add_argument("--env", default="remote", help="an environment id (default: a new one)")
            ag.add_argument("--continue", dest="previous", default="", help="an interaction id to continue")
            ag.add_argument("--max-steps", type=int, default=30, help="1-60 (default 30)")
            b = ag.parse_args(argv[1:])
            return show_agent_result(run_agent(key, base, " ".join(b.task), b.env, b.previous, b.max_steps))
        if argv[:1] == ["workspace"]:                 # your workspace; admins: healthcare mode's safety report
            if argv[1:2] == ["safety"]:
                days = 30
                if "--days" in argv:
                    try:
                        days = int(argv[argv.index("--days") + 1])
                    except (IndexError, ValueError):
                        raise GinkError("gink workspace safety --days 30")
                r = _env_call(key, base, "GET", f"/workspace/safety?days={days}").json()
                t = r["totals"]
                print(f"{r['workspace']['name']} \u2014 last {r['days']} days (counts only, never words)")
                print(f"  patient details removed   {t['patient_details_removed']}")
                print(f"  messages stopped          {t['patient_details_stopped']}")
                print(f"  photos checked            {t['photo_checked']}")
                for p in r["by_person"]:
                    bits = [f"{p[k]} {w}" for k, w in (("patient_details_removed", "removed"), ("patient_details_stopped", "stopped"),
                                                      ("photo_checked", "photos")) if p.get(k)]
                    print(f"    {p['name'] or p['account']}: " + ", ".join(bits))
                return 0
            r = _env_call(key, base, "GET", "/workspace").json()
            w = r.get("workspace")
            if not w:
                print("You're not in a workspace (create or join one in Gink > Settings > Workspace).")
                return 0
            mode = ("on \u2014 " + ("messages with patient details are stopped" if w["patient_details"] == "stop"
                                    else "patient details are removed automatically")) if w["healthcare"] else "off"
            print(f"{w['name']}  ({r.get('role')}, {r.get('status')})\n  healthcare mode: {mode}")
            if w["healthcare"] and r.get("role") == "admin":
                print("  safety report: gink workspace safety [--days 30]")
            return 0
        if argv[:1] == ["see"]:                       # a photo: Gink works out what it needs (like the Live camera)
            if len(argv) < 2:
                raise GinkError('gink see PHOTO ["question"]   e.g. gink see label.jpg "what does this say?"')
            try:
                from gink.client import image_data_url
                url = image_data_url(argv[1])
            except OSError:
                raise GinkError(f"can't read the photo {argv[1]}")
            except Exception as exc:                          # not a photo Gink can look at
                raise GinkError(str(exc))
            question = " ".join(argv[2:]).strip() or "What's this?"
            stream_answer(key, base, [{"role": "user", "content": [{"type": "text", "text": question},
                                                                   {"type": "image_url", "image_url": {"url": url}}]}])
            return 0
        if argv[:1] in (["batch"], ["batches"]):      # many requests at once, answered in the background
            sub = argv[1] if len(argv) > 1 else ("list" if argv[0] == "batches" else "")
            if sub == "list" or (argv[0] == "batches" and len(argv) == 1):
                for b in _env_call(key, base, "GET", "/batches").json()["data"]:
                    c = b["request_counts"]
                    print(f"{b['id']}  {b['status']:<10} {c['completed']}/{c['total']} done" + (f", {c['failed']} failed" if c["failed"] else "")
                          + (f"  {b['name']}" if b.get("name") else ""))
                return 0
            if sub in ("status", "results", "cancel") and len(argv) > 2:
                bid = argv[2]
                if sub == "results":
                    print(_env_call(key, base, "GET", f"/batches/{bid}/results").text, end="")
                    return 0
                b = _env_call(key, base, "POST" if sub == "cancel" else "GET", f"/batches/{bid}" + ("/cancel" if sub == "cancel" else "")).json()
                print(f"{b['id']}  {b['status']}  {b['request_counts']['completed']}/{b['request_counts']['total']} done")
                return 0
            if not sub:
                raise GinkError("gink batch FILE [--name NAME]   (one prompt per line, or JSON Lines {\"custom_id\", \"body\"})\n"
                                "gink batches | gink batch status|results|cancel BATCH_ID")
            name = ""
            if "--name" in argv:
                i = argv.index("--name")
                name = argv[i + 1] if i + 1 < len(argv) else ""
            try:
                lines = [ln for ln in open(sub, encoding="utf-8").read().splitlines() if ln.strip()]
            except OSError:
                raise GinkError(f"can't read {sub}")
            items = []
            for i, ln in enumerate(lines):
                try:
                    obj = json.loads(ln)
                except ValueError:
                    obj = None
                if isinstance(obj, dict) and "body" in obj:
                    items.append({"custom_id": str(obj.get("custom_id") or f"request-{i + 1}"), "body": obj["body"]})
                else:
                    items.append({"custom_id": f"request-{i + 1}", "body": {"messages": [{"role": "user", "content": ln}]}})
            b = _env_call(key, base, "POST", "/batches", json=dict({"requests": items}, **({"name": name} if name else {}))).json()
            print(f"{b['id']}  {b['status']}  ({len(items)} requests) -- gink batch results {b['id']} when it's done")
            return 0
        if argv[:1] == ["screen"]:                    # like Live screen view: what's on this computer's screen
            from gink.client import GinkAPIError as _SdkError, image_data_url, screen_image
            try:
                url = image_data_url(screen_image())
            except _SdkError as exc:
                raise GinkError(str(exc))
            question = " ".join(argv[1:]).strip() or "What's on my screen?"
            stream_answer(key, base, [{"role": "user", "content": [{"type": "text", "text": question},
                                                                   {"type": "image_url", "image_url": {"url": url}}]}])
            return 0
        if argv[:1] == ["map"]:                       # places by name or address, with a map link each
            photos = "--photos" in argv                 # and a picture of each, like Gink's map cards
            query = " ".join(a for a in argv[1:] if a != "--photos").strip()
            if not query:
                raise GinkError('gink map PLACE [--photos]   e.g. gink map "National Museum, Lagos" --photos')
            places = _env_call(key, base, "GET", "/geo/search", params={"q": query, "limit": 5}).json()["data"]
            if not places:
                print(f"No place found for \u201c{query}\u201d.")
            for p in places:
                print(f"\U0001F4CD {p['name']}  ({p['lat']}, {p['lon']})\n   {p['display']}\n   {p['map_url']}")
                if photos:
                    try:
                        pic = _env_call(key, base, "GET", "/places/photo",
                                        params={"name": p["name"], "lat": p["lat"], "lon": p["lon"]}).json()
                        print(f"   Photo: {pic['image']}  ({pic['credit']}: {pic['page']})")
                    except GinkError:
                        print("   (no photo)")
            return 0
        if argv[:1] == ["say"]:                       # Gink's natural voice, saved as a WAV file
            out = "gink-voice.wav"
            if "-o" in argv:
                i = argv.index("-o")
                out = argv[i + 1] if i + 1 < len(argv) else out
                argv = argv[:i] + argv[i + 2:]
            text = " ".join(argv[1:]).strip() or (sys.stdin.read() if not sys.stdin.isatty() else "")
            if not text:
                raise GinkError('gink say "text" [-o hello.wav]')
            audio = _env_call(key, base, "POST", "/audio/speech", json={"input": text[:1500]}).content
            with open(out, "wb") as f:
                f.write(audio)
            print(f"Saved {out} ({len(audio) // 1024} KB).")
            return 0
        if argv[:1] == ["transcribe"]:                # a voice message (any language) as text
            if len(argv) < 2:
                raise GinkError("gink transcribe RECORDING   (WAV, WebM, OGG, M4A, MP3 or FLAC)")
            try:
                raw = open(argv[1], "rb").read()
            except OSError:
                raise GinkError(f"can't read {argv[1]}")
            r = _env_call(key, base, "POST", "/audio/transcriptions", files={"file": (os.path.basename(argv[1]), raw)}).json()
            print(r.get("text", ""))
            return 0
        if argv[:1] == ["ideas"]:                     # Media Studio's looks, for --image --idea
            import httpx
            with httpx.Client(timeout=30) as c:
                cat = c.get(base + "/images/ideas").json()
            for i in cat["ideas"]:
                print(f"{i['id']:<11} {i['title']:<18} e.g. gink --image \"{i['example_subject']}\" --idea {i['id']}")
            if cat.get("looks"):                       # picked by themselves from the words
                print("automatic: " + ", ".join(i["title"] for i in cat["looks"])
                      + ' -- just say it: gink --image "an x-ray of my camera"')
            print("styles: " + ", ".join(s["id"] for s in cat["styles"]))
            return 0
        if argv[:1] == ["status"]:                      # is Gink working right now? (no key needed)
            import httpx
            st = httpx.get((base[:-3] if base.endswith("/v1") else base) + "/status", timeout=15).json()
            print({"ok": "\u2705 Gink is working normally.", "notice": "\u2139\ufe0f " + st.get("message", ""),
                   "degraded": "\u26a0\ufe0f " + st.get("message", ""), "down": "\u274c " + st.get("message", "")}.get(st["status"], st["status"]))
            for k, v in st.get("components", {}).items():
                print(f"  {k:<8} {v}")
            return 0 if st["status"] in ("ok", "notice") else 1
        if argv[:2] == ["memories", "prompt"]:          # what to ask the other AI assistant
            print(_env_call(key, base, "GET", "/memories/import-prompt").json()["prompt"])
            return 0
        if argv[:2] in (["memories", "import"], ["memories", "generate"]):
            flags = {a for a in argv[2:] if a.startswith("--")}
            rest = [a for a in argv[2:] if not a.startswith("--")]
            if argv[1] == "import":                     # what the other assistant answered
                src = rest[0] if rest else "-"
                text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
                r = _env_call(key, base, "POST", "/memories/import",
                              json={"text": text, "sensitive": "--sensitive" in flags}).json()
                for m in r["data"]:
                    print("Remembered: " + m["text"])
                print(f"Added {len(r['data'])}." + (f" Skipped {r['skipped_sensitive']} about sensitive topics (--sensitive keeps them)."
                                                   if r.get("skipped_sensitive") else "")
                      + (f" Skipped {r['skipped']} Gink never keeps." if r.get("skipped") else "")
                      + (" Gink's memory is full." if r.get("memory_full") else ""))
                return 0
            text = sys.stdin.read() if rest[:1] == ["-"] or not rest else " ".join(rest)
            r = _env_call(key, base, "POST", "/memories/generate", json={
                "messages": [{"role": "user", "content": text[:20000]}], "save": "--dry-run" not in flags,
                "sensitive": "--sensitive" in flags}).json()
            for m in r["data"]:
                print(("Would remember: " if "--dry-run" in flags else "Remembered: ") + m["text"])
            if not r["data"]:
                print(r.get("note") or "Nothing lasting to remember in that.")
            return 0
        if argv[:1] in (["remember"], ["memories"], ["forget"]):    # what Gink remembers (the same as the apps)
            if argv[0] == "remember":
                if len(argv) < 2:
                    raise GinkError('gink remember "I live in Nairobi"')
                m = _env_call(key, base, "POST", "/memories", json={"text": " ".join(argv[1:])}).json()
                print(("Updated: " if m.get("replaced") else "Remembered: ") + m["text"]
                      + (f"   (replaces: {m['replaced']})" if m.get("replaced") else ""))
            elif argv[0] == "forget":
                if len(argv) < 2:
                    raise GinkError("gink forget ID   (ids: gink memories)")
                _env_call(key, base, "DELETE", f"/memories/{argv[1]}")
                print("Forgotten.")
            else:
                rows = _env_call(key, base, "GET", "/memories").json()["data"]
                for m in rows:
                    print(f"{m['id'][:8]}  {m['text']}")
                if not rows:
                    print('Nothing yet. Add one: gink remember "I prefer short answers"')
            return 0
        if argv[:1] == ["export"]:                      # everything on the server, as a ZIP
            out = argv[1] if len(argv) > 1 else f"gink-data-{time.strftime('%Y-%m-%d')}.zip"
            data = _env_call(key, base, "GET", "/account/export.zip").content
            with open(out, "wb") as f:
                f.write(data)
            print(f"Saved {out} ({len(data) // 1024} KB)")
            return 0
        if argv[:2] == ["webhook", "secret"]:           # the secret webhooks are signed with
            print(_env_call(key, base, "GET", "/webhooks/secret").json()["secret"])
            return 0
        if argv[:1] in (["tasks"], ["task"]):
            return tasks_command(key, base, argv[1:])
        if argv[:1] == ["schedule"]:
            return schedule_command(key, base, argv[1:])
        if argv[:1] == ["env"]:
            return env_command(key, base, argv[1:])
        if argv[:1] in (["version"], ["--version"]):
            print(f"gink {__version__}")
            return 0

        ap = argparse.ArgumentParser(prog="gink", description="Gink in your terminal.",
                                     epilog="Also: gink agent \"task\" | env ... | login | logout | models | version")
        ap.add_argument("question", nargs="*", help="what to ask (leave out for a chat)")
        ap.add_argument("-m", "--model", default="", help="a model from 'gink models' (default: your account's)")
        ap.add_argument("-s", "--search", action="store_true", help="search the web; answers list their sources")
        ap.add_argument("--system", default="", help="instructions for Gink in this conversation")
        ap.add_argument("--image", metavar="PROMPT", help="make an image instead of answering")
        ap.add_argument("-o", "--output", default="", help="where to save the image (default gink-image-<time>.png)")
        ap.add_argument("--idea", default="", help="with --image: a ready-made look (gink ideas), the prompt is its subject")
        ap.add_argument("--style", default="", help="with --image: photo, 3d, illustration, sticker, anime... or your own words")
        ap.add_argument("--aspect", default="", help="with --image: 1:1, 16:9, 9:16, 4:3 or 3:4")
        ap.add_argument("--photo", default="", help="with --image: start from this photo (JPEG, PNG or WebP)")
        ap.add_argument("--save-artifacts", nargs="?", const=".", default=None, metavar="DIR",
                        help="save the finished things in the answer (pages, SVGs, documents, code files) in DIR")
        ap.add_argument("--schedule", action="store_true", help="make the scheduled tasks the answer offers")
        ap.add_argument("--no-auto", action="store_true", help="don't read linked pages or code, or search by itself")
        a = ap.parse_args(argv)
        model = "gink-search" if a.search else a.model

        if a.image:
            path = make_image(key, base, a.image, a.output or f"gink-image-{int(time.time())}.png", a.idea, a.style,
                              a.aspect, a.photo)
            print(f"Saved {path}")
            return 0
        question = " ".join(a.question).strip()
        piped = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        if not question and not piped:
            return chat(key, base, model, a.system)
        messages = ([{"role": "system", "content": a.system}] if a.system else []) + \
                   [{"role": "user", "content": with_piped_text(question, piped)}]
        extra = {} if a.no_auto else {"gink_web": "auto", "gink_code": True}   # like the apps (0.1.161)
        if a.save_artifacts is not None:
            extra["gink_artifacts"] = True
        if a.schedule:
            extra["gink_tasks"] = True
        if not extra:
            stream_answer(key, base, messages, model)
            return 0
        answer = stream_answer(key, base, messages, model, extra=extra)
        if a.save_artifacts is not None:
            for path in save_artifacts(answer, a.save_artifacts):
                print(f"Saved {path}", file=sys.stderr)
        if a.schedule:
            from gink.client import schedules_in
            for offer in schedules_in(answer):
                t = _env_call(key, base, "POST", "/tasks", json=offer).json()
                print(f"Scheduled \u201c{t['title']}\u201d: {_when(t)} (results in its chat in your Gink apps)", file=sys.stderr)
        return 0
    except GinkError as exc:
        print(f"gink: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n(stopped)", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
