"""Growing the Gink dataset: GPT-OSS rewrites that can't change the answer, people's examples, and a
held-out set that stays the same."""
import csv
import json
import os
import subprocess
import sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
DS = os.path.join(ROOT, "tools", "gink_dataset")
sys.path.insert(0, DS)
import pytest
import paraphrase as pp


def test_checks_keep_the_facts():
    assert pp.problems("Wake me up at 6:30 am for the gym", "Could you get me up at 6:30 am? Gym day.", "en") == []
    assert "lost '6:30'" in pp.problems("Wake me up at 6:30 am", "Wake me up at 7:30 am", "en")
    assert "lost 'am'" in pp.problems("Wake me up at 6:30 am", "Wake me up at 6:30 in the evening", "en")
    assert any("added numbers" in p for p in pp.problems("Set a timer for 5 minutes", "Set 2 timers for 5 minutes", "en"))
    assert "lost 'euros'" in pp.problems("How much is 100 euros in CFA francs?", "Convert 100 dollars to CFA francs", "en")
    assert "lost 'tomorrow'" in pp.problems("Remind me to call mum tomorrow at 9 am", "Remind me to call mum at 9 am", "en")
    assert "lost 'dakar'" in pp.problems("What's the weather in Dakar?", "What's the weather like?", "en")
    assert "lost 'demain'" in pp.problems("Rappelle-moi demain à 9h d'appeler maman", "Rappelle-moi à 9h d'appeler maman", "fr")
    assert pp.problems("Réveille-moi à 6h30", "Tu peux me réveiller à 6h30 ?", "fr") == []
    assert "doesn't look French" in pp.problems("Réveille-moi à 6h30", "Wake me at 6h30", "fr")
    assert "same as the original" in pp.problems("Set an alarm for 7 am", "set an alarm for 7 am!", "en")


def test_run_writes_reviewable_rows_and_resumes(tmp_path):
    train = tmp_path / "train.jsonl"
    rows = [{"category": "action", "language": "en", "messages": [{"role": "system", "content": "s"},
             {"role": "user", "content": "Wake me up at 6:30 am"}]},
            {"category": "action", "language": "en", "messages": [{"role": "system", "content": "s"},
             {"role": "user", "content": "Set a timer for 5 minutes"}]},
            {"category": "identity", "language": "en", "messages": [{"role": "user", "content": "Who are you?"}]}]
    train.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    asked = []

    def fake(base, key, model, text, lang, n):
        asked.append(text)
        if "6:30" in text:
            return ["Get me up at 6:30 am please", "Wake me at 7 am", "Get me up at 6:30 am please"]
        raise OSError("rate limited")
    out = tmp_path / "p.csv"
    assert pp.main(["--train", str(train), "--csv", str(out), "--key", "k"], ask_fn=fake) == 0
    got = list(csv.DictReader(open(out, encoding="utf-8")))
    assert [(r["original"], r["paraphrase"], r["approved"]) for r in got] == \
        [("Wake me up at 6:30 am", "Get me up at 6:30 am please", "yes")]            # wrong time + duplicate dropped
    assert asked == ["Wake me up at 6:30 am", "Set a timer for 5 minutes"]           # identity rows untouched
    asked.clear()
    pp.main(["--train", str(train), "--csv", str(out), "--key", "k"], ask_fn=fake)
    assert asked == ["Set a timer for 5 minutes"]                                    # resumes where it stopped
    assert pp.approved_map(str(out)) == {"Wake me up at 6:30 am": ["Get me up at 6:30 am please"]}


def _generate(env, out_dir):
    e = dict(os.environ, **env)
    subprocess.run([sys.executable, os.path.join(DS, "generate.py")], check=True, capture_output=True, env=e)
    return {n: [json.loads(l) for l in open(os.path.join(out_dir, n), encoding="utf-8")] for n in ("train.jsonl", "eval.jsonl")}


