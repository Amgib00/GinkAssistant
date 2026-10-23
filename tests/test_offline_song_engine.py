"""The offline song engine: learn a song, then recognise a noisy excerpt and where it comes from."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
se = pytest.importorskip("ginkassistant.services.shazam_engine")
if not se.HAS_SHAZAM_DEPS:
    pytest.skip("numpy/librosa/scipy/sounddevice not installed", allow_module_level=True)
import numpy as np


def song(seed, seconds=20, sr=22050):
    rng = np.random.default_rng(seed); t = np.arange(sr * seconds) / sr; n = seconds * 8
    notes = 220 * 2 ** (rng.integers(0, 24, n) / 12)
    sig = np.zeros_like(t)
    for i, f in enumerate(notes):
        seg = slice(i * len(t) // n, (i + 1) * len(t) // n)
        sig[seg] += sum(np.sin(2 * np.pi * f * k * t[seg]) / k for k in (1, 2, 3)) + 0.5 * np.sin(2 * np.pi * f * 1.5 * t[seg])
    return (sig / np.abs(sig).max()).astype(np.float32)


def engine():
    e = se.ShazamEngine.__new__(se.ShazamEngine)
    from collections import defaultdict
    e.fingerprints, e.song_metadata = defaultdict(list), {}
    return e


def test_learn_then_recognise_a_noisy_excerpt():
    e, sr = engine(), 22050
    a, b = song(1), song(2)
    assert e.add_song(a, "Gink Groove", "Ibrahim") > 100 and e.add_song(b, "Other Tune") > 100
    start = 8                                                                        # seconds into the song
    clip = a[start * sr:(start + 6) * sr] * 0.6 + 0.08 * np.random.default_rng(3).standard_normal(6 * sr).astype(np.float32)
    meta, offset = e.identify(clip)
    assert meta == {"title": "Gink Groove", "artist": "Ibrahim"}
    assert abs(offset - start) < 0.5                                                 # and where in the song


def test_recognises_most_excerpts_and_never_names_the_wrong_song():
    e, sr, rng = engine(), 22050, np.random.default_rng(3)
    for s in (1, 2, 3):
        e.add_song(song(s), f"Song {s}")
    found = 0
    for s in (1, 2, 3):
        for start, noise in ((2, 0.05), (8, 0.08), (12, 0.12)):
            clip = song(s)[start * sr:(start + 6) * sr] * 0.6 + noise * rng.standard_normal(6 * sr).astype(np.float32)
            meta, offset = e.identify(clip)
            assert meta is None or meta["title"] == f"Song {s}"                      # never the wrong song
            found += meta is not None and abs(offset - start) < 0.5
    assert found >= 7                                                                # most noisy excerpts

    for seed in range(4, 24):                                                        # 20 tunes it never learned
        assert e.identify(song(seed, seconds=6)) == (None, None)
