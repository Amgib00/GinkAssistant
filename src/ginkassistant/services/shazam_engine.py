"""
From-scratch Shazam-style audio fingerprinting -- async port of
tools/shazam.py's ShazamEngine. The algorithm itself is unchanged
(spectrogram -> 2D peak detection -> combinatorial peak-pair hashing ->
match against a local database); the only real changes are the database
path (now under services/paths.py's data_dir() instead of a bare
relative "shazam_db.pkl") and wrapping the blocking librosa/sounddevice
calls in run_in_executor so they don't freeze the UI.

Now wired in: services/song_recognition.py falls back to this engine when
shazamio is unavailable or finds nothing. librosa and scipy are listed in
pyproject.toml for macOS/Windows/Linux ONLY -- never Android/iOS, where
this module just reports HAS_SHAZAM_DEPS = False and is skipped. Older
note kept for context: librosa and scipy were not in pyproject.toml at all, and librosa commonly pulls in
numba for JIT compilation, which is often difficult or impossible to get
working in a sandboxed Android/iOS environment. This is included because
you asked for everything back in, but it's genuinely the highest-risk
single piece in the app for mobile builds -- test an Android/iOS build
with this included early, specifically, rather than near the end.
"""

import asyncio
import hashlib
import logging
import os
import pickle
from collections import defaultdict
from operator import itemgetter

import toga

from .paths import data_dir

try:
    import numpy as np          # optional like librosa/scipy: missing on iPhone -> engine unavailable, app still opens
    import librosa
    import sounddevice as sd
    from scipy.ndimage import generate_binary_structure, iterate_structure, maximum_filter

    HAS_SHAZAM_DEPS = True
except ImportError:
    HAS_SHAZAM_DEPS = False

logger = logging.getLogger("ShazamEngine")


class ShazamUnavailable(Exception):
    pass


class ShazamEngine:
    SAMPLE_RATE = 22050
    N_FFT = 4096
    N_HOP = 2048
    PEAK_NEIGHBORHOOD_SIZE = 20
    MIN_AMPLITUDE = 10
    FAN_VALUE = 15
    MATCH_THRESHOLD = 5

    def __init__(self, app: toga.App):
        self.db_path = data_dir(app) / "shazam_db.pkl"
        self.fingerprints = defaultdict(list)
        self.song_metadata = {}
        self._load_database()

    def _load_database(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "rb") as f:
                    data = pickle.load(f)
                    self.fingerprints = data.get("db", defaultdict(list))
                    self.song_metadata = data.get("song_info", {})
            except (pickle.UnpicklingError, EOFError) as e:
                logger.error(f"Failed to load Shazam database: {e}. Starting fresh.")

    def save_database(self):
        with open(self.db_path, "wb") as f:
            pickle.dump({"db": dict(self.fingerprints), "song_info": self.song_metadata}, f)

    async def add_track(self, filepath: str, track_name: str):
        if not HAS_SHAZAM_DEPS:
            raise ShazamUnavailable("librosa/scipy/sounddevice aren't available on this build.")
        loop = asyncio.get_event_loop()
        y = await loop.run_in_executor(None, lambda: librosa.load(filepath, sr=self.SAMPLE_RATE, mono=True)[0])

        track_id = len(self.song_metadata)
        self.song_metadata[track_id] = track_name
        hashes = await loop.run_in_executor(None, self._generate_fingerprints, y)
        for h, offset in hashes:
            self.fingerprints[h].append((track_id, offset))
        self.save_database()

    async def listen_and_identify(self, duration: int = 10):
        if not HAS_SHAZAM_DEPS:
            raise ShazamUnavailable("librosa/scipy/sounddevice aren't available on this build.")

        def _record():
            recording = sd.rec(int(duration * self.SAMPLE_RATE), samplerate=self.SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            return recording.flatten()

        loop = asyncio.get_event_loop()
        samples = await loop.run_in_executor(None, _record)
        return await loop.run_in_executor(None, self.identify, samples)

    def identify(self, audio_data):
        hashes = self._generate_fingerprints(audio_data)
        matches = defaultdict(list)
        for h, offset in hashes:
            for track_id, track_offset in self.fingerprints.get(h, []):
                matches[track_id].append((track_offset, offset))

        best_track_id, best_offset, max_alignment = None, 0, 0
        for track_id, offsets in matches.items():
            diffs = defaultdict(int)
            for t_off, s_off in offsets:
                diffs[t_off - s_off] += 1
            if diffs:
                current_max = max(diffs.values())
                if current_max > max_alignment:
                    max_alignment = current_max
                    best_track_id = track_id
                    best_offset = max(diffs, key=diffs.get)

        if best_track_id is not None and max_alignment >= self.MATCH_THRESHOLD:
            time_offset = (best_offset * self.N_HOP) / self.SAMPLE_RATE
            return self.song_metadata[best_track_id], round(time_offset, 2)
        return None, None

    def _generate_fingerprints(self, samples):
        stft = np.abs(librosa.stft(samples, n_fft=self.N_FFT, hop_length=self.N_HOP))
        spectrogram = librosa.amplitude_to_db(stft, ref=np.max)

        struct = generate_binary_structure(2, 1)
        neighborhood = iterate_structure(struct, self.PEAK_NEIGHBORHOOD_SIZE)
        local_max = maximum_filter(spectrogram, footprint=neighborhood) == spectrogram
        background = spectrogram < -70
        detected_peaks = local_max ^ background

        freqs, times = np.where(detected_peaks)
        amps = spectrogram[freqs, times]
        peaks = sorted(
            [(t, f, a) for t, f, a in zip(times, freqs, amps) if a > self.MIN_AMPLITUDE],
            key=itemgetter(2), reverse=True,
        )

        hashes = []
        for i in range(len(peaks)):
            for j in range(1, self.FAN_VALUE):
                if (i + j) < len(peaks):
                    t1, f1, _ = peaks[i]
                    t2, f2, _ = peaks[i + j]
                    t_delta = t2 - t1
                    if 0 <= t_delta <= 200:
                        h_str = f"{f1}|{f2}|{t_delta}"
                        h = hashlib.sha1(h_str.encode("utf-8")).hexdigest()[:20]
                        hashes.append((h, t1))
        return hashes