def test_generator_uses_rewrites_for_training_only(tmp_path):
    out = os.path.join(DS, "out")
    try:
        plain = _generate({"GINK_PARAPHRASES": str(tmp_path / "none.csv"), "GINK_GENERAL_CSV": str(tmp_path / "none2.csv")}, out)
        train_user = next(m["content"] for r in plain["train.jsonl"] if r["category"] == "action"
                          for m in r["messages"] if m["role"] == "user")
        eval_user = next(m["content"] for r in plain["eval.jsonl"] if r["category"] == "action"
                         for m in r["messages"] if m["role"] == "user")
        p = tmp_path / "p.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=pp.FIELDS); w.writeheader()
            w.writerow({"language": "en", "original": train_user, "paraphrase": "REWRITE-A", "model": "m", "approved": "yes"})
            w.writerow({"language": "en", "original": train_user, "paraphrase": "REWRITE-NO", "model": "m", "approved": "no"})
            w.writerow({"language": "en", "original": eval_user, "paraphrase": "REWRITE-EVAL", "model": "m", "approved": "yes"})
        g = tmp_path / "g.csv"
        with open(g, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["language", "category", "user_message", "gink_reply", "author", "reviewer", "approved"])
            w.writerow(["en", "general", "Q-APPROVED", "A-APPROVED", "a", "b", "yes"])
            w.writerow(["fr", "safety", "Q-NOT-YET", "A", "a", "", "no"])
        grown = _generate({"GINK_PARAPHRASES": str(p), "GINK_GENERAL_CSV": str(g)}, out)
        users = lambda rows: [m["content"] for r in rows for m in r["messages"] if m["role"] == "user"]
        added = [r for r in grown["eval.jsonl"] if r not in plain["eval.jsonl"]]
        assert all(r in grown["eval.jsonl"] for r in plain["eval.jsonl"])             # the held-out set doesn't move...
        assert all(r["category"] == "general" for r in added)                          # ...new rows may join it
        n_copies = users(plain["train.jsonl"]).count(train_user)
        assert users(grown["train.jsonl"]).count("REWRITE-A") == n_copies
        assert "REWRITE-NO" not in users(grown["train.jsonl"])                         # rejected by a person
        assert "REWRITE-EVAL" not in users(grown["eval.jsonl"])                         # held-out examples stay as they are
        assert users(grown["train.jsonl"]).count("REWRITE-EVAL") == users(plain["train.jsonl"]).count(eval_user)
        assert "Q-APPROVED" in users(grown["train.jsonl"] + grown["eval.jsonl"]) and "Q-NOT-YET" not in users(grown["train.jsonl"])
        r = subprocess.run([sys.executable, os.path.join(DS, "validate.py")], capture_output=True, text=True)
        assert r.returncode == 0 and "rewrites from paraphrases.csv" in r.stdout
    finally:
        import shutil
        shutil.rmtree(out, ignore_errors=True)


def test_owners_data_is_never_in_an_update_package():
    """People's examples, rewrites and translations are written on the owner's computer: an update
    package must never contain them (unzipping it would overwrite them); publishing sends the owner's."""
    manifest = open(os.path.join(ROOT, "tools", "MANIFEST.txt"), encoding="utf-8").read().split()
    for f in ("tools/gink_dataset/paraphrases.csv", "tools/gink_dataset/translations.csv",
              "tools/gink_dataset/examples_general.csv", "tools/gink_dataset/languages/wolof.csv"):
        assert f not in manifest
    script = open(os.path.join(ROOT, "tools", "publish_to_github.sh"), encoding="utf-8").read()
    for f in ("tools/gink_dataset/paraphrases.csv", "tools/gink_dataset/translations.csv",
              "tools/gink_dataset/examples_general.csv", "tools/gink_dataset/languages"):
        assert f in script.split("OWNER_DATA=(", 1)[1].split(")", 1)[0]


def test_placeholder_keys_and_certificates(monkeypatch):
    """Mac python.org Python has no certificates of its own (CERTIFICATE_VERIFY_FAILED); and
    `GROQ_API_KEY=...` copied literally is not a key."""
    import evaluate
    for mod in (pp, evaluate):
        assert mod.real_key("...") == "" and mod.real_key("<your key>") == "" and mod.real_key("gsk_abc") == "gsk_abc"
        import certifi
        import ssl
        seen = {}
        real = ssl.create_default_context
        monkeypatch.setattr(ssl, "create_default_context", lambda cafile=None: seen.update(cafile=cafile) or real(cafile=cafile))
        mod.ssl_context()
        assert seen["cafile"] == certifi.where()
        monkeypatch.setattr(ssl, "create_default_context", real)


def test_refused_key_is_explained(tmp_path, capsys):
    import urllib.error
    train = tmp_path / "train.jsonl"
    train.write_text(json.dumps({"category": "action", "language": "en", "messages": [
        {"role": "system", "content": "s"}, {"role": "user", "content": "Wake me up at 6:30 am"}]}), encoding="utf-8")

    import io as _io

    def refused(*a):
        raise urllib.error.HTTPError("https://api.groq.com", 401, "Unauthorized", {},
                                     _io.BytesIO(b'{"error": {"message": "Invalid API Key", "code": "invalid_api_key"}}'))
    pp.main(["--train", str(train), "--csv", str(tmp_path / "p.csv"), "--key", "gsk_wrong_but_long_enough_1234"], ask_fn=refused)
    out = capsys.readouterr().out
    assert "Groq refused the key (Invalid API Key)" in out and "--ask-key" in out
    assert "gsk_\u20261234 (30 characters)" in out and "wrong_but" not in out          # masked, never the whole key
    rows = list(csv.DictReader(open(tmp_path / "p.csv", encoding="utf-8")))
    assert rows == []                                                           # nothing marked done: a re-run retries


