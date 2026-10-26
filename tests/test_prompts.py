"""The prompt library (the "/" menu): the apps' store and the page wiring."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import pytest
from ginkassistant.services.prompts import PromptStore, MAX_PROMPTS


def test_prompt_store(tmp_path):
    st = PromptStore(str(tmp_path / "data" / "prompts.json"))
    assert st.all() == []
    a = st.add("  Reply to this customer politely:  ")
    assert a["text"] == "Reply to this customer politely:" and [p["id"] for p in st.all()] == [a["id"]]
    for bad, msg in (("", "Write the prompt"), ("x" * 2001, "up to 2000"), ("Reply to this customer politely:", "already")):
        with pytest.raises(ValueError, match=msg):
            st.add(bad)
    for i in range(MAX_PROMPTS - 1):
        st.add(f"prompt {i}")
    with pytest.raises(ValueError, match="up to 50"):
        st.add("one too many")
    assert st.delete(a["id"]) and not st.delete(a["id"]) and len(st.all()) == MAX_PROMPTS - 1
    (tmp_path / "data" / "prompts.json").write_text("{broken")
    assert st.all() == [] and st.add("works again")["text"] == "works again"           # a damaged file never blocks


def test_page_and_settings_wiring():
    extras = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "chat_extras.py"), encoding="utf-8").read()
    js = extras[extras.index('JS = r"""'):]
    assert "window.setPrompts" in js and "SLASH_BUILTIN" in js and "e.stopImmediatePropagation(); slashPick" in js
    settings = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    assert "action: 'add_prompt'" in settings and "action: 'delete_prompt'" in settings
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert 'name === "add_prompt"' in bridge and "prompts: myPrompts()" in bridge


def test_server_keeps_each_accounts_prompts(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "p.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    me = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "E")["token"]}
    assert c.get("/account/prompts", headers=me).json() == {"prompts": [], "updated": 0}
    r = c.put("/account/prompts", headers=me, json={"prompts": [{"id": "a1", "text": " Hi "}, {"id": "a2", "text": "Hi"},
                                                                {"id": "<x>", "text": "Two"}, {"text": ""}]}).json()
    assert [p["text"] for p in r["prompts"]] == ["Hi", "Two"] and r["prompts"][1]["id"] == "x" and r["updated"] > 0
    assert c.get("/account/prompts", headers=eve).json()["prompts"] == []                      # separate accounts
    too_many = [{"id": f"p{i}", "text": f"t{i}"} for i in range(51)]
    assert c.put("/account/prompts", headers=me, json={"prompts": too_many}).status_code == 422
    assert c.get("/account/prompts").status_code == 401
    c.post("/account/delete", headers=me, json={"confirm": "DELETE"})
    assert b._prompts_db(lambda con: con.execute("SELECT COUNT(*) FROM account_prompts").fetchone()[0]) == 0


def test_replace_all_takes_the_accounts_list(tmp_path):
    st = PromptStore(str(tmp_path / "prompts.json"))
    st.add("old one")
    st.replace_all([{"id": "s1", "text": "from the account"}, {"bad": True}])
    assert st.all() == [{"id": "s1", "text": "from the account"}]
