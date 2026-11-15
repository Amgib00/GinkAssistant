"""
Image looks and ideas, shared by Media Studio (apps), the web app, the server's /media/image and
/v1/images/generations (API), the SDKs and the CLI -- so "statue", "3d" or "football figurine" mean the same
everywhere. The server image copies this file flat (deploy/Dockerfile), so it imports nothing from the package.
"""
import re

STYLES = {
    "": "No style",
    "photo": "photorealistic photograph, natural light, high detail",
    "illustration": "clean digital illustration, vibrant colours",
    "3d": "3D render, soft studio lighting, tactile materials",
    "sticker": "die-cut sticker, bold outlines, simple shading, white background",
    "poster": "bold graphic poster design with strong typography",
    "logo": "minimal modern logo, flat vector, simple shapes, white background",
    "watercolor": "soft watercolour painting on textured paper",
    "anime": "anime style, cel shading, expressive",
}

# Ideas: (id, title, prompt with {subject}, default subject, style, aspect, card colours, symbol)
IDEAS = [
    ("zen", "Zen", "{subject} floating peacefully in deep meditation, soft morning light, calm and minimal, gentle film photograph",
     "a person", "photo", "3:4", "#9FB4C7,#E8EEF2", "\U0001F9D8"),
    ("claw", "Claw machine", "a cute plush toy of {subject} inside a colourful claw machine full of plushies, neon arcade lights",
     "a smiling student", "3d", "3:4", "#F472B6,#8B5CF6", "\U0001F9F8"),
    ("chibi", "Chibi keychain", "a tiny chibi keychain charm of {subject}, glossy acrylic, held up in front of a soft blurred background",
     "a girl with round glasses", "3d", "3:4", "#FBCFE8,#FDE68A", "\U0001F511"),
    ("elven", "Elven", "{subject} as an elven archer in a sunlit enchanted forest, fantasy film still, golden light",
     "a young woman", "photo", "3:4", "#65A30D,#FACC15", "\U0001F3F9"),
    ("sitcom", "Sitcom", "{subject} as the guest star of a bright 90s TV sitcom, colourful retro kitchen set, title card that says GUEST STAR",
     "a cheerful man in a colourful jacket", "photo", "3:4", "#F59E0B,#10B981", "\U0001F4FA"),
    ("8bit", "8-bit game", "{subject} as characters in a joyful 8-bit pixel-art video game scene, bright pixel sky, a heart above them",
     "two friends and their cat", "illustration", "1:1", "#F97316,#DC2626", "\U0001F47E"),
    ("figurine", "Football figurine", "a collectible action figure of {subject} as a footballer in a clear blister pack, with ball, boots and cones",
     "a smiling young man", "3d", "3:4", "#1E3A8A,#FACC15", "\u26BD"),
    ("landscape", "Landscape", "a wide, moody landscape photograph of {subject}, golden hour, high detail",
     "a rugged coastline at dawn", "photo", "16:9", "#475569,#CBD5E1", "\U0001F3DE\uFE0F"),
    ("statue", "Statue", "{subject} as a white marble statue in a grand classical museum hall, soft daylight",
     "a woman holding a basket of fruit", "photo", "3:4", "#A8A29E,#F5F5F4", "\U0001F3DB\uFE0F"),
    ("underwater", "Underwater", "an underwater portrait of {subject}, sunlight rippling through the water, tiny bubbles, dreamy",
     "a young woman", "photo", "3:4", "#0E7490,#67E8F9", "\U0001F30A"),
    ("room", "Cozy room", "a cozy reading nook for my room: {subject}, warm fairy lights, records on the wall, soft blankets, sunset window",
     "a small bedroom", "photo", "4:3", "#7C2D12,#FDBA74", "\U0001F6CB\uFE0F"),
]


def style_text(style: str) -> str:
    """A style key ("3d") -> its description; any other text is used as it is."""
    s = str(style or "").strip()
    return STYLES[s.lower()] if s and s.lower() in STYLES else s


# Looks Gink picks BY ITSELF from the words ("an x-ray of my camera", "exploded view of a drone") -- no cards to tap.
# X-ray vision: an ILLUSTRATION of what's inside (from what's generally known), never a real scan.
LOOKS = [
    ("xray", "X-ray", "a glowing blue X-ray style cutaway illustration of {subject}, see-through outer shell revealing the inner parts, "
     "components and layers clearly visible, dark background, technical and beautiful, labelled callouts",
     "a vintage film camera", "illustration", "4:3", "#0B1E3F,#38BDF8", "\U0001FA7B"),
    ("exploded", "Exploded view", "a clean exploded-view technical illustration of {subject}, every part floating apart in order along "
     "its axis with thin guide lines and small labels, white background, product-design blueprint",
     "a wireless mouse", "illustration", "4:3", "#334155,#E2E8F0", "\U0001F9E9"),
    ("cutaway", "Cutaway", "a detailed cutaway cross-section of {subject}, one quarter sliced open to show the inside, "
     "museum-quality educational illustration, soft lighting, labelled parts",
     "a modern house", "3d", "16:9", "#7C3AED,#FDE68A", "\U0001F52C"),
]

