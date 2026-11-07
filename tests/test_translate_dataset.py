"""Gink's actions in many languages (tools/gink_dataset/translate.py): only translations that can't
change the action; drafts for languages that need a native speaker; training examples only."""
import csv
import json
import os
import subprocess
import sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
DS = os.path.join(ROOT, "tools", "gink_dataset")
sys.path.insert(0, DS)
import translate as tr


def ex(user, tool, args, reply):
    return {"category": "action", "language": "en", "messages": [
        {"role": "system", "content": "s"}, {"role": "user", "content": user},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                                                              "function": {"name": tool, "arguments": json.dumps(args)}}]},
        {"role": "tool", "tool_call_id": "c1", "name": tool, "content": "ok"},
        {"role": "assistant", "content": reply}]}


WEATHER = ex("What's the weather in Thiès today?", "get_weather", {"place": "Thiès", "day": "today"}, "It's 31°C and sunny in Thiès.")
CURRENCY = ex("How much is 100 euros in CFA francs?", "convert_currency", {"amount": 100, "from_currency": "EUR", "to_currency": "XOF"},
              "100 euros is about 65,595.70 CFA francs.")
REMINDER = ex("Remind me to call mum at 6 pm", "add_reminder", {"text": "call mum", "when": "2026-11-02T18:00"}, "Done.")
TIMER_LABEL = ex("Set a 5 minute timer for the rice", "set_timer", {"seconds": 300, "label": "rice"}, "Timer set.")


def test_which_examples_can_be_translated():
    assert tr.translatable(WEATHER) and tr.translatable(CURRENCY)
    assert not tr.translatable(REMINDER)                     # its own words would change
    assert not tr.translatable(TIMER_LABEL)                  # "rice" would be translated


def test_checks():
    assert tr.problems(WEATHER, "es", "¿Qué tiempo hace hoy en Thiès?", "Hace 31°C y sol en Thiès.") == []
    assert "lost 'Thiès'" in tr.problems(WEATHER, "es", "¿Qué tiempo hace hoy en Thies?", "Hace 31°C.")
    assert "the reply lost numbers" in tr.problems(CURRENCY, "es", "¿Cuánto son 100 euros en francos CFA?", "Unos 65.000 francos.")
    assert any("added numbers" in p for p in tr.problems(CURRENCY, "pt", "Quanto são 100 euros em 2 francos CFA?", "65,595.70"))
    assert "not in ar's script" in tr.problems(CURRENCY, "ar", "How much is 100 euros?", "65,595.70")
    assert tr.problems(CURRENCY, "ar", "كم تساوي 100 يورو بالفرنك الأفريقي؟", "100 يورو تساوي حوالي 65,595.70 فرنك.") == []
    assert "not translated" in tr.problems(WEATHER, "es", "What's the weather in Thiès today?", "31 Thiès")


def test_run_approves_well_supported_and_drafts_the_rest(tmp_path):
    train = tmp_path / "train.jsonl"
    train.write_text("\n".join(json.dumps(r) for r in (WEATHER, REMINDER, CURRENCY)), encoding="utf-8")
    answers = {"Spanish": ("¿Qué tiempo hace hoy en Thiès?", "Hace 31°C y sol en Thiès."),
               "Hausa": ("Yaya yanayi yake a Thiès yau?", "31°C ne a Thiès.")}

    def fake(base, key, model, user, reply, language):
        if "100" in user:
            return ("Cuánto son 100 euros", "unos 65 francos") if language == "Spanish" else ("100 Yuro", "65,595.70")
        return answers[language]
    out = tmp_path / "t.csv"
    assert tr.main(["--languages", "es,ha", "--train", str(train), "--csv", str(out), "--key", "gsk_test_key_123456"], ask_fn=fake) == 0
    rows = {(r["language"], r["original"][:10]): r for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert rows[("es", "What's the")]["approved"] == "yes"
    assert rows[("ha", "What's the")]["approved"] == ""                          # a draft for a Hausa speaker
    assert rows[("es", "How much i")]["approved"] == "no"                        # reply lost 65,595.70
    assert not any(r["original"].startswith("Remind") for r in rows.values())     # never sent
    assert tr.approved_map(str(out)) == {"What's the weather in Thiès today?":
                                         [("es", "¿Qué tiempo hace hoy en Thiès?", "Hace 31°C y sol en Thiès.")]}
    calls = []
    tr.main(["--languages", "es,ha", "--train", str(train), "--csv", str(out), "--key", "gsk_test_key_123456"],
            ask_fn=lambda *a: calls.append(a) or ("x", "y"))
    assert calls == []                                                            # resumes: nothing left to do
    assert tr.main(["--languages", "xx"], ask_fn=fake) == 1                       # unknown code


def test_generator_adds_approved_translations_to_training_only(tmp_path):
    out_dir = os.path.join(DS, "out")
    env = dict(os.environ, GINK_PARAPHRASES=str(tmp_path / "none.csv"), GINK_GENERAL_CSV=str(tmp_path / "none2.csv"),
               GINK_TRANSLATIONS=str(tmp_path / "none3.csv"))
    try:
        subprocess.run([sys.executable, os.path.join(DS, "generate.py")], check=True, capture_output=True, env=env)
        train = [json.loads(l) for l in open(os.path.join(out_dir, "train.jsonl"), encoding="utf-8")]
        first = next(r for r in train if tr.translatable(r))
        user = next(m["content"] for m in first["messages"] if m["role"] == "user")
        t = tmp_path / "t.csv"
        with open(t, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=tr.FIELDS); w.writeheader()
            w.writerow({"language": "es", "original": user, "user": "PETICION-ES", "reply": "RESPUESTA-ES", "model": "m", "approved": "yes"})
            w.writerow({"language": "ha", "original": user, "user": "DRAFT-HA", "reply": "x", "model": "m", "approved": ""})
        env["GINK_TRANSLATIONS"] = str(t)
        subprocess.run([sys.executable, os.path.join(DS, "generate.py")], check=True, capture_output=True, env=env)
        grown = [json.loads(l) for l in open(os.path.join(out_dir, "train.jsonl"), encoding="utf-8")]
        held = [json.loads(l) for l in open(os.path.join(out_dir, "eval.jsonl"), encoding="utf-8")]
        es = [r for r in grown if r.get("language") == "es"]
        assert es and all(any(m.get("content") == "PETICION-ES" for m in r["messages"]) for r in es)
        assert all(r["messages"][-1]["content"] == "RESPUESTA-ES" for r in es)
        assert not any("DRAFT-HA" in json.dumps(r) for r in grown + held)        # drafts unused
        assert not any(r.get("translation") for r in held)
        v = subprocess.run([sys.executable, os.path.join(DS, "validate.py")], capture_output=True, text=True, env=env)
        assert v.returncode == 0 and "in 1 languages (es " in v.stdout, v.stdout[-600:]
    finally:
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)
