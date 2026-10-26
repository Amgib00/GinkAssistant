"""
Voice on Android, through Chaquopy's Java bridge (`from java import ...`):

  * the microphone permission (asked while the app runs -- the manifest alone isn't enough);
  * listening: android.speech.SpeechRecognizer (the phone's own recognizer), with live
    partial text and the voice level for the orb;
  * speaking: the natural Gink voices from YOUR server (/voice/speak) through MediaPlayer,
    and the phone's built-in voice (android.speech.tts) when offline;
  * "Hey Gink": the recognizer in a loop while Gink is open, looking for the wake phrase.

Android's speech recognizer must be used from the app's main thread. Gink's asyncio loop
runs there on Android, so everything below is called from coroutines on that loop; pause()
may be called from another thread and only schedules work onto the loop.
"""
import asyncio
import base64
import os
import re
import tempfile
import threading
import time

PERMISSION = "android.permission.RECORD_AUDIO"
# "Hey Gink" as phone recognizers actually write it
WAKE_RE = re.compile(r"\b(?:hey|hi|hay|ok|okay|a|he)[\s,.!]*(?:gink|ginc|gynk|jink|ginks|ging|gink's|kink|gin k)\b", re.I)
ERRORS = {1: "network timeout", 2: "no network", 3: "audio problem", 4: "speech service problem", 5: "client problem",
          6: "no speech", 7: "no match", 8: "recognizer busy", 9: "microphone permission is off", 10: "too many requests",
          11: "server disconnected", 12: "language not supported", 13: "language unavailable"}


class VoiceProblem(Exception):
    def __init__(self, message: str = "", code: int = 0):
        super().__init__(message)
        self.code = code                     # the recognizer's error number (0: not from the recognizer)


# Hey Gink must keep listening through everyday hiccups; only these stop it (and it says why)
WAKE_FATAL = (9,)                            # the microphone permission is off
NO_OFFLINE = (12, 13)                        # this language isn't available offline on this phone -> go online
TRANSIENT = (1, 2, 3, 4, 5, 8, 10, 11)       # network, busy, client and server problems: wait and retry


def _java():
    from java import dynamic_proxy, jarray, jclass      # only exists on Android (Chaquopy)
    return jclass, dynamic_proxy, jarray


def _activity():
    jclass, _, _ = _java()
    return jclass("org.beeware.android.MainActivity").singletonThis


# ---------------------------------------------------------------- microphone permission
def has_mic_permission() -> bool:
    jclass, _, _ = _java()
    granted = jclass("android.content.pm.PackageManager").PERMISSION_GRANTED
    return _activity().checkSelfPermission(PERMISSION) == granted


async def ensure_mic_permission(timeout: float = 45.0) -> bool:
    """Ask once if needed, then wait for the person's answer (Android shows its own dialog)."""
    if has_mic_permission():
        return True
    _, _, jarray = _java()
    _activity().requestPermissions(jarray("java.lang.String")([PERMISSION]), 7101)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        await asyncio.sleep(0.4)
        if has_mic_permission():
            return True
    return False


# ---------------------------------------------------------------- listening
def _best(bundle) -> str:
    jclass, _, _ = _java()
    items = bundle.getStringArrayList(jclass("android.speech.SpeechRecognizer").RESULTS_RECOGNITION) if bundle else None
    return str(items.get(0)) if items is not None and items.size() > 0 else ""


