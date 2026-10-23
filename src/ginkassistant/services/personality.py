"""Settings > Personalization: how Gink writes. Each choice becomes one short instruction for the AI;
"default" adds nothing. The web app mirrors these in webapp/bridge.js (personalityNote)."""

STYLES = {
    "default": "",
    "professional": "Write in a polished, professional tone.",
    "friendly": "Write in a warm, friendly, conversational tone.",
    "concise": "Be brief and to the point: short answers, no filler.",
    "candid": "Be direct and candid: say plainly what you think, including disagreement.",
    "playful": "Be playful and lighthearted where it fits, without getting in the way of the answer.",
}
LEVELS = {"less", "default", "more"}
NOTES = {
    "warmth": {"less": "Keep a neutral, matter-of-fact warmth.", "more": "Be especially warm, encouraging and kind."},
    "enthusiasm": {"less": "Keep enthusiasm low-key; avoid exclamation marks.", "more": "Be upbeat and enthusiastic."},
    "emoji": {"less": "Don't use emoji.", "more": "Use a few fitting emoji."},
    "headers": {"less": "Prefer flowing paragraphs; avoid headers and bullet lists unless asked.",
                "more": "Use headers and lists to structure longer answers."},
}
KEYS = {"style": "style_base", "warmth": "style_warmth", "enthusiasm": "style_enthusiasm",
        "emoji": "style_emoji", "headers": "style_headers"}


def note(p: dict) -> str:
    parts = [STYLES.get(p.get(KEYS["style"], "default"), "")]
    for name, levels in NOTES.items():
        parts.append(levels.get(p.get(KEYS[name], "default"), ""))
    text = " ".join(x for x in parts if x)
    return ("\n\nHow to write (the user's personalization): " + text) if text else ""
