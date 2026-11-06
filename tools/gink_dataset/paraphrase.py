"""
More ways to ask: rewrites each action request in the training set several ways, with an
Apache-2.0 model (GPT-OSS on Groq by default), and keeps only rewrites that can't change the answer.

    python tools/gink_dataset/generate.py
    python tools/gink_dataset/paraphrase.py --limit 20          # try a few first (asks for your Groq key, hidden)
    python tools/gink_dataset/paraphrase.py                     # then all (resumes where it stopped)
    python tools/gink_dataset/generate.py && python tools/gink_dataset/validate.py

Why GPT-OSS and not Claude: Anthropic's terms don't allow using Claude's output to train other
models; GPT-OSS is Apache-2.0. The key: GROQ_API_KEY, or it's asked for (hidden); --ask-key always
asks. It prints which key it used (masked: first and last 4 characters) and Groq's reason if refused.

Every rewrite must keep the request's facts -- each number and time, am/pm, day words (tomorrow,
lundi...), names, places, currencies -- and add no new numbers, so the tool call the example teaches
(computed from the original) is still exactly right. Rewrites that fail a check are dropped.
Results go to paraphrases.csv (one row per rewrite): skim it and set approved to "no" for anything
odd; generate.py uses rows with approved = yes, for the TRAINING examples only (the held-out
examples stay as they are, so scores stay honest).
"""
import argparse
import csv
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "paraphrases.csv")
FIELDS = ["language", "original", "paraphrase", "model", "approved"]
DAY_WORDS = {"today", "tonight", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
             "sunday", "aujourd'hui", "ce soir", "demain", "lundi", "mardi", "mercredi", "jeudi", "vendredi",
             "samedi", "dimanche", "am", "pm", "morning", "evening", "matin", "soir", "minutes", "minute", "hour",
             "hours", "heure", "heures"}
CURRENCY_WORDS = {"euro", "euros", "dollar", "dollars", "naira", "nairas", "cedi", "cedis", "leone", "leones",
                  "shilling", "shillings", "pound", "pounds", "livres", "franc", "francs", "cfa"}
FR_HINTS = {"le", "la", "les", "de", "du", "des", "à", "au", "mon", "ma", "mes", "pour", "est", "un", "une", "je",
            "moi", "tu", "te", "et", "dans", "s'il", "plaît", "combien", "quel", "quelle", "réveille", "mets"}



# Groq (and other providers) sit behind Cloudflare, which refuses Python's default "Python-urllib/3.x"
# with HTTP 403 ("error code: 1010") -- the owner's first runs. A plain name of our own goes through.
USER_AGENT = "GinkDataset/1.0 (+https://github.com/Amgib00/GinkAssistant)"

