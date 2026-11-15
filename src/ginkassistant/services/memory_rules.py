"""
Memory rules, shared by the apps (services/memory.py) and the server (the web app, the API, the SDKs and the CLI ask
it): no imports from the package, so the server image can copy this file on its own (deploy/Dockerfile).

  subject(text)            what a memory is about, when a person has only ONE of it (a new one replaces the old)
  suggest(message, known)  a lasting fact in something the person just said, worth offering to remember -- or None.
                           Gink only OFFERS: nothing is saved unless the person chooses Remember.
"""
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
    """Anything about someone's health -- never remembered automatically."""
    return bool(_HEALTH.search(text or ""))


_NOT_A_FACT = re.compile(r"\b(?:where|because|if|when|while|but|although|unless|maybe|might|think|guess|wish|used to)\b", re.I)


def suggest(message: str, known=()):
    """A lasting fact in `message` worth remembering by itself (tidied: "I live in Nairobi"), or None. `known` = the
    memories the person already has: nothing they already told Gink is offered again."""
    text = (message or "").replace("\u2019", "'").strip()
    if not text or len(text) > 400:
        return None
    have = {norm(k) for k in known}
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = raw.strip()
        if not s or s.endswith("?"):
            continue
        s = _LEAD_IN.sub("", s.rstrip(".! ")).strip()
        if not (6 <= len(s) <= 120) or _NOT_A_FACT.search(s) or is_health(s):
            continue
        if any(rx.match(s) for rx in _FACTS):
            fact = s[0].upper() + s[1:]
            if norm(fact) not in have:
                return fact
    return None
