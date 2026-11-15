"""The offline "Hey Gink" listener, as measured with tools/wake_bench: single words the model knows (never "gink" or
"jink" themselves -- a word it doesn't know is silently dropped from a phrase), everyday decoy words so ordinary talk
doesn't wake it, "Jink" as well as "Gink", and the name alone only when it's safe."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import pytest
from ginkassistant.services import wake_word as w

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture(autouse=True)
def short_on():
    w.SHORT["on"] = True
    yield
    w.SHORT["on"] = True


def test_only_words_the_model_knows_go_into_the_listener():
    vocabulary = set(w.LEADS + w.NEAR_GINK + w.NEAR_JINK + w.DECOYS) - {"jinn", "genk", "let's"}
    words = w.grammar_words(lambda x: x in vocabulary)
    assert words[-1] == "[unk]" and "jinn" not in words and "genk" not in words and "king" in words and "think" in words
    assert all(" " not in x for x in words)                              # single words: nothing to collapse to "hey"
    everything = w.grammar_words()
    assert "gink" not in everything and "jink" not in everything         # the model has neither (it would drop them)
    assert len(set(everything)) == len(everything)


def test_hey_gink_and_hey_jink():
    for heard in ("hey king", "hi kink", "okay ginkgo", "hey getting", "hey jinx", "hi jing", "hey jank", "okay jinn",
                  "hey gink", "hey jink", "ok jink", "so well hey king what"):
        assert w.matches(heard, final=False), heard
    for heard in ("i think so", "hi kim", "hey kids", "okay thanks", "hey there", "the king", "king", "i like gin",
                  "hey [unk] king", "hey think", "getting what it", "hey"):
        assert not w.matches(heard), heard


def test_the_name_alone():
    assert w.matches("kink") and w.matches("jing") and w.matches("gink") and w.matches("jink")      # said, then a pause
    assert w.matches("getting", final=True) and not w.matches("getting", final=False)               # only once it's final
    assert not w.matches("getting ready", final=True)                                               # ...and the only word
    assert w.matches("kink what", final=False) and not w.matches("kink", final=False)               # still listening: wait
    assert not w.matches("king") and not w.matches("gin") and not w.matches("think")                # too ordinary
    w.SHORT["on"] = False
    assert not w.matches("kink") and not w.matches("getting") and not w.matches("jink") and w.matches("hey jink")


def test_the_engine_asks_the_model_which_words_it_knows(monkeypatch, tmp_path):
    seen = {}

    class Model:
        def __init__(self, path): pass
        def vosk_model_find_word(self, word): return -1 if word in ("genk", "jinn") else 7

    class KaldiRecognizer:
        def __init__(self, model, rate, grammar): seen["grammar"] = grammar
    monkeypatch.setitem(sys.modules, "vosk", types.SimpleNamespace(Model=Model, KaldiRecognizer=KaldiRecognizer, SetLogLevel=lambda n: None))
    engine = w.VoskEngine(str(tmp_path))
    import json
    words = json.loads(seen["grammar"])
    assert words == engine.words and "genk" not in words and "jinn" not in words and "hey" in words and words[-1] == "[unk]"


def test_other_platforms_accept_jink_too():
    from ginkassistant.services import android_voice as a
    for heard in ("hey jink", "hi jink", "okay gink", "Hey, Jink what's up"):          # phones know any word: "jink" itself
        assert a.WAKE_RE.search(heard), heard
    assert not a.WAKE_RE.search("hey king") and not a.WAKE_RE.search("a ginkgo tree")  # real words stay out there
    assert a.WAKE_SHORT_RE.match("jink what time is it") and not a.WAKE_SHORT_RE.match("king of the hill")
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "gink|ginks|king|kink|jink|jinks|jinx|jing|ginkgo|ging" in bridge and "(gink|ginks|jink|jinks|jinx|ginkgo)" in bridge


def test_the_bench_and_the_voice_check_tools():
    sys.path.insert(0, os.path.join(ROOT, "tools", "wake_bench"))
    import bench, wake_check
    assert set(bench.ALONE) <= set(bench.WAKE) and "hey jink" in bench.WAKE and "i think so too" in bench.ORDINARY
    assert len(bench.ORDINARY) == len(set(bench.ORDINARY)) >= 70
    assert wake_check.level(b"\x00\x00" * 100) == 0 and wake_check.level(b"\xff\x7f" * 10) == 100
    assert any(not should for _, should in wake_check.PROMPTS) and sum(1 for p, s in wake_check.PROMPTS if s) >= 5


def test_a_silent_microphone_is_noticed_and_said(monkeypatch):
    """A blocked microphone (macOS without the permission) sends perfect silence instead of failing: Hey Gink would
    wait forever with a green light. The listener watches the level and the chip says what to do."""
    import time
    from ginkassistant.services import wake_status
    engine = types.SimpleNamespace(frame=4000, name="test", process=lambda pcm: False)
    lst = w.WakeWordListener(engine, on_wake=lambda: None, open_stream=lambda frame: None)
    monkeypatch.setattr(lst, "SILENT_AFTER", 0.05)
    lst._note_level(b"\x00\x00" * 4000)
    assert lst.level == 0 and not lst.silent                              # not yet: only just went quiet
    time.sleep(0.08)
    lst._note_level(b"\x00\x00" * 4000)
    assert lst.silent
    lst._thread = types.SimpleNamespace(is_alive=lambda: True)             # "running", for the status text
    st = wake_status.describe(enabled=True, supported=True, listener=lst)
    assert st["state"] == "problem" and "can\u2019t hear you" in st["label"] and "Microphone" in st["detail"]
    lst._note_level((b"\x10\x27" + b"\x00\x00") * 2000)                    # real sound (10000/32768)
    assert not lst.silent and lst.level == 31
    assert wake_status.describe(enabled=True, supported=True, listener=lst)["state"] == "ready"
