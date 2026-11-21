"""0.1.160 fixes: Gink knows which device it's on and checks it itself ("do a check now" runs a real check instead of
giving steps), knows its own website and source code, answered question cards stay answered when a chat is opened
again (and the AI reads them as answers), Markdown tables and lists right after a sentence render, a question sent
twice is kept once, and the Catalina build can hear the microphone (Info.plist privacy texts)."""
import json, os, plistlib, re, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---------------------------------------------------------------- which device, and checking it
def test_the_ai_is_told_which_device_it_runs_on(monkeypatch):
    from ginkassistant.services import device_info
    monkeypatch.setattr(device_info, "_cache", {"os": "macOS 10.15.7 (Catalina)", "model": "MacBook Air", "laptop": True,
                                                "chip": "Intel Core i5", "memory": "8 GB"})
    assert device_info.describe() == "a MacBook Air (a laptop) with macOS 10.15.7 (Catalina), Intel Core i5, 8 GB of memory"
    note = device_info.prompt_note()
    assert "MacBook Air" in note and "never ask which operating system" in note and "device_check" in note
    from ginkassistant.services.groq_worker import GroqBrain
    brain = GroqBrain.__new__(GroqBrain)
    brain.memory_provider = brain.reply_language_note = None
    brain.city_fn = lambda: ""
    prompt = brain._with_memory("You are Gink.")
    assert "MacBook Air" in prompt and "https://github.com/Amgib00/GinkAssistant" in prompt
    from ginkassistant.services.actions import agent
    system = agent._system_prompt()
    assert "MacBook Air" in system and "https://amgib00.github.io/GinkAssistant/" in system and "device_check" in system
    monkeypatch.setattr(device_info, "_cache", {"os": "Android 12", "model": "TECNO BF6", "phone": True})
    assert "device_check" not in device_info.prompt_note() and "TECNO BF6 (a phone or tablet)" in device_info.prompt_note()


def test_gink_knows_its_own_links_everywhere():
    from ginkassistant.services.about_gink import ABOUT_GINK, SOURCE, WEBSITE
    bridge = read("webapp", "bridge.js")
    assert json.loads(re.search(r"var ABOUT_GINK = (\".*?\");\n", bridge).group(1)) == ABOUT_GINK   # the web app: same words
    assert "deviceNote() + \" \" + ABOUT_GINK" in bridge and "function deviceNote()" in bridge
    assert SOURCE == "https://github.com/Amgib00/GinkAssistant" and WEBSITE.endswith("/GinkAssistant/")
    from ginkassistant.services import backend_server as b
    assert SOURCE in b._about_gink_note() and "About Gink" in b._about_gink_note()                 # Genie
    assert "about_gink.py ./about_gink.py" in read("deploy", "Dockerfile")


def test_do_a_check_runs_the_check(monkeypatch, tmp_path):
    import asyncio
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner, agent, health, quick_parse
    for text in ("do a check now please", "Do a check now", "check my computer", "run a full scan", "health check"):
        assert quick_parse.parse(text) == ("device_check", {}), text
        assert agent.looks_like_action(text), text
    for text in ("why is my laptop so slow", "which device am I using", "how much storage do I have"):
        assert agent.looks_like_action(text), text
    assert quick_parse.parse("check the weather") != ("device_check", {})
    monkeypatch.setattr(health, "check_device", lambda updates=False: {
        "ok": True, "message": "", "summary": "1 thing to look at",
        "report": {"device": "MacBook Air", "system": "macOS 10.15.7", "storage": "12 GB free of 121 GB"},
        "issues": [{"level": "warn", "what": "macOS 10.15 no longer gets security updates.", "fix": "Use a supported browser."}]})
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    r = asyncio.run(TaskAgent(runner, api_key="").run("do a check now please"))
    assert "Your device check" in r.text and "12 GB free" in r.text and "no longer gets security updates" in r.text
    from ginkassistant.services.actions.tools import TOOL_SPECS
    spec = [t for t in TOOL_SPECS if t["function"]["name"] == "device_check"][0]["function"]
    assert "read-only" in spec["description"] and "updates" in spec["parameters"]["properties"]


