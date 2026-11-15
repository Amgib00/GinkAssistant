"""0.1.153: healthcare workspaces keep a patient's details out of Gink AUTOMATICALLY -- removed before anything reaches
the AI, a web search, a stored name or a saved task (or stopped, if the admins choose that) -- in chat (apps, web app,
API), photos, Gink Genie, agents, scheduled agents and websites; and admins get a safety report: counts only, never
words or photos (Settings > Workspace in the apps and the web app, the API, both SDKs, the CLI)."""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest
from test_genie import SCRIPT, SEEN      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")
Y = time.gmtime().tm_year


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def sent_text(body) -> str:
    """Everything the AI was sent (all messages, all text parts)."""
    out = []
    for m in body["messages"]:
        c = m.get("content")
        out.append(c if isinstance(c, str) else " ".join(p.get("text", "") for p in c or [] if isinstance(p, dict)))
    return "\n".join(out)


@pytest.fixture
def ws(genie_srv):
    """City Hospital in healthcare mode: ib@example.com (admin) and awa@x.co (a nurse); an API key for each."""
    b, c, admin = genie_srv
    b._set_birth_year("ib@example.com", Y - 40)
    b._upsert_user("awa@x.co", "Awa", None, "password")
    b._set_birth_year("awa@x.co", Y - 30)
    nurse = {"Authorization": "Bearer " + b._token_response("awa@x.co", "Awa")["token"]}
    assert c.post("/org", headers=admin, json={"name": "City Hospital", "healthcare": True}).status_code == 200
    c.post("/org/invite", headers=admin, json={"email": "awa@x.co"})
    c.post("/org/respond", headers=nurse, json={"accept": True})
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    admin_key = {"Authorization": "Bearer " + b._create_api_key("ib@example.com", "a")["key"]}
    nurse_key = {"Authorization": "Bearer " + b._create_api_key("awa@x.co", "n")["key"]}
    return b, c, admin, nurse, admin_key, nurse_key


# ---- finding and removing a patient's details
def test_removal_finds_details_and_leaves_ordinary_work_alone():
    from ginkassistant.services import backend_server as b
    clean, kinds = b._redact_patient_data(
        "Summarise the notes for patient Mamadou Diallo, MRN: 2026-114578, DOB 12/03/1961. Mr Diallo is stable.")
    assert "Mamadou" not in clean and "Diallo" not in clean and "114578" not in clean and "1961" not in clean
    assert clean.count("[patient name]") == 2 and "[record number]" in clean and "[date of birth]" in clean
    assert set(kinds) == {"name", "record number", "date of birth"}
    for text, gone in (("patiente Aïssatou Ndiaye au 77 123 45 67", ("Aïssatou", "45 67")),
                       ("Patient named Jean-Pierre Martin, né le 3 janv. 1955", ("Jean-Pierre", "1955")),
                       ("patient O'Neill Brady, SSN 123-45-6789", ("O'Neill", "6789")),
                       ("Patient: Ronald McDonald, email ronald.m@example.com", ("McDonald", "example.com")),
                       ("numéro de dossier 88-41237 pour la sortie", ("41237",))):
        clean, kinds = b._redact_patient_data(text)
        assert kinds and not any(g in clean for g in gone), (text, clean)
    for text in ("Write a night-shift rota for 6 nurses", "Draft a letter to patients about parking",
                 "Plan the Patient Safety Week posters", "The PT Department meets on Tuesday",
                 "medical record keeping policy for 2026", "see the patient Monday Morning",
                 "Explain sepsis warning signs for a staff training session"):
        assert b._redact_patient_data(text) == (text, []), text
    assert b._removed_words(["name"]) == "a name"
    assert b._removed_words(["name", "record number", "email address"]) == "a name, a record number and an email address"