class _Session:
    """One recognition: start -> (partial results, levels) -> final text."""

    def __init__(self, language: str = "", prefer_offline: bool = False, on_partial=None, on_level=None):
        self.language, self.prefer_offline = language, prefer_offline
        self.on_partial, self.on_level = on_partial, on_level
        self.recognizer, self.future = None, None

    def _finish(self, text, error):
        if self.future is not None and not self.future.done():
            self.future.set_result((text, error))

    def _listener(self):
        jclass, dynamic_proxy, _ = _java()
        session = self

        class Listener(dynamic_proxy(jclass("android.speech.RecognitionListener"))):
            def onReadyForSpeech(self, params): pass
            def onBeginningOfSpeech(self): pass
            def onBufferReceived(self, buffer): pass
            def onEndOfSpeech(self): pass
            def onEvent(self, event_type, params): pass
            def onSegmentResults(self, results): pass                 # Android 13+
            def onEndOfSegmentedSession(self): pass                   # Android 13+
            def onLanguageDetection(self, results): pass              # Android 14+

            def onRmsChanged(self, rms):
                if session.on_level:
                    session.on_level(max(0.0, min(1.0, (float(rms) + 2.0) / 12.0)))

            def onPartialResults(self, results):
                if session.on_partial:
                    text = _best(results)
                    if text:
                        session.on_partial(text)

            def onResults(self, results):
                session._finish(_best(results), 0)

            def onError(self, error):
                session._finish("", int(error))

        return Listener()

    async def run(self, timeout: float = 20.0) -> str:
        jclass, _, _ = _java()
        SR, RI = jclass("android.speech.SpeechRecognizer"), jclass("android.speech.RecognizerIntent")
        activity = _activity()
        if not SR.isRecognitionAvailable(activity):
            raise VoiceProblem("this phone has no speech recognition service (install or update Google app)", code=-1)
        self.future = asyncio.get_running_loop().create_future()
        self.recognizer = SR.createSpeechRecognizer(activity)
        self.recognizer.setRecognitionListener(self._listener())
        intent = jclass("android.content.Intent")(RI.ACTION_RECOGNIZE_SPEECH)
        intent.putExtra(RI.EXTRA_LANGUAGE_MODEL, RI.LANGUAGE_MODEL_FREE_FORM)
        intent.putExtra(RI.EXTRA_PARTIAL_RESULTS, True)
        intent.putExtra(RI.EXTRA_MAX_RESULTS, 3)
        if self.language and self.language != "auto":
            intent.putExtra(RI.EXTRA_LANGUAGE, self.language)
        if self.prefer_offline:
            intent.putExtra(RI.EXTRA_PREFER_OFFLINE, True)
        self.recognizer.startListening(intent)
        try:
            text, error = await asyncio.wait_for(self.future, timeout)
        except asyncio.TimeoutError:
            text, error = "", 6
        finally:
            self.close()
        if error in (6, 7):                                   # silence / nothing understood
            return ""
        if error == 9:
            raise VoiceProblem("the microphone permission is off (Settings > Apps > Gink > Permissions)", code=9)
        if error:
            raise VoiceProblem(ERRORS.get(error, f"speech error {error}"), code=error)
        return text.strip()

    def close(self):
        rec, self.recognizer = self.recognizer, None
        if rec is not None:
            try:
                rec.cancel()
                rec.destroy()
            except Exception:
                pass
        self._finish("", 6)


async def listen(language: str = "", on_amplitude=None, on_partial=None) -> str:
    if not await ensure_mic_permission():
        raise VoiceProblem("Gink needs the microphone \u2014 allow it in Settings > Apps > Gink > Permissions")
    return await _Session(language, on_partial=on_partial, on_level=on_amplitude).run()


# ---------------------------------------------------------------- speaking
_player = {"media": None, "tts": None, "tts_ready": None}


async def _natural_wav(text: str, voice_key: str, base_url: str, token: str, speed: str = "normal"):
    """The natural Gink voice from your server -> a .wav file, or None (then the phone's voice)."""
    if not (base_url and token):
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(base_url.rstrip("/") + "/voice/speak", headers={"Authorization": f"Bearer {token}"},
                             json={"text": text, "persona": voice_key, "speed": speed})
        if r.status_code != 200:
            return None
        fd, path = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(fd, "wb") as f:
            f.write(base64.b64decode(r.json()["audio_b64"]))
        return path
    except Exception:
        return None


async def _play_file(path: str, on_amplitude=None) -> None:
    jclass, _, _ = _java()
    mp = jclass("android.media.MediaPlayer")()
    _player["media"] = mp
    try:
        mp.setDataSource(path)
        mp.prepare()
        mp.start()
        pulse = 0
        while _player["media"] is mp and mp.isPlaying():
            pulse += 1
            if on_amplitude:
                on_amplitude(0.35 + 0.25 * ((pulse % 4) / 3))         # the orb breathes while Gink talks
            await asyncio.sleep(0.12)
    finally:
        if _player["media"] is mp:
            _player["media"] = None
        try:
            mp.release()
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            pass