def test_a_real_check_of_this_computer_is_read_only_and_shaped():
    from ginkassistant.services.actions import health
    r = health.check_device()
    assert r["ok"] is True and isinstance(r["report"], dict) and isinstance(r["issues"], list)
    assert all({"level", "what", "fix"} <= set(i) for i in r["issues"])
    assert health.format_report(r).startswith("**Your device check**")
    assert health._days(1800) == "less than an hour" and health._days(3 * 86400) == "3 days"


# ---------------------------------------------------------------- question cards
def test_answered_question_cards_stay_answered(tmp_path):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    from ginkassistant.ui.web_chat_view import _build_page_html
    from ginkassistant.services.markdown_render import render_markdown_body
    ask = render_markdown_body('A couple of questions first.\n\n```ask\n{"questions": [{"q": "Which laptop?", "options": '
                               '["MacBook Air", "Windows laptop"]}, {"q": "How old is it?", "options": ["New", "Over 5 years"]}]}\n```')
    f = tmp_path / "page.html"
    f.write_text(_build_page_html("Hi", "x"), encoding="utf-8")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no browser here: {exc}")
        page = browser.new_page()
        page.goto(f.as_uri())
        sent = page.evaluate("""([html]) => { window.__sent = []; window.ginkEmit = (k, v) => window.__sent.push([k, v]);
            addAssistantMessage('m1', ''); finalizeMessage('m1', html); return true; }""", [ask])
        assert sent and page.locator(".qcard:not(.done)").count() == 1
        page.locator(".qcard .qo", has_text="MacBook Air").click()
        page.locator(".qcard .qo", has_text="Over 5 years").click()
        page.locator(".qcard .qsend").click()
        msg = page.evaluate("window.__sent[0][1]")
        assert msg == "My answers:\n• Which laptop? → MacBook Air\n• How old is it? → Over 5 years"
        # opening the chat again: the card is drawn again, then the message after it closes it with its answers
        page.goto(f.as_uri())
        page.evaluate("""([html, msg]) => { addAssistantMessage('m1', ''); finalizeMessage('m1', html); addUserMessage(msg); }""",
                      [ask, msg])
        assert page.locator(".qcard.done").count() == 1 and page.locator(".qcard:not(.done)").count() == 0
        answers = page.locator(".qcard.done .qans").all_inner_texts()
        assert answers == ["Which laptop? — MacBook Air", "How old is it? — Over 5 years"]
        # an older chat ("Q A" lines) and a chat where the person typed something else instead
        page.goto(f.as_uri())
        page.evaluate("""([html]) => { addAssistantMessage('m1', ''); finalizeMessage('m1', html);
            addUserMessage('Which laptop? Windows laptop\\nHow old is it? New'); }""", [ask])
        assert page.locator(".qcard.done .qans").all_inner_texts()[0] == "Which laptop? — Windows laptop"
        browser.close()
    from ginkassistant.services.groq_worker import DEFAULT_SYSTEM_PROMPT
    assert '"My answers:"' in DEFAULT_SYSTEM_PROMPT and '\\"My answers:\\"' in read("webapp", "bridge.js")


# ---------------------------------------------------------------- Markdown, history
def test_tables_and_lists_right_after_a_sentence_render():
    from ginkassistant.services.markdown_render import render_markdown_body
    html = render_markdown_body("Here is the comparison:\n| Model | RAM |\n|---|---|\n| Air | 8 GB |\nThat's all.\n"
                                "Steps:\n- Open Settings\n- Click Update\n1. First\n2. Second")
    assert "<table>" in html and "<td>Air</td>" in html and "| Model |" not in html
    assert "<li>Open Settings</li>" in html and "<li>First</li>" in html
    assert "<td>That" not in html and "That" in html
    code = render_markdown_body("Run:\n```bash\necho a\n- not a list\n| not | a table |\n```")
    plain = re.sub(r"<[^>]+>", "", code)
    assert "- not a list\n| not | a table |" in plain and "<li>" not in code and "<table>" not in code   # code: untouched
    nested = render_markdown_body("- Mac\n  - Catalina\n  - Sonoma\n- Windows")
    assert "<li>Mac<ul>\n<li>Catalina</li>" in nested                                    # 2-space sub-lists nest


