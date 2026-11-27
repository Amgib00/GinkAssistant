"""0.1.163: Gink is automatic -- an open request is made, not questioned; a typed answer on a question card can be sent;
more kinds of artifacts (React, charts, tables, slides); opened web chats are readable at once with their answered
cards closed; and the website never shows an older page half-styled."""
import base64
import json
import os
import re
import sys
import time
import pytest
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "tools"))


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


needs_browser = pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")


def _launch(p):
    try:
        return p.chromium.launch()
    except Exception as exc:
        pytest.skip(f"no Chromium here ({type(exc).__name__})")


# ---------------------------------------------------------------- the words, the same everywhere
def test_open_requests_are_made_and_the_prompts_match_everywhere():
    from ginkassistant.services import groq_worker as g, backend_server as b
    assert g.ASK_PROMPT in g.DEFAULT_SYSTEM_PROMPT and '"My answers:"' in g.ASK_PROMPT
    for said in ('"make me anything"', '"add more to it"', '"continue"', "don't ask what they want", 'never an \\"Other\\" option'.replace("\\", "")):
        assert said in g.ASK_PROMPT, said
    assert "ask a follow-up question when it would help rather than guessing" not in g.DEFAULT_SYSTEM_PROMPT
    js = read("webapp", "bridge.js")
    line = next(x for x in js.splitlines() if x.strip().startswith("var ASK_PROMPT = "))
    assert json.loads(line.split("= ", 1)[1].rstrip(";")) == g.ASK_PROMPT and '" " + ASK_PROMPT' in js
    assert "When you genuinely need the person" not in js                      # the old words, gone everywhere
    # artifacts: the new kinds, and never "save the snippet as index.html"
    assert b.ARTIFACT_PROMPT == g.ARTIFACT_PROMPT
    for kind in ('```jsx title=\\"Habit tracker\\"', '```chart title=\\"Sales by month\\"', '```csv title=\\"Budget\\"',
                 '```slides title=\\"Pitch\\"'):
        assert kind.replace("\\", "") in g.ARTIFACT_PROMPT, kind
    assert "never tell them to save, copy or paste it into a file" in g.ARTIFACT_PROMPT
    assert "keeping everything that was there" in g.ARTIFACT_PROMPT and "no lorem ipsum" in g.ARTIFACT_PROMPT


def test_the_sdks_and_cli_know_the_new_kinds(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "cli"))
    from gink.client import artifacts
    text = ('```jsx title="Habit tracker"\nexport default function App() { return <p>Hi</p>; }\n```\n'
            '```chart title="Sales"\n{"type": "bar", "data": {"labels": ["Jan"], "datasets": [{"data": [3]}]}}\n```\n'
            '```csv title="Budget"\nItem,Cost\nRent,1200\n```\n```slides title="Pitch"\n# Gink\n\n---\n\n## Why\n```')
    got = [(a["kind"], a["filename"]) for a in artifacts(text)]
    assert got == [("react", "habit-tracker.jsx"), ("chart", "sales.json"), ("table", "budget.csv"), ("slides", "pitch.md")]
    js = read("sdk", "js", "index.js")
    assert 'jsx: "react"' in js and 'csv: "table"' in js and 'slides: "slides"' in js and 'chart: "chart"' in js
    assert '"react" | "chart" | "table" | "slides"' in read("sdk", "js", "index.d.ts")
    assert 'extra={"gink_fit": True}' in read("cli", "gink_cli", "main.py")


# ---------------------------------------------------------------- the chat page (apps and web app)
def _chat_page(tmp_path):
    from ginkassistant.ui.web_chat_view import _build_page_html
    f = tmp_path / "page.html"
    f.write_text(_build_page_html("Hi", "x"), encoding="utf-8")
    return f.as_uri()


