import os
import sys
import tempfile
import asyncio
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import toga
from datetime import datetime, timedelta
from ginkassistant.services.actions import TaskStore, ToolRunner, TaskAgent
from ginkassistant.ui.tasks_screen import TasksScreen
from ginkassistant.ui.home_actions import HomeActions
from test_actions import FakeDevice

def test_screens_build_and_refresh():
    app = toga.App("Gink", "com.amgib.ginkassistant")
    s = TaskStore(os.path.join(tempfile.mkdtemp(), "t.db"))
    agent = TaskAgent(ToolRunner(s, FakeDevice()), api_key="")
    scr = TasksScreen(app, s, agent)
    assert scr.snapshot()["groups"] == []                                   # the page shows its "All clear" state
    p = s.add("task", "Exam prep"); s.add("task", "Past papers", parent_id=p.id)
    s.add("alarm", "Wake up", due=datetime.now() + timedelta(hours=8), system_scheduled=True)
    snap = scr.snapshot()
    items = [i for g in snap["groups"] for i in g["items"]]
    assert len(items) == 2 and items[[i["title"] for i in items].index("Exam prep")]["steps_total"] == 1
    scr.call = lambda *a: asyncio.sleep(0)
    asyncio.run(scr._run_command("set a timer for 5 minutes"))
    assert "5m" in scr.status and scr.snapshot()["stats"]["timer"] == 1
    home = HomeActions(s, on_prompt=lambda t: None, on_open_tasks=lambda: None)
    assert "Next alarm" in home.today.text and "1 open task" in home.today.text
