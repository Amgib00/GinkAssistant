"""
Builds the Gink training dataset (chat "messages" JSONL, the format Unsloth, TRL and
Axolotl read):  tools/gink_dataset/out/train.jsonl, eval.jsonl, tools.json

    python tools/gink_dataset/generate.py          # then: python tools/gink_dataset/validate.py

What it teaches, and why every example is correct by construction:
  * ACTIONS -- everyday requests -> Gink's REAL tools (services/actions/agent.py). Each
    example states the current date/time (random), and the right arguments are COMPUTED
    from it ("tomorrow at 7" on Sat 17 Oct -> "2026-10-18 07:00"). English and French.
  * IDENTITY + TONE and VOICE STYLE -- hand-written (examples_identity.jsonl, examples_voice.jsonl).
  * LANGUAGES -- reviewed examples from native speakers (languages/*.csv -> only rows marked
    approved=yes are used). Nothing in Wolof, Krio or Pidgin is machine-invented.
Sources are Gink's own templates: no outputs from Claude or other models whose terms forbid
training other models on them.
"""
import datetime as dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(ROOT, "src"))
from ginkassistant.services.actions.agent import TOOL_SPECS      # noqa: E402

SEED = 2026
PER_TOOL = int(os.environ.get("GINK_DATA_PER_TOOL", "60"))
TIMEZONES = ["Africa/Dakar", "Africa/Lagos", "Africa/Freetown", "Africa/Accra", "Africa/Abidjan", "Africa/Nairobi", "Europe/Paris"]
CITIES = ["Dakar", "Lagos", "Freetown", "Accra", "Abidjan", "Nairobi", "Bamako", "Conakry", "Kumasi", "Thiès", "Paris", "London"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
TASKS = [("call mum", "appeler maman"), ("pay the electricity bill", "payer la facture d'électricité"),
         ("buy bread", "acheter du pain"), ("send the report to Awa", "envoyer le rapport à Awa"),
         ("take my medicine", "prendre mes médicaments"), ("pick up the kids", "récupérer les enfants"),
         ("water the plants", "arroser les plantes"), ("revise for the exam", "réviser pour l'examen"),
         ("book the car service", "réserver la révision de la voiture"), ("call the landlord", "appeler le propriétaire")]
CURRENCIES = [("CFA francs", "francs CFA", "XOF"), ("naira", "nairas", "NGN"), ("cedis", "cedis", "GHS"),
              ("dollars", "dollars", "USD"), ("euros", "euros", "EUR"), ("leones", "leones", "SLE"),
              ("Kenyan shillings", "shillings kényans", "KES"), ("pounds", "livres sterling", "GBP")]
RATES_PER_USD = {"XOF": 605.0, "NGN": 1530.0, "GHS": 15.4, "USD": 1.0, "EUR": 0.92, "SLE": 22.6, "KES": 129.0, "GBP": 0.78}
SYSTEM_EN = "You are Gink, a warm, capable AI assistant. Use your tools for actions and live information, then answer briefly."
SYSTEM_FR = "Tu es Gink, un assistant IA chaleureux et compétent. Utilise tes outils pour les actions et les informations en direct, puis réponds brièvement."

rnd = random.Random(SEED)
_ids = [0]


def call_id():
    _ids[0] += 1
    return f"call_{_ids[0]:06d}"


def random_now():
    start = dt.datetime(2026, 1, 1, 6, 0)
    t = start + dt.timedelta(days=rnd.randrange(0, 600), minutes=rnd.randrange(0, 16 * 60))
    return t.replace(minute=(t.minute // 5) * 5)


def now_line(now, tz, fr):
    if fr:
        return (f"Nous sommes le {DAYS_FR[now.weekday()]} {now.day} {MONTHS_FR[now.month - 1]} {now.year}, "
                f"il est {now:%H:%M} ({tz}).")
    return f"It is now {DAYS_EN[now.weekday()]} {now.day} {MONTHS_EN[now.month - 1]} {now.year}, {now:%H:%M} ({tz})."


def t12(h, m):
    suffix = "am" if h < 12 else "pm"
    hh = h % 12 or 12
    return f"{hh}:{m:02d} {suffix}" if m else f"{hh} {suffix}"


def tfr(h, m):
    return f"{h}h{m:02d}" if m else f"{h}h"


def example(fr, now, tz, user, tool, args, result, final, category):
    sys_prompt = (SYSTEM_FR if fr else SYSTEM_EN) + " " + now_line(now, tz, fr)
    cid = call_id()
    return {"category": category, "language": "fr" if fr else "en", "messages": [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user},
        {"role": "assistant", "content": "", "tool_calls": [{"id": cid, "type": "function",
                                                             "function": {"name": tool, "arguments": json.dumps(args, ensure_ascii=False)}}]},
        {"role": "tool", "tool_call_id": cid, "name": tool, "content": result},
        {"role": "assistant", "content": final}]}


# ------------------------------------------------------------------ action generators
def gen_alarm():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    h, m = rnd.choice([5, 6, 6, 7, 7, 8, 9]), rnd.choice([0, 0, 15, 30, 45])
    label = rnd.choice([None, None, ("gym", "sport"), ("prayer", "prière"), ("work", "travail")])
    if fr:
        user = rnd.choice([f"Réveille-moi à {tfr(h, m)}", f"Mets une alarme à {tfr(h, m)}", f"Alarme à {tfr(h, m)} s'il te plaît"])
        if label:
            user += f" pour le {label[1]}"
        final = f"C'est fait : je te réveille à {tfr(h, m)}."
    else:
        user = rnd.choice([f"Wake me up at {t12(h, m)}", f"Set an alarm for {t12(h, m)}", f"alarm at {h:02d}:{m:02d}",
                           f"Can you wake me at {t12(h, m)}?"])
        if label:
            user += f" for the {label[0]}"
        final = f"Done, I'll wake you at {t12(h, m)}."
    args = {"time": f"{h:02d}:{m:02d}"}
    if label:
        args["label"] = label[1] if fr else label[0]
    return example(fr, now, tz, user, "set_alarm", args, f"Alarm set for {h:02d}:{m:02d}.", final, "action")


def gen_timer():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    minutes = rnd.choice([1, 2, 3, 5, 10, 15, 20, 25, 30, 45, 60, 90])
    what = rnd.choice([None, ("rice", "le riz"), ("tea", "le thé"), ("laundry", "la lessive")])
    if fr:
        user = f"Mets un minuteur de {minutes} minutes" + (f" pour {what[1]}" if what else "")
        final = f"Minuteur de {minutes} minutes lancé."
    else:
        span = f"{minutes // 60} hour" + ("s" if minutes >= 120 else "") + (f" {minutes % 60} minutes" if minutes % 60 else "") if minutes >= 60 else f"{minutes} minutes"
        user = rnd.choice([f"Set a timer for {span}", f"Timer {span}", f"Start a {span} timer"]) + (f" for the {what[0]}" if what else "")
        final = f"Your {span} timer is running."
    args = {"seconds": minutes * 60}
    if what:
        args["label"] = what[1] if fr else what[0]
    return example(fr, now, tz, user, "set_timer", args, f"Timer started: {minutes * 60} seconds.", final, "action")


def gen_reminder():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    task_en, task_fr = rnd.choice(TASKS)
    kind = rnd.choice(["tomorrow", "in_minutes", "weekday", "today_later"])
    h, m = rnd.choice([7, 8, 9, 10, 12, 14, 16, 18, 19, 20]), rnd.choice([0, 0, 30])
    if kind == "tomorrow":
        when = (now + dt.timedelta(days=1)).replace(hour=h, minute=m)
        en, frw = f"tomorrow at {t12(h, m)}", f"demain à {tfr(h, m)}"
    elif kind == "in_minutes":
        mins = rnd.choice([10, 15, 20, 30, 45])
        when = now + dt.timedelta(minutes=mins)
        en, frw = f"in {mins} minutes", f"dans {mins} minutes"
    elif kind == "weekday":
        wd = rnd.randrange(7)
        ahead = (wd - now.weekday()) % 7 or 7                     # "on Monday" = the next Monday, never today
        when = (now + dt.timedelta(days=ahead)).replace(hour=h, minute=m)
        en, frw = f"on {DAYS_EN[wd]} at {t12(h, m)}", f"{DAYS_FR[wd]} à {tfr(h, m)}"
    else:
        h = max(now.hour + 2, 9)
        if h > 22:
            return gen_reminder()
        when = now.replace(hour=h, minute=0)
        en, frw = f"at {t12(h, 0)} today", f"aujourd'hui à {tfr(h, 0)}"
    if fr:
        user, final = f"Rappelle-moi de {task_fr} {frw}", f"D'accord, je te rappellerai de {task_fr} {frw}."
    else:
        user, final = f"Remind me to {task_en} {en}", f"Got it. I'll remind you to {task_en} {en}."
    args = {"text": task_fr if fr else task_en, "when": f"{when:%Y-%m-%d %H:%M}"}
    return example(fr, now, tz, user, "add_reminder", args, f"Reminder saved for {when:%Y-%m-%d %H:%M}.", final, "action")


def gen_currency():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    (a_en, a_fr, a), (b_en, b_fr, b) = rnd.sample(CURRENCIES, 2)
    amount = rnd.choice([10, 20, 50, 100, 250, 1000, 5000, 10000, 25000, 100000])
    value = amount / RATES_PER_USD[a] * RATES_PER_USD[b]
    shown = f"{value:,.2f}"
    if fr:
        user = rnd.choice([f"Combien font {amount} {a_fr} en {b_fr} ?", f"Convertis {amount} {a_fr} en {b_fr}"])
        final = f"{amount} {a_fr} font environ {shown} {b_fr}, au taux actuel."
    else:
        user = rnd.choice([f"How much is {amount} {a_en} in {b_en}?", f"Convert {amount} {a_en} to {b_en}"])
        final = f"{amount} {a_en} is about {shown} {b_en} at today's rate."
    return example(fr, now, tz, user, "convert_currency", {"amount": amount, "from_currency": a, "to_currency": b},
                   f"{amount} {a} = {shown} {b}", final, "action")


def gen_weather():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    city, day = rnd.choice(CITIES), rnd.choice(["now", "today", "tomorrow"])
    temp, sky = rnd.randrange(18, 38), rnd.choice([("sunny", "ensoleillé"), ("cloudy", "nuageux"), ("light rain", "petite pluie")])
    if fr:
        q = {"now": "en ce moment", "today": "aujourd'hui", "tomorrow": "demain"}[day]
        user = f"Quel temps fait-il à {city} {q} ?"
        final = f"À {city} {q} : {sky[1]}, environ {temp} °C."
    else:
        q = {"now": "right now", "today": "today", "tomorrow": "tomorrow"}[day]
        user = rnd.choice([f"What's the weather in {city} {q}?", f"Weather {city} {q}"])
        final = f"{city} {q}: {sky[0]}, around {temp}°C."
    return example(fr, now, tz, user, "get_weather", {"place": city, "day": day},
                   f"{city} {day}: {sky[0]}, {temp}°C", final, "action")


def gen_calculate():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    if rnd.random() < 0.5:
        p, n = rnd.choice([5, 10, 15, 18, 20, 25]), rnd.choice([1200, 5000, 15000, 80000, 250000])
        expr, value = f"{p}% of {n}", n * p / 100
        user = f"Combien font {p} % de {n} ?" if fr else f"What's {p}% of {n}?"
    else:
        a, c = rnd.randrange(12, 999), rnd.randrange(3, 60)
        expr, value = f"{a}*{c}", a * c
        user = f"Calcule {a} fois {c}" if fr else f"What is {a} times {c}?"
    shown = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    final = f"Ça fait {shown}." if fr else f"That's {shown}."
    return example(fr, now, tz, user, "calculate", {"expression": expr}, shown, final, "action")


def gen_media():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    action, en, frw = rnd.choice([("next", "Next song", "Chanson suivante"), ("pause", "Pause the music", "Mets la musique en pause"),
                                  ("play", "Play some music", "Lance la musique"), ("previous", "Go back a song", "Chanson précédente")])
    return example(fr, now, tz, frw if fr else en, "media_control", {"action": action}, f"Music: {action}.",
                   "C'est fait." if fr else "Done.", "action")


def gen_volume():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    if rnd.random() < 0.5:
        level = rnd.choice([10, 20, 30, 40, 50, 60, 70, 80])
        user = f"Mets le volume à {level}" if fr else f"Set the volume to {level}"
        args, final = {"level": level}, (f"Volume à {level}." if fr else f"Volume set to {level}.")
    else:
        action, en, frw = rnd.choice([("up", "Turn it up", "Monte le son"), ("down", "Turn the volume down", "Baisse le son"),
                                      ("mute", "Mute the sound", "Coupe le son")])
        user, args, final = (frw if fr else en), {"action": action}, ("C'est fait." if fr else "Done.")
    return example(fr, now, tz, user, "set_volume", args, "Volume changed.", final, "action")


def gen_open_app():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    app = rnd.choice(["Spotify", "WhatsApp", "Calculator", "Notes", "Safari", "Chrome", "Mail", "Calendar"])
    user = rnd.choice([f"Ouvre {app}", f"Lance {app}"]) if fr else rnd.choice([f"Open {app}", f"Launch {app}", f"Can you open {app}?"])
    return example(fr, now, tz, user, "open_app", {"name": app}, f"Opened {app}.", f"{app} est ouvert." if fr else f"Opened {app}.", "action")


def gen_remember():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    who_en, who_fr = rnd.choice([("sister", "sœur"), ("brother", "frère"), ("mother", "mère"), ("best friend", "meilleur ami")])
    d, mo = rnd.randrange(1, 29), rnd.randrange(12)
    if fr:
        user = f"Retiens que l'anniversaire de ma {who_fr} est le {d} {MONTHS_FR[mo]}" if who_fr in ("sœur", "mère") else \
               f"Retiens que l'anniversaire de mon {who_fr} est le {d} {MONTHS_FR[mo]}"
        fact, final = f"L'anniversaire de la {who_fr} de l'utilisateur est le {d} {MONTHS_FR[mo]}." if who_fr in ("sœur", "mère") else \
                      f"L'anniversaire du {who_fr} de l'utilisateur est le {d} {MONTHS_FR[mo]}.", "C'est noté, je m'en souviendrai."
    else:
        user = f"Remember that my {who_en}'s birthday is on {MONTHS_EN[mo]} {d}"
        fact, final = f"The user's {who_en}'s birthday is on {MONTHS_EN[mo]} {d}.", "Got it, I'll remember that."
    return example(fr, now, tz, user, "remember", {"fact": fact}, "Saved.", final, "action")


def gen_create_file():
    now, tz, fr = random_now(), rnd.choice(TIMEZONES), rnd.random() < 0.35
    fmt = rnd.choice(["pdf", "docx", "md"])
    items_en = rnd.sample(["rice", "onions", "palm oil", "fish", "tomatoes", "bread", "milk", "eggs", "sugar"], 4)
    items_fr = {"rice": "riz", "onions": "oignons", "palm oil": "huile de palme", "fish": "poisson", "tomatoes": "tomates",
                "bread": "pain", "milk": "lait", "eggs": "œufs", "sugar": "sucre"}
    name = {"pdf": "PDF", "docx": "Word", "md": "Markdown"}[fmt]
    if fr:
        items = [items_fr[i] for i in items_en]
        user = f"Fais-moi un {name} de ma liste de courses : {', '.join(items)}"
        title, final = "Liste de courses", f"Voici ta liste de courses en {name}."
    else:
        items = items_en
        user = f"Make a {name} of my shopping list: {', '.join(items)}"
        title, final = "Shopping list", f"Here's your shopping list as a {name} file."
    content = f"# {title}\n\n" + "\n".join(f"- {i}" for i in items)
    return example(fr, now, tz, user, "create_file", {"format": fmt, "title": title, "content": content},
                   f"Created {title}.{fmt}", final, "action")


GENERATORS = [gen_alarm, gen_timer, gen_reminder, gen_currency, gen_weather, gen_calculate,
              gen_media, gen_volume, gen_open_app, gen_remember, gen_create_file]


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_language_rows():
    """languages/*.csv from native speakers: only rows with approved = yes."""
    import csv
    out = []
    folder = os.path.join(HERE, "languages")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".csv"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("approved") or "").strip().lower() != "yes":
                    continue
                if not (row.get("user_message") and row.get("gink_reply")):
                    continue
                out.append({"category": "language", "language": row.get("language", name[:-4]), "messages": [
                    {"role": "system", "content": SYSTEM_EN},
                    {"role": "user", "content": row["user_message"].strip()},
                    {"role": "assistant", "content": row["gink_reply"].strip()}]})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    data = [g() for g in GENERATORS for _ in range(PER_TOOL)]
    data += load_jsonl(os.path.join(HERE, "examples_identity.jsonl"))
    data += load_jsonl(os.path.join(HERE, "examples_voice.jsonl"))
    data += load_language_rows()
    rnd.shuffle(data)
    n_eval = max(20, len(data) // 20)                              # 5% held out to measure progress
    splits = {"eval.jsonl": data[:n_eval], "train.jsonl": data[n_eval:]}
    for name, rows in splits.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    used = sorted({c["function"]["name"] for r in data for m in r["messages"] for c in m.get("tool_calls") or []})
    with open(os.path.join(OUT, "tools.json"), "w", encoding="utf-8") as f:
        json.dump([t for t in TOOL_SPECS if t["function"]["name"] in used], f, ensure_ascii=False, indent=1)
    cats = {}
    for r in data:
        key = f"{r['category']}/{r['language']}"
        cats[key] = cats.get(key, 0) + 1
    print(f"{len(data)} examples -> train {len(splits['train.jsonl'])}, eval {len(splits['eval.jsonl'])} | "
          + ", ".join(f"{k} {v}" for k, v in sorted(cats.items())))


if __name__ == "__main__":
    main()
