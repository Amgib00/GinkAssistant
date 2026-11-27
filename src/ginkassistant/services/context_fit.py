"""Fitting a request into what the AI model takes (0.1.163).

Groq's free plan takes about 8,000 tokens a minute for GPT-OSS 120B, and one request has to fit inside that on its
own. A chat that made a web page three times carried three whole copies of the page, so the next request was 17,295
tokens and Groq refused it ("Request too large for model ... Limit 8000, Requested 17295") -- and that raw message,
with the organization id of Gink's Groq account in it, reached the person.

Now, before a request goes (backend_server._fit_request, and the apps when they talk to Groq themselves):

1. Earlier versions of the same artifact (the same title) are left out -- the newest one stays. Always: nothing is
   lost, the chat page keeps every version.
2. Still too big for the model's limit: the room for the answer shrinks to what's left (never below a floor), long
   code in older messages becomes a line saying it was there, the oldest turns are left out (a turn whole, so a tool
   call keeps its result), long tool results are shortened, then older artifacts.
3. A request that can't fit one model goes to the next one that can (on the free plan Llama 4 Scout takes 30,000
   tokens a minute, Llama 3.3 70B 12,000).

The limits are learned from Groq's own answers: every reply's x-ratelimit-limit-tokens header, and a refusal's
"Limit 8000, Requested 17295" -- which also shows whether the room asked for the answer (max_tokens) counts.
Refusals are told in plain words (friendly_refusal); a developer sees Groq's message without Gink's account details
(scrub). Pure Python, no other module: the server image copies it as it is (deploy/Dockerfile)."""
from __future__ import annotations

import json
import re
from typing import List, Optional

CHARS_PER_TOKEN = 3.3        # GPT-OSS's tokenizer: about 4 characters a token in English prose, about 3 in code and HTML
MESSAGE_TOKENS = 8           # each message's role and framing
IMAGE_TOKENS = 1500          # a picture (never left out)
MARGIN = 0.9                 # aim under the limit: an estimate isn't a count
MIN_ANSWER = 1024            # the least room left for an answer
OLD_CODE_CHARS = 600         # longer code in an older message: a line saying it was there
TOOL_RESULT_CHARS = 1500     # an older tool result is shortened to this

# Groq's free plan: tokens a minute (TPM) per model, until Groq's own answers say otherwise (a paid plan: much more).
FREE_TPM = {
    "openai/gpt-oss-120b": 8000, "openai/gpt-oss-20b": 8000, "qwen/qwen3.8-27b": 6000, "qwen/qwen3-32b": 6000,
    "llama-3.3-70b-versatile": 12000, "meta-llama/llama-4-scout-17b-16e-instruct": 30000,
    "meta-llama/llama-4-maverick-17b-128e-instruct": 6000, "llama-3.1-8b-instant": 6000,
    "moonshotai/kimi-k2-instruct": 10000, "moonshotai/kimi-k2-instruct-0905": 10000,
}
DEFAULT_TPM = 6000

TOO_LONG = ("This chat has grown too long for Gink's AI to read in one go. Start a new chat for the next step "
            "(paste the part you're working on), or ask for a smaller change.")
BUSY = "Gink's AI is busy right now. Please try again in {wait}."
DAILY = "Gink's AI has reached its limit for today. Please try again later."
PROBLEM = "The AI service had a problem. Please try again in a moment."


# ---------------------------------------------------------------- reading messages
def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return "" if content is None else json.dumps(content, default=str)


def _images(content) -> int:
    if not isinstance(content, list):
        return 0
    return sum(1 for p in content if isinstance(p, dict) and p.get("type") in ("image_url", "input_image"))


def estimate(messages, tools=None, factor: float = 1.0) -> int:
    """About how many tokens the messages (and tool definitions) are."""
    chars, extra = 0, 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        chars += len(text_of(m.get("content")))
        if m.get("tool_calls"):
            chars += len(json.dumps(m["tool_calls"], default=str))
        extra += MESSAGE_TOKENS + IMAGE_TOKENS * _images(m.get("content"))
    if tools:
        chars += len(json.dumps(tools, default=str))
    return int(chars / CHARS_PER_TOKEN * (factor or 1.0)) + extra


