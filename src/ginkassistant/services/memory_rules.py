"""
Memory rules, shared by the apps (services/memory.py) and the server (the web app, the API, the SDKs and the CLI ask
it): no imports from the package, so the server image can copy this file on its own (deploy/Dockerfile).

  subject(text)            what a memory is about, when a person has only ONE of it (a new one replaces the old)
  suggest(message, known)  a lasting fact in something the person just said, worth remembering -- or None
  is_sensitive(text)       health, religion, sexuality, politics...: kept only when the person turned on
                           Settings > Memory > "Include sensitive topics in memory" (never for teens or in healthcare)
  never_keep(text)         self-harm, abuse, crime, immigration status, passwords: never kept by itself, whatever the setting
  import_lines(text, ...)  the memories another AI assistant listed (IMPORT_PROMPT asks it for them), tidied and checked
  clean_generated(...)     the same checks for the memories Gink's AI picked out of a conversation ("Generate memory from chats")
"""
import json
import re

# ---- One fact per subject: "My phone number is ..." said again REPLACES the old number instead of sitting beside it.
# Only for things a person has one of (a name, an age, an address, a favourite X, where they live or work...):
# "My sister is Awa" and "My sister is a nurse" are both kept.
_ONE_OF = (r"name|nickname|age|birthday|date of birth|address|home address|e-?mail(?: address)?|phone(?: number)?|number|job|city|"
           r"town|country|height|weight|blood (?:type|group)|time ?zone|shoe size|wi-?fi password|budget|salary|"
           r"favou?rite [a-z' -]{2,30}")
_SUBJECTS = [
    (re.compile(rf"^my ({_ONE_OF}) (?:is|are|was|will be)\b", re.I), lambda m: "my " + m.group(1).lower()),
    (re.compile(r"^i(?: am|'m|\u2019m) \d{1,3}(?: years? old)?$", re.I), lambda m: "my age"),
    (re.compile(r"^i(?: now)? live (?:in|at|near)\b", re.I), lambda m: "i live"),
    (re.compile(r"^i(?: now)? work (?:at|for|as|in)\b", re.I), lambda m: "i work"),
    (re.compile(r"^i was born\b", re.I), lambda m: "i was born"),
    (re.compile(r"^(?:call me|i go by)\b", re.I), lambda m: "call me"),
]


def subject(text: str) -> str:
    """What a memory is about, when a person has only one of it ("my phone number", "i live"); "" otherwise."""
    t = " ".join((text or "").split())
    for rx, key in _SUBJECTS:
        m = rx.match(t)
        if m:
            return key(m).replace("favorite", "favourite").replace("color", "colour").replace("e-mail", "email")
    return ""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", " ".join((text or "").lower().split()))


# ---- suggest(): lasting facts people mention in passing ------------------------------------------------------
_JOBS = (r"student|teacher|nurse|doctor|engineer|developer|programmer|designer|driver|farmer|lawyer|chef|cook|writer|artist|"
         r"musician|trader|tailor|carpenter|mechanic|accountant|manager|pilot|soldier|pastor|imam|journalist|photographer|"
         r"electrician|plumber|pharmacist|dentist|architect|scientist|researcher|translator|banker|salesperson|shopkeeper|"
         r"founder|freelancer|consultant|midwife|fisherman|builder|cleaner|waiter|barber|hairdresser")
_FAMILY = (r"wife|husband|partner|son|daughter|mother|mom|mum|father|dad|brother|sister|girlfriend|boyfriend|fianc[e\u00e9]e?|"
           r"best friend|boss|dog|cat|pet|baby|grandmother|grandfather|uncle|aunt|cousin")
