"""
Reply languages for Settings -> General -> Language (the searchable picker).
(code, native name, English name, experimental?)  -- "experimental" marks
languages where today's AI models are noticeably weaker, so users aren't
misled about answer quality.
"""

LANGUAGES = [
    ("auto", "Same as my message", "Automatic", False),
    ("af", "Afrikaans", "Afrikaans", False), ("sq", "Shqip", "Albanian", False), ("am", "\u12a0\u121b\u122d\u129b", "Amharic", False),
    ("ar", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629", "Arabic", False), ("hy", "\u0540\u0561\u0575\u0565\u0580\u0565\u0576", "Armenian", False),
    ("as", "\u0985\u09b8\u09ae\u09c0\u09af\u09bc\u09be", "Assamese", True), ("az", "Az\u0259rbaycan", "Azerbaijani", False),
    ("bm", "Bamanankan", "Bambara", True), ("eu", "Euskara", "Basque", False), ("be", "\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u043a\u0430\u044f", "Belarusian", False),
    ("bn", "\u09ac\u09be\u0982\u09b2\u09be", "Bangla", False), ("bho", "\u092d\u094b\u091c\u092a\u0941\u0930\u0940", "Bhojpuri", True),
    ("bs", "Bosanski", "Bosnian", False), ("bg", "\u0411\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438", "Bulgarian", False),
    ("my", "\u1019\u103c\u1014\u103a\u1019\u102c", "Burmese", True), ("ca", "Catal\u00e0", "Catalan", False), ("ceb", "Cebuano", "Cebuano", True),
    ("zh-Hans", "\u4e2d\u6587\uff08\u7b80\u4f53\uff09", "Chinese (Simplified)", False), ("zh-Hant", "\u4e2d\u6587\uff08\u7e41\u9ad4\uff09", "Chinese (Traditional)", False),
    ("hr", "Hrvatski", "Croatian", False), ("cs", "\u010ce\u0161tina", "Czech", False), ("da", "Dansk", "Danish", False),
    ("nl", "Nederlands", "Dutch", False), ("en-US", "English (United States)", "English (United States)", False),
    ("en-GB", "English (United Kingdom)", "English (United Kingdom)", False), ("eo", "Esperanto", "Esperanto", False),
    ("et", "Eesti", "Estonian", False), ("ee", "E\u028begbe", "Ewe", True), ("fil", "Filipino", "Filipino", False),
    ("fi", "Suomi", "Finnish", False), ("fr", "Fran\u00e7ais (France)", "French (France)", False),
    ("fr-CA", "Fran\u00e7ais (Canada)", "French (Canada)", False), ("ff", "Fulfulde", "Fula", True), ("gl", "Galego", "Galician", False),
    ("ka", "\u10e5\u10d0\u10e0\u10d7\u10e3\u10da\u10d8", "Georgian", False), ("de", "Deutsch", "German", False),
    ("el", "\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac", "Greek", False), ("gn", "Ava\u00f1e'\u1ebd", "Guarani", True),
    ("gu", "\u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0", "Gujarati", False), ("ht", "Krey\u00f2l ayisyen", "Haitian Creole", True),
    ("ha", "Hausa", "Hausa", False), ("haw", "\u02bb\u014clelo Hawai\u02bbi", "Hawaiian", True), ("he", "\u05e2\u05d1\u05e8\u05d9\u05ea", "Hebrew", False),
    ("hi", "\u0939\u093f\u0928\u094d\u0926\u0940", "Hindi", False), ("hu", "Magyar", "Hungarian", False), ("is", "\u00cdslenska", "Icelandic", False),
    ("ig", "As\u1ee5s\u1ee5 Igbo", "Igbo", True), ("id", "Bahasa Indonesia", "Indonesian", False), ("ga", "Gaeilge", "Irish", False),
    ("it", "Italiano", "Italian", False), ("ja", "\u65e5\u672c\u8a9e", "Japanese", False), ("jv", "Basa Jawa", "Javanese", True),
    ("kn", "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1", "Kannada", False), ("kk", "\u049a\u0430\u0437\u0430\u049b", "Kazakh", False),
    ("km", "\u1781\u17d2\u1798\u17c2\u179a", "Khmer", True), ("rw", "Kinyarwanda", "Kinyarwanda", True), ("ko", "\ud55c\uad6d\uc5b4", "Korean", False),
    ("kri", "Krio", "Krio", True), ("ku", "Kurd\u00ee", "Kurdish", True), ("ky", "\u041a\u044b\u0440\u0433\u044b\u0437\u0447\u0430", "Kyrgyz", True),
    ("lo", "\u0ea5\u0eb2\u0ea7", "Lao", True), ("la", "Latina", "Latin", False), ("lv", "Latvie\u0161u", "Latvian", False),
    ("ln", "Ling\u00e1la", "Lingala", True), ("lt", "Lietuvi\u0173", "Lithuanian", False), ("lb", "L\u00ebtzebuergesch", "Luxembourgish", True),
    ("mk", "\u041c\u0430\u043a\u0435\u0434\u043e\u043d\u0441\u043a\u0438", "Macedonian", False), ("mg", "Malagasy", "Malagasy", True),
    ("ms", "Bahasa Melayu", "Malay", False), ("ml", "\u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02", "Malayalam", False), ("mt", "Malti", "Maltese", False),
    ("mnk", "Mandinka", "Mandinka", True), ("mi", "Te Reo M\u0101ori", "M\u0101ori", True), ("mr", "\u092e\u0930\u093e\u0920\u0940", "Marathi", False),
    ("mn", "\u041c\u043e\u043d\u0433\u043e\u043b", "Mongolian", True), ("ne", "\u0928\u0947\u092a\u093e\u0932\u0940", "Nepali", False),
    ("no", "Norsk", "Norwegian", False), ("ny", "Chichewa", "Nyanja (Chichewa)", True), ("or", "\u0b13\u0b21\u0b3c\u0b3f\u0b06", "Odia", True),
    ("om", "Afaan Oromoo", "Oromo", True), ("ps", "\u067e\u069a\u062a\u0648", "Pashto", True), ("fa", "\u0641\u0627\u0631\u0633\u06cc", "Persian", False),
    ("pl", "Polski", "Polish", False), ("pt-BR", "Portugu\u00eas (Brasil)", "Portuguese (Brazil)", False),
    ("pt-PT", "Portugu\u00eas (Portugal)", "Portuguese (Portugal)", False), ("pa", "\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40", "Punjabi", False),
    ("qu", "Runasimi", "Quechua", True), ("ro", "Rom\u00e2n\u0103", "Romanian", False), ("ru", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439", "Russian", False),
    ("sm", "Gagana Samoa", "Samoan", True), ("sr", "\u0421\u0440\u043f\u0441\u043a\u0438", "Serbian", False), ("st", "Sesotho", "Sesotho", True),
    ("sn", "chiShona", "Shona", True), ("sd", "\u0633\u0646\u068c\u064a", "Sindhi", True), ("si", "\u0dc3\u0dd2\u0d82\u0dc4\u0dbd", "Sinhala", True),
    ("sk", "Sloven\u010dina", "Slovak", False), ("sl", "Sloven\u0161\u010dina", "Slovenian", False), ("so", "Soomaali", "Somali", True),
    ("es", "Espa\u00f1ol (Espa\u00f1a)", "Spanish (Spain)", False), ("es-419", "Espa\u00f1ol (Latinoam\u00e9rica)", "Spanish (Latin America)", False),
    ("su", "Basa Sunda", "Sundanese", True), ("sw", "Kiswahili", "Swahili", False), ("sv", "Svenska", "Swedish", False),
    ("tg", "\u0422\u043e\u04b7\u0438\u043a\u04e3", "Tajik", True), ("ta", "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd", "Tamil", False),
    ("tt", "\u0422\u0430\u0442\u0430\u0440\u0447\u0430", "Tatar", True), ("te", "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41", "Telugu", False),
    ("th", "\u0e44\u0e17\u0e22", "Thai", False), ("ti", "\u1275\u130d\u122d\u129b", "Tigrinya", True), ("tn", "Setswana", "Tswana", True),
    ("tr", "T\u00fcrk\u00e7e", "Turkish", False), ("tk", "T\u00fcrkmen", "Turkmen", True), ("tw", "Twi", "Twi (Akan)", True),
    ("uk", "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430", "Ukrainian", False), ("ur", "\u0627\u0631\u062f\u0648", "Urdu", False),
    ("ug", "\u0626\u06c7\u064a\u063a\u06c7\u0631\u0686\u06d5", "Uyghur", True), ("uz", "O\u02bbzbek", "Uzbek", False),
    ("vi", "Ti\u1ebfng Vi\u1ec7t", "Vietnamese", False), ("cy", "Cymraeg", "Welsh", False), ("wo", "Wolof", "Wolof", True),
    ("xh", "isiXhosa", "Xhosa", True), ("yi", "\u05d9\u05d9\u05b4\u05d3\u05d9\u05e9", "Yiddish", True), ("yo", "Yor\u00f9b\u00e1", "Yoruba", True),
    ("zu", "isiZulu", "Zulu", True),
]
BY_CODE = {c: (native, english, exp) for c, native, english, exp in LANGUAGES}
# older saved values from the first language list
ALIASES = {"en": "en-US", "pt": "pt-BR", "zh": "zh-Hans"}


def normalise(code: str) -> str:
    code = ALIASES.get(code, code)
    return code if code in BY_CODE else "auto"


def reply_note(code: str) -> str:
    code = normalise(code)
    if code == "auto":
        return ("\n\nReply in the same language the user writes in (for example French to French, Wolof to Wolof, "
                "Pidgin to Pidgin). If they mix languages, use the main one. Keep names and quoted text as they are.")
    native, english, _ = BY_CODE[code]
    return f"\n\nAlways reply in {english} ({native}), whatever language the user writes in."


def label(code: str) -> str:
    native, english, exp = BY_CODE[normalise(code)]
    return native + (" \u00b7 experimental" if exp else "")
