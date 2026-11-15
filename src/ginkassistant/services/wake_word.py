"""
"Hey Gink" -- a wake word, like "Hey Siri".

PRIVACY FIRST: spotting the wake word happens entirely on this computer.
Nothing is sent anywhere until "Hey Gink" is heard; only then does Gink
listen to the request (which, like typing, goes to the speech service).
It's OFF until the user switches it on (Settings -> Voice -> Hey Gink).

Engines (best available is used):
  * Picovoice Porcupine -- most accurate, very light on battery. Needs your own
    "Hey Gink" keyword file from console.picovoice.ai and an AccessKey:
      PICOVOICE_ACCESS_KEY=...   GINK_WAKEWORD_FILE=/path/Hey-Gink_en_mac_v4.ppn
    (Free for personal use; commercial use needs a Picovoice licence.)
  * Vosk -- free, open source (Apache-2.0), offline. Uses the small English
    model (~40 MB, downloaded once with permission). "Gink" isn't in its
    dictionary, so it listens for "hey gink" plus close sound-alikes.

The listener runs in a background thread, reads 16 kHz mono audio, and
releases the microphone whenever Gink needs it (pause()/resume()), so it
never hears Gink's own voice or fights over the mic.
"""

import json
import os
import re
import shutil
import struct
import threading
import time
import zipfile
from typing import Callable, Optional

# ---- How the offline listener hears "Hey Gink" (measured with tools/wake_bench, not guessed) -------------------
# The free model has a fixed dictionary and neither "gink" nor "jink" is in it (a word it doesn't know is silently
# DROPPED from a phrase: "hey jink" would become just "hey"). So the listener is given single words it does know:
#   LEADS      hey / hi / okay
#   NEAR_GINK  what "Gink" (hard g) is heard as        NEAR_JINK  what "Jink" (soft g) is heard as
#   DECOYS     everyday words, so ordinary talk has somewhere to go instead of being squeezed into "hey king"
#              ("I think..." was heard as "hi king"; "hey kids", "okay thanks" too): false wakes fell from 29% to 3-7%
# Wake = a lead followed directly by a near word. With "Also wake on just Gink" on: a rare near word first
# (ALONE_FIRST), or ALONE_EXACT as the whole thing said ("Gink." then a pause).
# Before changing ANY list, run tools/wake_bench: one decoy ("getting", when it wasn't a near word) took the
# listener from 95% to 26%.
LEADS = ("hey", "hi", "okay")
NEAR_GINK = ("king", "kink", "ginkgo", "getting")
NEAR_JINK = ("jinx", "jinks", "jing", "jin", "jinn", "jank", "gin", "genk")
ALONE_FIRST = ("kink", "ginkgo", "jing", "jank", "jinx", "jinks", "jinn", "genk")      # never "king", "gin", "getting"
ALONE_EXACT = ("getting",)
DECOYS = ("i", "think", "there", "guys", "kids", "can", "look", "what", "come", "siri", "mum", "kim", "jim", "let's",
          "thanks", "google", "you", "everyone", "so", "well", "it", "we", "how", "is", "the", "a", "and", "this", "that")
# engines that know any word (Android, browsers, a future model) may also hear the name itself
MATCH_WORDS = ("gink", "jink") + NEAR_GINK + NEAR_JINK
WAKE_PHRASES = [f"{lead} {w}" for lead in LEADS for w in NEAR_GINK + NEAR_JINK] + list(ALONE_FIRST)   # (for reference/tests)


def grammar_words(knows=None) -> list:
    """The words the offline listener may answer with, + "[unk]" (anything else). `knows(word)` says whether the
    model's dictionary has a word (VoskEngine passes the model's own lookup): unknown ones are left out."""
    words = []
    for w in LEADS + NEAR_GINK + NEAR_JINK + DECOYS:
        if w not in words and (knows is None or knows(w)):
            words.append(w)
    return words + ["[unk]"]


MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_MB = 40
RATE = 16000


# ---------------------------------------------------------------- model files
def model_path(base_dir) -> str:
    return os.path.join(str(base_dir), "models", MODEL_NAME)


def model_ready(base_dir) -> bool:
    p = model_path(base_dir)
    return os.path.isdir(os.path.join(p, "am")) or os.path.isfile(os.path.join(p, "conf", "model.conf"))


async def download_model(base_dir, on_progress: Optional[Callable[[float], None]] = None) -> str:
    """Download + unpack the small Vosk model once. Returns the model folder."""
    import httpx
    models = os.path.join(str(base_dir), "models")
    os.makedirs(models, exist_ok=True)
    tmp = os.path.join(models, MODEL_NAME + ".zip.part")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as client:
        async with client.stream("GET", MODEL_URL) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            got = 0
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
                    got += len(chunk)
                    if on_progress and total:
                        on_progress(got / total)
    try:
        with zipfile.ZipFile(tmp) as z:
            z.extractall(models)
    finally:
        os.remove(tmp)
    if not model_ready(base_dir):
        shutil.rmtree(model_path(base_dir), ignore_errors=True)
        raise RuntimeError("The voice model download looks incomplete.")
    return model_path(base_dir)