_FACTS = [re.compile(p, re.I) for p in (
    rf"^my (?:{_ONE_OF}) (?:is|are) .{{1,80}}$",
    rf"^my (?:{_FAMILY})(?:'s name)? is (?:called |named )?[^\s].{{0,40}}$",
    r"^i(?: now)? live (?:in|at|near) .{2,60}$",
    r"^i(?: now)? work (?:at|for|as|in) .{2,60}$",
    r"^i was born (?:in|on) .{2,40}$",
    r"^(?:call me|i go by) [^\s].{0,30}$",
    r"^i(?:'m| am) \d{1,3}(?: years? old)?$",
    r"^i(?:'m| am) (?:a |an )?(?:vegetarian|vegan|pescatarian|left[- ]handed|married|retired)$",
    rf"^i(?:'m| am) an? (?:[a-z-]+ )?(?:{_JOBS})$",
    r"^i(?: am|'m)? study(?:ing)? .{2,50}$",
    r"^i(?:'m| am) learning .{2,40}$",
    r"^i speak .{2,50}$",
    r"^i (?:don't|do not|can't|cannot|never) (?:eat|drink) .{2,40}$",
    r"^i prefer .{3,60}$",
)]
_LEAD_IN = re.compile(r"^(?:(?:and|but|so|well|also|btw|fyi|oh|hi|hello|hey|okay|ok|thanks|thank you|by the way|"
                      r"just so you know|for the record)[,!. ]+)+", re.I)
# Gink remembers by itself now, so health stays out completely: conditions, allergies, medicines, treatment,
# pregnancy, mental health -- about you or anyone else. (Your job -- "I'm a nurse" -- is fine; a diagnosis isn't.)
_HEALTH = re.compile(r"\b(?:allerg\w*|diabet\w*|asthma\w*|cancer|tumou?r|hiv|aids|pregnan\w*|miscarr\w*|depress\w*|anxiety|"
                     r"adhd|autis\w*|bipolar|schizo\w*|ptsd|ocd|epilep\w*|disab\w*|disorder|syndrome|diagnos\w*|medic(?:ine|ation)s?|"
                     r"pills?|dose|dosage|insulin|chemo\w*|surgery|operation|therapy|therapist|rehab|addict\w*|sober|"
                     r"illness|disease|condition|symptoms?|infection|blood (?:pressure|type|sugar)|lactose|intoleran\w*|"
                     r"colou?r[- ]?blind|blind|deaf|wheelchair|hospitali[sz]ed|sick|injur\w*|wound|fracture|"
                     r"suicid\w*|self[- ]harm|eating disorder|anorexi\w*|bulimi\w*)\b", re.I)


def is_health(text: str) -> bool:
    """Anything about someone's health -- not remembered by itself unless sensitive topics are on."""
    return bool(_HEALTH.search(text or ""))


# Other sensitive topics: beliefs, sexuality, politics, union membership, ethnicity. Like health, Gink keeps them only
# when the person turned on "Include sensitive topics in memory". (Food choices -- vegetarian, halal, kosher -- are fine.)
_SENSITIVE = re.compile(r"\b(?:relig\w*|muslim|islam\w*|christian\w*|catholic\w*|protestant|evangelical|hindu\w*|buddhis\w*|"
                        r"jewish|judaism|sikh\w*|atheis\w*|agnostic|church|mosque|synagogue|pray\w*|bible|qur'?an|koran|"
                        r"gay|lesbian|bisexual|transgender|queer|lgbt\w*|non-?binary|sexual\w*|sexuality|"
                        r"democrat\w*|republican\w*|socialis\w*|communis\w*|fascis\w*|political party|vote[ds]? for|"
                        r"trade union|union member\w*|ethnicity|ethnic|my race|my tribe|caste)\b", re.I)
# Never kept by Gink itself, whatever the settings (the person can still say "remember that ..." themselves).
_NEVER = re.compile(r"\b(?:suicid\w*|self[- ]harm\w*|kill(?:ing)? myself|eating disorder|anorexi\w*|bulimi\w*|"
                    r"abus(?:e|ed|er|ive)|rape[ds]?|molest\w*|assault\w*|arrest\w*|convict\w*|criminal record|prison|jail|"
                    r"undocumented|asylum|deport\w*|immigration status|visa status|"
                    r"passwords?|passcodes?|pin(?: code)?|cvv|card number|account number|routing number|iban|"
                    r"social security|national id|passport number|seed phrase|private key)\b", re.I)


def is_sensitive(text: str) -> bool:
    """Health or another sensitive topic (religion, sexuality, politics...)."""
    return is_health(text) or bool(_SENSITIVE.search(text or ""))


