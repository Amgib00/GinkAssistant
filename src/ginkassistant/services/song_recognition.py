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


async def identify_ambient_song() -> Optional[dict]:
    """Returns {"title", "artist", "url"} on a confident match, else None.
    Tries the real Shazam API (shazamio) first, then the local
    fingerprint database (shazam_engine.py) if that's unavailable or
    finds nothing."""
    if not HAS_SHAZAMIO or not HAS_SOUNDDEVICE:
        return await _identify_with_local_engine()

    loop = asyncio.get_event_loop()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        await loop.run_in_executor(None, _record_sample_blocking, tmp_path, SAMPLE_SECONDS)
        shazam = Shazam()
        result = await shazam.recognize(tmp_path)
        track = result.get("track")
        if not track:
            return await _identify_with_local_engine()
        return {
            "title": track.get("title", "Unknown title"),
            "artist": track.get("subtitle", "Unknown artist"),
            "url": track.get("url"),
        }
    except Exception:
        return await _identify_with_local_engine()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)