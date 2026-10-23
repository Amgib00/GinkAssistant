"""
Voice input/output bridge -- ported against stt_worker.py's
VoiceRecognitionWorker and tts_worker.py's TTSWorker, confirmed as the
canonical pair over the two other implementations found earlier
(core/listener.py+speaker.py, and voice_app.py's inline workers).

One behavior NOT carried over on purpose: the original run() loop wraps
its entire while-loop body in a single try/except, so an
sr.UnknownValueError -- which just means "didn't catch that one
utterance", routine for background noise or silence -- propagates out
and ends the whole continuous listening session instead of just being
skipped. listen() here catches it per-call and returns "" so the caller
just listens again, which is almost certainly the intended behavior.

Needs `edge_tts` added to pyproject.toml -- it isn't listed there yet.
`pygame` is already listed, and is now confirmed load-bearing for the
canonical TTS path (not just a flagged-but-unused dependency anymore),
which sharpens the risk already noted there: pygame has no confirmed
Android (Chaquopy) or iOS (BeeWare anaconda.org) wheel.

One simplification versus the original: sr.Microphone() here opens and
closes per listen() call rather than staying open for an entire
continuous session, since this is structured as "capture one utterance
at a time" (matching how services/audio_engine.py's loop calls it) rather
than a single long-lived worker thread. A module-level flag still limits
ambient-noise calibration to once, matching the original's intent.

Android still has no native audio bridge wired up -- listen()/speak()
stay stubs there, same as before.
"""

import asyncio
import os
import sys
import tempfile
import threading
from typing import Callable, Optional


def _is_android() -> bool:
    """True on Android AND iOS -- neither has pygame/edge-tts/PyAudio.
    Uses platform_utils (sys.getandroidapilevel, which only Chaquopy adds).
    The old check here ("android" in sys.platform) never matched on Chaquopy,
    which reports "linux" -- so the desktop branch ran and the app crashed on
    launch with "No module named 'pygame'" (found with adb logcat)."""
    from .platform_utils import is_mobile
    return is_mobile()


# The page's Stop ring shows while Gink speaks: main_screen sets on_speaking(bool).
on_speaking = None
_stop = {"requested": False, "proc": None}


def _notify_speaking(on: bool) -> None:
    if on_speaking:
        try:
            on_speaking(on)
        except Exception:
            pass


# Settings -> Voice -> Speed: (edge-tts rate, macOS `say` words per minute)
SPEEDS = {"slow": ("-15%", 150), "normal": ("+0%", 185), "fast": ("+20%", 225)}
speed = ["normal"]


def set_speed(name: str) -> None:
    speed[0] = name if name in SPEEDS else "normal"


class VoiceUnavailable(Exception):
    pass


from .voice_profiles import VOICE_PROFILES as _PROFILES

VOICES = {v["key"]: v["id"] for v in _PROFILES}      # services/voice_profiles.py
listen_language = ["auto"]                            # Settings -> Voice -> Language ("auto": any language)


def _speakable(text: str) -> str:
    """Markdown -> plain sentences (no '**', '#', link addresses or video-card lines read aloud)."""
    import re as _re
    lines = [l for l in text.splitlines() if not l.strip().startswith("[\u25b6")]
    t = "\n".join(lines)
    t = _re.sub(r"```.*?```", " (code shown on screen) ", t, flags=_re.S)
    t = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)          # [text](url) -> text
    t = _re.sub(r"https?://\S+", "", t)
    t = _re.sub(r"[*_`#>|~]+", "", t)
    t = _re.sub(r"^\s*[-\u2022]\s+", "", t, flags=_re.M)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


# ---------------------------------------------------------------- natural, streaming speech
cloud = {"base_url_fn": None, "token_fn": None}      # main_screen: your Gink server + the session token
_current_voice = ["Female (Jenny)"]                  # the Gink voice speaking now (fallback voices match it)
last_cloud_error = [""]                              # why the natural voice last failed (Settings -> Voice -> Test)
last_heard_language = [""]                           # what Whisper detected last ("french"...)


def _device_language() -> str:
    """'fr-SN' style tag from the computer's locale, for when the server can't be used."""
    import locale
    try:
        loc = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "en_US")
    except Exception:
        loc = "en_US"
    return loc.replace("_", "-") if "_" in loc else "en-US"