@needs_browser
def test_a_typed_answer_on_a_question_card_is_sent(tmp_path):
    from ginkassistant.services.markdown_render import render_markdown_body
    ask = render_markdown_body('Sure, a quick choice first.\n\n```ask\n{"questions": [{"q": "Choose the type of artifact you want:", '
                               '"options": ["A short story", "A simple HTML web page", "Other (type your own)", "a short story"]}]}\n```')
    with _browser()() as p:
        b = _launch(p)
        pg = b.new_page()
        pg.goto(_chat_page(tmp_path))
        pg.evaluate("""([h]) => { window.__sent = []; window.ginkEmit = (k, v) => window.__sent.push([k, v]);
                        addAssistantMessage('m1', ''); finalizeMessage('m1', h); }""", [ask])
        assert pg.locator(".qcard .qo").all_inner_texts() == ["A short story", "A simple HTML web page"]   # no "Other", no twice
        send = pg.locator(".qcard .qsend")
        assert send.is_disabled()
        pg.locator(".qcard .qe input").click()
        pg.keyboard.type("Any you choose")
        assert not send.is_disabled()                       # before 0.1.163 it stayed greyed out: nothing could be sent
        send.click()
        assert pg.evaluate("window.__sent") == [["send", "My answers:\n• Choose the type of artifact you want: → Any you choose"]]
        assert pg.locator(".qcard.done .qans").all_inner_texts() == ["Choose the type of artifact you want: — Any you choose"]
        # Enter sends it too; choosing an option again lets a typed answer go
        pg.evaluate("""([h]) => { window.__sent = []; addAssistantMessage('m2', ''); finalizeMessage('m2', h); }""", [ask])
        inp = pg.locator(".qcard:not(.done) .qe input")
        inp.fill("A poem about Freetown")
        inp.press("Enter")
        assert pg.evaluate("window.__sent")[0][1].endswith("→ A poem about Freetown")
        b.close()


@needs_browser
def test_quick_formatting_is_safe_and_readable(tmp_path):
    with _browser()() as p:
        b = _launch(p)
        pg = b.new_page()
        pg.goto(_chat_page(tmp_path))
        html = pg.evaluate("""() => quickMarkdown('Here is **bold**, *it*, `<b>code</b>` and [a link](https://example.org/?a=1&b=2) and ' +
            '[bad](javascript:alert(1))\\n\\n# Title\\n\\n- one\\n- two\\n\\n1. a\\n2. b\\n\\n<img src=x onerror=alert(1)>\\n\\n' +
            '| A | B |\\n|---|---|\\n| 1 | 2 |\\n\\n```js\\nlet x = \"<b>\";\\n```')""")
        assert "<strong>bold</strong>" in html and "<em>it</em>" in html and "<code>&lt;b&gt;code&lt;/b&gt;</code>" in html
        assert '<a href="https://example.org/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">a link</a>' in html
        assert "javascript:" not in html and "<img src=x" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
        assert "<h1>Title</h1>" in html and "<ul><li>one</li><li>two</li></ul>" in html and "<ol><li>a</li><li>b</li></ol>" in html
        assert "<td>1</td>" in html and '<pre><code class="language-js">let x = &quot;&lt;b&gt;&quot;;</code></pre>' in html
        # an answer as it arrives (the web app): formatted, the artifact being written shown by its name
        pg.evaluate("""() => { addAssistantMessage('m3', ''); setQuickText('m3', 'Working on **it**\\n\\n```html title=\"Portfolio\"\\n<div>'); }""")
        pg.wait_for_timeout(120)
        assert pg.inner_html("#m3 .stream").startswith("<p>Working on <strong>it</strong></p>")
        assert "Making “Portfolio”" in pg.inner_text("#m3 .stream") and pg.locator("#m3 .gink-spin").count() == 1
        b.close()


