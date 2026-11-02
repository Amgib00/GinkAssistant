"""
Gink's actions in many languages: translates action examples (and Gink's short reply) with an
Apache-2.0 model (GPT-OSS on Groq by default) and keeps only translations that can't change the action.

    python tools/gink_dataset/generate.py
    python tools/gink_dataset/translate.py --languages es,pt,ar --limit 10     # try a few
    python tools/gink_dataset/translate.py --languages all                      # every listed language
    python tools/gink_dataset/generate.py && python tools/gink_dataset/validate.py

Which examples: only actions whose details survive translation unchanged -- numbers, times, amounts,
currency codes, place and app names (calculate, convert_currency, get_weather, open_app, set_alarm,
set_timer, set_volume, media_control). A reminder's or a file's own words would change in another
language and no longer match the example's action, so those stay English and French.

Checks: every number in the request and the reply is kept, no number added, every place / app name in
the action is still in the translation, and the text is in the right script (Arabic, Devanagari, CJK...).

Approval: for widely used languages that GPT-OSS writes well, a translation that passes the checks is
approved = yes (set it to no if a speaker finds it wrong). For every other language -- including
Hausa, Yoruba, Wolof, Krio, Pidgin -- it's a DRAFT (approved empty) until a native speaker corrects it
and sets approved = yes. generate.py uses approved rows, for training examples only.
Results: translations.csv. Same key handling and retries as paraphrase.py.
"""
import argparse
import csv
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paraphrase import USER_AGENT, masked, provider_message, real_key, ssl_context, with_retries  # noqa: E402

CSV_PATH = os.path.join(HERE, "translations.csv")
FIELDS = ["language", "original", "user", "reply", "model", "approved"]
# languages GPT-OSS writes well: translations that pass the checks count as approved
WELL_SUPPORTED = {"es": "Spanish", "pt": "Portuguese", "de": "German", "it": "Italian", "nl": "Dutch",
                  "ar": "Arabic", "hi": "Hindi", "bn": "Bengali", "ur": "Urdu", "zh": "Chinese (Simplified)",
                  "ja": "Japanese", "ko": "Korean", "ru": "Russian", "uk": "Ukrainian", "pl": "Polish",
                  "tr": "Turkish", "id": "Indonesian", "ms": "Malay", "vi": "Vietnamese", "th": "Thai",
                  "fa": "Persian", "sw": "Swahili"}
# drafts: need a native speaker before they're used
NEEDS_REVIEW = {"ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "am": "Amharic", "zu": "Zulu", "ff": "Fula",
                "wo": "Wolof", "kri": "Krio", "pcm": "Nigerian Pidgin", "ln": "Lingala", "so": "Somali",
                "rw": "Kinyarwanda", "tw": "Twi", "mg": "Malagasy", "bm": "Bambara"}
SCRIPTS = {"ar": r"[\u0600-\u06FF]", "fa": r"[\u0600-\u06FF]", "ur": r"[\u0600-\u06FF]", "hi": r"[\u0900-\u097F]",
           "bn": r"[\u0980-\u09FF]", "zh": r"[\u4E00-\u9FFF]", "ja": r"[\u3040-\u30FF\u4E00-\u9FFF]",
           "ko": r"[\uAC00-\uD7AF]", "ru": r"[\u0400-\u04FF]", "uk": r"[\u0400-\u04FF]", "th": r"[\u0E00-\u0E7F]",
           "am": r"[\u1200-\u137F]"}
SAME_EVERYWHERE = {"action", "format", "day", "from_currency", "to_currency", "time", "when", "expression",
                   "seconds", "level", "amount"}        # values that are the same in every language
OWN_WORDS = {"label", "text", "fact", "content", "title"}   # the person's own words: they'd change in translation
TRANSLATABLE_TOOLS = {"calculate", "convert_currency", "get_weather", "open_app", "set_alarm", "set_timer",
                      "set_volume", "media_control"}


def numbers(text: str) -> set:
    return set(re.findall(r"\d+", text or ""))


def kept_names(example) -> list:
    """Words in the action that must appear unchanged in a translated request (places, app names...)."""
    names = []
    for m in example["messages"]:
        for c in m.get("tool_calls") or []:
            for k, v in json.loads(c["function"]["arguments"]).items():
                if isinstance(v, str) and k not in SAME_EVERYWHERE:
                    names.append(v)
    return names


def translatable(example) -> bool:
    calls = [c for m in example["messages"] for c in m.get("tool_calls") or []]
    if example.get("category") != "action" or not calls:
        return False
    if any(c["function"]["name"] not in TRANSLATABLE_TOOLS for c in calls):
        return False
    if any(k in OWN_WORDS for c in calls for k in json.loads(c["function"]["arguments"])):
        return False                                                   # e.g. a timer's label "rice"
    user = next(m["content"] for m in example["messages"] if m["role"] == "user").lower()
    return all(n.lower() in user for n in kept_names(example))      # places / app names written in the request


def final_reply(example) -> str:
    last = example["messages"][-1]
    return last["content"] if last["role"] == "assistant" and not last.get("tool_calls") else ""


