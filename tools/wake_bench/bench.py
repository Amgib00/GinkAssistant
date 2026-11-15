#!/usr/bin/env python3
"""
Measure the offline "Hey Gink" listener instead of guessing.

Many synthetic voices (espeak-ng: different speakers, speeds, pitches) say the wake phrases -- "Gink" with a hard g
and "Jink" with a soft one -- and ordinary sentences that must NOT wake Gink ("I think...", "hey kids...", "okay
thanks..."). Every recording goes through the app's own listener (services/wake_word.py), a quarter of a second at
a time, exactly as the microphone would.

    brew install espeak-ng ffmpeg        (Linux: sudo apt install espeak-ng ffmpeg)
    pip install vosk
    python tools/wake_bench/bench.py --model ~/path/to/vosk-model-small-en-us-0.15

The model is the folder the app downloads for Hey Gink (Settings > Voice shows where), or download it from
https://alphacephei.com/vosk/models. Run this BEFORE and AFTER changing any word list in wake_word.py.
Synthetic voices are not your voice: tools/wake_check.py tests the listener with your own microphone.
"""
import argparse
import itertools
import json
import os
import random
import subprocess
import sys
import wave
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

VOICES = ["en-us", "en-us+f3", "en-us+m3", "en-gb", "en-gb+f4", "en-us+m7", "en+f2", "en-029", "en-gb-scotland", "en-us+f5"]
SPEEDS, PITCHES = [130, 160, 185], [35, 50, 65]
# [[...]] are espeak phonemes: "gink" with a hard g, "jink" with a soft one
WAKE = {"hey gink": "[[h'eI g'INk]]", "hey jink": "[[h'eI dZ'INk]]", "hi gink": "[[h'aI g'INk]]", "okay gink": "[[oUk'eI g'INk]]",
        "hey gink + request": "[[h'eI g'INk]] what's the weather today", "hey jink + request": "[[h'eI dZ'INk]] set a timer for ten minutes",
        "gink alone": "[[g'INk]]", "jink alone": "[[dZ'INk]]", "gink + request": "[[g'INk]], what time is it"}
ALONE = ("gink alone", "jink alone", "gink + request")
ORDINARY = [
    "good morning how are you doing today", "i think the link is broken again", "the ink in this pen is dry", "can i get a drink of water",
    "the king of the hill is a show", "hey there how was your day", "okay let's go to the shop", "hi mum i will call you later",
    "play some music in the kitchen", "we are thinking about dinner", "hey can you pass the salt", "he drank gin and tonic",
    "okay i will send the link now", "hi kim nice to see you", "the meeting starts at nine", "hey look at this picture",
    "i am going to bed now good night", "okay thanks see you tomorrow", "what a wonderful thing to think", "hey kids dinner is ready",
    "i think we should leave now", "i think so too", "do you think it will rain", "hi i think you dropped this", "okay i think that is enough",
    "hey i think your phone is ringing", "what are you thinking about", "the king and queen arrived", "she is drinking tea in the garden",
    "hey guys come and look at this", "hi there nice to meet you", "okay kids time for school", "hey what is going on", "hi can i help you",
    "okay google what is the weather", "hey siri call my brother", "alexa play the news", "that thing is getting bigger",
    "i am getting ready to go", "he is kidding you know", "give me the keys please", "okay king street is on the left",
    "hey kim are you coming", "hi jim how is the gym", "bring the pink ink for the printer", "click the link in the email",
    "okay good night everyone", "hey come here for a minute", "i need to think about it", "nothing is working today",
    # single words and short bits: what "the name alone" must not be confused with
    "yes", "no", "okay", "thanks", "king", "think", "getting", "going", "kidding", "can", "good", "cool", "thing", "drink", "kim",
    "come in", "keep going", "good king", "kings and queens", "thinking", "nothing", "give it", "again", "kitchen", "gimme that",
    "big thing", "the king", "kinda"]


def say(text, voice, speed, pitch, path):
    raw = path + ".tmp.wav"
    subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), "-w", raw, text], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-ar", "16000", "-ac", "1", "-af", "apad=pad_dur=0.8,adelay=300|300", path], check=True)
    os.remove(raw)