# ---------------------------------------------------------------- fenced blocks and artifacts
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([^\n]*)$")
_TITLE = re.compile(r"""\btitle\s*=\s*["“']([^"”'\n]{1,120})["”']""", re.I)


def blocks(text: str) -> list:
    """The fenced blocks in a text: [{"start", "end", "lang", "title", "body"}] (an unclosed one runs to the end)."""
    out, lines, pos, i = [], text.split("\n"), 0, 0
    offsets = []
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence, info = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(lines):
            close = lines[j].strip()
            if close and close[0] == fence[0] and set(close) == {fence[0]} and len(close) >= len(fence):
                break
            j += 1
        end = (offsets[j] + len(lines[j])) if j < len(lines) else len(text)
        t = _TITLE.search(info)
        out.append({"start": offsets[i], "end": end, "lang": (info.split() or [""])[0].lower().split("title=")[0],
                    "title": t.group(1).strip() if t else "", "body": "\n".join(lines[i + 1:j])})
        i = j + 1
    return out


def _key(title: str) -> str:
    return " ".join(title.lower().split())


def _note(title: str, why: str = "") -> str:
    return (f"[An earlier version of “{title}” was here. It's left out to keep this chat within the AI's limits"
            f"{why}; the newest version is further down.]")


def _latest_versions(messages) -> dict:
    """title key -> (message index, block start) of the newest version of each artifact."""
    latest = {}
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("content"), str):
            for b in blocks(m["content"]):
                if b["title"]:
                    latest[_key(b["title"])] = (i, b["start"])
    return latest


def drop_old_versions(messages) -> tuple:
    """Earlier versions of the same artifact left out (the newest stays). -> (messages, how many were left out)."""
    latest, out, n = _latest_versions(messages), [], 0
    for i, m in enumerate(messages or []):
        if not (isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("content"), str)):
            out.append(m)
            continue
        text, changed = m["content"], False
        for b in reversed(blocks(text)):
            if b["title"] and latest.get(_key(b["title"])) != (i, b["start"]):
                text = text[:b["start"]] + _note(b["title"]) + text[b["end"]:]
                changed, n = True, n + 1
        out.append(dict(m, content=text) if changed else m)
    return out, n


def _strip_old_code(messages, protect: int, keep_latest: bool = True) -> tuple:
    """Long code in older messages (not the newest version of an artifact) -> a line saying it was there."""
    latest = _latest_versions(messages) if keep_latest else {}
    keep_from = _protected_from(messages, protect)
    out, n = [], 0
    for i, m in enumerate(messages):
        if i >= keep_from or not (isinstance(m, dict) and m.get("role") in ("assistant", "user")
                                  and isinstance(m.get("content"), str)):
            out.append(m)
            continue
        text, changed = m["content"], False
        for b in reversed(blocks(text)):
            newest = b["title"] and latest.get(_key(b["title"])) == (i, b["start"])
            if newest or len(b["body"]) < OLD_CODE_CHARS:
                continue
            what = f"“{b['title']}”" if b["title"] else (f"{b['lang']} code" if b["lang"] else "code")
            text = (text[:b["start"]] + f"[{what} ({b['body'].count(chr(10)) + 1} lines) was here; left out to keep this "
                    "chat within the AI's limits.]" + text[b["end"]:])
            changed, n = True, n + 1
        out.append(dict(m, content=text) if changed else m)
    return out, n


def _protected_from(messages, protect: int) -> int:
    """The index from which messages are never left out: the last `protect` turns (a turn starts at a person's message)."""
    starts = [i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "user"]
    if not starts:
        return 0
    return starts[-min(max(protect, 1), len(starts))]