def test_a_question_sent_twice_is_kept_once(tmp_path):
    from ginkassistant.services.history import HistoryStore
    app = types.SimpleNamespace(paths=types.SimpleNamespace(data=tmp_path))
    h = HistoryStore(app)
    for role, text in (("user", "which device i'm using"), ("user", "which device i'm using"), ("assistant", "A MacBook Air."),
                       ("user", "thanks"), ("assistant", "You're welcome."), ("user", "thanks")):
        h.save_message("s1", role, text)
    import sqlite3
    rows = sqlite3.connect(h.db_path).execute("SELECT role, content FROM chat_history WHERE session_id='s1' ORDER BY id").fetchall()
    assert [r[1] for r in rows] == ["which device i'm using", "A MacBook Air.", "thanks", "You're welcome.", "thanks"]


# ---------------------------------------------------------------- "Hey Gink can't hear you" on Catalina
def test_mac_privacy_texts_reach_info_plist(tmp_path):
    import mac_permissions as mp
    entries = mp.wanted()
    assert entries["NSMicrophoneUsageDescription"].startswith("Gink uses the microphone")
    assert "NSCameraUsageDescription" in entries and "NSAppleEventsUsageDescription" in entries
    saved = mp.tomllib
    try:
        mp.tomllib = None                                                     # Python 3.10 without tomli: same answer
        assert mp.wanted() == entries
    finally:
        mp.tomllib = saved
    app = tmp_path / "Gink.app" / "Contents"
    app.mkdir(parents=True)
    with open(app / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleIdentifier": "com.amgib.ginkassistant"}, f)
    assert sorted(mp.apply(str(tmp_path / "Gink.app"), entries)) == sorted(entries)
    assert mp.apply(str(tmp_path / "Gink.app"), entries) == []                 # nothing left to change
    with open(app / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleIdentifier"] == "com.amgib.ginkassistant" and info["NSMicrophoneUsageDescription"] == entries["NSMicrophoneUsageDescription"]
    assert mp.main([str(tmp_path / "nowhere.app")]) == 2
    flow = read(".github", "workflows", "macos-catalina.yml")
    assert 'python tools/mac_permissions.py "$APP"' in flow and "tools/mac_permissions.py" in read("tools", "MANIFEST.txt")
    from ginkassistant.services import wake_status
    silent = types.SimpleNamespace(running=True, silent=True, error="", paused=False)
    d = wake_status.describe(enabled=True, supported=True, listener=silent)
    assert d["label"] == "Hey Gink can’t hear you" and "update Gink and open it again" in d["detail"]


# ---------------------------------------------------------------- code blocks in Gink Genie too
def test_genie_answers_get_formatted_code_blocks(tmp_path, monkeypatch):
    genie = read("src", "ginkassistant", "services", "web_app", "genie.html")
    for text in ("function formatAnswer(box, entry)", 'api("/render", { body: { items:', "window.copyCodeBlock = function (btn)",
                 "window.downloadCodeBlock = function (btn)", 'if (entry.kind === "g") formatAnswer(body, entry);',
                 'enumerable: false });   // not saved', "/*__GINK_CODE_CSS__*/"):
        assert text in genie, text
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "g.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    from ginkassistant.services.markdown_render import code_css_for_media
    page = TestClient(b.app).get("/genie").text
    assert "/*__GINK_CODE_CSS__*/" not in page and "@media (prefers-color-scheme: dark) { .codehilite {" in page
    assert code_css_for_media().count("--tk-kw:") == 2 and "body.theme-dark" not in code_css_for_media()