@needs_browser
def test_tables_and_slides_preview_and_react_and_charts_load_their_libraries(tmp_path):
    from ginkassistant.services.markdown_render import render_markdown_body
    arts = render_markdown_body(
        'A tracker:\n\n```jsx title="Habit tracker"\nimport React, { useState } from "react";\nexport default function App() {\n'
        '  const [n, setN] = useState(0);\n  return <button onClick={() => setN(n + 1)}>Done {n} times</button>;\n}\n```\n\n'
        'Sales:\n\n```chart title="Sales by month"\n{"type": "bar", "data": {"labels": ["Jan", "Feb"], "datasets": [{"label": "Freetown", "data": [12, 19]}]}}\n```\n\n'
        'Budget:\n\n```csv title="Budget"\nItem,Cost (Le),Month\nRent,"1,200",Jan\nFood,450,Jan\nTransport,120,Feb\n```\n\n'
        'Deck:\n\n```slides title="Pitch"\n# Gink\nAn assistant for everyone\n\n---\n\n## Why\n- Works on old phones\n- Speaks Krio\n```')
    with _browser()() as p:
        b = _launch(p)
        pg = b.new_page(viewport={"width": 1200, "height": 800})
        asked = []
        pg.route("https://cdn.jsdelivr.net/**", lambda r: (asked.append(r.request.url), r.abort()))   # never fetched for real here
        pg.goto(_chat_page(tmp_path))
        pg.evaluate("""([h]) => { window.ginkEmit = () => {}; addAssistantMessage('m', ''); finalizeMessage('m', h); }""", [arts])
        assert pg.locator("#m .artcard").all_inner_texts() == [
            "Habit tracker\nReact app\nOpen", "Sales by month\nChart\nOpen", "Budget\nTable, 3 rows\nOpen", "Pitch\nSlides, 2\nOpen"]
        cards = pg.locator("#m .artcard")
        cards.nth(2).click()
        frame = pg.frame_locator("#codeview .cvframe")
        assert frame.locator("tbody tr").count() == 3 and frame.locator("th").all_inner_texts() == ["Item", "Cost (Le)", "Month"]
        frame.locator("th").nth(1).click()                                      # sorts by the numbers, not the text
        assert frame.locator("tbody tr td:nth-child(2)").all_inner_texts() == ["120", "450", "1,200"]
        cards.nth(3).click()
        assert frame.locator(".slide:not([hidden])").inner_text().startswith("Gink")
        frame.locator("#next").click()
        assert frame.locator(".slide:not([hidden]) h2").inner_text() == "Why" and frame.locator("#n").inner_text() == "2 / 2"
        cards.nth(0).click()
        assert "The preview needs the internet" in frame.locator("#gink-e").inner_text(timeout=8000)   # offline: said plainly
        cards.nth(1).click()
        assert "The preview needs the internet" in frame.locator("#gink-e").inner_text(timeout=8000)
        libs = pg.evaluate("window.ART_LIBS")
        assert all(re.search(r"@\d+\.\d+\.\d+/", u) for u in libs.values())          # exact versions only
        assert {u for u in asked} >= {libs["react"], libs["reactDom"], libs["babel"], libs["chart"]}
        # downloads: a chart and slides come as pages that open anywhere; a table as its CSV
        dl = pg.evaluate("""() => { var t = Array.prototype.slice.call(document.querySelectorAll('#m .artcard'));
            return [cvDownload({kind: 'slides', name: 'Pitch.md', title: 'Pitch', text: '# A\\n\\n---\\n\\n# B'}).name,
                    cvDownload({kind: 'chart', name: 'Sales.json', title: 'Sales', text: '{}'}).name]; }""")
        assert dl == ["Pitch.html", "Sales.html"]
        b.close()