def problems(example, lang: str, user: str, reply: str) -> list:
    out = []
    orig_user = next(m["content"] for m in example["messages"] if m["role"] == "user")
    if not user.strip() or len(user) > 400:
        return ["empty or too long"]
    if user.strip().lower() == orig_user.strip().lower():
        out.append("not translated")
    if not numbers(orig_user) <= numbers(user):
        out.append(f"lost numbers {sorted(numbers(orig_user) - numbers(user))}")
    if numbers(user) - numbers(orig_user):
        out.append(f"added numbers {sorted(numbers(user) - numbers(orig_user))}")
    for n in kept_names(example):
        if n.lower() not in user.lower():
            out.append(f"lost {n!r}")
    if final_reply(example):
        if not reply.strip():
            out.append("no reply")
        elif not numbers(final_reply(example)) <= numbers(reply):
            out.append("the reply lost numbers")
    if lang in SCRIPTS and not re.search(SCRIPTS[lang], user):
        out.append(f"not in {lang}'s script")
    return out


PROMPT = ("Translate this conversation between a person and the phone assistant Gink into {language}. "
          "Write it the way a native speaker would naturally say it. Keep every number, time, amount, "
          "currency code, place name and app name exactly as written. "
          'Answer with JSON only: {{"user": "...", "reply": "..."}}\n\nPerson: {user}\nGink: {reply}')


def ask(base, key, model, user, reply, language):
    body = {"model": model, "temperature": 0.3, "max_tokens": 900, "reasoning_effort": "low",
            "messages": [{"role": "user", "content": PROMPT.format(language=language, user=user, reply=reply or "(no reply)")}]}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120, context=ssl_context()) as r:
        content = json.load(r)["choices"][0]["message"].get("content") or ""
    m = re.search(r"\{.*\}", content, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    return str(data.get("user") or ""), str(data.get("reply") or "")


def load(path=CSV_PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def approved_map(path=CSV_PATH) -> dict:
    """original request -> [(language, user, reply)] with approved = yes (generate.py uses this)."""
    out = {}
    for row in load(path):
        if (row.get("approved") or "").strip().lower() == "yes" and row.get("user"):
            out.setdefault(row["original"], []).append((row["language"], row["user"], row.get("reply") or ""))
    return out


def main(argv=None, ask_fn=ask):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--languages", default="es,pt,ar,sw", help="codes (es,pt,ar...), or all")
    ap.add_argument("--train", default=os.path.join(HERE, "out", "train.jsonl"))
    ap.add_argument("--base-url", default=os.environ.get("GINK_PARA_BASE", "https://api.groq.com/openai/v1"))
    ap.add_argument("--model", default=os.environ.get("GINK_PARA_MODEL", "openai/gpt-oss-120b"))
    ap.add_argument("--limit", type=int, default=0, help="only this many requests per language (to try it)")
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--key", default="")
    ap.add_argument("--ask-key", action="store_true")
    a = ap.parse_args(argv)
    known = dict(WELL_SUPPORTED, **NEEDS_REVIEW)
    langs = list(known) if a.languages.strip() == "all" else [x.strip() for x in a.languages.split(",") if x.strip()]
    unknown = [x for x in langs if x not in known]
    if unknown:
        print(f"Unknown language codes: {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
        return 1
    if not os.path.exists(a.train):
        print("Run tools/gink_dataset/generate.py first.")
        return 1
    key = real_key(a.key) or ("" if a.ask_key else real_key(os.environ.get("GROQ_API_KEY", ""))) \
        or getpass.getpass("Groq API key (hidden): ").strip()
    print(f"Using key {masked(key)}")
    rows = [json.loads(l) for l in open(a.train, encoding="utf-8") if l.strip()]
    todo, seen = [], set()
    for ex in rows:
        user = next((m["content"] for m in ex["messages"] if m["role"] == "user"), "")
        if user not in seen and translatable(ex):
            seen.add(user)
            todo.append(ex)
    done = {(r["language"], r["original"]) for r in load(a.csv)}
    new_file = not os.path.exists(a.csv)
    kept = dropped = 0
    with open(a.csv, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for lang in langs:
            batch = [ex for ex in todo if (lang, next(m["content"] for m in ex["messages"] if m["role"] == "user")) not in done]
            if a.limit:
                batch = batch[:a.limit]
            print(f"{known[lang]}: {len(batch)} requests")
            for ex in batch:
                user = next(m["content"] for m in ex["messages"] if m["role"] == "user")
                try:
                    t_user, t_reply = with_retries(lambda: ask_fn(a.base_url, key, a.model, user, final_reply(ex), known[lang]))
                except urllib.error.HTTPError as exc:
                    print(f"  Stopped: HTTP {exc.code} ({provider_message(exc)}). Run again to continue.")
                    return 1
                except Exception as exc:
                    print(f"  Stopped: {exc}. Run again to continue.")
                    return 1
                why = problems(ex, lang, t_user, t_reply)
                ok = not why
                kept += ok
                dropped += not ok
                approved = ("yes" if lang in WELL_SUPPORTED else "") if ok else "no"
                w.writerow({"language": lang, "original": user, "user": t_user if ok else "", "reply": t_reply if ok else "",
                            "model": a.model, "approved": approved})
                f.flush()
    print(f"Done: {kept} translations kept, {dropped} dropped by the checks -> {a.csv}")
    drafts = [x for x in langs if x in NEEDS_REVIEW]
    if drafts:
        print(f"Drafts for native speakers to check (approved empty): {', '.join(known[x] for x in drafts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
