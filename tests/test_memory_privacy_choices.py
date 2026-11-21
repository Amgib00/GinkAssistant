"""Settings > Memory and Settings > Privacy (0.1.159), across the suite: "Generate memory from chats" (the AI picks the
lasting facts out of a conversation), "Include sensitive topics in memory" (off unless turned on; never for teens or in
a healthcare workspace), "Import memory from other AI providers" (a prompt to copy, the other assistant's answer
pasted back), "Location metadata" (off: only the clock's UTC offset) and "Privacy choices" (Gink's own policy pages)."""
import asyncio, json, os, shutil, subprocess, sys, time, types
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---------------------------------------------------------------- the rules (apps and server share them)
def test_sensitive_topics_only_when_turned_on_and_never_the_worst():
    from ginkassistant.services import memory_rules as r
    for touchy in ("I have asthma", "I'm allergic to peanuts", "I'm Muslim", "I'm diabetic", "I take insulin every day"):
        assert r.suggest(touchy) is None, touchy                                     # off by default
        assert r.suggest(touchy, sensitive=True) == touchy, touchy                    # on: kept
    assert r.is_sensitive("I go to church on Sundays") and r.is_sensitive("I'm gay") and not r.is_sensitive("I live in Lima")
    for never in ("My wifi password is abc123", "I was arrested last year", "I self-harm sometimes",
                  "My card number is 4111 1111 1111 1111"):
        assert r.suggest(never) is None and r.suggest(never, sensitive=True) is None, never
    assert r.suggest("I have a dog", sensitive=True) is None                          # "I have" is for health only
    assert r.suggest("I'm vegetarian") == "I'm vegetarian"                            # food choices aren't sensitive


def test_importing_what_another_assistant_listed():
    from ginkassistant.services import memory_rules as r
    answer = """Here's what I remember about you:
- The user lives in Nairobi.
- **User's name** is Ibrahim
2. [2025-03-01] - Prefers short answers
* The user works as a nurse
- I have type 2 diabetes
- I'm Christian
- User's bank account number is 0123456
- I live in Nairobi
Let me know if you'd like anything else!"""
    got = r.import_lines(answer, known=["Prefers short answers"])
    assert got["facts"] == ["I live in Nairobi", "My name is Ibrahim", "I work as a nurse"]
    assert got["skipped_sensitive"] == 2 and got["skipped"] == 1                     # health + belief; the account number
    assert r.import_lines(answer, sensitive=True)["facts"][-2:] == ["I have type 2 diabetes", "I'm Christian"]
    assert r.import_lines('```json\n{"memories": ["I speak Wolof", {"text": "I study law"}]}\n```')["facts"] == \
        ["I speak Wolof", "I study law"]
    assert "one fact per line" in r.IMPORT_PROMPT and "passwords" in r.IMPORT_PROMPT
    assert r.clean_generated(["I work at a bank", "I'm pregnant", "x" * 300, 7], known=[]) == ["I work at a bank"]


# ---------------------------------------------------------------- the server (web app, API)
@pytest.fixture
def srv(genie_srv):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "s")["key"]
    b._memgen_calls.clear()
    return b, c, h, {"Authorization": f"Bearer {key}"}


def test_sensitive_topics_follow_the_setting_and_never_for_teens(srv):
    b, c, h, k = srv
    assert c.post("/memory/auto", headers=h, json={"text": "I'm allergic to penicillin"}).json()["saved"] is None
    saved = c.post("/memory/auto", headers=h, json={"text": "I'm allergic to penicillin", "sensitive": True}).json()["saved"]
    assert saved["text"] == "I'm allergic to penicillin"
    c.put("/account/preferences", headers=h, json={"prefs": {"memory_sensitive": True, "location_metadata": False}})
    assert b._account_prefs("ib@example.com")["memory_sensitive"] is True                # synced: follows the account
    assert c.post("/v1/memories/suggest", headers=k, json={"text": "I'm Hindu"}).json()["fact"] == "I'm Hindu"
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 15)                     # a teen: never sensitive topics
    assert c.post("/memory/auto", headers=h, json={"text": "I'm Buddhist", "sensitive": True}).json()["saved"] is None
    assert c.post("/memory/auto", headers=h, json={"text": "I live in Accra"}).json()["saved"]["text"] == "I live in Accra"