# ---- chat: removed by default, with a notice; stopped when the admins choose that
def test_chat_removes_details_before_the_ai_sees_them(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "Here is the summary."}]
    r = c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [
        {"role": "user", "content": "Earlier: DOB 12/03/1961"}, {"role": "assistant", "content": "Noted."},
        {"role": "user", "content": "Summarise the notes for patient Mamadou Diallo, MRN 2026-114578"}]})
    assert r.status_code == 200
    text = sent_text(SEEN[-1])
    assert "Mamadou" not in text and "114578" not in text and "1961" not in text            # older messages too
    assert "[patient name]" in text and b.HEALTHCARE_RULES.split(".")[0] in text
    answer = r.json()["choices"][0]["message"]["content"]
    assert answer.startswith("_\U0001F512 Patient details were removed before Gink read this (a record number and a name)._")
    assert answer.endswith("Here is the summary.") and r.json()["gink"]["patient_details_removed"] == ["record number", "name"]
    assert r.headers["x-gink-patient-details-removed"] == "record number,name"
    # nothing in the newest message: no notice (the older one is cleaned quietly)
    SCRIPT[:] = [{"content": "Done."}]
    r = c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [
        {"role": "user", "content": "patient Awa Ndiaye"}, {"role": "user", "content": "Write a rota"}]})
    assert r.json()["choices"][0]["message"]["content"] == "Done." and "Ndiaye" not in sent_text(SEEN[-1])


def test_streamed_answers_start_with_the_notice(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "ok"}]
    r = c.post("/ai/openai/v1/chat/completions", headers=nurse,
               json={"stream": True, "messages": [{"role": "user", "content": "Letter for patient Fatou Sow"}]})
    assert r.status_code == 200 and r.text.startswith('data: {"id": "gink-note"')
    first = json.loads(r.text.split("\n\n")[0][6:])
    assert "Patient details were removed" in first["choices"][0]["delta"]["content"]
    assert first["gink"]["patient_details_removed"] == ["name"] and "Fatou" not in sent_text(SEEN[-1])


def test_api_callers_get_the_same_protection(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "Sure."}]
    r = c.post("/v1/chat/completions", headers=nurse_key, json={"messages": [{"role": "user", "content": "patient Awa Ndiaye, DOB 1/2/1990"}]})
    assert r.status_code == 200 and r.json()["gink"]["patient_details_removed"] == ["date of birth", "name"]
    assert "Ndiaye" not in sent_text(SEEN[-1])


def test_stop_mode_stops_and_counts(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    c.put("/org/settings", headers=admin, json={"patient_details": "stop"})
    n = len(SEEN)
    r = c.post("/ai/openai/v1/chat/completions", headers=nurse,
               json={"messages": [{"role": "user", "content": "Summarise the notes for patient Mamadou Diallo"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "patient_data" and len(SEEN) == n   # nothing sent
    assert c.get("/org/safety", headers=admin).json()["totals"]["patient_details_stopped"] == 1


# ---- photos in healthcare workspaces are counted (rules: tests/test_photos_agents_care.py)
def test_photos_are_counted(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "An infusion pump."}]
    c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": [
        {"type": "text", "text": "What's this?"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}}]}]})
    rep = c.get("/org/safety", headers=admin).json()
    assert rep["totals"]["photo_checked"] == 1 and rep["by_feature"] == {"chat": 1}


# ---- everywhere else: Genie, agents, scheduled agents, websites
def test_genie_projects_and_requests_never_keep_details(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "Built it."}]
    r = c.post("/genie/projects", headers=nurse, json={"prompt": "Build a page listing patient Mamadou Diallo's results"})
    assert r.status_code == 200
    assert "Mamadou" not in r.json()["project"]["name"] and "[patient name]" in r.json()["project"]["name"]
    steps = r.json()["result"]["steps"]
    assert steps[0]["kind"] == "note" and "Patient details were removed before Genie read this (a name)" in steps[0]["title"]
    assert "Mamadou" not in sent_text(SEEN[-1])
    chat = c.get(f"/genie/projects/{r.json()['project']['id']}/chat", headers=nurse).json()["messages"]
    assert chat and not any("Mamadou" in m["text"] for m in chat)