# ---------------------------------------------------------------- the web app: opening a chat
@needs_browser
def test_an_opened_web_chat_is_readable_at_once_and_its_answered_cards_are_closed(tmp_path):
    from ginkassistant.services.markdown_render import render_markdown_body
    html = read("src", "ginkassistant", "services", "web_app", "index.html")
    ask = ('Sure, what kind of thing would you like me to create?\n\n```ask\n{"questions": [{"q": "Choose the type of artifact '
           'you want:", "options": ["A short story", "A simple HTML web page"]}]}\n```')
    page = 'Here\'s your **portfolio** page:\n\n```html title="Personal Portfolio"\n<!doctype html><html><body><h1>Ibrahim</h1></body></html>\n```'
    msgs = [{"role": "user", "content": "make me anything"}, {"role": "assistant", "content": ask},
            {"role": "user", "content": "My answers:\n• Choose the type of artifact you want: → A simple HTML web page"},
            {"role": "assistant", "content": page}]
    token = "x." + base64.urlsafe_b64encode(json.dumps({"name": "Ibrahim"}).encode()).decode().rstrip("=") + ".y"
    sessions = {"s1": {"id": "s1", "title": "Portfolio chat", "messages": msgs, "updated": time.time(), "created": time.time()}}
    state = {"renders": 0, "down": True}

    def api(route):
        url = route.request.url
        if url.rstrip("/").endswith("/app"):
            return route.fulfill(body=html, content_type="text/html")
        if "/render" in url:
            state["renders"] += 1
            if state["down"]:
                return route.fulfill(status=503, json={"detail": "down"})
            items = json.loads(route.request.post_data or "{}").get("items") or []
            return route.fulfill(json={"html": [render_markdown_body(x) for x in items]})
        return route.fulfill(json={})
    with _browser()() as p:
        b = _launch(p)
        ctx = b.new_context(viewport={"width": 1200, "height": 850})
        ctx.route("http://gink.test/**", api)
        pg = ctx.new_page()
        pg.goto("http://gink.test/app")
        pg.evaluate("""([t, s]) => { localStorage.setItem('gink_token', t); localStorage.setItem('gink_email', 'ib@example.org');
                                     localStorage.setItem('gink_sessions', JSON.stringify(s)); }""", [token, sessions])
        pg.goto("http://gink.test/app")
        pg.get_by_text("Portfolio chat").first.click()
        pg.wait_for_timeout(400)
        feed = pg.inner_text("#feed")                          # the server can't format: readable anyway
        assert "**portfolio**" not in feed and "<!doctype" not in feed and "```" not in feed
        assert pg.locator("#feed strong").all_inner_texts() == ["portfolio"] and "“Personal Portfolio” is ready" in feed
        state["down"] = False
        pg.get_by_text("New chat").first.click()
        pg.get_by_text("Portfolio chat").first.click()
        pg.wait_for_timeout(600)
        assert pg.locator(".qcard:not(.done)").count() == 0      # answered in the next message: closed, with the answer
        assert pg.locator(".qcard.done .qans").all_inner_texts() == ["Choose the type of artifact you want: — A simple HTML web page"]
        assert pg.locator(".artcard").count() == 1
        n = state["renders"]
        pg.get_by_text("New chat").first.click()
        pg.get_by_text("Portfolio chat").first.click()
        pg.wait_for_timeout(150)
        assert state["renders"] == n and pg.locator(".artcard").count() == 1     # opened again: formatted at once
        b.close()


# ---------------------------------------------------------------- the website
def test_the_website_never_shows_an_older_page_half_styled(tmp_path, monkeypatch):
    import build_website
    monkeypatch.setattr(build_website, "OUT", str(tmp_path / "_site"))
    build_website.build()
    page = (tmp_path / "_site" / "index.html").read_text(encoding="utf-8")
    v = re.search(r'<meta name="gink-build" content="([0-9a-f]{10})">', page).group(1)
    assert f'href="assets/styles.css?v={v}"' in page and f'src="assets/site.js?v={v}"' in page
    js = (tmp_path / "_site" / "assets" / "site.js").read_text(encoding="utf-8")
    assert f'var build = "{v}"' in js and "__GINK_BUILD__" not in js and 'cache: "reload"' in js and "sessionStorage" in js
    assert build_website.build_id() == v                                 # the same files: the same build
    css = read("website", "assets", "styles.css")
    assert re.search(r"\.hero \{[^}]*background: var\(--night\)", css)  # light words never on white
