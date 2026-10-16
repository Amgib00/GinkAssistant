"""
Morning briefing: weather, what's on today, open tasks, a headline.

Runs automatically once a day at the time set in Settings -> Morning
briefing (if Gink is open then -- or the first time you open Gink that
morning, until noon), from the + menu, or when you say "brief me" /
"good morning".

Weather is from Open-Meteo (free, no key). The city comes from Settings;
without one, the weather line is skipped and the briefing says how to add it.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx

WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    80: "rain showers", 81: "heavy showers", 82: "violent showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "severe thunderstorms",
}


async def fetch_weather(city: str) -> Optional[dict]:
    if not city.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            parts = [x.strip() for x in city.split(",") if x.strip()]
            country = parts[-1].lower() if len(parts) > 1 else ""
            geo = (await client.get("https://geocoding-api.open-meteo.com/v1/search",
                                    params={"name": parts[0], "count": 10})).json()
            if not geo.get("results"):
                return {"error": f"I couldn't find \u201c{city}\u201d for the weather."}
            place = geo["results"][0]
            if country:
                place = next((r for r in geo["results"] if country in (r.get("country", "").lower(),
                                                                      (r.get("country_code") or "").lower())), place)
            fc = (await client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "forecast_days": 1})).json()
        daily = fc["daily"]
        return {
            "place": place.get("name", city),
            "now": round(fc["current"]["temperature_2m"]),
            "high": round(daily["temperature_2m_max"][0]), "low": round(daily["temperature_2m_min"][0]),
            "rain": daily.get("precipitation_probability_max", [None])[0],
            "sky": WEATHER_CODES.get(daily["weather_code"][0], "mixed weather"),
        }
    except Exception:
        return {"error": "Weather isn't available right now."}


def _today_items(store, now: datetime) -> Tuple[List, List, List, List]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    top = store.list(include_done=False, top_level_only=True)
    alarms = [i for i in top if i.kind == "alarm" and i.due and start <= i.due < end]
    agenda = [i for i in top if i.kind in ("reminder", "event") and i.due and start <= i.due < end]
    overdue = [i for i in top if i.kind in ("task", "reminder") and i.due and i.due < start]
    tasks = [i for i in top if i.kind == "task" and (not i.due or i.due >= start)]
    return alarms, agenda, overdue, tasks


def in_progress_tasks(store):
    """Top-level tasks with some (not all) steps done, closest to finished first.
    -> [(task, done, total, next_step_title)]"""
    out = []
    for t in store.list(include_done=False, top_level_only=True):
        if t.kind != "task":
            continue
        steps = store.children(t.id)
        done = sum(1 for x in steps if x.done)
        if steps and 0 < done < len(steps):
            nxt = next((x.title for x in steps if not x.done), "")
            out.append((t, done, len(steps), nxt))
    out.sort(key=lambda r: r[1] / r[2], reverse=True)
    return out


def pick_up_section(store, chats=None, files=None):
    """'Pick up where you left off': tasks in progress, recent chats, files being edited.
    -> (markdown lines, spoken sentences, facts for the AI opening line)"""
    import os
    from urllib.parse import quote
    md, say, facts = [], [], []
    progress = in_progress_tasks(store)
    if progress or chats or files:
        md += ["", "**Pick up where you left off**"]
    for i, (t, done, total, nxt) in enumerate(progress[:3]):
        tip = " \u2014 you're nearly there, finish this one first" if i == 0 and done / total >= 0.5 else ""
        md.append(f"- \U0001F3AF **{t.title}** \u2014 {done}/{total} steps done" + (f". Next: *{nxt}*" if nxt else "") + tip)
        facts.append(f"Task '{t.title}': {done} of {total} steps done; next step '{nxt}'.")
    if progress:
        t, done, total, nxt = progress[0]
        say.append(f"You're {done} of {total} steps into {t.title}" + (f". Next up: {nxt}." if nxt else "."))
    for c in (chats or [])[:3]:
        md.append(f"- \U0001F4AC {c['title']} ({c['when']}) \u2014 [Continue](gink://chat/{c['id']})")
        facts.append(f"Recent conversation: '{c['title']}' ({c['when']}).")
    if chats and not progress:
        say.append(f"{chats[0]['when'].capitalize()} you were working on {chats[0]['title']}.")
    for path in (files or [])[:3]:
        name = os.path.basename(path)
        md.append(f"- \U0001F4C4 {name} \u2014 [Open](gink://open/{quote(path, safe='')})")   # fully encoded path
        # (file names are deliberately NOT added to `facts`: those go to the AI for the
        #  opening line, and Settings promises file names stay on this computer)
    return md, say, facts


def fallback_opening(store, chats=None) -> str:
    progress = in_progress_tasks(store)
    if progress:
        t, done, total, nxt = progress[0]
        return (f"You're {done} of {total} steps into **{t.title}**"
                + (f" \u2014 *{nxt}* would be a great next step today." if nxt else " \u2014 keep it going today."))
    if chats:
        return f"{chats[0]['when'].capitalize()} you were working on **{chats[0]['title']}** \u2014 want to pick it up?"
    return ""


async def build_briefing(store, prefs: dict, user_name: str = "", news_fn=None,
                         now: Optional[datetime] = None, chats=None, files=None, writer=None) -> Tuple[str, str]:
    """Returns (markdown for the chat, plain text to read aloud).
    chats / files / writer are optional: recent conversations, recently edited files,
    and an async writer(facts) -> one or two encouraging sentences (the AI)."""
    now = now or datetime.now()
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
    hello = f"Good {part}{', ' + user_name if user_name else ''}!"
    weather_task = asyncio.create_task(fetch_weather(prefs.get("city") or prefs.get("briefing_city", "")))
    news_task = asyncio.create_task(news_fn()) if news_fn else None

    alarms, agenda, overdue, tasks = _today_items(store, now)
    md = [f"### \u2600\ufe0f {hello} Here's your {now:%A, %d %B}.", ""]
    say = [f"{hello} It's {now:%A the} {now.day}."]

    w = await weather_task
    if w and not w.get("error"):
        rain = f", {w['rain']}% chance of rain" if w.get("rain") is not None else ""
        md.append(f"**Weather in {w['place']}:** {w['sky']}, {w['now']}\u00b0 now "
                  f"(high {w['high']}\u00b0, low {w['low']}\u00b0{rain}).")
        say.append(f"In {w['place']} it's {w['now']} degrees with {w['sky']}, up to {w['high']} today{rain}.")
    elif w and w.get("error"):
        md.append(f"*{w['error']}*")
    else:
        md.append("*Add your city in Settings \u2192 Location to get the weather here.*")

    md.append("")
    if alarms or agenda:
        md.append("**Today**")
        for i in sorted(alarms + agenda, key=lambda x: x.due):
            icon = {"alarm": "\u23f0", "event": "\U0001F4C5"}.get(i.kind, "\U0001F514")
            md.append(f"- {icon} {i.due:%H:%M} \u2014 {i.title}")
        say.append("Today you have " + "; ".join(f"{i.title} at {i.due:%H:%M}" for i in
                                                  sorted(alarms + agenda, key=lambda x: x.due)[:4]) + ".")
    else:
        md.append("**Today:** nothing scheduled \u2014 a clear day.")
        say.append("Nothing is scheduled today.")

    if overdue:
        md.append("")
        md.append(f"**Overdue ({len(overdue)})**")
        md += [f"- {i.title} (was due {i.due:%a %d %b})" for i in overdue[:5]]
        say.append(f"{len(overdue)} item{'s are' if len(overdue) > 1 else ' is'} overdue, "
                   f"including {overdue[0].title}.")
    if tasks:
        md.append("")
        md.append(f"**Open tasks ({len(tasks)})**")
        for t in tasks[:5]:
            steps = store.children(t.id)
            prog = f" \u2014 {sum(s.done for s in steps)}/{len(steps)} steps" if steps else ""
            md.append(f"- {t.title}{prog}")
        say.append(f"You have {len(tasks)} open task{'s' if len(tasks) != 1 else ''}"
                   + (f", starting with {tasks[0].title}." if tasks else "."))

    pick_md, pick_say, facts = pick_up_section(store, chats, files)
    md += pick_md
    say += pick_say
    opening = ""
    if facts:
        if writer is not None:
            try:
                opening = (await asyncio.wait_for(writer("\n".join(facts)), timeout=12) or "").strip()
            except Exception:
                opening = ""
        opening = opening or fallback_opening(store, chats)
    if opening:
        md.insert(1, opening)
        md.insert(2, "")

    if news_task:
        try:
            _summary, headlines = await asyncio.wait_for(news_task, timeout=8)
            if headlines:
                h = headlines[0]
                title = h.get("title", "")
                link = h.get("link") or h.get("url") or ""
                md.append("")
                md.append("**Top story:** " + (f"[{title}]({link})" if link else title))
                say.append(f"Top story: {title}.")
        except Exception:
            pass

    md.append("")
    md.append("Have a great day! Ask me to plan anything on that list.")
    return "\n".join(_list_spacing(md)), " ".join(say)


def _list_spacing(lines):
    """Markdown only starts a bullet list after a blank line -- without one, "**Today**"
    followed by "- 16:00 ..." showed as plain text with dashes."""
    out = []
    for line in lines:
        if line.startswith("- ") and out and out[-1].strip() and not out[-1].startswith("- "):
            out.append("")
        out.append(line)
    return out


def is_due(prefs: dict, now: Optional[datetime] = None) -> bool:
    """Time for today's automatic briefing? (once a day, from the set time until noon)"""
    now = now or datetime.now()
    if not prefs.get("briefing_enabled", True):
        return False
    if prefs.get("briefing_last_date") == now.strftime("%Y-%m-%d"):
        return False
    try:
        h, m = (int(x) for x in prefs.get("briefing_time", "07:30").split(":"))
    except Exception:
        h, m = 7, 30
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return start <= now < max(start + timedelta(hours=1), now.replace(hour=12, minute=0, second=0))