def test_generate_memory_from_chats(srv, monkeypatch):
    b, c, h, k = srv
    asked = []

    async def ai(system, transcript):
        asked.append((system, transcript))
        return ["I live in Kigali", "I prefer short answers", "I have asthma", "My PIN is 1234", "I live in Kigali"]
    monkeypatch.setattr(b, "_memgen_ask", ai)
    chat = [{"role": "user", "content": "I moved to Kigali last month"}, {"role": "assistant", "content": "Welcome!"},
            {"role": "user", "content": [{"type": "text", "text": "keep answers short"}, {"type": "image_url", "image_url": {"url": "data:x"}}]}]
    j = c.post("/memory/generate", headers=h, json={"messages": chat}).json()
    assert j["memories"] == ["I live in Kigali", "I prefer short answers"]               # no health, no PIN, no repeats
    assert [s["text"] for s in j["saved"]] == ["I live in Kigali", "I prefer short answers"]
    system, transcript = asked[0]
    assert "Never include health" in system and transcript.startswith("Person: I moved to Kigali")
    assert "Gink: Welcome!" in transcript and "data:x" not in transcript                 # text only, never photos
    assert c.post("/memory/generate", headers=h, json={"messages": chat}).json()["note"]  # not twice in 10 seconds
    b._memgen_calls.clear()
    dry = c.post("/v1/memories/generate", headers=k, json={"messages": chat, "save": False, "sensitive": True}).json()
    assert dry["data"] == [{"object": "memory", "text": "I have asthma"}]                 # the rest is already known
    assert "may be kept" in asked[-1][0]
    assert c.post("/v1/memories/generate", headers=k, json={"messages": "hi"}).json()["error"]["code"] == "invalid_messages"
    assert c.post("/memory/generate", json={"messages": chat}).status_code == 401


def test_never_generated_in_a_healthcare_workspace(srv, monkeypatch):
    b, c, h, k = srv

    async def ai(system, transcript):
        raise AssertionError("no AI call in a healthcare workspace")
    monkeypatch.setattr(b, "_memgen_ask", ai)
    b._set_birth_year("ib@example.com", time.gmtime().tm_year - 35)
    assert c.post("/org", headers=h, json={"name": "City Hospital", "healthcare": True}).status_code == 200
    j = c.post("/memory/generate", headers=h, json={"messages": [{"role": "user", "content": "I live in Lima"}]}).json()
    assert j["memories"] == [] and "healthcare" in j["note"]


def test_import_memory_from_another_ai(srv):
    b, c, h, k = srv
    prompt = c.get("/memory/import-prompt").json()["prompt"]
    assert prompt == c.get("/v1/memories/import-prompt", headers=k).json()["prompt"] and "one fact per line" in prompt
    j = c.post("/memory/import", headers=h, json={"text": "- I live in Lima\n- I'm Catholic\n- My password is hunter2\n- I speak Quechua"}).json()
    assert [s["text"] for s in j["saved"]] == ["I live in Lima", "I speak Quechua"]
    assert j["skipped_sensitive"] == 1 and j["skipped"] == 1 and j["full"] is False
    again = c.post("/v1/memories/import", headers=k, json={"text": "- I live in Lima\n- I'm Catholic", "sensitive": True}).json()
    assert [m["text"] for m in again["data"]] == ["I'm Catholic"] and again["data"][0]["object"] == "memory"
    assert c.post("/memory/import", headers=h, json={"text": " "}).status_code == 422
    assert c.post("/v1/memories/import", headers=k, json={}).json()["error"]["code"] == "invalid_import"


# ---------------------------------------------------------------- location metadata
def test_location_metadata_off_sends_only_the_clock(srv):
    b, c, h, k = srv
    req = types.SimpleNamespace(headers={"x-gink-tz": "Africa/Dakar", "x-gink-locale": "fr-SN"})
    assert b._client_place_from(req) == {"tz": "Africa/Dakar", "city": "Dakar", "language": "fr", "region": "SN"}
    off = types.SimpleNamespace(headers={"x-gink-tz": "Africa/Dakar", "x-gink-location": "off", "x-gink-utc-offset": "+01:00"})
    place = b._client_place_from(off)
    assert place == {"utc_offset": "+01:00", "location": "off"}                            # the time zone is ignored
    note = b._place_note(place)
    assert "UTC+01:00" in note and "don't assume" in note and "Dakar" not in note
    bad = types.SimpleNamespace(headers={"x-gink-location": "off", "x-gink-utc-offset": "Africa/Dakar"})
    assert b._client_place_from(bad) == {"location": "off"} and "ask if a place matters" in b._place_note({"location": "off"})


