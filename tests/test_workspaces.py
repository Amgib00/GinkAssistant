"""Workspaces for hospitals, schools and businesses: invite and accept, admins see members and counts
(never chats), shared instructions, and healthcare mode that keeps patient data out of every AI feature."""
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from fastapi import HTTPException

Y = time.gmtime().tm_year


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "org.db"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    monkeypatch.setattr(b, "_send_email", lambda *a, **k: "")
    c = TestClient(b.app)

    def account(email, by=Y - 35):
        b._upsert_user(email, email.split("@")[0].title(), None, "password")
        if by:
            b._set_birth_year(email, by)
        return {"Authorization": "Bearer " + b._token_response(email, email.split("@")[0])["token"]}
    return b, c, account


def setup(b, c, account, healthcare=True):
    admin = account("director@hopital.sn")
    nurse = account("awa@hopital.sn")
    assert c.post("/org", headers=admin, json={"name": "Hôpital Principal", "healthcare": healthcare}).status_code == 200
    assert c.post("/org/invite", headers=admin, json={"email": "awa@hopital.sn"}).json()["status"] == "invited"
    assert c.get("/org", headers=nurse).json()["status"] == "invited"
    assert b._org_rules("awa@hopital.sn") is None                                 # not until she accepts
    c.post("/org/respond", headers=nurse, json={"accept": True})
    return admin, nurse


def test_create_invite_accept_and_what_admins_see(srv):
    b, c, account = srv
    teen = account("teen@x.co", Y - 15)
    assert c.post("/org", headers=teen, json={"name": "X"}).status_code == 403       # adults create workspaces
    admin, nurse = setup(b, c, account)
    view = c.get("/org", headers=admin).json()
    assert view["role"] == "admin" and view["org"]["healthcare"] is True
    m = {x["id"]: x for x in view["members"]}
    assert m["awa@hopital.sn"]["status"] == "active" and m["awa@hopital.sn"]["messages_today"] == 0
    assert "members" not in c.get("/org", headers=nurse).json()                       # members don't see the list
    assert c.post("/org/invite", headers=nurse, json={"email": "x@y.z"}).status_code == 403
    other = account("other@x.co")
    c.post("/org", headers=other, json={"name": "Other"})
    assert c.post("/org/invite", headers=other, json={"email": "awa@hopital.sn"}).status_code == 409   # one workspace


def test_patient_data_is_refused_in_healthcare_mode(srv):
    b, c, account = srv
    for text in ("Summarise the notes for patient Mamadou Diallo, bed 4", "MRN: 2026-114578 needs a discharge letter",
                 "DOB 12/03/1961, admitted yesterday with chest pain", "patiente Aïssatou Ndiaye au 77 123 45 67",
                 "numéro de dossier 88-41237 pour la sortie"):
        assert b._looks_like_patient_data(text), text
    for text in ("Write a night-shift rota for 6 nurses", "What are the WHO guidelines for hand hygiene?",
                 "Explain sepsis warning signs for a staff training session", "Draft a letter to patients about parking"):
        assert not b._looks_like_patient_data(text), text
    admin, nurse = setup(b, c, account)
    r = c.post("/ai/openai/v1/chat/completions", headers=nurse,
               json={"messages": [{"role": "user", "content": "Summarise the notes for patient Mamadou Diallo"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "patient_data"
    r = c.post("/sites", headers=nurse, json={"prompt": "a page with the results of patient Fatou Sow"})
    assert r.status_code == 422 and "healthcare mode" in r.json()["detail"]


def test_workspace_rules_reach_the_ai(srv, monkeypatch):
    b, c, account = srv
    admin, nurse = setup(b, c, account)
    c.put("/org/settings", headers=admin, json={"instructions": "Answer in French. We are in Dakar."})
    seen = {}

    def stop(body, cap):
        seen["messages"] = body["messages"]
        raise HTTPException(status_code=418, detail="stop")
    monkeypatch.setattr(b, "_fit_reasoning", stop)
    async def same(model, images=False): return model
    monkeypatch.setattr(b, "_current_model", same)
    c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": "Write a rota"}]})
    system = seen["messages"][0]["content"]
    assert b.HEALTHCARE_RULES in system and "Answer in French. We are in Dakar." in system
    c.put("/org/settings", headers=admin, json={"healthcare": False})
    c.post("/ai/openai/v1/chat/completions", headers=nurse, json={"messages": [{"role": "user", "content": "patient Mamadou Diallo"}]})
    assert b.HEALTHCARE_RULES not in seen["messages"][0]["content"]                 # off: no guard, no rules


def test_leave_remove_and_delete(srv):
    b, c, account = srv
    admin, nurse = setup(b, c, account)
    assert c.post("/org/leave", headers=admin).status_code == 409                    # the only admin, others inside
    assert c.post("/org/remove", headers=admin, json={"email": "awa@hopital.sn"}).status_code == 200
    assert b._org_rules("awa@hopital.sn") is None
    assert c.post("/org/delete", headers=admin, json={"confirm": "wrong"}).status_code == 422
    assert c.post("/org/delete", headers=admin, json={"confirm": "Hôpital Principal"}).json() == {"org": None}
    assert c.get("/org", headers=admin).json() == {"org": None}


def test_settings_pieces():
    root = os.path.join(os.path.dirname(__file__), "..")
    page = open(os.path.join(root, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    bridge = open(os.path.join(root, "webapp", "bridge.js"), encoding="utf-8").read()
    ctl = open(os.path.join(root, "src", "ginkassistant", "ui", "settings_controller.py"), encoding="utf-8").read()
    assert "id: 'workspace'" in page and "never their chats" in page
    for a in ("org_create", "org_invite", "org_accept", "org_decline", "org_leave", "org_remove", "org_instructions", "org_set", "org_delete"):
        assert f'name === "{a}"' in bridge and f"_a_{a}" in ctl, a


def test_genie_follows_the_workspace_too(srv):
    b, c, account = srv
    admin, nurse = setup(b, c, account)
    r = c.post("/genie/projects", headers=nurse, json={"prompt": "Build a page listing patient Mamadou Diallo's results"})
    assert r.status_code == 422 and "healthcare mode" in r.json()["detail"]
    assert c.get("/genie/projects", headers=nurse).json()["projects"] == []        # nothing half-made


def test_admins_download_usage_without_chats(srv):
    b, c, account = srv
    admin, nurse = setup(b, c, account)
    b._count_call("awa@hopital.sn", "t1", "free")
    b._count_call("awa@hopital.sn", "t2", "free")
    r = c.get("/org/usage.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="gink-H-pital-Principal-usage.csv"' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,name,account,messages,images,songs"
    awa = [l for l in lines if "awa@hopital.sn" in l]
    assert len(awa) == 1 and awa[0].endswith(",2,0,0")
    assert c.get("/org/usage.csv", headers=nurse).status_code == 403                  # admins only


def test_sidebar_waits_before_sliding_open():
    page = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    assert "var PEEK_DELAY = 300;" in page and "setTimeout(function () { if (!hoverBlocked) document.body.classList.add('peek'); }, PEEK_DELAY)" in page
