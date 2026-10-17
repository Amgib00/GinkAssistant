"""
Checks the Gink dataset before any training run -- a model learns its data's mistakes.

    python tools/gink_dataset/validate.py            # checks out/train.jsonl + out/eval.jsonl

Fails (exit code 1) on: broken structure; tools Gink doesn't have; missing, unknown or
wrongly-typed arguments; wrong formats (HH:MM, YYYY-MM-DD HH:MM, allowed values); tool calls
without results; reminders in the past (relative to the example's own "now"); things that
look like real personal data (emails, phone or card numbers).
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "src"))
from ginkassistant.services.actions.agent import TOOL_SPECS      # noqa: E402

TOOLS = {t["function"]["name"]: t["function"].get("parameters", {}) for t in TOOL_SPECS}
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
ALLOWED = {("media_control", "action"): {"play", "pause", "play_pause", "next", "previous"},
           ("set_volume", "action"): {"up", "down", "mute", "unmute"},
           ("create_file", "format"): {"pdf", "docx", "xlsx", "csv", "md", "html", "txt"},
           ("compose_message", "channel"): {"sms", "whatsapp", "email"}}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
STAMP = "%Y-%m-%d %H:%M"
WEATHER_DAY = re.compile(r"^(now|today|tomorrow|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?<!\d)\+?\d[\d\s-]{8,}\d(?!\d)")
DATES = re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
NOW_EN = re.compile(r"It is now \w+ (\d+) (\w+) (\d{4}), (\d\d:\d\d)")
NOW_FR = re.compile(r"Nous sommes le \w+ (\d+) (\S+) (\d{4}), il est (\d\d:\d\d)")
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}
MONTHS.update({m: i + 1 for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                                               "septembre", "octobre", "novembre", "décembre"])})


def example_now(system: str):
    m = NOW_EN.search(system) or NOW_FR.search(system)
    if not m:
        return None
    d, mon, y, hm = m.groups()
    return dt.datetime.strptime(f"{y}-{MONTHS[mon]:02d}-{int(d):02d} {hm}", STAMP)


def check_args(name, args, now):
    errs, schema = [], TOOLS[name]
    props, required = schema.get("properties", {}), schema.get("required", [])
    for r in required:
        if r not in args:
            errs.append(f"{name}: missing required '{r}'")
    for k, v in args.items():
        if k not in props:
            errs.append(f"{name}: unknown argument '{k}'"); continue
        want = TYPES.get(props[k].get("type"))
        if want and (not isinstance(v, want) or (props[k].get("type") in ("integer", "number") and isinstance(v, bool))):
            errs.append(f"{name}.{k}: expected {props[k].get('type')}, got {type(v).__name__}")
        enum = props[k].get("enum") or ALLOWED.get((name, k))
        if enum and v not in enum:
            errs.append(f"{name}.{k}: '{v}' isn't one of {sorted(enum)}")
    if name == "set_alarm" and not HHMM.match(str(args.get("time", ""))):
        errs.append(f"set_alarm.time must be HH:MM, got {args.get('time')!r}")
    for key in (("add_reminder", "when"), ("add_task", "due"), ("add_calendar_event", "start")):
        if name == key[0] and key[1] in args:
            try:
                when = dt.datetime.strptime(args[key[1]], STAMP)
                if now and name == "add_reminder" and when < now:
                    errs.append(f"add_reminder.when {args[key[1]]} is before the example's now ({now:%Y-%m-%d %H:%M})")
            except ValueError:
                errs.append(f"{name}.{key[1]} must be YYYY-MM-DD HH:MM, got {args[key[1]]!r}")
    if name == "get_weather" and "day" in args and not WEATHER_DAY.match(str(args["day"])):
        errs.append(f"get_weather.day: {args['day']!r} isn't now/today/tomorrow/week/a weekday/YYYY-MM-DD")
    if name == "set_volume" and "level" in args and not 0 <= args["level"] <= 100:
        errs.append("set_volume.level must be 0-100")
    if name == "set_timer" and isinstance(args.get("seconds"), int) and args["seconds"] <= 0:
        errs.append("set_timer.seconds must be positive")
    return errs


def check_example(ex):
    errs, msgs = [], ex.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 3:
        return ["needs a system, user and assistant message"]
    if msgs[0].get("role") != "system":
        errs.append("first message must be the system prompt")
    if msgs[-1].get("role") != "assistant" or not (msgs[-1].get("content") or "").strip():
        errs.append("must end with Gink's written answer")
    now, pending = example_now(msgs[0].get("content", "")), {}
    for m in msgs:
        role = m.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            errs.append(f"unknown role {role!r}")
        for call in m.get("tool_calls") or []:
            fn = call.get("function") or {}
            name = fn.get("name")
            if name not in TOOLS:
                errs.append(f"Gink has no tool called {name!r}"); continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                errs.append(f"{name}: arguments aren't valid JSON"); continue
            errs += check_args(name, args, now)
            pending[call.get("id")] = name
        if role == "tool":
            if m.get("tool_call_id") not in pending:
                errs.append("a tool result answers no tool call")
            pending.pop(m.get("tool_call_id"), None)
    if pending:
        errs.append(f"tool call(s) without a result: {sorted(pending.values())}")
    text = " ".join(str(m.get("content") or "") for m in msgs[1:])
    for e in EMAIL.findall(text):
        if not e.endswith(("example.com", "example.org")):
            errs.append(f"looks like a real email address: {e}")
    no_dates = DATES.sub(" ", text)                       # "2026-04-14 19:30" isn't a phone number
    if PHONE.search(no_dates) or CARD.search(no_dates.replace(",", "")):
        errs.append("looks like a phone or card number")
    return errs


def main(paths):
    total, bad, seen, dupes = 0, 0, set(), 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                total += 1
                try:
                    ex = json.loads(line)
                except ValueError:
                    bad += 1; print(f"{os.path.basename(path)}:{n}: not valid JSON"); continue
                key = json.dumps(ex.get("messages"), sort_keys=True)
                if key in seen:
                    dupes += 1
                seen.add(key)
                errs = check_example(ex)
                if errs:
                    bad += 1
                    if bad <= 25:
                        print(f"{os.path.basename(path)}:{n}: " + "; ".join(errs))
    print(f"checked {total} examples: {total - bad} OK, {bad} with problems, {dupes} exact duplicates")
    return 1 if bad else 0


if __name__ == "__main__":
    out = os.path.join(HERE, "out")
    sys.exit(main(sys.argv[1:] or [os.path.join(out, "train.jsonl"), os.path.join(out, "eval.jsonl")]))