SHORT = {"on": True}          # also wake on just "Gink" (Settings > Voice; main_screen sets it from prefs)


def matches(text: str, final: bool = True) -> bool:
    """Does what was heard contain the wake word? `final` = the listener finished the utterance (a pause followed);
    while it's still listening (partial text) the name alone needs a second word after it, so a word that is still
    changing doesn't wake Gink."""
    words = re.sub(r"[^a-z' ]", " ", (text or "").lower()).split()        # "[unk]" -> "unk": it breaks "hey ... king"
    for a, b in zip(words, words[1:]):
        if a in LEADS + ("ok",) and b in MATCH_WORDS:
            return True
    if not SHORT["on"] or not words:
        return False
    if words[0] in ("gink", "jink") + ALONE_FIRST and (final or len(words) > 1):      # not "king": too common
        return True
    return final and len(words) == 1 and words[0] in ALONE_EXACT


# ---------------------------------------------------------------- engines
class VoskEngine:
    name = "Vosk (offline, free)"

    def __init__(self, path: str):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        self._model = Model(path)
        # a small set of single words the model knows (+ "anything else"): fast, and ordinary talk doesn't wake it
        knows = lambda w: self._model.vosk_model_find_word(w) >= 0        # noqa: E731
        self.words = grammar_words(knows)
        self._rec = KaldiRecognizer(self._model, RATE, json.dumps(self.words))
        self.frame = 4000                       # samples per read (0.25 s)
        self.last_heard = ""                    # shown in Settings -> Voice -> Hey Gink (helps tuning)

    def process(self, pcm: bytes) -> bool:
        final = bool(self._rec.AcceptWaveform(pcm))
        if final:
            text = json.loads(self._rec.Result()).get("text", "")
            if text and text != "[unk]":
                self.last_heard = text
        else:
            text = json.loads(self._rec.PartialResult()).get("partial", "")
        if matches(text, final):
            self.last_heard = text
            self._rec.Reset()
            return True
        return False


class PorcupineEngine:
    name = "Picovoice Porcupine"

    def __init__(self, access_key: str, keyword_file: str, sensitivity: float = 0.6):
        import pvporcupine
        self._h = pvporcupine.create(access_key=access_key, keyword_paths=[keyword_file], sensitivities=[sensitivity])
        self.frame = self._h.frame_length

    def process(self, pcm: bytes) -> bool:
        samples = struct.unpack_from(f"{self.frame}h", pcm)
        return self._h.process(samples) >= 0


def best_engine(base_dir):
    """-> (engine, "") or (None, reason in plain words)."""
    key, kw = os.environ.get("PICOVOICE_ACCESS_KEY", "").strip(), os.environ.get("GINK_WAKEWORD_FILE", "").strip()
    if key and kw and os.path.isfile(kw):
        try:
            return PorcupineEngine(key, kw), ""
        except Exception as exc:
            reason = f"Porcupine couldn't start ({exc.__class__.__name__}); "
    else:
        reason = ""
    try:
        import vosk  # noqa: F401
    except ImportError:
        return None, reason + "the offline speech package isn't installed (pip install vosk)"
    if not model_ready(base_dir):
        return None, reason + f"the offline voice model isn't downloaded yet ({MODEL_MB} MB)"
    try:
        return VoskEngine(model_path(base_dir)), ""
    except Exception as exc:
        return None, reason + f"the offline voice model couldn't load ({exc.__class__.__name__})"


# ---------------------------------------------------------------- the listener
class _PyAudioMic:
    """ONE PyAudio instance for the listener's whole life; only the input stream
    opens and closes. (Creating/terminating PyAudio over and over, or opening a
    second input stream before the first is closed, makes macOS CoreAudio fail with
    "PaMacCore (AUHAL) err=-10863: cannot do in current context".)"""

    def __init__(self):
        self._pa = None

    def __call__(self, frame: int):
        import pyaudio
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=frame)

        class S:
            def read(self):
                return stream.read(frame, exception_on_overflow=False)

            def close(self):
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
        return S()

    def terminate(self):
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None


class _SoundDeviceMic:
    """The same microphone through sounddevice, which ships its own PortAudio on macOS and Windows:
    Hey Gink keeps working when PyAudio isn't installed (it has no ready-made Mac builds) or fails to open."""
    name = "sounddevice"

    def __call__(self, frame: int):
        import sounddevice as sd
        stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=frame)
        stream.start()

        class S:
            def read(self):
                data, _overflowed = stream.read(frame)
                return bytes(data)

            def close(self):
                try:
                    stream.stop()
                finally:
                    stream.close()
        return S()

    def terminate(self):
        pass


