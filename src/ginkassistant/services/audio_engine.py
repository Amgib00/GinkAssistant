"""
Continuous listen->ask->speak loop, composing services/voice_bridge.py
(the confirmed-canonical stt_worker.py + tts_worker.py pair) the same
way ginkassistant/core/audio.py's GinkAudioEngine composes GinkListener
+ GinkSpeaker.

Also interleaves ambient song recognition (services/song_recognition.py)
into the same loop, so a running song gets noticed and announced on its
own -- no "Identify Song" button needed. This runs sequentially with
speech listening (never concurrently), both to avoid two things fighting
over the same microphone at once, and because that's naturally how one
continuous loop works: each pass through does either a listen-for-speech
check or, periodically, a listen-for-music check, never both at once.

Kept the name GinkAudioEngine for continuity, though this isn't a 1:1
port of any single one of the three implementations found in this
project -- it's the loop shape from core/audio.py, running the confirmed
STT/TTS pair underneath. Toga's single-threaded async loop lets
on_transcription/on_status/on_amplitude/on_song_detected be called
directly; no Qt signals needed.
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from . import song_recognition, voice_bridge

logger = logging.getLogger("GinkAudioEngine")

SONG_CHECK_INTERVAL_SECONDS = 25


class GinkAudioEngine:
    def __init__(self, voice_key: str = "Female (Jenny)"):
        self.is_running = True
        self._is_listening = False
        self.voice_key = voice_key
        self._last_song_check = 0.0
        self._last_announced_song = None

    def start_listening(self):
        self._is_listening = True

    def stop_listening(self):
        self._is_listening = False

    async def speak(
        self,
        text: str,
        on_status: Optional[Callable[[str], None]] = None,
        on_amplitude: Optional[Callable[[float], None]] = None,
    ):
        """Pauses listening, speaks, then resumes -- genuinely waits for
        playback to finish (voice_bridge.speak() awaits pygame's get_busy()
        loop) before resuming, unlike core/audio.py's 0.1s-then-resume."""
        self.stop_listening()
        if on_status:
            on_status("Speaking...")
        await voice_bridge.speak(text, voice_key=self.voice_key, on_amplitude=on_amplitude)
        if on_status:
            on_status("Gink is Ready")
        self.start_listening()

    def stop(self):
        self.is_running = False
        self._is_listening = False
        voice_bridge.stop_speaking()

    async def run_loop(
        self,
        on_transcription: Callable[[str], Awaitable[None]],
        on_status: Optional[Callable[[str], None]] = None,
        on_amplitude: Optional[Callable[[float], None]] = None,
        on_song_detected: Optional[Callable[[dict], Awaitable[None]]] = None,
    ):
        """Schedule with asyncio.create_task() once Toga's loop is running
        (app.add_background_task is deprecated in newer Toga versions).
        Captures one utterance at a time and awaits on_transcription(text)
        for each one recognized; periodically also checks for ambient
        music and awaits on_song_detected(song) on a new, confident match.
        """
        while self.is_running:
            if self._is_listening:
                if on_status:
                    on_status("Listening...")
                try:
                    text = await voice_bridge.listen(on_amplitude=on_amplitude)
                except voice_bridge.VoiceUnavailable as exc:
                    if on_status:
                        on_status(str(exc))
                    self.stop_listening()
                    continue
                except Exception as exc:
                    logger.error(f"Audio engine loop error: {exc}")
                    await asyncio.sleep(1)
                    continue

                if text and text.strip():
                    if on_status:
                        on_status("Processing...")
                    await on_transcription(text)
                    continue  # don't also run a song check on the same beat

                # No speech caught this pass -- a quiet, periodic moment is
                # exactly when it's safe (mic's free) to check for music.
                if on_song_detected and self._due_for_song_check():
                    await self._check_for_song(on_status, on_song_detected)
            else:
                await asyncio.sleep(0.3)

    def _due_for_song_check(self) -> bool:
        return (time.monotonic() - self._last_song_check) >= SONG_CHECK_INTERVAL_SECONDS

    async def _check_for_song(self, on_status, on_song_detected):
        self._last_song_check = time.monotonic()
        if on_status:
            on_status("Listening for music...")
        try:
            song = await song_recognition.identify_ambient_song()
        except Exception as exc:
            logger.error(f"Song recognition error: {exc}")
            return

        if not song:
            return

        fingerprint = (song.get("title"), song.get("artist"))
        if fingerprint == self._last_announced_song:
            return  # same song still playing -- don't repeat ourselves

        self._last_announced_song = fingerprint
        await on_song_detected(song)