def ssl_context():
    """Certificates for https: Python from python.org on a Mac has none of its own until you run its
    "Install Certificates" command, which made every request fail with CERTIFICATE_VERIFY_FAILED.
    certifi (already installed with Gink) carries them."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def real_key(value: str) -> str:
    """Placeholders like "..." or "your-key" count as no key (then it's asked for, hidden)."""
    v = (value or "").strip().strip("'\"")
    placeholder = (not v or set(v) <= {".", "x", "X", "*"} or any(c in v for c in "<> ")
                   or v.lower() in ("your-key", "your_key", "key", "groq_api_key", "api_key"))
    return "" if placeholder else v

def masked(key: str) -> str:
    """Enough to tell keys apart, never enough to use: "gsk_…9f2c (56 characters)"."""
    k = key or ""
    return f"{k[:4]}\u2026{k[-4:]} ({len(k)} characters)" if len(k) > 10 else f"({len(k)} characters)"


def provider_message(exc) -> str:
    """The provider's own reason, from its error reply (never the key)."""
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    try:
        data = json.loads(body)
        return str((data.get("error") or {}).get("message") or data.get("detail") or body)[:200]
    except Exception:
        text = " ".join(re.sub(r"<[^>]+>", " ", body).split())[:160]        # e.g. Cloudflare's "error code: 1010"
        return text or getattr(exc, "reason", "") or "no reason given"


def words(text: str) -> list:
    return re.findall(r"[\w'’]+", text.lower())


def anchors(text: str) -> set:
    """What a rewrite must keep: numbers/times, day and time words, capitalised names, codes."""
    keep = set(re.findall(r"\d+(?:[:h.,]\d+)?", text.lower()))
    low = " " + " ".join(words(text)) + " "
    keep |= {w for w in DAY_WORDS | CURRENCY_WORDS if f" {w} " in low}
    tokens = re.findall(r"[\w'’]+", text)
    for i, tok in enumerate(tokens):
        if tok[:1].isupper() and i > 0 and tok.lower() not in DAY_WORDS and len(tok) > 1:
            keep.add(tok.lower())                       # names, places (not the first word of the sentence)
        if re.fullmatch(r"[A-Z]{3}", tok):
            keep.add(tok.lower())                       # currency codes
    return keep


REMEMBER_CUES = {"remember", "memorize", "memorise", "retiens", "souviens", "mémorise"}
REMIND_CUES = {"remind", "reminder", "reminders", "rappelle", "rappel", "rappels", "rappeler"}


def changed_intent(original: str, rewrite: str) -> str:
    """"Remember that..." (a fact) and "Remind me..." (a reminder) are different actions."""
    o, r = set(words(original)), set(words(rewrite))
    if o & REMEMBER_CUES and r & REMIND_CUES and not r & REMEMBER_CUES:
        return "turned 'remember' into 'remind'"
    if o & REMIND_CUES and r & REMEMBER_CUES and not r & REMIND_CUES:
        return "turned 'remind' into 'remember'"
    return ""


def problems(original: str, rewrite: str, language: str) -> list:
    out = []
    r = rewrite.strip()
    if not r or len(r) > 300:
        out.append("empty or too long")
        return out
    if re.sub(r"\W+", "", r.lower()) == re.sub(r"\W+", "", original.lower()):
        out.append("same as the original")
    ratio = len(r) / max(1, len(original))
    if not 0.4 <= ratio <= 3.0:
        out.append("length changed too much")
    low = " " + " ".join(words(r)) + " "
    for a in sorted(anchors(original)):
        if a.isdigit() or re.fullmatch(r"\d+(?:[:h.,]\d+)?", a):
            if a not in r.lower():
                out.append(f"lost {a!r}")
        elif f" {a} " not in low:
            out.append(f"lost {a!r}")
    if changed_intent(original, r):
        out.append(changed_intent(original, r))
    new_numbers = set(re.findall(r"\d+", r)) - set(re.findall(r"\d+", original))
    if new_numbers:
        out.append(f"added numbers {sorted(new_numbers)}")
    if language == "fr" and not (set(words(r)) & FR_HINTS):
        out.append("doesn't look French")
    if language == "en" and len(set(words(r)) & FR_HINTS) >= 3:
        out.append("doesn't look English")
    return out


PROMPT = ("Rewrite this request to a phone assistant {n} different ways a real person might type or say it, "
          "in {lang}. Keep EVERY number, time (with am/pm), day, name, place, amount and currency exactly as "
          "written; don't add any. Vary the wording, length and tone (short, polite, casual). "
          'Answer with JSON only: {{"variants": ["...", "..."]}}\n\nRequest: {text}')


def ask(base, key, model, text, language, n):
    body = {"model": model, "temperature": 0.9, "max_tokens": 900, "reasoning_effort": "low",
            "messages": [{"role": "user", "content": PROMPT.format(n=n, lang="French" if language == "fr" else "English",
                                                                   text=text)}]}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120, context=ssl_context()) as r:
        content = json.load(r)["choices"][0]["message"].get("content") or ""
    m = re.search(r"\{.*\}", content, re.S)
    try:
        return [str(v) for v in json.loads(m.group(0)).get("variants", [])] if m else []
    except ValueError:
        return []


def with_retries(call, tries: int = 8, out=print):
    """Groq's free plan allows only so many requests a minute: on 429, wait (Retry-After, or longer each
    time) and try again, so a full run finishes on its own."""
    for attempt in range(1, tries + 1):
        try:
            return call()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries:
                raise
            try:
                wait = float(exc.headers.get("Retry-After") or 0)
            except (TypeError, ValueError, AttributeError):
                wait = 0
            wait = min(max(wait, 15 * attempt), 120)
            out(f"  Groq is busy; waiting {wait:.0f} s and trying again ({attempt}/{tries - 1})")
            time.sleep(wait)