async def _phone_voice(text: str, rate: float = 1.0, on_amplitude=None) -> None:
    """The phone's own text-to-speech (works offline)."""
    jclass, dynamic_proxy, _ = _java()
    TTS = jclass("android.speech.tts.TextToSpeech")
    if _player["tts"] is None:
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        class OnInit(dynamic_proxy(jclass("android.speech.tts.TextToSpeech$OnInitListener"))):
            def onInit(self, status):
                if not ready.done():
                    ready.set_result(int(status))

        _player["tts"] = TTS(_activity(), OnInit())
        try:
            status = await asyncio.wait_for(ready, 10)
        except asyncio.TimeoutError:
            status = -1
        if status != TTS.SUCCESS:
            _player["tts"] = None
            raise VoiceProblem("the phone's text-to-speech isn't available")
    tts = _player["tts"]
    tts.setSpeechRate(float(rate))
    tts.speak(text, TTS.QUEUE_FLUSH, None, f"gink-{time.monotonic()}")
    started = time.monotonic()
    while time.monotonic() - started < 1.5 and not tts.isSpeaking():   # wait for it to start
        await asyncio.sleep(0.05)
    while tts.isSpeaking():
        if on_amplitude:
            on_amplitude(0.45)
        await asyncio.sleep(0.12)


async def speak(text: str, voice_key: str, base_url: str = "", token: str = "", speed: str = "normal",
                on_amplitude=None) -> str:
    """Speak `text`. Returns which voice was used: "natural" or "phone"."""
    text = (text or "").strip()
    if not text:
        return ""
    path = await _natural_wav(text, voice_key, base_url, token, speed)
    if path:
        await _play_file(path, on_amplitude)
        return "natural"
    await _phone_voice(text, {"slow": 0.85, "fast": 1.2}.get(speed, 1.0), on_amplitude)
    return "phone"


def stop_speaking() -> None:
    mp, _player["media"] = _player["media"], None
    if mp is not None:
        try:
            mp.stop()
        except Exception:
            pass
    if _player["tts"] is not None:
        try:
            _player["tts"].stop()
        except Exception:
            pass


# ---------------------------------------------------------------- "Hey Gink"
class _EngineInfo:                      # what Settings shows (same shape as the desktop engines)
    name = "Android speech recognizer"
    last_heard = ""


class AndroidWakeListener:
    """Listens for "Hey Gink" while Gink is open, with the phone's recognizer (offline when the
    phone supports it). Same interface as wake_word.WakeWordListener so main_screen can use it."""

    def __init__(self, on_wake, language: str = "", pause_between: float = 0.4):
        self.on_wake, self.language, self.pause_between = on_wake, language, pause_between
        self.engine, self.running, self.error, self.detections = _EngineInfo(), False, "", 0
        self.heard_after_wake = ""             # "hey gink what's the weather" -> "what's the weather"
        self._paused, self._task, self._session = False, None, None
        self.prefer_offline = True               # switched off for good if this phone has no offline language
        self._released = threading.Event()
        self._released.set()
        self._loop = None

    def start(self):
        if self.running:
            return
        self.running, self.error = True, ""
        self._loop = asyncio.get_event_loop()
        self._task = asyncio.ensure_future(self._run())

    def stop(self):
        self.running = False
        self._stop_session()
        if self._task is not None:
            self._task.cancel()

    def pause(self, wait: bool = False):
        """Let go of the microphone (Gink is about to listen itself). Safe from any thread."""
        self._paused = True
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_session)
            except RuntimeError:
                pass
        if wait and threading.current_thread() is not threading.main_thread():
            self._released.wait(3)

    def resume(self):
        self._paused = False

    def _stop_session(self):
        s, self._session = self._session, None
        if s is not None:
            s.close()
        self._released.set()

    async def _run(self):
        failures = 0
        if not await ensure_mic_permission():
            self.error, self.running = "the microphone permission is off", False
            return
        while self.running:
            if self._paused:
                await asyncio.sleep(0.3)
                continue
            self._released.clear()
            self._session = _Session(self.language, prefer_offline=self.prefer_offline)
            try:
                text = await self._session.run(timeout=12)
                failures = 0
            except VoiceProblem as exc:
                text = ""
                code = getattr(exc, "code", 0)
                if code in WAKE_FATAL or code == -1:     # no permission / no speech service: stop and say why
                    self.error, self.running = str(exc), False
                    break
                if code in NO_OFFLINE and self.prefer_offline:
                    self.prefer_offline = False          # no offline language pack here: use online recognition
                    continue
                failures += 1                            # busy, network...: wait a bit longer each time, keep listening
                self.error = str(exc)
                await asyncio.sleep(min(30, 1 + 2 * failures))
                continue
            except asyncio.CancelledError:
                break
            finally:
                self._session = None
                self._released.set()
            self.error = "" if failures == 0 else self.error
            if text:
                self.engine.last_heard = text
                m = WAKE_RE.search(text)
                if m and not self._paused:
                    self.detections += 1
                    self.heard_after_wake = text[m.end():].strip(" ,.!?")
                    self.on_wake()
            await asyncio.sleep(self.pause_between)