def test_ask_key_ignores_the_terminals_key(tmp_path, monkeypatch, capsys):
    train = tmp_path / "train.jsonl"
    train.write_text("", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_old_revoked_key_000000")
    typed = []
    monkeypatch.setattr(pp.getpass, "getpass", lambda prompt: typed.append(prompt) or "gsk_new_working_key_999999")
    pp.main(["--train", str(train), "--csv", str(tmp_path / "p.csv"), "--ask-key"], ask_fn=lambda *a: [])
    out = capsys.readouterr().out
    assert typed and "what you typed" in out and "9999" in out
    pp.main(["--train", str(train), "--csv", str(tmp_path / "p.csv")], ask_fn=lambda *a: [])
    assert "GROQ_API_KEY in this Terminal" in capsys.readouterr().out


def test_requests_have_our_own_user_agent(monkeypatch):
    """Cloudflare (in front of Groq) answers Python's default "Python-urllib/3.x" with 403 error 1010."""
    import evaluate
    import io as _io
    import urllib.request
    sent = []

    class Resp(_io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None, context=None):
        sent.append({k.lower(): v for k, v in req.header_items()})
        return Resp(json.dumps({"choices": [{"message": {"content": '{"variants": ["Get me up at 6:30 am"]}'}}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert pp.ask("https://api.groq.com/openai/v1", "gsk_x", "m", "Wake me up at 6:30 am", "en", 1) == ["Get me up at 6:30 am"]
    evaluate.ask("https://api.groq.com/openai/v1", "gsk_x", "m", [{"role": "user", "content": "hi"}], [])
    assert all(h["user-agent"].startswith("GinkDataset/") and "urllib" not in h["user-agent"].lower() for h in sent)


def test_cloudflare_refusal_text_is_shown():
    import io as _io
    import urllib.error
    exc = urllib.error.HTTPError("https://api.groq.com", 403, "Forbidden", {}, _io.BytesIO(b"error code: 1010"))
    assert pp.provider_message(exc) == "error code: 1010"


def test_remember_and_remind_are_different_actions():
    """From the owner's first review: "Reminder: June 19 is my best friend's birthday." for a remember-a-fact
    request would teach the reminder action."""
    assert "turned 'remember' into 'remind'" in pp.problems(
        "Remember that my best friend's birthday is on June 19", "Reminder: June 19 is my best friend's birthday.", "en")
    assert pp.problems("Remember that my best friend's birthday is on June 19",
                       "Please note that my best friend's birthday falls on June 19.", "en") == []
    assert "turned 'remind' into 'remember'" in pp.problems("Rappelle-moi d'appeler maman demain à 9h",
                                                            "Souviens-toi d'appeler maman demain à 9h", "fr")


def test_waits_out_the_rate_limit(monkeypatch):
    import urllib.error
    waits, tries = [], {"n": 0}
    monkeypatch.setattr(pp.time, "sleep", lambda s: waits.append(s))

    def busy_twice():
        tries["n"] += 1
        if tries["n"] <= 2:
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": "7"}, None)
        return ["ok"]
    assert pp.with_retries(busy_twice, out=lambda *a: None) == ["ok"] and waits == [15, 30]
    with pytest.raises(urllib.error.HTTPError):
        pp.with_retries(lambda: (_ for _ in ()).throw(urllib.error.HTTPError("u", 401, "x", {}, None)), out=lambda *a: None)


def test_recheck_applies_new_checks_to_old_rows(tmp_path):
    p = tmp_path / "p.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pp.FIELDS); w.writeheader()
        w.writerow({"language": "en", "original": "Remember that my best friend's birthday is on June 19",
                    "paraphrase": "Reminder: June 19 is my best friend's birthday.", "model": "m", "approved": "yes"})
        w.writerow({"language": "en", "original": "Set an alarm for 9:30 am", "paraphrase": "Alarm 9:30 am, thanks.",
                    "model": "m", "approved": "yes"})
    assert pp.main(["--recheck", "--csv", str(p)]) == 0
    assert [r["approved"] for r in csv.DictReader(open(p, encoding="utf-8"))] == ["no", "yes"]
