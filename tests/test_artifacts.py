"""Automatic artifacts (0.1.161): finished things come in one titled block (```html title="..."), the chat turns each
into a card that opens in the viewer (preview, code, versions, copy, download), the web app previews pages in a
sandboxed frame on its own address, and developers get the same with "gink_artifacts": true."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from test_genie import SCRIPT, SEEN      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def test_titled_blocks_keep_their_title_and_documents_their_markdown():
    from ginkassistant.services.markdown_render import render_markdown_body as r, fence_title
    assert fence_title(' title="Pomodoro timer"') == "Pomodoro timer" and fence_title(" title='Logo'") == "Logo"
    assert fence_title("") == "" and fence_title(' name="x"') == ""
    h = r('Here.\n\n```html title="Pomodoro timer"\n<p>25:00</p>\n```\n\n```document title="Cover letter"\n# Hi\n\nDear team\n```'
          '\n\n```bash\nls -la\n```')
    assert '<div class="code-block" data-lang="html" data-title="Pomodoro timer"' in h
    assert 'class="doc-block" data-md="# Hi\n\nDear team" data-title="Cover letter"' in h
    assert h.count('data-title="') == 2                                       # the plain snippet has none
    h = r('```html title="A <b>&amp; \\"quote\\""\n<p>x</p>\n```')
    assert "<b>" not in h.split("data-title=")[1].split(">")[0]               # the title is escaped


def test_the_prompt_is_the_same_everywhere_and_in_the_system_prompts():
    from ginkassistant.services import backend_server as b, groq_worker as g
    assert b.ARTIFACT_PROMPT == g.ARTIFACT_PROMPT and g.ARTIFACT_PROMPT in g.DEFAULT_SYSTEM_PROMPT
    js = read("webapp", "bridge.js")
    line = next(x for x in js.splitlines() if x.strip().startswith("var ARTIFACT_PROMPT = "))
    assert json.loads(line.split("= ", 1)[1].rstrip(";")) == g.ARTIFACT_PROMPT
    assert '" " + ARTIFACT_PROMPT' in js
    assert 'title="Pomodoro timer"' in g.ARTIFACT_PROMPT and "same title" in g.ARTIFACT_PROMPT


def test_the_preview_frame_is_sandboxed_on_its_own_terms(genie_srv):
    b, c, h = genie_srv
    r = c.get("/artifact/frame")
    assert r.status_code == 200 and "gink-artifact" in r.text and "gink-artifact-ready" in r.text
    csp = r.headers["content-security-policy"]
    assert csp.startswith("sandbox allow-scripts") and "allow-same-origin" not in csp and "frame-ancestors 'self'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/vendor/mermaid.min.js").status_code in (200, 404)           # served when deploy/vendor has it
    extras = read("src", "ginkassistant", "ui", "chat_extras.py")
    assert "/artifact/frame" in extras and "gink-artifact" in extras          # the web app's preview: its own frame


def test_developers_ask_for_artifacts_with_a_flag(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "k")["key"]
    SEEN.clear()
    SCRIPT[:] = [{"content": "ok"}]
    c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
           json={"messages": [{"role": "user", "content": "make a timer page"}], "gink_artifacts": True, "gink_web": False})
    assert any(m["role"] == "system" and m["content"] == b.ARTIFACT_PROMPT for m in SEEN[-1]["messages"])
    SEEN.clear()
    SCRIPT[:] = [{"content": "ok"}]
    c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
           json={"messages": [{"role": "user", "content": "make a timer page"}], "gink_web": False})
    assert all(m.get("content") != b.ARTIFACT_PROMPT for m in SEEN[-1]["messages"])      # only when asked
    props = c.get("/v1/openapi.json").json()["paths"]["/chat/completions"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["properties"]
    assert {"gink_artifacts", "gink_tasks", "gink_code", "gink_web", "gink_maps"} <= set(props)


def test_the_chat_page_has_the_artifact_pieces():
    extras = read("src", "ginkassistant", "ui", "chat_extras.py")
    for part in ("window.upgradeArtifacts = function (root)", "window.openArtifact", "function artWhat(block)",
                 "function cvFrame(", "function cvDiagramPage(", "MERMAID_VERSION = '11.17.2'", ".artcard .arti",
                 "var(--accent, #3F8212)"):
        assert part in extras, part
    assert "var(--ac," not in extras                                       # the theme's real accent (dark mode too)
    assert "allow-same-origin" not in extras
    page = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "if (window.upgradeArtifacts) upgradeArtifacts(el);" in page
    assert "Making " in page and "is ready" in page                     # while it streams: its name, not its code
    # what becomes an artifact: pages, SVGs, diagrams, titled documents, titled or long code -- never maps, questions
    # or schedules (they have their own cards)
    m = re.search(r"function artWhat\(block\) \{(.*?)\n  \}", extras, re.S)
    assert m and all(x in m.group(1) for x in ("'map'", "'ask'", "'schedule'", "'mermaid'", "'svg'"))
