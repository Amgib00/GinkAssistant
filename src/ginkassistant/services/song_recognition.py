"""
Ambient song recognition -- unlike tools/shazam.py's from-scratch
ShazamEngine (which can only match songs already added to its own local
database), this identifies *any* song via shazamio, a real Shazam API
client. That's what "notices a song playing and tells the user" actually
needs -- the from-scratch engine has no way to recognize something it
hasn't seen before.

Records a short ambient sample, sends it off for recognition, and
returns a plain dict on a confident match or None on no match / silence
/ unavailable. Designed to be called periodically from the continuous
voice loop (services/audio_engine.py), not from a button.

Writes the sample via the stdlib `wave` module rather than adding
`soundfile` as a dependency -- one less compiled-library wheel to worry
about on Android/iOS, on top of everything already flagged there.

sounddevice's import is now guarded the same way shazamio's already was
-- confirmed via an actual Android build attempt that pyaudio (a
different PortAudio-wrapping package, used elsewhere for sr.Microphone())
has zero Android wheels at all; sounddevice wraps the same native
PortAudio library the same way, so it's extremely likely to fail
identically there. Before this fix, the unconditional `import
sounddevice` at module level would have hard-crashed on first import
anywhere that's true, rather than just disabling ambient song
recognition gracefully the way a missing shazamio already does.
"""

import asyncio
import os
import tempfile
import wave
from typing import Optional

try:
    import sounddevice as sd

    HAS_SOUNDDEVICE = True
except (ImportError, OSError):
    HAS_SOUNDDEVICE = False

try:
    from shazamio import Shazam

    HAS_SHAZAMIO = True
except ImportError:
    HAS_SHAZAMIO = False

SAMPLE_RATE = 44100
SAMPLE_SECONDS = 8


def _record_sample_blocking(path: str, duration: int):
    import numpy as np          # lazy: desktop-only (no numpy build exists for iPhone)
    recording = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()

    pcm16 = np.clip(recording, -1.0, 1.0)
    pcm16 = (pcm16 * 32767).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())


_local_engine = None


async def _identify_with_local_engine() -> Optional[dict]:
    """Fallback: services/shazam_engine.py, the from-scratch
    fingerprinting engine. It can only recognise songs you've added to
    its own local database, but it works offline. Desktop-only in
    practice -- librosa/scipy are only installed on macOS/Windows/Linux,
    and the engine already reports itself unavailable (HAS_SHAZAM_DEPS)
    anywhere they're missing, so this quietly returns None on phones."""
    global _local_engine
    try:
        import toga
        from .shazam_engine import HAS_SHAZAM_DEPS, ShazamEngine
        if not HAS_SHAZAM_DEPS or toga.App.app is None:
            return None
        if _local_engine is None:
            _local_engine = ShazamEngine(toga.App.app)
        if not _local_engine.song_metadata:
            return None  # empty database: nothing it could ever match
        title, offset = await _local_engine.listen_and_identify(duration=SAMPLE_SECONDS)
        if not title:
            return None
        return {"title": title, "artist": "", "url": None, "source": "local", "offset": offset}
    except Exception:
        return None


class SongProblem(Exception):
    """A reason worth telling the person (no microphone permission, daily limit, not signed in...)."""


# Phones (and desktops without shazamio) ask YOUR Gink server, which runs shazamio (POST /media/song).
# main_screen sets server["fn"] = lambda: (base_url, session_token).
server = {"fn": None}


async def _record() -> Optional[str]:
    """A short recording -> .wav path (the caller deletes it), or None when this device can't record."""
    from .platform_utils import is_android
    if is_android():
        from .android_voice import VoiceProblem, record_wav
        try:
            return await record_wav(SAMPLE_SECONDS, 16000)
        except VoiceProblem as exc:
            raise SongProblem(str(exc)) from exc
    if not HAS_SOUNDDEVICE:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        path = tmp_file.name
    try:
        await asyncio.get_event_loop().run_in_executor(None, _record_sample_blocking, path, SAMPLE_SECONDS)
    except Exception:
        os.remove(path)
        return None
    return path


async def _recognise_here(path: str) -> Optional[dict]:
    result = await Shazam().recognize(path)
    track = result.get("track")
    if not track:
        return None
    return {"title": track.get("title", "Unknown title"), "artist": track.get("subtitle", "Unknown artist"),
            "url": track.get("url")}


async def _recognise_on_server(path: str) -> Optional[dict]:
    fn = server.get("fn")
    base, token = fn() if fn else ("", "")
    if not (base and token):
        raise SongProblem("Sign in to recognise songs on this device.")
    from .api_client import ApiClient, ApiError
    with open(path, "rb") as f:
        audio = f.read()
    try:
        found = await ApiClient(base).identify_song(token, audio)
    except ApiError as exc:
        raise SongProblem(str(exc)) from exc
    if not found.get("match"):
        return None
    return {"title": found.get("title") or "Unknown title", "artist": found.get("artist") or "Unknown artist",
            "url": found.get("url")}


async def identify_ambient_song() -> Optional[dict]:
    """Returns {"title", "artist", "url"} on a confident match, else None (raises SongProblem when
    there's a reason to tell the person). Records a short sample, then: shazamio on this device if it's
    installed (desktops), otherwise YOUR Gink server (phones); then the local fingerprint database."""
    path = await _record()
    if path is None:
        return await _identify_with_local_engine()
    try:
        if HAS_SHAZAMIO:
            try:
                song = await _recognise_here(path)
            except Exception:
                song = None
        else:
            song = await _recognise_on_server(path)
        return song or await _identify_with_local_engine()
    finally:
        if os.path.exists(path):
            os.remove(path)
