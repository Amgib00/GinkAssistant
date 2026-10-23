"""A stand-in for Chaquopy's `java` module: enough Android to test services/android_voice.py off a phone."""
import asyncio, types

STATE = {"granted": True, "grant_on_request": False, "requested": 0, "recognizers": [], "script": [],
         "tts_spoken": [], "played": [], "available": True}


class Bundle:
    def __init__(self, texts): self.texts = texts
    def getStringArrayList(self, key):
        items = self.texts
        return types.SimpleNamespace(size=lambda: len(items), get=lambda i: items[i])


class Intent:
    def __init__(self, action): self.action, self.extras = action, {}
    def putExtra(self, k, v): self.extras[k] = v


class Recognizer:
    def __init__(self): self.listener, self.intent, self.cancelled = None, None, False; STATE["recognizers"].append(self)
    def setRecognitionListener(self, l): self.listener = l
    def startListening(self, intent):
        self.intent = intent
        step = STATE["script"].pop(0) if STATE["script"] else ("error", 7)
        loop = asyncio.get_event_loop()
        def fire():
            if self.cancelled:
                return
            self.listener.onRmsChanged(4.0)
            kind, value = step
            if kind == "text":
                self.listener.onPartialResults(Bundle([value[: max(1, len(value) // 2)]]))
                self.listener.onResults(Bundle([value, "alternative"]))
            elif kind == "error":
                self.listener.onError(value)
        if step[0] != "hang":
            loop.call_later(0.01, fire)
    def cancel(self): self.cancelled = True
    def destroy(self): pass


class SpeechRecognizer:
    RESULTS_RECOGNITION = "results_recognition"
    @staticmethod
    def isRecognitionAvailable(ctx): return STATE["available"]
    @staticmethod
    def createSpeechRecognizer(ctx): return Recognizer()


class RecognizerIntent:
    ACTION_RECOGNIZE_SPEECH = "RECOGNIZE"; EXTRA_LANGUAGE_MODEL = "lm"; LANGUAGE_MODEL_FREE_FORM = "free"
    EXTRA_PARTIAL_RESULTS = "partial"; EXTRA_MAX_RESULTS = "max"; EXTRA_LANGUAGE = "lang"; EXTRA_PREFER_OFFLINE = "offline"


class Activity:
    def checkSelfPermission(self, p): return 0 if STATE["granted"] else -1
    def requestPermissions(self, perms, code):
        STATE["requested"] += 1
        if STATE["grant_on_request"]:
            STATE["granted"] = True


class TTS:
    SUCCESS, QUEUE_FLUSH = 0, 0
    def __init__(self, ctx, on_init): self.ticks = 0; asyncio.get_event_loop().call_later(0.01, lambda: on_init.onInit(0))
    def setSpeechRate(self, r): self.rate = r
    def speak(self, text, mode, params, uid): STATE["tts_spoken"].append(text); self.ticks = 3
    def isSpeaking(self):
        self.ticks -= 1
        return self.ticks > 0
    def stop(self): self.ticks = 0


class MediaPlayer:
    def __init__(self): self.ticks = 0
    def setDataSource(self, p): STATE["played"].append(open(p, "rb").read())
    def prepare(self): pass
    def start(self): self.ticks = 3
    def isPlaying(self):
        self.ticks -= 1
        return self.ticks > 0
    def stop(self): self.ticks = 0
    def release(self): pass


CLASSES = {"org.beeware.android.MainActivity": types.SimpleNamespace(singletonThis=Activity()),
           "android.content.pm.PackageManager": types.SimpleNamespace(PERMISSION_GRANTED=0),
           "android.speech.SpeechRecognizer": SpeechRecognizer, "android.speech.RecognizerIntent": RecognizerIntent,
           "android.content.Intent": Intent, "android.speech.RecognitionListener": object,
           "android.speech.tts.TextToSpeech": TTS, "android.speech.tts.TextToSpeech$OnInitListener": object,
           "android.media.MediaPlayer": MediaPlayer}

java = types.ModuleType("java")
java.jclass = lambda name: CLASSES[name]
java.dynamic_proxy = lambda iface: object
java.jarray = lambda t: (lambda items: list(items))


def reset(**kw):
    STATE.update(granted=True, grant_on_request=False, requested=0, recognizers=[], script=[], tts_spoken=[],
                 played=[], available=True)
    STATE.update(kw)