def _drop_old_turns(messages, protect: int, fits, keep_latest: bool = True) -> tuple:
    """The oldest turns left out, whole (system messages stay), until `fits(messages)`; turns holding the newest
    version of an artifact stay while keep_latest. -> (messages, how many turns were left out)."""
    msgs, n = list(messages), 0
    while not fits(msgs):
        keep_from = _protected_from(msgs, protect)
        latest = {v[0] for v in _latest_versions(msgs).values()} if keep_latest else set()
        starts = [i for i, m in enumerate(msgs) if isinstance(m, dict) and m.get("role") == "user" and i < keep_from]
        groups = []
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else keep_from
            groups.append((s, e))
        lead = [i for i, m in enumerate(msgs[:starts[0] if starts else keep_from])
                if isinstance(m, dict) and m.get("role") != "system"]          # assistant words before any question
        if lead:
            groups.insert(0, (lead[0], lead[-1] + 1))
        drop = next(((s, e) for s, e in groups if not any(s <= i < e for i in latest)), None)
        if drop is None:
            break
        s, e = drop
        msgs = [m for i, m in enumerate(msgs) if not (s <= i < e) or (isinstance(m, dict) and m.get("role") == "system")]
        n += 1
    return msgs, n


def _shorten_tool_results(messages, keep_last: int = 2, chars: int = TOOL_RESULT_CHARS) -> tuple:
    idx = [i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "tool"]
    old, out, n = set(idx[:-keep_last] if keep_last else idx), [], 0
    for i, m in enumerate(messages):
        c = text_of(m.get("content")) if isinstance(m, dict) else ""
        if i in old and len(c) > chars:
            out.append(dict(m, content=c[:chars] + "\n[... the rest of this result is left out to keep within the AI's limits]"))
            n += 1
        else:
            out.append(m)
    return out, n