def _google_language() -> str:
    return _device_language() if listen_language[0] == "auto" else listen_language[0]


def _transcribe_any_language(wav: bytes):
    """Whisper on the Gink server (detects the language itself). None -> use Google instead."""
    base, token = cloud.get("base_url_fn"), cloud.get("token_fn")
    if not (base and token and token()):
        return None
    import base64 as _b64
    import httpx
    try:
        r = httpx.post(base().rstrip("/") + "/voice/transcribe", json={"audio_b64": _b64.b64encode(wav).decode()},
                       headers={"Authorization": f"Bearer {token()}"}, timeout=30)
        if r.status_code != 200:
            return None
        j = r.json()
        last_heard_language[0] = j.get("language", "")
        return (j.get("text") or "").strip()
    except Exception:
        return None


def _note_cloud_error(reason: str):
    if reason and reason != last_cloud_error[0]:
        print(f"[Gink] Natural voice unavailable: {reason}")
    last_cloud_error[0] = reason

import re as _re
_BOUNDARY = _re.compile(r'([.!?\u2026]+["\u201d\u2019)\]]*)(\s+)|(\n+)')
_ABBREV = {"mr", "mrs", "ms", "dr", "st", "prof", "e.g", "i.e", "vs", "etc", "no", "approx", "fig", "jr", "sr"}


def split_sentences(buf: str, final: bool = False):
    """-> (complete sentences, remainder). Very short pieces are joined to the next
    one so the voice doesn't sound choppy; 'Dr. Diallo' or 'e.g.' isn't a sentence end."""
    out, start, pending = [], 0, ""
    for m in _BOUNDARY.finditer(buf):
        end = m.end()
        piece = buf[start:m.start() + len(m.group(1) or "")] if m.group(1) else buf[start:m.start()]
        last_word = piece.strip().split(" ")[-1].rstrip(".").lower() if piece.strip() else ""
        if m.group(1) and m.group(1).startswith(".") and last_word in _ABBREV:
            continue
        pending = (pending + " " + piece.strip()).strip()
        start = end
        if len(pending) >= 24:
            out.append(pending)
            pending = ""
    # keep the leftover's trailing space: the next streamed chunk may start
    # without one ("sunny " + "and" must not become "sunnyand")
    rest = (pending + " " + buf[start:].lstrip()) if pending else buf[start:]
    if final and rest.strip():
        out.append(rest.strip())
        rest = ""
    return out, rest


class SpeechQueue:
    """Feed it text as the reply streams in; it speaks each complete sentence,
    preparing the next one while the current one plays (no waiting for the
    whole answer, no gaps between sentences). stop_speaking() ends it at once."""
    _active = set()

    def __init__(self, voice_key: str, on_amplitude=None):
        self.voice_key, self.on_amplitude = voice_key, on_amplitude
        _current_voice[0] = voice_key
        self.buf, self.spoke = "", False
        self._texts, self._audio = asyncio.Queue(), asyncio.Queue(maxsize=2)
        _stop["requested"] = False
        _notify_speaking(True)
        SpeechQueue._active.add(self)
        self._synth_task = asyncio.ensure_future(self._synth_loop())
        self._play_task = asyncio.ensure_future(self._play_loop())

    def _push(self, sentence: str):
        clean = _speakable(sentence)
        if clean:
            self._texts.put_nowait(clean)
            self.spoke = True

    def feed(self, chunk: str):
        self.buf += chunk or ""
        sentences, self.buf = split_sentences(self.buf)
        for x in sentences:
            self._push(x)

    def finish(self):
        sentences, self.buf = split_sentences(self.buf, final=True)
        for x in sentences:
            self._push(x)
        self._texts.put_nowait(None)

    def _abort(self):
        self._texts.put_nowait(None)

    GROUP_CHARS = 450        # later sentences are grouped: fewer voice requests (Google limits per minute / per day)

    async def _synth_loop(self):
        first, ended = True, False
        while True:
            t = await self._texts.get()
            if t is None or _stop["requested"]:
                await self._audio.put(None)
                return
            if not first:                                   # the first sentence goes alone -> Gink starts talking fast
                while len(t) < self.GROUP_CHARS:
                    try:
                        more = self._texts.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if more is None:
                        ended = True
                        break
                    t = f"{t} {more}"
            first = False
            item = await _synth_sentence(t, self.voice_key)
            if _stop["requested"]:
                _cleanup_item(item)
                await self._audio.put(None)
                return
            await self._audio.put(item)
            if ended:
                await self._audio.put(None)
                return

    async def _play_loop(self):
        while True:
            item = await self._audio.get()
            if item is None:
                return
            if _stop["requested"]:
                _cleanup_item(item)
                continue
            await _play_item(item, self.on_amplitude)

    async def wait(self):
        try:
            await self._play_task
        finally:
            SpeechQueue._active.discard(self)
            if not self._synth_task.done():
                self._synth_task.cancel()
            _stop["proc"] = None
            _notify_speaking(False)


