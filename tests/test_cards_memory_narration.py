"""Question cards, recalled memories and Genie's narration."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
read = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_memory_recall_picks_the_matching_memories():
    from ginkassistant.services.memory import recall
    mem = [{"text": "My exams start on 12 November", "created": 1}, {"text": "I live in Dakar", "created": 2},
           {"text": "My sister Awa studies medicine", "created": 3}]
    assert [m["text"] for m in recall(mem, "When are my exams?")] == ["My exams start on 12 November"]
    assert recall(mem, "hello there") == [] and recall(mem, "") == []
    assert len(recall(mem * 3, "exams Dakar Awa medicine", k=3)) == 3


def test_question_cards_and_recalled_line_are_wired_everywhere():
    extras = read("src", "ginkassistant", "ui", "chat_extras.py")
    js = extras[extras.index('JS = r"""'):]
    assert "window.upgradeQuestionCards" in js and "window.showRecalled" in js and "ginkEmit('send', text)" in js
    assert "if (window.upgradeQuestionCards) upgradeQuestionCards(el);" in read("src", "ginkassistant", "ui", "web_chat_view.py")
    from ginkassistant.services.groq_worker import DEFAULT_SYSTEM_PROMPT
    bridge = read("webapp", "bridge.js")
    assert "language ask" in DEFAULT_SYSTEM_PROMPT and "language ask" in bridge                # apps and web know about cards
    assert "showRecalled(recallMemories(text))" in bridge and "takeMemories((j.changes || {}).memories)" in bridge
    assert "await web_chat.show_recalled(recalled)" in read("src", "ginkassistant", "ui", "main_screen.py")


def test_genie_records_its_narration(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_genie as T
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "n.db"))
    gen = T.srv.__wrapped__(tmp_path, monkeypatch)
    b, c, h = next(gen)
    pid = c.post("/genie/projects", headers=h, json={"name": "N"}).json()["project"]["id"]
    T.SCRIPT[:] = [{"content": "Writing the page.", "tool_calls": [T.call("write_file", path="a.html", content="x")]}, {"content": "Done."}]
    steps = c.post(f"/genie/projects/{pid}/ask", headers=h, json={"instruction": "go"}).json()["steps"]
    assert [s["kind"] for s in steps] == ["note", "write"] and steps[0]["title"] == "Writing the page."
    assert "fix any error you find and run it again" in b.GENIE_SYSTEM