def load_csv(path=CSV_PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def approved_map(path=CSV_PATH) -> dict:
    """original request -> [approved rewrites] (generate.py uses this)."""
    out = {}
    for row in load_csv(path):
        if (row.get("approved") or "").strip().lower() == "yes" and row.get("paraphrase"):
            out.setdefault(row["original"], []).append(row["paraphrase"])
    return out


def recheck(path=CSV_PATH) -> int:
    """New checks apply to old rows too: approved rewrites that fail today's checks become "no"."""
    rows = load_csv(path)
    flipped = []
    for row in rows:
        if (row.get("approved") or "").lower() == "yes" and row.get("paraphrase"):
            why = problems(row["original"], row["paraphrase"], row.get("language") or "en")
            if why:
                row["approved"] = "no"
                flipped.append((row["paraphrase"], why[0]))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    for text, why in flipped:
        print(f"  no: {text}  ({why})")
    print(f"Rechecked {len(rows)} rows: {len(flipped)} set to no.")
    return 0


def main(argv=None, ask_fn=ask):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=os.path.join(HERE, "out", "train.jsonl"))
    ap.add_argument("--base-url", default=os.environ.get("GINK_PARA_BASE", "https://api.groq.com/openai/v1"))
    ap.add_argument("--model", default=os.environ.get("GINK_PARA_MODEL", "openai/gpt-oss-120b"))
    ap.add_argument("--per-request", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="only this many requests (to try it)")
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--key", default="")
    ap.add_argument("--ask-key", action="store_true", help="ignore GROQ_API_KEY and ask for the key (hidden)")
    ap.add_argument("--recheck", action="store_true", help="run today's checks on paraphrases.csv again (no AI calls)")
    a = ap.parse_args(argv)
    if a.recheck:
        return recheck(a.csv)
    if not os.path.exists(a.train):
        print("Run tools/gink_dataset/generate.py first.")
        return 1
    key, source = real_key(a.key), "--key"
    if not key and not a.ask_key:
        key, source = real_key(os.environ.get("GROQ_API_KEY", "")), "GROQ_API_KEY in this Terminal"
    if not key:
        key, source = getpass.getpass("Groq API key (hidden): ").strip(), "what you typed"
    print(f"Using API key from {source}.")
    rows = [json.loads(l) for l in open(a.train, encoding="utf-8") if l.strip()]
    todo, seen = [], set()
    for r in rows:
        if r.get("category") != "action":
            continue
        user = next(m["content"] for m in r["messages"] if m["role"] == "user")
        if user not in seen:
            seen.add(user)
            todo.append((r.get("language", "en"), user))
    done = {row["original"] for row in load_csv(a.csv)}
    todo = [t for t in todo if t[1] not in done]
    if a.limit:
        todo = todo[:a.limit]
    new_file = not os.path.exists(a.csv)
    kept = dropped = 0
    with open(a.csv, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, (lang, text) in enumerate(todo, 1):
            try:
                variants = with_retries(lambda: ask_fn(a.base_url, key, a.model, text, lang, a.per_request))
            except urllib.error.HTTPError as exc:
                why = provider_message(exc)
                if exc.code == 401:
                    print(f"  Groq refused the key ({why}). Copy a working one -- the same one your Gink server uses "
                          "(Render -> gink-server -> Environment -> GROQ_API_KEY) -- and run again with --ask-key.")
                elif exc.code == 403:
                    print(f"  Groq said no (HTTP 403: {why}). If the key is right, Groq may be refusing this "
                          "network or country. Plan B, through your Gink server: --base-url "
                          "https://gink-server.onrender.com/v1 --model gink-crystal --ask-key (a Gink developer key).")
                elif exc.code == 429:
                    print("  Groq is still busy after several tries. Run again later: it continues where it stopped.")
                else:
                    print(f"  {i}: the AI service answered HTTP {exc.code}; run again later to continue")
                break
            except Exception as exc:
                print(f"  {i}: request failed ({exc}); run again later to continue")
                break
            ok_any = False
            for v in dict.fromkeys(v.strip() for v in variants):
                why = problems(text, v, lang)
                if why:
                    dropped += 1
                    continue
                w.writerow({"language": lang, "original": text, "paraphrase": v, "model": a.model, "approved": "yes"})
                kept += 1
                ok_any = True
            if not ok_any:                              # remember it was tried, so a re-run moves on
                w.writerow({"language": lang, "original": text, "paraphrase": "", "model": a.model, "approved": "no"})
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(todo)} requests: {kept} rewrites kept, {dropped} dropped")
            time.sleep(0.2)
    print(f"Done: {kept} rewrites kept, {dropped} dropped by the checks -> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
