"""0.1.152 across the suite: every photo gets the same rules from the server (works out what it needs, careful with
health, patients' details never read out in a healthcare workspace) -- the apps, the web app's Live camera, the API,
both SDKs' see() and `gink see`; agents fix their whole environment before finishing; Live is hands-free and shows
the patient-privacy reminder in healthcare workspaces."""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest
from test_genie import SCRIPT, SEEN, call      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def photo_message(text="What's this?"):
    return [{"role": "user", "content": [{"type": "text", "text": text},
                                         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}}]}]


def system_text(body) -> str:
    return "\n".join(m["content"] for m in body["messages"] if m.get("role") == "system" and isinstance(m.get("content"), str))


@pytest.fixture
def srv(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "s")["key"]
    return b, c, h, {"Authorization": f"Bearer {key}"}


# ---- photos: the server's rules, for every client
def test_the_rules_say_what_matters():
    from ginkassistant.services import vision_rules as v
    for must in ("read it out", "steps to fix it", "step by step", "never diagnose", "never give doses",
                 "qualified health professional", "emergency help now", "identify a real person from their face"):
        assert must in v.PHOTO_RULES, must
    assert "wristband" in v.HEALTHCARE_PHOTO_RULES and "patient details must not be shared" in v.HEALTHCARE_PHOTO_RULES
    assert v.rules_for(False) == v.PHOTO_RULES and v.HEALTHCARE_PHOTO_RULES in v.rules_for(True)


def test_every_photo_gets_the_rules_and_text_doesnt(srv):
    b, c, h, k = srv
    from ginkassistant.services import vision_rules as v
    SCRIPT[:] = [{"content": "It's a bicycle."}]
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"messages": photo_message()})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "It's a bicycle."
    sent = system_text(SEEN[-1])
    assert v.PHOTO_RULES in sent and v.HEALTHCARE_PHOTO_RULES not in sent
    SCRIPT[:] = [{"content": "Hello!"}]
    c.post("/ai/openai/v1/chat/completions", headers=h, json={"messages": [{"role": "user", "content": "Hi"}]})
    assert v.PHOTO_RULES not in system_text(SEEN[-1])                                   # only when there's a photo
    SCRIPT[:] = [{"content": "From the API."}]
    r = c.post("/v1/chat/completions", headers=k, json={"messages": photo_message("Read this")})
    assert r.status_code == 200 and v.PHOTO_RULES in system_text(SEEN[-1])           # developers get them too


def test_healthcare_workspace_photos_never_read_patient_details(srv):
    b, c, h, k = srv
    from ginkassistant.services import vision_rules as v
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 35)
    assert c.post("/org", headers=h, json={"name": "City Hospital", "healthcare": True}).status_code == 200
    SCRIPT[:] = [{"content": "That's an infusion pump."}]
    c.post("/ai/openai/v1/chat/completions", headers=h, json={"messages": photo_message()})
    sent = system_text(SEEN[-1])
    assert v.PHOTO_RULES in sent and v.HEALTHCARE_PHOTO_RULES in sent
    # patient details typed with the photo are removed before anything is sent (tests/test_patient_details_safety.py)
    SCRIPT[:] = [{"content": "Ask the ward's doctor."}]
    r = c.post("/ai/openai/v1/chat/completions", headers=h,
               json={"messages": photo_message("Patient: Awa Diallo, MRN 12345678 -- is this rash bad?")})
    assert r.status_code == 200 and r.json()["gink"]["patient_details_removed"] == ["record number", "name"]
    user = SEEN[-1]["messages"][-1]["content"][0]["text"]
    assert "Awa" not in user and "12345678" not in user and "[patient name]" in user


def test_python_sdk_see(srv):
    b, c, h, k = srv
    from gink import Client, GinkAPIError
    from gink.client import image_data_url
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c)
    SCRIPT[:] = [{"content": "The label says: keep refrigerated."}]
    assert gink.see(JPEG, "what does it say?") == "The label says: keep refrigerated."
    user = SEEN[-1]["messages"][-1]["content"]
    assert user[0] == {"type": "text", "text": "what does it say?"}
    assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert image_data_url(PNG).startswith("data:image/png;base64,") and image_data_url("data:image/gif;base64,R0") == "data:image/gif;base64,R0"
    SCRIPT[:] = [{"content": "A cup."}]
    gink.see(JPEG)
    assert SEEN[-1]["messages"][-1]["content"][0]["text"] == "What's this?"            # nothing asked: a short default
    with pytest.raises(GinkAPIError) as e:
        gink.see(b"just text, not a photo")
    assert e.value.code == "invalid_image"


def test_cli_see(tmp_path, monkeypatch, capsys):
    from gink_cli import main as cli
    photo = tmp_path / "label.jpg"
    photo.write_bytes(JPEG)
    seen = []
    monkeypatch.setattr(cli, "stream_answer", lambda key, base, messages, model="", out=None: seen.append(messages) or "ok")
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["see", str(photo), "read", "it"]) == 0
    content = seen[-1][0]["content"]
    assert content[0]["text"] == "read it" and content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert cli.main(["see", str(photo)]) == 0 and seen[-1][0]["content"][0]["text"] == "What's this?"
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    assert cli.main(["see", str(notes)]) == 1 and "JPEG, PNG, WebP or GIF" in capsys.readouterr().err
    assert cli.main(["see", str(tmp_path / "missing.jpg")]) == 1
    assert "gink see PHOTO" in read("cli", "gink_cli", "main.py")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_see(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink, imageDataURL } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([url, JSON.parse(init.body)]);
  return new Response(JSON.stringify({ choices: [{ message: { content: "A tap, dripping." } }] }), { status: 200 }); } });