def _stop_queues():
    for q in list(SpeechQueue._active):
        try:
            q._abort()
        except Exception:
            pass


if _is_android():
    # Android: services/android_voice.py (the phone's recognizer; natural Gink voices from your
    # server, the phone's own voice offline).
    from . import android_voice as _av

    def _cloud_auth():
        base_fn, token_fn = cloud.get("base_url_fn"), cloud.get("token_fn")
        return (base_fn() if base_fn else "") or "", (token_fn() if token_fn else "") or ""

    async def listen(on_amplitude: Optional[Callable[[float], None]] = None) -> str:
        try:
            return await _av.listen(listen_language[0], on_amplitude=on_amplitude)
        except _av.VoiceProblem as exc:
            raise VoiceUnavailable(str(exc))

    async def speak(
        text: str,
        voice_key: str = "Female (Jenny)",
        on_amplitude: Optional[Callable[[float], None]] = None,
    ) -> None:
        base, token = _cloud_auth()
        try:
            used = await _av.speak(text, voice_key, base, token, speed[0], on_amplitude)
            if used == "phone":
                _note_cloud_error("the natural voice wasn't available, so the phone's voice was used")
        except _av.VoiceProblem as exc:
            _note_cloud_error(str(exc))

    def stop_speaking() -> None:
        _av.stop_speaking()

    async def _synth_sentence(text, voice_key):
        return None

    async def test_natural_voice(voice_key):
        base, token = _cloud_auth()
        path = await _av._natural_wav("This is how I sound.", voice_key, base, token, speed[0])
        if not path:
            return "the natural voice isn't available right now \u2014 the phone's own voice will be used"
        await _av._play_file(path)
        return ""

    def _cleanup_item(item):
        pass

    async def _play_item(item, on_amplitude):
        pass