def test_agents_and_schedules_never_keep_details(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "Written."}]
    it = c.post("/v1/interactions", headers=nurse_key, json={"input": "Write a discharge letter for patient Fatou Sow",
                                                              "environment": "remote"}).json()
    assert it["steps"][0]["tool"] == "privacy" and "a name" in it["steps"][0]["result"]
    assert "Fatou" not in sent_text(SEEN[-1])
    env = c.get(f"/v1/environments/{it['environment']}", headers=nurse_key).json()
    assert "Fatou" not in env["name"]
    s = c.post("/v1/schedules", headers=nurse_key, json={"input": "Every morning, check the notes of patient Awa Ndiaye",
                                                         "every": "daily", "at": "08:00"}).json()
    assert "Ndiaye" not in s["input"] and "[patient name]" in s["input"]
    by_feature = c.get("/org/safety", headers=admin).json()["by_feature"]
    assert by_feature.get("agent") == 1 and by_feature.get("schedule") == 1


def test_websites_never_keep_details(ws, monkeypatch):
    b, c, admin, nurse, admin_key, nurse_key = ws
    seen = {}

    async def site_ai(messages):
        seen["messages"] = messages
        return "<!DOCTYPE html><html><head><title>Results</title></head><body><h1>Results</h1></body></html>"
    monkeypatch.setattr(b, "_site_ai", site_ai)
    r = c.post("/sites", headers=nurse, json={"prompt": "a page with the results of patient Fatou Sow"})
    assert r.status_code == 200
    assert "Fatou" not in json.dumps(seen["messages"])
    stored = b._sites_db(lambda con: con.execute("SELECT prompt FROM sites WHERE id=?", (r.json()["id"],)).fetchone()[0])
    assert "Fatou" not in stored and "[patient name]" in stored


# ---- the safety report: admins only, counts only
def test_safety_report_for_admins_only(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "ok"}, {"content": "ok"}]
    for text in ("Letter for patient Fatou Sow", "MRN 2026-114578 needs a letter"):
        c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": text}]})
    view = c.get("/org", headers=admin).json()
    assert view["org"]["patient_details"] == "remove" and view["safety"]["totals"]["patient_details_removed"] == 2
    person = view["safety"]["by_person"][0]
    assert person["account"] == "awa@x.co" and person["name"] == "Awa" and person["patient_details_removed"] == 2
    assert "safety" not in c.get("/org", headers=nurse).json()                          # members don't see it
    assert c.get("/org/safety", headers=nurse).status_code == 403
    csv_text = c.get("/org/safety.csv", headers=admin).text
    assert csv_text.splitlines()[0] == "date,name,account,what,where,times"
    assert "patient details removed,chat,2" in csv_text and "Fatou" not in csv_text and "114578" not in csv_text
    api = c.get("/v1/workspace/safety?days=7", headers=admin_key).json()
    assert api["object"] == "safety_report" and api["days"] == 7 and api["totals"]["patient_details_removed"] == 2
    assert api["workspace"]["name"] == "City Hospital"
    assert c.get("/v1/workspace/safety", headers=nurse_key).json()["error"]["code"] == "not_admin"
    w = c.get("/v1/workspace", headers=nurse_key).json()
    assert w["workspace"]["healthcare"] is True and w["workspace"]["patient_details"] == "remove" and w["role"] == "member"


def test_counts_leave_with_the_person_and_the_workspace(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "ok"}]
    c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": "patient Fatou Sow"}]})
    assert c.get("/org/safety", headers=admin).json()["totals"]["patient_details_removed"] == 1
    c.post("/org/remove", headers=admin, json={"email": "awa@x.co"})
    assert c.get("/org/safety", headers=admin).json()["totals"]["patient_details_removed"] == 0
    assert b._org_db(lambda con: con.execute("SELECT COUNT(*) FROM org_safety").fetchone()[0]) == 0


