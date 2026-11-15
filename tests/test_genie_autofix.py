"""Genie fixes its own mistakes: before answering it checks that every file its pages link to exists (and creates
missing ones); after answering, the page checks the live preview and asks Genie to fix errors by itself."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from test_genie import SCRIPT, SEEN, call      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_finding_missing_linked_files(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "site"}).json()["project"]["id"]
    b._genie_write(pid, "index.html", '<link rel="stylesheet" href="style.css"><script src="js/app.js"></script>'
                   '<img src="img/logo.png"><a href="https://example.com">x</a><script src="//cdn.example.com/x.js"></script>'
                   '<img src="data:image/png;base64,AAA">')
    b._genie_write(pid, "js/app.js", "import {x} from './util.js'; console.log(x)")
    missing = b._genie_missing_refs(pid)
    assert missing == ["style.css (linked from index.html)", "img/logo.png (linked from index.html)",
                       "js/util.js (linked from js/app.js)"]


def test_genie_creates_the_files_it_forgot_before_answering(genie_srv):
    """The owner's screenshot: index.html linked style.css and script.js, which were never written."""
    b, c, h = genie_srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html",
                  content='<link rel="stylesheet" href="style.css"><h1>John</h1><script src="script.js"></script>')]},
                 {"content": "Your portfolio is ready."},                                       # forgot the 2 files
                 {"content": "", "tool_calls": [call("write_file", path="style.css", content="h1{color:teal}"),
                                                call("write_file", path="script.js", content="console.log('hi')")]},
                 {"content": "Your portfolio is ready, with its styles and script."}]
    r = c.post("/genie/projects", headers=h, json={"prompt": "Make a personal portfolio website"}).json()
    paths = sorted(f["path"] for f in r["files"])
    assert paths == ["index.html", "script.js", "style.css"]
    nudge = [m["content"] for m in SEEN[2]["messages"] if m["role"] == "user"][-1]
    assert "style.css (linked from index.html)" in nudge and "script.js (linked from index.html)" in nudge
    assert any(s["kind"] == "check" and "2 missing files" in s["title"] for s in r["result"]["steps"])
    assert r["result"]["reply"] == "Your portfolio is ready, with its styles and script."


def test_it_gives_up_after_a_few_rounds(genie_srv, monkeypatch):
    b, c, h = genie_srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html", content='<script src="x.js"></script>')]}] + \
                [{"content": "Done (still no x.js)."}] * (b.GENIE_AUTOFIX_ROUNDS + 1)
    r = c.post("/genie/projects", headers=h, json={"prompt": "Make a page"}).json()
    checks = [s for s in r["result"]["steps"] if s["kind"] == "check"]
    assert len(checks) == b.GENIE_AUTOFIX_ROUNDS and r["result"]["reply"] == "Done (still no x.js)."


def test_plan_mode_and_questions_dont_trigger_it(genie_srv):
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "p"}).json()["project"]["id"]
    b._genie_write(pid, "index.html", '<script src="missing.js"></script>')
    SCRIPT[:] = [{"content": "It's a small page."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "What does this project do?"}).json()
    assert not any(s["kind"] == "check" for s in r["steps"])                        # nothing changed: no nudge


def test_the_page_fixes_preview_errors_by_itself():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    assert "AUTOFIX_MAX = 3" in page and "autoCheckPreview(j.changes);" in page and 'id="autofix-btn"' in page
    assert 'localStorage.setItem("genie_autofix"' in page and "AUTOFIX.rounds = 0;" in page


def test_broken_json_and_python_are_caught_before_answering(genie_srv):
    """High, long, large auto-fix: a changed file that its own language can't read is caught without running anything,
    Genie gets up to 6 rounds, and is told to change approach when the same problem comes back."""
    b, c, h = genie_srv
    pid = c.post("/genie/projects", headers=h, json={"name": "p"}).json()["project"]["id"]
    b._genie_write(pid, "data.json", '{"a": 1,}')
    b._genie_write(pid, "app.py", "def f(:\n    pass\n")
    b._genie_write(pid, "ok.py", "print('fine')\n")
    probs = b._genie_file_problems(pid, [{"path": "data.json"}, {"path": "app.py"}, {"path": "ok.py"}, {"path": "gone.txt"}])
    assert len(probs) == 2 and probs[0].startswith("app.py: Python syntax error") and "line 1" in probs[0]
    assert probs[1].startswith("data.json: not valid JSON")
    assert b.GENIE_AUTOFIX_ROUNDS == 6
    b._genie_write(pid, "data.json", '{"a": 1}')                  # the whole project is checked now: start clean
    b._genie_write(pid, "app.py", "def f():\n    pass\n")

    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="config.json", content='{"name": "x",}')]},
                 {"content": "Saved the config."},                                           # still broken
                 {"content": "", "tool_calls": [call("write_file", path="config.json", content='{"name": "x",}')]},
                 {"content": "Saved again."},                                                # the same problem again
                 {"content": "", "tool_calls": [call("write_file", path="config.json", content='{"name": "x"}')]},
                 {"content": "The config is valid now."}]
    r = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "Add a config file"}).json()
    assert r["reply"] == "The config is valid now."
    checks = [s for s in r["steps"] if s["kind"] == "check"]
    assert len(checks) == 2 and "not valid JSON" in checks[0]["output"]
    nudges = [m["content"] for m in SEEN[-1]["messages"] if m["role"] == "user" and m["content"].startswith("Before you finish")]
    assert "SAME problems" not in nudges[0] and "SAME problems" in nudges[1]              # second time: change approach


def test_deep_mode_in_the_page():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "genie.html"), encoding="utf-8").read()
    assert "AUTOFIX_LEVELS = { off: 0, on: 3, deep: 8 }" in page and '{ on: "deep", deep: "off", off: "on" }' in page
    assert "SAME errors as after your last fix" in page
