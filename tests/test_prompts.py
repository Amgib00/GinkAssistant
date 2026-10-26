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