def recordings(folder, per_wake, per_ordinary):
    os.makedirs(folder, exist_ok=True)
    combos = list(itertools.product(VOICES, SPEEDS, PITCHES))
    out = {"wake": [], "ordinary": []}
    for group, items, per, seed in (("wake", list(WAKE.items()), per_wake, 7), ("ordinary", [(t, t) for t in ORDINARY], per_ordinary, 11)):
        rnd = random.Random(seed)
        for j, (name, text) in enumerate(items):
            for i, (v, s, p) in enumerate(rnd.sample(combos, per)):
                f = os.path.join(folder, f"{group[0]}{j}_{i}.wav")
                if not os.path.exists(f):
                    say(text, v, s, p, f)
                out[group].append((name, f))
    return out


def listen(engine, path):
    """Feed one recording to a fresh recognizer, 0.25 s at a time -> (woke, last text heard)."""
    from vosk import KaldiRecognizer
    from ginkassistant.services import wake_word as w
    engine._rec = KaldiRecognizer(engine._model, w.RATE, json.dumps(engine.words))
    engine.last_heard = ""
    with wave.open(path, "rb") as f:
        data = f.readframes(f.getnframes())
    step = engine.frame * 2
    for k in range(0, len(data), step):
        if engine.process(data[k:k + step].ljust(step, b"\0")):
            return True, engine.last_heard
    final = json.loads(engine._rec.FinalResult()).get("text", "")
    return w.matches(final, True), final or engine.last_heard


def run(model, folder, per_wake=24, per_ordinary=4, short=True, show=12):
    from ginkassistant.services import wake_word as w
    w.SHORT["on"] = short
    engine = w.VoskEngine(model)
    recs = recordings(folder, per_wake, per_ordinary)
    hits, false, heard = defaultdict(lambda: [0, 0]), Counter(), defaultdict(Counter)
    for name, f in recs["wake"]:
        woke, text = listen(engine, f)
        hits[name][0] += woke
        hits[name][1] += 1
        if not woke:
            heard[name][text or "-"] += 1
    for name, f in recs["ordinary"]:
        woke, text = listen(engine, f)
        if woke:
            false[name] += 1
            heard[name][text] += 1
    lead = sum(v[0] for k, v in hits.items() if k not in ALONE), sum(v[1] for k, v in hits.items() if k not in ALONE)
    alone = sum(v[0] for k, v in hits.items() if k in ALONE), sum(v[1] for k, v in hits.items() if k in ALONE)
    n = len(recs["ordinary"])
    print(f'"Also wake on just Gink": {"on" if short else "off"}   ({len(recs["wake"])} wake recordings, {n} ordinary ones)')
    print(f"  after hey/hi/okay : {lead[0]}/{lead[1]}  ({100 * lead[0] // lead[1]}%)")
    print(f"  the name alone    : {alone[0]}/{alone[1]}  ({100 * alone[0] // alone[1]}%)")
    print(f"  FALSE wakes       : {sum(false.values())}/{n}  ({100 * sum(false.values()) / n:.1f}%)")
    for k, (a, b) in hits.items():
        miss = f"   missed as: {dict(heard[k].most_common(3))}" if heard[k] else ""
        print(f"    {k:<20} {a:>2}/{b}{miss}")
    for name, c in false.most_common(show):
        print(f"    false x{c}: {name!r} heard as {dict(heard[name].most_common(2))}")
    return {"lead": lead, "alone": alone, "false": sum(false.values()), "ordinary": n}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", required=True, help="the vosk-model-small-en-us-0.15 folder")
    ap.add_argument("--recordings", default=os.path.join(HERE, "recordings"), help="where the generated .wav files are kept")
    ap.add_argument("--quick", action="store_true", help="fewer recordings (about a minute)")
    a = ap.parse_args()
    for tool in ("espeak-ng", "ffmpeg"):
        if subprocess.run(["which", tool], capture_output=True).returncode:
            sys.exit(f"{tool} is needed: brew install espeak-ng ffmpeg  (Linux: sudo apt install espeak-ng ffmpeg)")
    per = (8, 2) if a.quick else (24, 4)
    for short in (True, False):
        run(os.path.expanduser(a.model), a.recordings, per[0], per[1], short)
        print()