def never_keep(text: str) -> bool:
    """Topics Gink never keeps by itself: self-harm, abuse, crime, immigration status, passwords and numbers."""
    return bool(_NEVER.search(text or ""))


# Facts that are only sensitive ones (offered only with sensitive topics on): "I'm allergic to peanuts", "I'm Muslim".
_SENSITIVE_FACTS = [re.compile(p, re.I) for p in (
    r"^i(?:'m| am) allergic to .{2,40}$",
    r"^i have (?:a |an |type [12] )?[a-z' -]{3,40}$",
    r"^i(?:'m| am) (?:a |an )?(?:muslim|christian|catholic|protestant|orthodox christian|evangelical|hindu|buddhist|jewish|"
    r"sikh|atheist|agnostic)$",
    r"^i(?:'m| am) (?:gay|lesbian|bisexual|queer|transgender|non-?binary|a trans (?:man|woman))$",
    r"^i(?:'m| am) (?:diabetic|asthmatic|epileptic|deaf|blind|colou?r[- ]?blind|pregnant|lactose intolerant)$",
    r"^i take .{2,50}$",
    r"^i pray .{2,40}$",
)]


_NOT_A_FACT = re.compile(r"\b(?:where|because|if|when|while|but|although|unless|maybe|might|think|guess|wish|used to)\b", re.I)


def suggest(message: str, known=(), sensitive: bool = False):
    """A lasting fact in `message` worth remembering by itself (tidied: "I live in Nairobi"), or None. `known` = the
    memories the person already has: nothing they already told Gink is offered again. sensitive=True (Settings >
    Memory > "Include sensitive topics in memory") also keeps health, religion and the like -- never never_keep() ones."""
    text = (message or "").replace("\u2019", "'").strip()
    if not text or len(text) > 400:
        return None
    have = {norm(k) for k in known}
    patterns = _FACTS + (_SENSITIVE_FACTS if sensitive else [])
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = raw.strip()
        if not s or s.endswith("?"):
            continue
        s = _LEAD_IN.sub("", s.rstrip(".! ")).strip()
        if not (6 <= len(s) <= 120) or _NOT_A_FACT.search(s) or never_keep(s):
            continue
        touchy = is_sensitive(s)
        if touchy and not sensitive:
            continue
        if any(rx.match(s) for rx in patterns):
            if s.lower().startswith("i have ") and not touchy:       # "I have a dog" isn't a health fact
                continue
            fact = s[0].upper() + s[1:]
            if norm(fact) not in have:
                return fact
    return None


# ---- Import memory from other AI providers ---------------------------------------------------------------------
# The person copies IMPORT_PROMPT into a chat with their other AI assistant, pastes its answer into Gink, and
# import_lines() turns that answer into memories: one fact per line, tidied, checked, nothing already known.
IMPORT_PROMPT = (
    "I'm moving to another AI assistant and want to bring my memory with me. Please list everything you remember "
    "about me and the lasting things you've learned from our conversations: my name and what I like to be called, "
    "where I live and work, my job or studies, the languages I speak, the people and pets in my life, how I like you "
    "to answer (length, tone, format), my ongoing projects and goals, and anything else I asked you to remember.\n\n"
    "Write one fact per line, each starting with \"- \", in the first person (for example \"- I live in Nairobi\" or "
    "\"- I prefer short answers\"). Don't add headings, explanations or anything you're not sure about. Leave out "
    "passwords, codes, card or account numbers and other secrets.")

_BULLET = re.compile(r"^\s*(?:[-*\u2022\u2013\u2014\u00b7>]+|\d{1,3}[.)]|\[[ xX]?\])\s*")
_DATE = re.compile(r"^\s*[\[(]?\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?[\])]?\s*[-:\u2013\u2014]?\s*")
_CHATTER = re.compile(r"^(?:here(?:'s| is| are)\b|sure\b|certainly\b|of course\b|okay\b|ok\b|absolutely\b|great\b|note\b|"
                      r"as an ai\b|i don't have\b|i do not have\b|i can't\b|i cannot\b|these are\b|this is\b|that's\b|"
                      r"that is all\b|let me know\b|i hope\b|feel free\b|below\b|memory\b|memories\b|summary\b)", re.I)