else:
    import edge_tts
    import numpy as np
    import pygame
    import speech_recognition as sr

    try:
        pygame.mixer.init()
    except Exception:
        pass

    _recognizer = sr.Recognizer()
    _microphone = None
    _calibrated = False
    # Guards the single shared sr.Microphone() against overlapping entry --
    # e.g. a fast double-press of the mic button, or the mic button and
    # the continuous Voice Assistant loop both calling listen() around the
    # same time. Without this, a second call can enter the Microphone's
    # context manager while the first is still inside it, which raises
    # "This audio source is already inside a context manager" instead of
    # just waiting its turn. threading.Lock (not asyncio.Lock) because
    # _listen_blocking runs on a thread-pool executor thread, not
    # directly on the asyncio loop.
    _mic_lock = threading.Lock()

    def _amplitude_from_raw(raw_pcm_bytes: bytes) -> float:
        audio_data = np.frombuffer(raw_pcm_bytes, dtype=np.int16)
        if len(audio_data) == 0:
            return 0.0
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        return min(1.0, (rms / 32768.0) * 5.0)  # same sensitivity boost as stt_worker.py

    def _listen_blocking(on_amplitude: Optional[Callable[[float], None]]) -> str:
        global _microphone, _calibrated
        with _mic_lock:
            if _microphone is None:
                _microphone = sr.Microphone()

            with _microphone as source:
                if not _calibrated:
                    _recognizer.adjust_for_ambient_noise(source, duration=1.0)
                    _calibrated = True
                try:
                    audio = _recognizer.listen(source, timeout=3, phrase_time_limit=8)
                except sr.WaitTimeoutError:
                    return ""

        if on_amplitude:
            on_amplitude(_amplitude_from_raw(audio.get_raw_data()))

        if listen_language[0] == "auto":
            text = _transcribe_any_language(audio.get_wav_data(convert_rate=16000, convert_width=2))
            if text is not None:
                return text                          # the server understood it (any language)
        try:
            return _recognizer.recognize_google(audio, language=_google_language())
        except sr.UnknownValueError:
            return ""  # see module docstring

    async def listen(on_amplitude: Optional[Callable[[float], None]] = None) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _listen_blocking, on_amplitude)

    _edge_down_until = [0.0]       # after an Edge voice failure, use the system voice for a while
    EDGE_RETRY_AFTER = 600

    _mac_voices_cache = []
    _FEMALE = ["Ava", "Samantha", "Allison", "Susan", "Zoe", "Joelle", "Nicky", "Serena", "Kate", "Stephanie", "Martha",
               "Karen", "Moira", "Tessa", "Fiona", "Victoria", "Am\u00e9lie", "Amelie", "Audrey", "Marie", "Aur\u00e9lie"]
    _MALE = ["Evan", "Nathan", "Tom", "Alex", "Aaron", "Daniel", "Oliver", "Arthur", "Lee", "Fred", "Thomas",
             "Jacques", "Nicolas", "Gordon"]

    def _mac_voices():
        """[(name, locale)] from `say -v ?` (cached)."""
        if not _mac_voices_cache:
            import re as _r, subprocess as _sp
            try:
                out = _sp.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
            except Exception:
                out = ""
            for line in out.splitlines():
                m = _r.match(r"^(.+?)\s{2,}([a-z]{2}_[A-Z]{2})\s+#", line)
                if m:
                    _mac_voices_cache.append((m.group(1).strip(), m.group(2)))
        return _mac_voices_cache

    def best_mac_voice(voice_key: str, voices=None):
        """The best installed macOS voice for the chosen Gink voice: right gender and accent,
        Premium > Enhanced > standard (Alex counts as high quality). None = system default."""
        from .voice_profiles import local_voice_wish
        gender, locales = local_voice_wish(voice_key)
        wanted, other = (_FEMALE, _MALE) if gender == "female" else (_MALE, _FEMALE)
        best, best_score = None, -1
        for name, loc in (voices if voices is not None else _mac_voices()):
            base = name.split(" (")[0]
            if base in other or (base not in wanted):
                continue
            score = 0
            if loc in locales:
                score += 30 - 5 * locales.index(loc)
            elif loc[:2] == locales[0][:2]:
                score += 10
            else:
                continue
            score += 6 if "(Premium)" in name else 4 if "(Enhanced)" in name else 2 if base == "Alex" else 0
            score += max(0, 3 - wanted.index(base) // 4)               # gentle preference for the nicest names
            if score > best_score:
                best, best_score = name, score
        return best

    async def _system_voice(text: str, on_amplitude) -> None:
        """Offline fallback: the best installed macOS voice, otherwise pyttsx3 (Windows SAPI / Linux espeak)."""
        if sys.platform == "darwin":
            args = ["say", "-r", str(SPEEDS.get(speed[0], SPEEDS["normal"])[1])]
            name = best_mac_voice(_current_voice[0])
            if name:
                args += ["-v", name]
            proc = await asyncio.create_subprocess_exec(*args,
                                                        text, stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
            _stop["proc"] = proc
            while proc.returncode is None:
                if on_amplitude:
                    on_amplitude(0.6)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass
            return
        try:
            import pyttsx3
        except ImportError:
            return

        def run():
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        await asyncio.get_event_loop().run_in_executor(None, run)

    import base64 as _b64
    import time as _time
    _cloud_down_until = [0.0]

    async def _cloud_wav(text: str, voice_key: str):
        """Natural voice from YOUR Gink server (Google Gemini TTS) -> a .wav path, or None."""
        base_fn, token_fn = cloud.get("base_url_fn"), cloud.get("token_fn")
        if not (base_fn and token_fn) or _time.time() < _cloud_down_until[0]:
            return None
        base, token = base_fn(), token_fn()
        if not base or not token:
            _note_cloud_error("not signed in to the Gink server (sign out and in again)")
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{base.rstrip('/')}/voice/speak", headers={"Authorization": f"Bearer {token}"},
                                 json={"text": text, "persona": voice_key, "speed": speed[0]})
            if r.status_code != 200:
                # daily allowance used -> standard voice for a while; not set up -> check again later
                _cloud_down_until[0] = _time.time() + (1800 if r.status_code == 429 else 600 if r.status_code in (404, 503) else 60)
                try:
                    err = r.json().get("error") or {}
                    reason = err.get("detail") or err.get("message") or r.json().get("detail") or ""
                    if err.get("retry_after"):                     # Google's own limit: wait exactly that long
                        _cloud_down_until[0] = _time.time() + min(int(err["retry_after"]), 12 * 3600)
                except Exception:
                    reason = ""
                if r.status_code == 404:
                    reason = "your Gink server is older than the app (restart it after updating)"
                _note_cloud_error(f"HTTP {r.status_code} \u2014 {reason or 'no details'}")
                return None
            raw = _b64.b64decode(r.json()["audio_b64"])
        except Exception as exc:
            _cloud_down_until[0] = _time.time() + 60
            _note_cloud_error(f"couldn't reach the Gink server ({exc.__class__.__name__})")
            return None
        _note_cloud_error("")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(raw)
            return f.name

    async def test_natural_voice(voice_key: str) -> str:
        """'' if the natural voice works, else the reason (plain words)."""
        _cloud_down_until[0] = 0.0
        path = await _cloud_wav("Hi! This is how I sound.", voice_key)
        if path:
            _cleanup_item(("file", path))
            return ""
        return last_cloud_error[0] or "unknown problem"

    async def _edge_mp3(text: str, voice_key: str):
        if _time.time() < _edge_down_until[0]:
            return None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            path = f.name
        try:
            communicate = edge_tts.Communicate(text, VOICES.get(voice_key, VOICES["Female (Jenny)"]),
                                               rate=SPEEDS.get(speed[0], SPEEDS["normal"])[0])
            await communicate.save(path)
            return path
        except Exception as exc:
            _edge_down_until[0] = _time.time() + EDGE_RETRY_AFTER
            print(f"[Gink] Edge voice unavailable ({exc.__class__.__name__}); using the system voice.")
            if os.path.exists(path):
                os.remove(path)
            return None

    async def _synth_sentence(text: str, voice_key: str):
        """Best available voice for one sentence: natural (server) -> Edge -> the computer's own."""
        path = await _cloud_wav(text, voice_key) or await _edge_mp3(text, voice_key)
        return ("file", path) if path else ("system", text)

    def _cleanup_item(item):
        if item and item[0] == "file" and os.path.exists(item[1]):
            try:
                os.remove(item[1])
            except OSError:
                pass

    async def _play_item(item, on_amplitude):
        if not item or _stop["requested"]:
            _cleanup_item(item)
            return
        if item[0] == "system":
            try:
                await _system_voice(item[1], on_amplitude)
            except Exception:
                pass
            return
        loaded = False
        try:
            pygame.mixer.music.load(item[1])
            loaded = True
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not _stop["requested"]:
                if on_amplitude:
                    on_amplitude(0.6)
                await asyncio.sleep(0.04)
        except Exception:
            pass
        finally:
            if loaded:
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
            _cleanup_item(item)

    async def speak(
        text: str,
        voice_key: str = "Female (Jenny)",
        on_amplitude: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Never raises. Speaks sentence by sentence (the next sentence is prepared
        while the current one plays), in the most natural voice available."""
        if not _speakable(text or ""):
            return
        q = SpeechQueue(voice_key, on_amplitude)
        q.feed(text)
        q.finish()
        await q.wait()

    def stop_speaking() -> None:
        """Stop ring / new message: silence the voice right away."""
        _stop["requested"] = True
        _stop_queues()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        proc = _stop.get("proc")
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()               # macOS `say`
            except Exception:
                pass