_LOOK_WORDS = [
    ("exploded", re.compile(r"\b(?:exploded[- ]?view|exploded|taken apart|take (?:it )?apart|every part|all (?:the|its) parts)\b", re.I)),
    ("cutaway", re.compile(r"\b(?:cut[- ]?away|cross[- ]?section|sliced open|cut in half)\b", re.I)),
    ("xray", re.compile(r"\b(?:x[- ]?ray(?:ed)?|see[- ]through|see inside|what'?s inside|inside of|insides)\b", re.I)),
]
# People's bodies are never drawn as "x-rays": a picture like that could be taken for a real medical image.
_BODY = re.compile(r"\b(?:body|bod(?:y|ies)|chest|lungs?|heart|brain|skull|head|spine|bones?|skeleton|ribs?|pelvis|hip|knee|"
                   r"ankle|wrist|hand|foot|feet|arm|leg|tooth|teeth|jaw|abdomen|stomach|belly|kidneys?|liver|womb|uterus|"
                   r"baby|fetus|foetus|patient|person|man|woman|child|boy|girl|my self|myself|(?:of|inside) (?:me|him|her|them|us)|scan|mri|ct|"
                   r"ultrasound|fracture|tumou?r)\b", re.I)
MEDICAL_NOTE = ("clearly an educational illustration, not a real medical image, with the word ILLUSTRATION written small in a corner")


def auto_look(prompt: str):
    """(look id, prompt to use, style key, aspect) when the words ask for an x-ray / exploded / cutaway picture of a
    THING; None otherwise. A person's body gets no x-ray look (see medical_prompt)."""
    text = str(prompt or "")
    if _BODY.search(text):
        return None
    for key, rx in _LOOK_WORDS:
        if rx.search(text):
            subject = rx.sub(" ", text)
            if re.search(r"\bof\b", subject, re.I):          # "make an x-ray image OF the engine" -> "the engine"
                subject = re.split(r"\bof\b", subject, maxsplit=1, flags=re.I)[1]
            subject = re.sub(r"^\W*(?:(?:make|draw|create|generate|show)(?: me)?\W+)?(?:an?\W+(?=image|picture|illustration))?(?:image|picture|illustration)?\W*",
                             "", subject.strip(), flags=re.I)
            subject = " ".join(subject.split()).strip(" ,.-") or None
            p, style, aspect = idea_prompt(key, subject or "")
            return key, p, style, aspect
    return None


def medical_prompt(prompt: str) -> str:
    """An x-ray / scan-like picture of a body: always clearly marked as an illustration."""
    text = str(prompt or "")
    if _BODY.search(text) and any(rx.search(text) for _k, rx in _LOOK_WORDS) or re.search(r"\b(?:mri|ct scan|ultrasound|scan)\b", text, re.I):
        return text + ", " + MEDICAL_NOTE
    return text


def idea(idea_id: str):
    key = str(idea_id or "").strip().lower()
    return next((i for i in IDEAS + LOOKS if i[0] == key), None)


def idea_prompt(idea_id: str, subject: str = "") -> tuple:
    """(prompt, style key, aspect) for an idea, with the subject filled in (or the idea's own example)."""
    it = idea(idea_id)
    if not it:
        raise KeyError(idea_id)
    return it[2].replace("{subject}", (subject or "").strip() or it[3]), it[4], it[5]


def catalog() -> dict:
    """For the API (GET /v1/images/ideas) and the SDKs."""
    return {"styles": [{"id": k, "description": v} for k, v in STYLES.items() if k],
            "ideas": [{"id": i[0], "title": i[1], "prompt": i[2], "example_subject": i[3], "style": i[4], "aspect_ratio": i[5]}
                      for i in IDEAS],
            # picked by themselves from the words ("an x-ray of my camera"); developers can also name them as an idea
            "looks": [{"id": i[0], "title": i[1], "prompt": i[2], "example_subject": i[3], "style": i[4], "aspect_ratio": i[5]}
                      for i in LOOKS]}
