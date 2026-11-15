"""Smarter memory: a single fact said again (a new phone number, a new city) REPLACES the old one; facts a person can
have several of are all kept."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.services import memory as mem


def texts(store):
    return [m["text"] for m in store.list()]


def test_single_facts_are_updated_not_duplicated(tmp_path):
    s = mem.MemoryStore(str(tmp_path / "m.db"))
    s.add("My phone number is 555 0101")
    out = s.add("my phone number is 555 0199")
    assert out["replaced"] == "My phone number is 555 0101" and texts(s) == ["My phone number is 555 0199"]
    s.add("I live in Lagos"); s.add("I now live in Nairobi")
    s.add("My favorite color is blue"); s.add("My favourite colour is green")
    s.add("I'm 30 years old"); s.add("I am 31")
    assert texts(s) == ["My phone number is 555 0199", "I now live in Nairobi", "My favourite colour is green", "I am 31"]


def test_things_you_can_have_several_of_are_all_kept(tmp_path):
    s = mem.MemoryStore(str(tmp_path / "m.db"))
    for fact in ("My sister is Maria", "My sister is a nurse", "I like tea", "I like football", "I speak French", "I speak Wolof",
                 "My dog is called Rex", "I am allergic to peanuts", "I am tired of traffic"):
        assert "replaced" not in s.add(fact), fact
    assert len(texts(s)) == 9
    assert s.add("I like tea") and len(texts(s)) == 9                              # exactly the same: not added twice


def test_what_counts_as_one_subject():
    assert mem.subject("My phone number is 555") == "my phone number" == mem.subject("my phone number was 444")
    assert mem.subject("My favorite color is blue") == mem.subject("My favourite colour is green") == "my favourite colour"
    assert mem.subject("I live in Lima") == mem.subject("I now live near Cusco") == "i live"
    assert mem.subject("Call me Ibra") == "call me" and mem.subject("I work as a nurse") == "i work"
    for several in ("My sister is Maria", "I like tea", "I am allergic to nuts", "My friends are coming", "I am 31 and tired"):
        assert mem.subject(several) == "", several


def test_the_remember_tool_says_when_it_updates(tmp_path):
    from ginkassistant.services.actions import TaskStore, ToolRunner, DeviceActions
    import asyncio
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    runner.memory = mem.MemoryStore(str(tmp_path / "m.db"))
    first = asyncio.run(runner.execute("remember", {"fact": "My address is 12 Palm Street"}))
    second = asyncio.run(runner.execute("remember", {"fact": "My address is 4 Lake Road"}))
    assert first["message"].startswith("I'll remember") and second["message"].startswith("Updated: My address is 4 Lake Road")
    assert "12 Palm Street" in second["message"]
