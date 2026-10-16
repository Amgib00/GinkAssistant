"""Offline understanding for the most common commands — works with no API key
and no internet, and answers instantly. Returns (tool_name, args) or None."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

_TIME = r"(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?"
_UNIT = {"s": 1, "sec": 1, "second": 1, "m": 60, "min": 60, "minute": 60,
         "h": 3600, "hr": 3600, "hour": 3600}


def _hm(h, m, ap):
    h, m = int(h), int(m or 0)
    ap = (ap or "").replace(".", "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return (h, m) if 0 <= h < 24 and 0 <= m < 60 else None


def _day_offset(text):
    return 1 if re.search(r"\btomorrow\b", text) else 0


def _duration(text) -> Optional[int]:
    total = 0
    for n, u in re.findall(r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", text):
        u = u.rstrip("s") if u not in ("s",) else u
        total += int(n) * _UNIT.get(u, _UNIT.get(u[:3], 60))
    return total or None


def parse(text: str, now: Optional[datetime] = None) -> Optional[Tuple[str, dict]]:
    now = now or datetime.now()
    t = " ".join((text or "").lower().split())

    # --- live information (instant answers; anything fuzzier goes to the AI) ---
    live = _parse_live(t, text, now)
    if live:
        return live

    # --- memory: "remember that ...", "forget ...", "what do you remember"
    if re.search(r"\bwhat do you (?:remember|know) about me\b|\bwhat have you remembered\b|^(?:show|list) (?:my )?memor(?:y|ies)$", t):
        return "list_memories", {}
    m = re.match(r"(?:please )?remember (?:that |this: ?)(.+)", t) or re.match(r"(?:please )?remember (my .+)", t)
    if m and not re.match(r"(?:please )?remember to\b", t):
        fact = (text or "").strip()
        fact = re.sub(r"(?i)^(?:please )?remember (?:that |this: ?)?", "", fact).strip()
        return "remember", {"fact": fact}
    m = re.match(r"forget (?:about |that |what i said about )?(.+)", t)
    if m:
        return "forget", {"what": m.group(1)}

    # --- timers: "set a timer for 10 minutes", "5 min timer"
    if re.search(r"\btimer\b|\bcount ?down\b", t):
        secs = _duration(t)
        if secs:
            return "set_timer", {"seconds": secs, "label": "Timer"}

    # --- alarms: "wake me up at 6:30", "set an alarm for 7am tomorrow"
    if re.search(r"\b(wake me|alarm)\b", t):
        m = re.search(r"\b(?:at|for)\s+" + _TIME, t) or re.search(_TIME + r"\s*(?=$|\b)", t)
        if m:
            hm = _hm(*m.groups())
            if hm:
                args = {"time": f"{hm[0]:02d}:{hm[1]:02d}", "label": "Wake up"}
                if _day_offset(t):
                    d = (now + timedelta(days=1)).date()
                    args["date"] = d.isoformat()
                return "set_alarm", args
        secs = re.search(r"\bin\s+", t) and _duration(t)
        if secs:
            due = now + timedelta(seconds=secs)
            return "set_alarm", {"time": f"{due:%H:%M}", "label": "Wake up",
                                 "date": due.date().isoformat()}

    # --- reminders: "remind me to call mom at 5pm", "remind me in 20 minutes to stretch"
    m = re.match(r"remind me (?:to |about )?(.+)", t)
    if m:
        rest = m.group(1)
        rel = re.search(r"\bin\s+(\d+\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)(?:\s*(?:and\s*)?\d+\s*(?:minutes?|mins?))?)", rest)
        at = re.search(r"\bat\s+" + _TIME, rest)
        due = None
        if rel:
            due = now + timedelta(seconds=_duration(rel.group(1)) or 0)
            what = (rest[:rel.start()] + rest[rel.end():])
        elif at:
            hm = _hm(*at.groups())
            if hm:
                due = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
                due += timedelta(days=_day_offset(rest))
                if due <= now:
                    due += timedelta(days=1)
            what = rest[:at.start()] + rest[at.end():]
        if due:
            what = re.sub(r"\b(tomorrow|today|to)\b\s*$", "", what.strip()).strip(" ,.") or "Reminder"
            what = re.sub(r"^to\s+", "", what)
            return "add_reminder", {"text": what[:1].upper() + what[1:], "when": f"{due:%Y-%m-%d %H:%M}"}

    # --- "open whatsapp" / "launch spotify"
    m = re.match(r"(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app)?$", t)
    if m and not re.search(r"https?://|\.\w{2,}/", m.group(1)):
        return "open_app", {"name": m.group(1).strip()}

    # --- "call +221..." 
    m = re.match(r"(?:call|dial|phone)\s+(\+?[\d\s\-]{6,})$", t)
    if m:
        return "make_call", {"number": m.group(1)}

    # --- "show my tasks / alarms"
    m = re.search(r"\b(?:show|list|what are)\b.*\b(tasks?|reminders?|alarms?|timers?|to-?dos?)\b", t)
    if m:
        kind = m.group(1).rstrip("s").replace("to-do", "task").replace("todo", "task")
        return "list_items", {"kind": kind if kind in ("task", "reminder", "alarm", "timer") else "all"}

    # --- "add buy milk to my list"
    m = re.match(r"(?:add|put)\s+(.+?)\s+(?:to|on)\s+my\s+(?:to-?do\s+)?(?:list|tasks?)$", t)
    if m:
        return "add_task", {"title": m.group(1)[:1].upper() + m.group(1)[1:]}

    return None


# ---------------------------------------------------------------- live info
_PLACE_RE = r"(?:in|at|for) ([a-z\u00c0-\u024f][a-z\u00c0-\u024f' .-]{1,40}?)"
_WHEN_RE = r"(today|tomorrow|this week|next 7 days|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))"
_MONTHS = "january february march april may june july august september october november december".split()
_CRYPTO = r"(bitcoin|btc|ethereum|eth|solana|sol|bnb|xrp|ripple|cardano|ada|dogecoin|doge|usdt|tether|ton|tron|trx|litecoin|ltc)"
_MONEY_WORD = r"([a-z$\u20ac\u00a3]{1,8}|cfa|fcfa)"


def _clean_place(p):
    p = re.sub(r"\b(today|tomorrow|now|right now|this week|please|currently)\b", "", p or "").strip(" ?.!,")
    return p or None


def _when(t):
    m = re.search(_WHEN_RE, t)
    if not m:
        return None
    w = m.group(1)
    return "week" if w in ("this week", "next 7 days") else w.replace("on ", "")


def _parse_date_words(s, now):
    s = s.strip(" ?.!")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return s
    m = re.match(r"(?:the )?(\d{1,2})(?:st|nd|rd|th)?(?: of)? ([a-z]+)(?: (\d{4}))?$", s) or \
        re.match(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)?(?:,? (\d{4}))?$", s)
    if not m:
        return None
    a, b, y = m.groups()
    day, month = (a, b) if a.isdigit() else (b, a)
    months = [mo for mo in _MONTHS if mo.startswith(month[:3])]
    if not months:
        return None
    mi = _MONTHS.index(months[0]) + 1
    year = int(y) if y else now.year
    try:
        d = datetime(year, mi, int(day))
    except ValueError:
        return None
    if not y and d.date() < now.date():
        d = d.replace(year=year + 1)
    return d.strftime("%Y-%m-%d")


def _parse_computer(t):
    """Short, unambiguous computer commands -> instant (works without the AI)."""
    m = re.fullmatch(r"(?:set |turn )?(?:the )?volume (?:to |at )?(\d{1,3})(?: ?%| percent)?", t)
    if m:
        return "set_volume", {"level": int(m.group(1))}
    if re.fullmatch(r"(?:turn (?:the )?(?:volume|sound|it) up|volume up|louder|make it louder|increase (?:the )?volume)", t):
        return "set_volume", {"action": "up"}
    if re.fullmatch(r"(?:turn (?:the )?(?:volume|sound|it) down|volume down|quieter|make it quieter|lower (?:the )?volume|decrease (?:the )?volume)", t):
        return "set_volume", {"action": "down"}
    if re.fullmatch(r"(?:mute|mute (?:the )?(?:sound|volume|computer))", t):
        return "set_volume", {"action": "mute"}
    if re.fullmatch(r"unmute(?: (?:the )?(?:sound|volume|computer))?", t):
        return "set_volume", {"action": "unmute"}
    m = re.fullmatch(r"(next|skip)(?: (?:the )?(?:song|track))?|(previous|last) (?:song|track)|(pause|stop|resume|play)(?: (?:the|my|some))? music", t)
    if m:
        act = "next" if m.group(1) else "previous" if m.group(2) else {"stop": "pause", "resume": "play"}.get(m.group(3), m.group(3))
        return "media_control", {"action": act}
    if re.fullmatch(r"(?:take|grab|capture) (?:a )?(?:screenshot|screen shot|picture of (?:my|the) screen)|screenshot", t):
        return "take_screenshot", {}
    if re.fullmatch(r"lock (?:my |the )?(?:screen|computer|mac|laptop)", t):
        return "lock_screen", {}
    m = re.fullmatch(r"(?:turn |switch )?(?:on |off )?(dark|light) mode(?: on| off)?", t)
    if m:
        on_off = "off" if t.endswith(" off") or " off " in t else "on"
        mode = ("on" if on_off == "on" else "off") if m.group(1) == "dark" else ("off" if on_off == "on" else "on")
        return "set_dark_mode", {"mode": mode}
    if re.fullmatch(r"(?:how(?:'s| is) my |what(?:'s| is) my |check my )?(?:battery|battery level|disk space|storage)(?: left| level)?|system status", t):
        return "system_status", {}
    m = re.fullmatch(r"open (?:number |file )?(\d{1,2})", t)
    if m:
        return "open_file", {"which": m.group(1)}
    m = re.fullmatch(r"(?:open|show(?: me)?) (?:my |the )?(desktop|documents|downloads|pictures|music|movies|videos|home|applications|icloud drive|icloud|trash)(?: folder)?", t)
    if m:
        return "open_folder", {"name": m.group(1)}
    m = re.fullmatch(r"open (?:my |the )?(.{2,60}?) folder", t)
    if m:
        return "open_folder", {"name": m.group(1)}
    m = re.fullmatch(r"open (?:a )?(?:new )?terminal(?: window)?(?: (?:in|at) (?:my |the )?(.{2,60}?)(?: folder)?)?", t)
    if m:
        return "open_terminal", {"folder": m.group(1) or ""}
    m = re.fullmatch(r"open (?:the )?(wi-?fi|bluetooth|sound|display|displays|notification|notifications|battery|privacy|security|keyboard|trackpad|mouse|appearance|dock|software update|network|accessibility|language|date and time) (?:settings|preferences)", t)
    if m:
        return "open_settings_pane", {"pane": m.group(1)}
    if re.fullmatch(r"(?:put (?:the |my )?(?:computer|mac|laptop) to sleep|sleep (?:the |my )?(?:computer|mac|laptop)|go to sleep)", t):
        return "sleep_computer", {}
    if re.fullmatch(r"(?:show|list|what are) (?:me )?(?:my )?recent (?:files|documents|work)|what was i working on", t):
        return "show_recent_files", {}
    if re.fullmatch(r"(?:what(?:'s| is) on |read )(?:my |the )?clipboard", t):
        return "read_clipboard", {}
    if re.fullmatch(r"(?:show it|reveal it) in finder", t):
        return "reveal_in_finder", {}
    m = re.fullmatch(r"(?:search google for|google search for|google) (.{2,200})", t)
    if m:
        return "search_in_browser", {"query": m.group(1)}
    m = re.fullmatch(r"(?:quit|close) ([a-z][\w .+-]{1,40}?)(?: app)?", t)
    if m and m.group(1) not in ("it", "this", "that", "the app", "everything", "all"):
        return "quit_app", {"name": m.group(1).title()}
    m = re.fullmatch(r"(?:find|search for|look for) (?:my |the )?(.{2,60}?)(?: files?| documents?| on my (?:mac|computer))?", t)
    if m and not re.search(r"\b(?:video|restaurant|near|recipe|phone|song)\b", t):
        return "find_files", {"query": m.group(1)}
    m = re.fullmatch(r"(?:make|take|add|write) (?:a )?note(?: that| saying|:|,)? (.{2,500})", t)
    if m:
        return "create_note", {"title": m.group(1).strip().rstrip(".")[:80], "body": m.group(1).strip()}
    return None


def _parse_live(t, raw, now):
    t = t.rstrip(" ?!.")
    pc = _parse_computer(t)
    if pc:
        return pc
    # explicit video requests (a plain "how do I ..." goes to the AI, which writes steps AND finds videos)
    m = re.fullmatch(r"(?:show me |find me |play |search youtube for |youtube )(?:a |some |the )?(?:youtube )?"
                     r"(?:videos?|tutorials?|clips?)? ?(?:on|about|of|for|showing)? ?(.{3,80})", t)
    if m and re.match(r"(?:show me|find me|play|search youtube|youtube)", t) and \
            re.search(r"\b(video|videos|youtube|tutorial|clip)\b", t):
        q = re.sub(r"\b(on youtube|youtube|videos?|tutorials?|clips?)\b", "", m.group(1)).strip(" .,")
        if q:
            return "find_video", {"query": q, "live": bool(re.search(r"\blive\b", t))}
    m = re.fullmatch(r"(.{3,80}?) (?:video|videos|tutorial|on youtube)", t)
    if m and (t.startswith(("how to ", "how do ", "how can ")) or
              not re.search(r"\b(?:make|edit|download|upload|record|film|shoot)\s+(?:a |an |my |the |this |our )?(?:\w+ )?video", t)):
        return "find_video", {"query": m.group(1), "live": False}
    # time
    if re.fullmatch(r"(?:what(?:'s| is) the )?time(?: is it)?(?: now| right now)?|what time is it(?: now| right now)?|"
                    r"(?:tell me )?the time(?: please)?|current time", t):
        return "get_time", {}
    m = re.fullmatch(r"(?:what(?:'s| is) the |the |current )?time (?:in|at) (.+)|what time is it (?:in|at) (.+)", t)
    if m:
        return "get_time", {"place": _clean_place(m.group(1) or m.group(2))}
    # date
    if re.fullmatch(r"(?:what(?:'s| is) )?(?:today'?s date|the date(?: today)?|today'?s day)|what day is (?:it|today)(?: today)?|"
                    r"what(?:'s| is) (?:the )?date(?: today)?|date today|what(?:'s| is) today", t):
        return "get_date", {"offset_days": 0}
    if re.fullmatch(r"what(?:'s| is) (?:the date |the day )?tomorrow|what day is tomorrow|tomorrow'?s date", t):
        return "get_date", {"offset_days": 1}
    m = re.fullmatch(r"how (?:many|long) (?:days )?(?:is it )?(?:until|till|til|to|before) (.+)", t)
    if m:
        d = _parse_date_words(m.group(1), now)
        if d:
            return "days_until", {"date": d}
    # weather
    m = re.fullmatch(r"(?:what(?:'s| is) the |how(?:'s| is) the |show me the |get the )?(?:weather|forecast|temperature)"
                     r"(?: like)?(?: " + _PLACE_RE + r")?(?: " + _WHEN_RE + r")?(?: " + _PLACE_RE + r")?", t) or \
        re.fullmatch(r"(?:what(?:'s| is) the )?(?:weather|forecast|temperature) " + _WHEN_RE + r"(?: " + _PLACE_RE + r")?", t) or \
        re.fullmatch(r"(?:is it|will it) (?:going to )?(?:rain|be hot|be cold|be sunny)(?: " + _WHEN_RE + r")?(?: " + _PLACE_RE + r")?", t) or \
        re.fullmatch(r"(?:how hot|how cold) is it(?: " + _PLACE_RE + r")?(?: today)?", t)
    if m:
        place = None
        for g in m.groups():
            if g and not re.fullmatch(_WHEN_RE, g) and g not in ("today", "tomorrow"):
                place = _clean_place(g)
        return "get_weather", {"place": place, "day": _when(t) or ("today" if "rain" in t else "now")}
    # air quality
    m = re.fullmatch(r"(?:what(?:'s| is) the |how(?:'s| is) the )?(?:air quality|aqi|air pollution|pollution|dust(?: level)?)"
                     r"(?: like)?(?: " + _PLACE_RE + r")?(?: today| now)?", t)
    if m:
        return "get_air_quality", {"place": _clean_place(m.group(1))}
    # sunrise / sunset
    m = re.fullmatch(r"(?:when is |what time is )?(?:the )?(?:sunrise|sunset|sunrise and sunset)(?: " + _WHEN_RE + r")?(?: " + _PLACE_RE + r")?(?: " + _WHEN_RE + r")?", t)
    if m:
        place = next((_clean_place(g) for g in m.groups() if g and g not in ("today", "tomorrow")
                      and not g.startswith(("on ", "this"))), None)
        return "get_sun_times", {"place": place, "day": "tomorrow" if "tomorrow" in t else "today"}
    # prayer times
    m = re.fullmatch(r"(?:what are the |what(?:'s| is) the |show me )?(?:prayer times?|salat times?|namaz times?|"
                     r"(?:fajr|dhuhr|asr|maghrib|isha) time)(?: " + _WHEN_RE + r")?(?: " + _PLACE_RE + r")?(?: " + _WHEN_RE + r")?", t)
    if m:
        place = next((_clean_place(g) for g in m.groups() if g and g not in ("today", "tomorrow")
                      and not g.startswith(("on ", "this"))), None)
        return "get_prayer_times", {"place": place, "day": "tomorrow" if "tomorrow" in t else "today"}
    # currency
    m = re.fullmatch(r"(?:convert |how much is |what(?:'s| is) )?([\d][\d,]*(?:\.\d+)?)\s*" + _MONEY_WORD +
                     r"(?: franc)?s? (?:to|in|into|en) " + _MONEY_WORD + r"(?: franc)?s?", t)
    if m:
        amt, a, b = m.groups()
        return "convert_currency", {"amount": float(amt.replace(",", "")), "from_currency": a, "to_currency": b}
    m = re.fullmatch(r"(?:what(?:'s| is) the )?(?:exchange rate|rate)(?: of| for| from)? " + _MONEY_WORD +
                     r" (?:to|in|and|vs) " + _MONEY_WORD, t)
    if m:
        return "convert_currency", {"amount": 1, "from_currency": m.group(1), "to_currency": m.group(2)}
    # crypto
    m = re.fullmatch(r"(?:what(?:'s| is) the |how much is |current )?(?:price of )?" + _CRYPTO +
                     r"(?: price| worth)?(?: in ([a-z]{3}|cfa|euros?|dollars?))?(?: now| today)?", t)
    if m and ("price" in t or "how much" in t or "worth" in t or t.startswith(m.group(1))):
        return "get_crypto_price", {"coin": m.group(1), "currency": m.group(2) or "usd"}
    # calculator
    m = re.fullmatch(r"(?:what(?:'s| is)|calculate|compute|how much is)\s+([\d\s().+\-*/x\u00d7\u00f7^%,]+?(?: of [\d.,\s]+)?)", t)
    if m and re.search(r"\d\s*(?:[+\-*/x\u00d7\u00f7^]|%\s*of|of|%)\s*[\d(]", m.group(1)):
        expr = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", m.group(1))
        return "calculate", {"expression": expr.strip()}
    return None