def _shorten_long_texts(messages, protect: int, chars: int = 2400, keep_latest: bool = True) -> tuple:
    """Very long older messages (pasted documents, long answers): their start and end, the middle left out -- never
    one holding the newest version of an artifact while keep_latest."""
    keep_from, out, n = _protected_from(messages, protect), [], 0
    latest = {v[0] for v in _latest_versions(messages).values()} if keep_latest else set()
    for i, m in enumerate(messages):
        if (i < keep_from and i not in latest and isinstance(m, dict) and m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str) and len(m["content"]) > chars):
            c = m["content"]
            out.append(dict(m, content=c[:chars * 2 // 3] + "\n[... the middle of this earlier message is left out to keep "
                            "this chat within the AI's limits ...]\n" + c[-chars // 3:]))
            n += 1
        else:
            out.append(m)
    return out, n


# ---------------------------------------------------------------- fitting
def fit(messages, limit: int, max_tokens: int, min_answer: int = MIN_ANSWER, factor: float = 1.0, tools=None,
        answer_counts: bool = True, compact: bool = True, level: int = 2) -> Optional[tuple]:
    """The request made to fit `limit` tokens. -> (messages, max_tokens, notes) -- or None when it can't.

    answer_counts: whether the room for the answer (max_tokens) counts toward the limit (Groq: yes, it showed so).
    compact: False = never change the messages (developers' own requests), only the room for the answer.
    level 1: the newest version of every artifact and the last two turns always stay (the server tries every model
    like this first); level 2: everything but the person's last message may be left out."""
    budget = int(limit * MARGIN)
    min_answer = max(64, min(int(min_answer), int(max_tokens or min_answer)))
    want = int(max_tokens or min_answer)
    notes: List[str] = []

    def size(ms):
        return estimate(ms, tools, factor)

    def ok(ms, out):
        return size(ms) + (out if answer_counts else 0) <= budget

    def room(ms):
        return want if not answer_counts else min(want, budget - size(ms))

    msgs = list(messages or [])
    if compact:
        msgs, n = drop_old_versions(msgs)
        if n:
            notes.append(f"{n} earlier version{'s' if n != 1 else ''} left out")
    if ok(msgs, want):
        return msgs, want, notes
    if room(msgs) >= min_answer and size(msgs) <= budget:
        notes.append("less room for the answer")
        return msgs, room(msgs), notes
    if not compact:
        return None
    floor = min_answer if answer_counts else 0
    steps = (
        ("long code in older messages left out", lambda ms: _strip_old_code(ms, 2)),
        ("older turns left out", lambda ms: _drop_old_turns(ms, 2, lambda x: size(x) + floor <= budget)),
        ("older tool results shortened", lambda ms: _shorten_tool_results(ms)),
        ("long older messages shortened", lambda ms: _shorten_long_texts(ms, 2)),
        ("earlier artifacts left out", lambda ms: _strip_old_code(ms, 1, keep_latest=False)),
        ("older turns left out", lambda ms: _drop_old_turns(ms, 1, lambda x: size(x) + floor <= budget, keep_latest=False)),
        ("tool results shortened", lambda ms: _shorten_tool_results(ms, keep_last=0, chars=800)),
        ("long older messages shortened", lambda ms: _shorten_long_texts(ms, 1, keep_latest=False)),
    )
    for note, step in (steps[:4] if level < 2 else steps):
        msgs, n = step(msgs)
        if n and note not in notes:
            notes.append(note)
        if ok(msgs, want):
            return msgs, want, notes
        if size(msgs) <= budget and room(msgs) >= min_answer:
            return msgs, room(msgs), notes + ["less room for the answer"]
    return None


# ---------------------------------------------------------------- what Groq said
_LIMIT = re.compile(r"on (tokens|requests) per (minute|day)\s*\((TPM|TPD|RPM|RPD)\)\s*:\s*Limit (\d+)"
                    r"(?:,\s*Used (\d+))?(?:,\s*Requested (\d+))?", re.I)
_WAIT = re.compile(r"try again in ((?:\d+(?:\.\d+)?h)?(?:\d+(?:\.\d+)?m(?!s))?(?:\d+(?:\.\d+)?s)?(?:\d+(?:\.\d+)?ms)?)", re.I)


def read_refusal(text) -> Optional[dict]:
    """Groq's "Limit 8000, Used 6524, Requested 7210 ... try again in 44.8s" -> {"kind": "TPM", "limit", "used",
    "requested", "wait"} (None when it isn't a limit refusal)."""
    raw = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text or "")
    m = _LIMIT.search(raw)
    if not m:
        return None
    w = _WAIT.search(raw)
    return {"kind": m.group(3).upper(), "limit": int(m.group(4)), "used": int(m.group(5)) if m.group(5) else None,
            "requested": int(m.group(6)) if m.group(6) else None, "wait": seconds(w.group(1)) if w and w.group(1) else None}


def seconds(text: str) -> Optional[float]:
    """ "44.8575s", "7m12.5s", "1h2m", "523ms" -> seconds."""
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", str(text or "")):
        total += float(num) * {"ms": 0.001, "h": 3600, "m": 60, "s": 1}[unit]
        found = True
    return total if found else None


def wait_words(secs) -> str:
    if not secs or secs < 2:
        return "a moment"
    if secs < 90:
        return f"{int(secs + 0.999)} seconds"
    if secs < 5400:
        return f"{int(secs / 60 + 0.5)} minutes"
    return f"{int(secs / 3600 + 0.5)} hours"


_ORG = re.compile(r"\s*(?:in|for) (?:the )?organi[sz]ation\s*`?org_[A-Za-z0-9]+`?", re.I)
_TIER = re.compile(r"\s*service tier\s*`?[\w-]+`?", re.I)
_UPSELL = re.compile(r"\s*(Need more tokens\?|Upgrade to|Visit https://console\.groq\.com)[^\n]*", re.I)


def scrub(text) -> str:
    """A provider's message without Gink's own account details (organization id, plan, upgrade links)."""
    raw = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text or "")
    raw = _UPSELL.sub("", _TIER.sub("", _ORG.sub("", raw)))
    raw = re.sub(r"\borg_[A-Za-z0-9]{6,}\b", "(account)", raw)
    return re.sub(r"[ \t]{2,}", " ", raw).strip()


def friendly_refusal(status: int, text) -> tuple:
    """What a person sees when the AI provider refused: (plain words, a short code)."""
    info = read_refusal(text) or {}
    raw = (text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text or "")).lower()
    if (status == 413 or (info.get("requested") and info.get("limit") and info.get("requested") > info.get("limit"))
            or "context_length" in raw or "reduce the length" in raw or "maximum context length" in raw):
        return TOO_LONG, "too_large"
    if status == 429 or info:
        if (info.get("kind") in ("TPD", "RPD") and (info.get("wait") or 0) > 600) or (not info and "per day" in raw):
            return DAILY, "busy"
        return BUSY.format(wait=wait_words(info.get("wait") or 20)), "busy"
    return PROBLEM, "upstream"