def test_apps_cli_and_sdks_send_no_place_when_off(monkeypatch):
    from ginkassistant.services import device_region, live_info
    monkeypatch.setattr(device_region, "metadata_allowed", [lambda: False])
    h = device_region.place_headers()
    assert h["X-Gink-Location"] == "off" and "X-Gink-TZ" not in h and h["X-Gink-UTC-Offset"][0] in "+-"
    live = live_info.LiveInfo(city_fn=lambda: "")
    live.estimate_fn = lambda: False

    async def no_ip():
        raise AssertionError("no estimate from the IP address")
    live.approximate_place = no_ip
    assert asyncio.run(live.where()) is None
    from gink.client import place_headers
    assert place_headers(False)["X-Gink-Location"] == "off"
    monkeypatch.setenv("GINK_LOCATION", "off")
    assert place_headers()["X-Gink-Location"] == "off"
    monkeypatch.delenv("GINK_LOCATION")
    from gink_cli import main as cli
    monkeypatch.setattr(cli, "settings", lambda: ("", "https://x/v1"))
    cli.main(["--no-location", "version"])
    assert os.environ.pop("GINK_LOCATION") == "off"
    for f in (("webapp", "bridge.js"), ("src", "ginkassistant", "services", "web_app", "genie.html"),
              ("src", "ginkassistant", "services", "web_app", "console.html")):
        assert "location_metadata === false" in read(*f) and '"X-Gink-Location"' in read(*f), f


# ---------------------------------------------------------------- privacy choices and the settings page
def test_privacy_choices_are_ginks_own_pages():
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    from ginkassistant.ui import settings_page as sp
    info = TestClient(b.app).get("/info").json()
    labels = [p["label"] for p in info["policies"]]
    assert labels == ["Privacy policy", "Responsible disclosure policy", "Terms of service: Commercial",
                      "Terms of service: Consumer", "Data Processing Agreement", "Usage Policy"]
    assert all(p["url"].startswith(b.GINK_SITE) for p in info["policies"]) and "anthropic" not in json.dumps(info).lower()
    assert sp.POLICY_PAGES == b.POLICY_PAGES and sp.GINK_SITE == b.GINK_SITE              # the page's fallback list
    for _id, _label, page in b.POLICY_PAGES:                                            # every page exists
        assert os.path.isfile(os.path.join(ROOT, "website", "pages", page)), page
    assert info["memory_help_url"].endswith("memory.html") and info["location_help_url"].endswith("#location-metadata")
    assert 'id="location-metadata"' in read("website", "pages", "privacy.html")
    memory = read("website", "pages", "memory.html")
    assert all(f'id="{a}"' in memory for a in ("generate", "sensitive", "import"))


def test_settings_page_rows():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    for text in ("Generate memory from chats", "Allow Gink to generate memories from chats",
                 "Include sensitive topics in memory", "Import memory from other AI providers",
                 "Location metadata", "Allow Gink to use coarse location metadata (city/region) to improve product experiences",
                 "Privacy choices", "Learn more", "memory_import_copy", "function copyPrompt("):
        assert text in html, text
    from ginkassistant.services import memory_rules
    assert json.dumps(memory_rules.IMPORT_PROMPT) in html and "__MEM_IMPORT_PROMPT__" not in html
    from ginkassistant.services import prefs
    assert prefs.DEFAULTS["memory_sensitive"] is False and prefs.DEFAULTS["location_metadata"] is True
    assert {"memory_sensitive", "location_metadata"} <= prefs.SYNCED
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert "async def auto_generate_memories(" in main and "keep_sensitive()" in main
    bridge = read("webapp", "bridge.js")
    assert '"/memory/generate"' in bridge and '"/memory/import"' in bridge and "function memgen(" in bridge