const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
const a = await gink.see(png, { question: "what's wrong?" });
const b = await gink.see(png);
let bad = "";
try { imageDataURL(new Uint8Array([1, 2, 3, 4])); } catch (e) { bad = e.code; }
console.log(JSON.stringify([a, seen, bad]));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    answer, seen, bad = json.loads(r.stdout)
    assert answer == "A tap, dripping." and seen[0][0] == "https://x/v1/chat/completions"
    content = seen[0][1]["messages"][0]["content"]
    assert content[0]["text"] == "what's wrong?" and content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert seen[1][1]["messages"][0]["content"][0]["text"] == "What's this?" and bad == "invalid_image"
    types = read("sdk", "js", "index.d.ts")
    assert "see(photo:" in types and "imageDataURL(photo:" in types


# ---- agents fix their whole environment before finishing
def _finish(c, k, iid):
    for _ in range(200):
        it = c.get(f"/v1/interactions/{iid}", headers=k).json()
        if it["status"] != "running":
            return it
        time.sleep(0.05)
    return it


def test_agents_fix_their_environment_before_finishing(srv):
    b, c, h, k = srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html", content='<script src="app.js"></script>')]},
                 {"content": "Made the page."},                                        # but app.js doesn't exist
                 {"content": "", "tool_calls": [call("write_file", path="app.js", content="console.log('hi')")]},
                 {"content": "Made the page, and added app.js."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "Make a page with a script", "environment": "remote",
                                                       "background": True}).json()
    it = _finish(c, k, it["id"])
    assert it["status"] == "completed" and it["output_text"] == "Made the page, and added app.js."
    checks = [s for s in it["steps"] if s["tool"] == "check"]
    assert len(checks) == 1 and "app.js" in checks[0]["result"]
    nudge = [m["content"] for m in SEEN[-1]["messages"] if m["role"] == "user" and m["content"].startswith("Before you finish")]
    assert nudge and "app.js" in nudge[0]
    assert c.get(f"/v1/environments/{it['environment']}/check", headers=k).json()["ok"] is True


def test_agents_that_change_nothing_dont_fix_anything(srv):
    b, c, h, k = srv
    env = c.post("/v1/environments", headers=k, json={"name": "Old site"}).json()["id"]
    b._genie_write(env, "index.html", '<script src="missing.js"></script>')              # already broken
    SCRIPT[:] = [{"content": "", "tool_calls": [call("read_file", path="index.html")]}, {"content": "It's a page with one script."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "What's in index.html?", "environment": env,
                                                       "background": True}).json()
    it = _finish(c, k, it["id"])
    assert it["output_text"] == "It's a page with one script." and not [s for s in it["steps"] if s["tool"] == "check"]


def test_agents_give_up_after_a_few_rounds(srv):
    b, c, h, k = srv
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="index.html", content='<script src="x.js"></script>')]}] + \
                [{"content": "Done (still no x.js)."}] * (b.AGENT_AUTOFIX_ROUNDS + 1)
    it = c.post("/v1/interactions", headers=k, json={"input": "Make a page", "environment": "remote", "background": True}).json()
    it = _finish(c, k, it["id"])
    assert it["status"] == "completed" and it["output_text"] == "Done (still no x.js)."
    assert len([s for s in it["steps"] if s["tool"] == "check"]) == b.AGENT_AUTOFIX_ROUNDS
    nudges = [m["content"] for m in SEEN[-1]["messages"] if m["role"] == "user" and m["content"].startswith("Before you finish")]
    assert "SAME problems" not in nudges[0] and "SAME problems" in nudges[1]           # second time: change approach


def test_cli_and_console_show_the_check_step():
    assert 'step.get("tool") == "check"' in read("cli", "gink_cli", "main.py")
    assert 'st.tool === "check"' in read("src", "ginkassistant", "services", "web_app", "console.html")
    assert "check [--fix]" in read("src", "ginkassistant", "services", "web_app", "agents.html")


# ---- Live: hands-free, private, and the healthcare reminder
def test_live_is_hands_free_and_private():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert "LIVE.quiet <= 8" in html and "LIVE.again = setTimeout" in html                # keeps listening through silence
    assert "document.addEventListener('visibilitychange', LIVE.onVis)" in html           # leave the window: camera off
    assert "if (document.hidden && !screen) closeLive()" in html       # screen view goes on: you switch windows to show it
    assert "window.setCareMode = function (on)" in html and "Healthcare workspace: never point the camera at patients" in html


def test_apps_and_web_app_turn_on_the_healthcare_reminder():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "care = await in_healthcare_workspace()" in main and "await web_chat.set_care_mode(care)" in main
    view = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "async def set_care_mode(self, on: bool)" in view
    bridge = read("webapp", "bridge.js")
    assert "function checkCare()" in bridge and "checkCare();" in bridge and "careFrom(j); pushSettings" in bridge
    assert "vision_rules.py ./vision_rules.py" in read("deploy", "Dockerfile")
