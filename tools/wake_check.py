#!/usr/bin/env python3
"""
Test "Hey Gink" with YOUR voice and YOUR microphone, and see exactly what the offline listener hears.

    python tools/wake_check.py                      (in the project's Python: the one that runs Gink)
    python tools/wake_check.py --model ~/path/to/vosk-model-small-en-us-0.15

It asks you to say the wake phrase a few times (and one ordinary sentence), then prints, for each try:
how loud the microphone was, what the listener heard, and whether Gink would have woken.

Reading the result:
  * "microphone is silent"  -> a permission or device problem, not the listener: on a Mac open System Settings >
                              Privacy & Security > Microphone and allow Gink (or Terminal/PyCharm for this test).
  * heard something else    -> send the "heard" words to whoever maintains Gink: they go into wake_word.py's
                              NEAR_GINK / NEAR_JINK lists (and tools/wake_bench checks nothing else breaks).
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

PROMPTS = [("Hey Gink", True), ("Hey Gink", True), ("Hey Gink, what time is it?", True), ("Gink", True), ("Gink", True),
           ("Hi Gink", True), ("Okay Gink", True), ("I think it is going to rain today", False)]


def find_model():
    home = os.path.expanduser("~")
    places = [os.path.join(home, "Library", "Application Support", "*", "models"), os.path.join(home, ".local", "share", "*", "models"),
              os.path.join(home, "AppData", "Local", "*", "*", "models"), os.path.join(home, "AppData", "Roaming", "*", "models"),
              os.path.join(HERE, "..", "models")]
    for pattern in places:
        for folder in glob.glob(os.path.join(pattern, "vosk-model-small-en-us-0.15")):
            if os.path.isdir(os.path.join(folder, "am")):
                return folder
    return ""


def level(pcm: bytes) -> int:
    """Loudest sample as a percentage of full scale (0 = silence)."""
    import array
    a = array.array("h")
    a.frombytes(pcm[:len(pcm) // 2 * 2])
    return round(100 * max((abs(x) for x in a), default=0) / 32768)


def record(seconds: float, rate: int) -> bytes:
    try:
        import sounddevice as sd
        data = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16")
        sd.wait()
        return data.tobytes()
    except ImportError:
        import pyaudio
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, frames_per_buffer=4000)
        out = b"".join(stream.read(4000, exception_on_overflow=False) for _ in range(int(seconds * rate / 4000)))
        stream.close()
        pa.terminate()
        return out


def hear(engine, pcm: bytes):
    """-> (woke, everything heard) for one recording, fed 0.25 s at a time like the microphone."""
    from vosk import KaldiRecognizer
    from ginkassistant.services import wake_word as w
    engine._rec = KaldiRecognizer(engine._model, w.RATE, json.dumps(engine.words))
    heard, woke, step = [], False, engine.frame * 2
    for k in range(0, len(pcm), step):
        chunk = pcm[k:k + step].ljust(step, b"\0")
        final = bool(engine._rec.AcceptWaveform(chunk))
        text = json.loads(engine._rec.Result() if final else engine._rec.PartialResult()).get("text" if final else "partial", "")
        if text and (not heard or heard[-1] != text):
            heard.append(text)
        woke = woke or w.matches(text, final)
    text = json.loads(engine._rec.FinalResult()).get("text", "")
    if text and (not heard or heard[-1] != text):
        heard.append(text)
    return woke or w.matches(text, True), heard


def main(argv=None):
    ap = argparse.ArgumentParser(description="Test Hey Gink with your own voice.")
    ap.add_argument("--model", default="", help="the vosk-model-small-en-us-0.15 folder (found automatically if Gink downloaded it)")
    ap.add_argument("--seconds", type=float, default=3.5)
    a = ap.parse_args(argv)
    from ginkassistant.services import wake_word as w
    model = os.path.expanduser(a.model) if a.model else find_model()
    if not model or not os.path.isdir(model):
        sys.exit("The listener's model wasn't found. Turn on Hey Gink in the app once (it downloads it), or pass --model FOLDER "
                 "(download: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip).")
    engine = w.VoskEngine(model)
    print(f"Listener ready. Words it listens for: {', '.join(x for x in engine.words if x in w.MATCH_WORDS)}\n")
    results = []
    for i, (phrase, should) in enumerate(PROMPTS, 1):
        input(f"[{i}/{len(PROMPTS)}] Press Enter, then say:  \u201c{phrase}\u201d ")
        pcm = record(a.seconds, w.RATE)
        loud = level(pcm)
        woke, heard = hear(engine, pcm)
        if loud < 2:
            verdict = "microphone is silent (permission or device?)"
        elif woke == should:
            verdict = "woke \u2714" if woke else "stayed asleep \u2714 (correct: it's an ordinary sentence)"
        else:
            verdict = "DID NOT WAKE" if should else "WOKE BY MISTAKE"
        print(f"      loudness {loud}%   heard: {heard or ['(nothing)']}   -> {verdict}\n")
        results.append((phrase, should, woke, loud, heard))
        time.sleep(0.2)
    silent = sum(1 for r in results if r[3] < 2)
    good = sum(1 for r in results if r[1] == r[2])
    print(f"Result: {good}/{len(results)} as expected." + (f"  {silent} recordings were silent: check the microphone permission first." if silent else ""))
    print("If it didn't wake: copy the lines above (the 'heard' words) and send them -- they show what to add to the listener.")
    return 0 if good == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