def test_deleting_an_account_deletes_its_counts(ws):
    b, c, admin, nurse, admin_key, nurse_key = ws
    SCRIPT[:] = [{"content": "ok"}]
    c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": "patient Fatou Sow"}]})
    assert c.post("/account/delete", headers=nurse, json={"confirm": "DELETE"}).json() == {"deleted": True}
    assert b._org_db(lambda con: con.execute("SELECT COUNT(*) FROM org_safety WHERE email='awa@x.co'").fetchone()[0]) == 0


# ---- the suite: Settings (apps + web app), SDKs, CLI
def test_settings_show_the_choice_the_report_and_tell_members():
    page = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "function safetyRows(sf)" in page and "function detailsChoice(org)" in page and "data-org=\"patient_details\"" in page
    assert "Remove automatically (recommended)" in page and "action: 'org_safety'" in page and 'class="s-select" data-org' in page
    assert "value: t.type === 'checkbox' ? t.checked : t.value" in page
    assert "Your admins see how many times patient details were removed or stopped for each person" in page
    assert 'name === "org_safety"' in read("webapp", "bridge.js") and "_a_org_safety" in read("src", "ginkassistant", "ui", "settings_controller.py")
    assert "async def org_safety_csv" in read("src", "ginkassistant", "services", "api_client.py")


def test_python_sdk_and_cli(ws, monkeypatch, capsys):
    b, c, admin, nurse, admin_key, nurse_key = ws
    from gink import Client, GinkAPIError
    gink = Client(api_key=admin_key["Authorization"][7:], base_url="http://testserver/v1", http=c)
    assert gink.workspace.get().workspace["name"] == "City Hospital"
    assert gink.workspace.safety(days=3).days == 3
    with pytest.raises(GinkAPIError) as e:
        Client(api_key=nurse_key["Authorization"][7:], base_url="http://testserver/v1", http=c).workspace.safety()
    assert e.value.code == "not_admin"
    from gink_cli import main as cli

    class R:
        def __init__(self, j): self._j = j
        def json(self): return self._j
    report = {"workspace": {"name": "City Hospital"}, "days": 30, "totals": {"patient_details_removed": 2, "patient_details_stopped": 0,
              "photo_checked": 1}, "by_person": [{"name": "Awa", "account": "awa@x.co", "patient_details_removed": 2, "photo_checked": 1}]}
    calls = []

    def fake(key, base, method, path, **kw):
        calls.append(path)
        return R(report if "safety" in path else {"workspace": {"name": "City Hospital", "healthcare": True, "patient_details": "remove"},
                                                  "role": "admin", "status": "active"})
    monkeypatch.setattr(cli, "_env_call", fake)
    monkeypatch.setattr(cli, "settings", lambda: ("k", "https://x/v1"))
    assert cli.main(["workspace"]) == 0
    out = capsys.readouterr().out
    assert "City Hospital" in out and "patient details are removed automatically" in out and "gink workspace safety" in out
    assert cli.main(["workspace", "safety", "--days", "7"]) == 0 and calls[-1] == "/workspace/safety?days=7"
    out = capsys.readouterr().out
    assert "patient details removed   2" in out and "Awa: 2 removed, 1 photos" in out and "never words" in out


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_sdk_workspace(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text('''
import { Gink } from "%s";
const seen = [];
const gink = new Gink({ apiKey: "k", baseURL: "https://x/v1", fetch: async (url, init) => {
  seen.push([init.method, url]);
  return new Response(JSON.stringify({ object: "safety_report", totals: {} }), { status: 200 }); } });
await gink.workspace.get();
await gink.workspace.safety({ days: 7 });
console.log(JSON.stringify(seen));
''' % os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [["GET", "https://x/v1/workspace"], ["GET", "https://x/v1/workspace/safety?days=7"]]
    types = read("sdk", "js", "index.d.ts")
    assert "export interface SafetyReport" in types and "safety(options?: { days?: number }): Promise<SafetyReport>;" in types