def test_apps_import_checks_the_same_rules(tmp_path):
    from ginkassistant.ui import settings_controller as sc
    saved, toasts = [], []

    class Mem:
        def list(self): return [{"uid": "1", "text": "I live in Lima"}]
        def add(self, t): saved.append(t); return {"uid": str(len(saved)), "text": t}

    class Web:
        async def settings_toast(self, text, kind="ok"): toasts.append((text, kind))
    ctl = sc.SettingsController.__new__(sc.SettingsController)
    ctl.app, ctl.web = types.SimpleNamespace(memory=Mem()), Web()
    ctl.p = lambda: {"memory_sensitive": False}

    async def push(*a, **k): pass
    ctl.push = push
    asyncio.run(ctl._a_memory_import("- I live in Lima\n- I speak Twi\n- I have epilepsy\n- My PIN is 0000"))
    assert saved == ["I speak Twi"]
    text = toasts[-1][0]
    assert "Added 1 memory." in text and "Skipped 1 about sensitive topics" in text and "Skipped 1 Gink never keeps" in text


def test_python_sdk_cli_and_js_sdk(srv, monkeypatch, capsys):
    b, c, h, k = srv

    async def ai(system, transcript):
        return ["I live in Accra"]
    monkeypatch.setattr(b, "_memgen_ask", ai)
    from gink import Client
    gink = Client(api_key=k["Authorization"][7:], base_url="http://testserver/v1", http=c, location=False)
    assert "one fact per line" in gink.memories.import_prompt()
    out = gink.memories.import_text("- I speak Hausa\n- I'm Muslim")
    assert [m["text"] for m in out["data"]] == ["I speak Hausa"] and out["skipped_sensitive"] == 1
    assert [m.text for m in gink.memories.generate([{"role": "user", "content": "I moved to Accra"}])] == ["I live in Accra"]
    assert gink._headers()["X-Gink-Location"] == "off"
    from gink_cli import main as cli
    calls = []

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j

    def fake(key, base, method, path, **kw):
        calls.append((method, path, kw.get("json")))
        if path == "/memories/import-prompt":
            return R({"prompt": "PROMPT"})
        if path == "/memories/import":
            return R({"data": [{"text": "I speak Hausa"}], "skipped": 0, "skipped_sensitive": 2, "memory_full": False})
        return R({"data": [{"text": "I live in Accra"}]})
    monkeypatch.setattr(cli, "_env_call", fake)
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["memories", "prompt"]) == 0 and "PROMPT" in capsys.readouterr().out
    f = os.path.join(os.path.dirname(__file__), "_import_tmp.txt")
    open(f, "w", encoding="utf-8").write("- I speak Hausa")
    try:
        assert cli.main(["memories", "import", f]) == 0
    finally:
        os.remove(f)
    o = capsys.readouterr().out
    assert "Remembered: I speak Hausa" in o and "Skipped 2 about sensitive topics" in o
    assert cli.main(["memories", "generate", "I", "moved", "to", "Accra", "--dry-run"]) == 0
    assert "Would remember: I live in Accra" in capsys.readouterr().out
    assert calls[-1] == ("POST", "/memories/generate", {"messages": [{"role": "user", "content": "I moved to Accra"}],
                                                        "save": False, "sensitive": False})
    if shutil.which("node") is None:
        return
    script = os.path.join(os.path.dirname(__file__), "_mem_tmp.mjs")
    open(script, "w", encoding="utf-8").write('''
import { Gink } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", location: false, fetch: async (url, init) => {
  seen.push([init.method, url, init.body ? JSON.parse(init.body) : null, init.headers["X-Gink-Location"] || ""]);
  return new Response(JSON.stringify({ data: [{ text: "I live in Accra" }], prompt: "P" }), { status: 200 }); } });
const g = await gink.memories.generate([{ role: "user", content: "hi" }], { save: false });
const p = await gink.memories.importPrompt();
await gink.memories.import("- I speak Twi", { sensitive: true });
console.log(JSON.stringify([seen, g, p]));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\", "/"))
    try:
        r = subprocess.run(["node", script], capture_output=True, text=True, timeout=60)
    finally:
        os.remove(script)
    assert r.returncode == 0, r.stderr
    seen, gen, prompt = json.loads(r.stdout)
    assert seen[0] == ["POST", "https://x/v1/memories/generate", {"messages": [{"role": "user", "content": "hi"}],
                                                                  "save": False, "sensitive": False}, "off"]
    assert seen[2][2] == {"text": "- I speak Twi", "sensitive": True} and gen[0]["text"] == "I live in Accra" and prompt == "P"
