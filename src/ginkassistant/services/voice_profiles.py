"""
Voices for voice conversations and read-aloud (Settings -> Voice and the
voice picker): a name, a one-line personality, orb colours, and the
Microsoft neural voice that speaks it (through edge-tts / the server later).

`key` values are what prefs store; the four original keys
("Female (Jenny)" ...) are kept so earlier choices still work.

SPEECH_LANGS: what the speech recognizer listens for. Google's free
recognizer needs ONE language (it can't auto-detect), so the user picks.
"""

VOICE_PROFILES = [
    {"key": "Female (Jenny)", "name": "Jenny", "desc": "Warm and friendly", "id": "en-US-JennyNeural",
     "colors": ["#7B61FF", "#C9C2FF", "#EEF0FF"]},
    {"key": "Male (Guy)", "name": "Guy", "desc": "Steady and clear", "id": "en-US-GuyNeural",
     "colors": ["#2F7DE1", "#9CC6F5", "#EAF3FD"]},
    {"key": "Female (Aria)", "name": "Aria", "desc": "Bright and expressive", "id": "en-US-AriaNeural",
     "colors": ["#E0629A", "#F7B6D2", "#FDEEF5"]},
    {"key": "Male (Christopher)", "name": "Christopher", "desc": "Composed and direct", "id": "en-US-ChristopherNeural",
     "colors": ["#5A4FCF", "#B3ADF2", "#F1F0FD"]},
    {"key": "sonia", "name": "Sonia", "desc": "Calm and articulate \u00b7 British", "id": "en-GB-SoniaNeural",
     "colors": ["#3F8E8C", "#A6D8D3", "#ECF8F6"]},
    {"key": "ryan", "name": "Ryan", "desc": "Relaxed and easygoing \u00b7 British", "id": "en-GB-RyanNeural",
     "colors": ["#6B7A8F", "#C2CCD8", "#F1F4F8"]},
    {"key": "ezinne", "name": "Ezinne", "desc": "Cheerful and grounded \u00b7 Nigerian", "id": "en-NG-EzinneNeural",
     "colors": ["#3F8212", "#A8F03C", "#F1FBE3"]},
    {"key": "abeo", "name": "Abeo", "desc": "Confident and calm \u00b7 Nigerian", "id": "en-NG-AbeoNeural",
     "colors": ["#C26A12", "#F5C27D", "#FDF3E6"]},
    {"key": "asilia", "name": "Asilia", "desc": "Gentle and patient \u00b7 Kenyan", "id": "en-KE-AsiliaNeural",
     "colors": ["#D9483B", "#F4AFA8", "#FDEFED"]},
    {"key": "denise", "name": "Denise", "desc": "Douce et pos\u00e9e \u00b7 Fran\u00e7ais", "id": "fr-FR-DeniseNeural",
     "colors": ["#2B65C9", "#F0A9B5", "#F4F2FB"]},
    {"key": "henri", "name": "Henri", "desc": "Clair et chaleureux \u00b7 Fran\u00e7ais", "id": "fr-FR-HenriNeural",
     "colors": ["#1E4FA0", "#A9C1EE", "#EEF3FC"]},
]
BY_KEY = {v["key"]: v for v in VOICE_PROFILES}
FEMALE_KEYS = {"Female (Jenny)", "Female (Aria)", "sonia", "ezinne", "asilia", "denise"}


def local_voice_wish(key: str):
    """(gender, preferred locales) for picking the computer's own voice when the
    natural voice isn't available. No Nigerian/Kenyan voices ship with macOS,
    so those use British English, then American."""
    v = BY_KEY.get(key, BY_KEY[DEFAULT_VOICE])
    gender = "female" if key in FEMALE_KEYS else "male"
    lang = v["id"][:5].replace("-", "_")               # en_US, en_GB, en_NG, fr_FR ...
    if lang in ("en_NG", "en_KE"):
        locales = ["en_GB", "en_ZA", "en_US"]
    elif lang.startswith("fr"):
        locales = ["fr_FR", "fr_CA"]
    else:
        locales = [lang, "en_US", "en_GB"]
    return gender, locales
DEFAULT_VOICE = "Female (Jenny)"


def sample_text(key: str) -> str:
    v = BY_KEY.get(key, BY_KEY[DEFAULT_VOICE])
    if v["id"].startswith("fr-"):
        return f"Bonjour, je suis {v['name']}. Je suis l\u00e0 pour vous aider."
    return f"Hi, I'm {v['name']}. Just say what's on your mind."


SPEECH_LANGS = [
    ("auto", "Automatic (any language)"),
    ("en-US", "English (United States)"), ("en-GB", "English (United Kingdom)"), ("en-NG", "English (Nigeria)"),
    ("en-GH", "English (Ghana)"), ("en-KE", "English (Kenya)"), ("en-ZA", "English (South Africa)"),
    ("fr-FR", "Fran\u00e7ais (France)"), ("fr-SN", "Fran\u00e7ais (S\u00e9n\u00e9gal)"), ("fr-CI", "Fran\u00e7ais (C\u00f4te d'Ivoire)"),
    ("fr-CA", "Fran\u00e7ais (Canada)"), ("ar-SA", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629"), ("pt-BR", "Portugu\u00eas (Brasil)"),
    ("pt-PT", "Portugu\u00eas (Portugal)"), ("es-ES", "Espa\u00f1ol (Espa\u00f1a)"), ("es-MX", "Espa\u00f1ol (M\u00e9xico)"),
    ("sw-KE", "Kiswahili"), ("zu-ZA", "isiZulu"), ("am-ET", "\u12a0\u121b\u122d\u129b"), ("de-DE", "Deutsch"),
    ("it-IT", "Italiano"), ("nl-NL", "Nederlands"), ("tr-TR", "T\u00fcrk\u00e7e"), ("ru-RU", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439"),
    ("hi-IN", "\u0939\u093f\u0928\u094d\u0926\u0940"), ("zh-CN", "\u4e2d\u6587\uff08\u666e\u901a\u8bdd\uff09"), ("ja-JP", "\u65e5\u672c\u8a9e"),
    ("ko-KR", "\ud55c\uad6d\uc5b4"),
]
SPEECH_LANG_CODES = {c for c, _ in SPEECH_LANGS}
