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

# The free model's dictionary doesn't contain "gink" or "jink" (Vosk logs "Ignoring word missing in
# vocabulary" and drops them), so only words it knows are used: "ginkgo" starts with the very same
# sounds as "Gink", and "king" is the closest short word. matches() also accepts "gink" for engines
# (or future models) that know it.
WAKE_PHRASES = ["hey ginkgo", "hey king", "hi ginkgo", "hi king", "okay ginkgo"]
MATCH_WORDS = ("gink", "ginkgo", "king", "jink")
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


def matches(text: str) -> bool:
    """Does a recognized phrase contain the wake word?"""
    t = " " + re.sub(r"[^a-z ]", " ", (text or "").lower()) + " "
    t = re.sub(r"\s+", " ", t)
    return any(f" {lead} {w} " in t for lead in ("hey", "hi", "okay", "ok") for w in MATCH_WORDS)


# ---------------------------------------------------------------- engines
class VoskEngine:
    name = "Vosk (offline, free)"

    def __init__(self, path: str):
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        self._model = Model(path)
        # only listen for the wake phrases (+ "anything else"): fast and few false alarms
        self._rec = KaldiRecognizer(self._model, RATE, json.dumps(WAKE_PHRASES + ["[unk]"]))
        self.frame = 4000                       # samples per read (0.25 s)
        self.last_heard = ""                    # shown in Settings -> Voice -> Hey Gink (helps tuning)

    def process(self, pcm: bytes) -> bool:
        if self._rec.AcceptWaveform(pcm):
            text = json.loads(self._rec.Result()).get("text", "")
            if text and text != "[unk]":
                self.last_heard = text
        else:
            text = json.loads(self._rec.PartialResult()).get("partial", "")
        if matches(text):
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


class WakeWordListener:
    """Background thread: mic -> engine -> on_wake().

    The microphone is RELEASED before anyone else uses it: on a detection the
    stream is closed first and only then on_wake() runs, and pause(wait=True)
    blocks until the stream is really closed. Two input streams at once is what
    caused the AUHAL -10863 errors."""

    def __init__(self, engine, on_wake: Callable[[], None], open_stream=None, cooldown: float = 2.0):
        self.engine, self.on_wake = engine, on_wake
        self._own_mic = open_stream is None
        self.open_stream = open_stream or _PyAudioMic()
        self.cooldown = cooldown
        self._run = threading.Event()
        self._paused = threading.Event()
        self._released = threading.Event()
        self._released.set()                    # no stream open yet
        self._thread: Optional[threading.Thread] = None
        self.error = ""
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