class _AnyMic:
    """PyAudio first (what the builds verify), sounddevice if PyAudio is missing or can't open the microphone.
    Remembers which one worked; the error of the last try is kept for the status line."""

    def __init__(self, pyaudio_mic=None, sounddevice_mic=None):
        self._mics = [pyaudio_mic or _PyAudioMic(), sounddevice_mic or _SoundDeviceMic()]
        self.using = ""

    def __call__(self, frame: int):
        errors = []
        for mic in list(self._mics):
            try:
                stream = mic(frame)
            except Exception as exc:                 # ImportError (not installed) or a device error
                errors.append(f"{type(mic).__name__.strip('_')}: {type(exc).__name__}: {exc}")
                continue
            if mic is not self._mics[0]:             # this one works: try it first from now on
                self._mics.remove(mic); self._mics.insert(0, mic)
            self.using = type(mic).__name__.strip("_")
            return stream
        raise RuntimeError("no microphone could be opened (" + "; ".join(errors)[:300] + ")")

    def terminate(self):
        for mic in self._mics:
            try:
                mic.terminate()
            except Exception:
                pass


class WakeWordListener:
    """Background thread: mic -> engine -> on_wake().

    The microphone is RELEASED before anyone else uses it: on a detection the
    stream is closed first and only then on_wake() runs, and pause(wait=True)
    blocks until the stream is really closed. Two input streams at once is what
    caused the AUHAL -10863 errors."""

    def __init__(self, engine, on_wake: Callable[[], None], open_stream=None, cooldown: float = 2.0):
        self.engine, self.on_wake = engine, on_wake
        self._own_mic = open_stream is None
        self.open_stream = open_stream or _AnyMic()       # PyAudio, or sounddevice when PyAudio can't
        self.cooldown = cooldown
        self._run = threading.Event()
        self._paused = threading.Event()
        self._released = threading.Event()
        self._released.set()                    # no stream open yet
        self._thread: Optional[threading.Thread] = None
        self.error = ""
        self.level = 0                          # loudest sound in the last quarter second, % of full scale
        self._silent_since = None
        self.detections = 0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:
            return
        self._run.set()
        self._thread = threading.Thread(target=self._loop, name="gink-wake-word", daemon=True)
        self._thread.start()

    def stop(self):
        self._run.clear()

    def pause(self, wait: bool = False, timeout: float = 1.5) -> bool:
        """Stop listening. wait=True: return only once the mic is really released."""
        self._paused.set()
        return self._released.wait(timeout) if wait else True

    def resume(self):
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def mic_released(self) -> bool:
        return self._released.is_set()

    # A microphone that is blocked (macOS without the Microphone permission) doesn't fail: it sends perfect
    # silence, and Hey Gink would wait forever with a green light. So the listener watches the level.
    SILENT_AFTER = 6.0

    def _note_level(self, pcm: bytes) -> None:
        import array
        a = array.array("h")
        a.frombytes(pcm[:len(pcm) // 2 * 2])
        peak = max(max(a, default=0), -min(a, default=0))
        self.level = round(100 * peak / 32768)
        if peak > 2:                                         # any real microphone has more noise than this
            self._silent_since = None
        elif self._silent_since is None:
            self._silent_since = time.time()

    @property
    def silent(self) -> bool:
        """The microphone has sent nothing but digital silence for a while (blocked, muted or the wrong device)."""
        since = getattr(self, "_silent_since", None)
        return since is not None and time.time() - since > self.SILENT_AFTER and not self.paused

    def _loop(self):
        last_hit = 0.0
        try:
            while self._run.is_set():
                if self._paused.is_set():
                    time.sleep(0.05)
                    continue
                try:
                    self._released.clear()
                    stream = self.open_stream(self.engine.frame)
                except Exception as exc:
                    self._released.set()
                    self.error = f"no microphone available ({exc.__class__.__name__})"
                    time.sleep(3)
                    continue
                self.error = ""
                woke = False
                try:
                    while self._run.is_set() and not self._paused.is_set():
                        pcm = stream.read()
                        if not pcm:
                            time.sleep(0.02)
                            continue
                        self._note_level(pcm)
                        if self.engine.process(pcm) and time.time() - last_hit > self.cooldown:
                            last_hit = time.time()
                            self.detections += 1
                            self._paused.set()           # hand the mic over...
                            woke = True
                            break
                except Exception as exc:
                    self.error = f"microphone stopped ({exc.__class__.__name__})"
                    time.sleep(1)
                finally:
                    try:
                        stream.close()                   # ...after closing it
                    except Exception:
                        pass
                    self._released.set()
                if woke:
                    try:
                        self.on_wake()                   # only now: the mic is free for Gink
                    except Exception:
                        pass
        finally:
            self._released.set()
            if self._own_mic:
                self.open_stream.terminate()