_THIRD_PERSON = [
    (re.compile(r"^(?:the )?user(?:'s|\u2019s) ", re.I), "My "),
    (re.compile(r"^(?:the )?user is ", re.I), "I am "),
    (re.compile(r"^(?:the )?user has ", re.I), "I have "),
    (re.compile(r"^(?:the )?user was ", re.I), "I was "),
    (re.compile(r"^(?:the )?user (?:is learning|is studying) ", re.I), "I am learning "),
    (re.compile(r"^(?:the )?user (lives|works|studies|prefers|likes|loves|wants|uses|speaks|enjoys|hates|dislikes|needs|"
                r"plans|runs|owns|teaches|writes|reads|travels|goes|drives|plays|follows|avoids|eats|drinks|"
                r"doesn't|does not|can't|cannot) ", re.I), None),
]
_BASE = {"lives": "live", "works": "work", "studies": "study", "prefers": "prefer", "likes": "like", "loves": "love",
         "wants": "want", "uses": "use", "speaks": "speak", "enjoys": "enjoy", "hates": "hate", "dislikes": "dislike",
         "needs": "need", "plans": "plan", "runs": "run", "owns": "own", "teaches": "teach", "writes": "write",
         "reads": "read", "travels": "travel", "goes": "go", "drives": "drive", "plays": "play", "follows": "follow",
         "avoids": "avoid", "eats": "eat", "drinks": "drink", "doesn't": "don't", "does not": "do not",
         "can't": "can't", "cannot": "cannot"}


def _tidy(line: str) -> str:
    """One imported line -> one memory ("- The user lives in Nairobi." -> "I live in Nairobi"), or ""."""
    t = " ".join(str(line or "").replace("\u2019", "'").replace("**", "").replace("__", "").split())
    for _ in range(2):
        t = _DATE.sub("", _BULLET.sub("", t)).strip()
    t = t.strip("\"'` ").rstrip(".;, ").strip()
    if not t or t.startswith(("#", "```")) or t.endswith(":") or len(t) < 4 or len(t) > 300 or not re.search(r"[^\W\d_]", t):
        return ""
    if _CHATTER.match(t):
        return ""
    for rx, to in _THIRD_PERSON:
        m = rx.match(t)
        if m:
            t = (to + t[m.end():]) if to else "I " + _BASE.get(m.group(1).lower(), m.group(1)) + " " + t[m.end():]
            break
    return t[0].upper() + t[1:]


def _lines_of(text: str) -> list:
    """The answer's lines -- or the items of a JSON list / {"memories": [...]} if that's what was pasted."""
    raw = str(text or "")[:200000].strip()
    body = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
    if body[:1] in "[{":
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                data = next((v for v in data.values() if isinstance(v, list)), [])
            if isinstance(data, list):
                return [x if isinstance(x, str) else str((x or {}).get("text") or (x or {}).get("content") or "")
                        for x in data if isinstance(x, (str, dict))]
        except ValueError:
            pass
    return re.split(r"\n+", raw)


def import_lines(text: str, known=(), sensitive: bool = False, limit: int = 200) -> dict:
    """{"facts": [...], "skipped_sensitive": n, "skipped": n} from what another AI assistant listed. Nothing the person
    already has is added twice; never_keep() lines are skipped; sensitive ones too unless sensitive=True."""
    have = {norm(k) for k in known}
    out, skipped_sensitive, skipped = [], 0, 0
    for line in _lines_of(text):
        t = _tidy(line)
        if not t:
            continue
        if never_keep(t):
            skipped += 1
            continue
        if is_sensitive(t) and not sensitive:
            skipped_sensitive += 1
            continue
        key = norm(t)
        if not key or key in have:
            continue
        have.add(key)
        out.append(t)
        if len(out) >= limit:
            break
    return {"facts": out, "skipped_sensitive": skipped_sensitive, "skipped": skipped}


def clean_generated(lines, known=(), sensitive: bool = False, limit: int = 5) -> list:
    """The memories Gink's AI picked out of a conversation, with the same checks as an import (at most `limit`)."""
    items = [x for x in (lines or []) if isinstance(x, str) and len(x) <= 200]
    return import_lines("\n".join(items), known, sensitive, limit)["facts"]
