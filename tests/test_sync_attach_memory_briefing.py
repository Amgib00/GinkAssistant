"""Sync between two devices, attachments, vision requests, memory, briefing."""
import asyncio, base64, io, json, os, sys, zipfile
from datetime import datetime, timedelta
from pathlib import Path
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import pytest


# ------------------------------------------------------------------ sync
class _Hist:
    """HistoryStore without a Toga app."""
    def __new__(cls, path):
        from ginkassistant.services.history import HistoryStore
        h = HistoryStore.__new__(HistoryStore)
        h.db_path = path
        h._init_db()
        return h


def _device(tmp, name):
    from ginkassistant.services.actions import TaskStore
    from ginkassistant.services.memory import MemoryStore
    d = tmp / name
    d.mkdir()
    return {"history": _Hist(d / "chat.db"), "items": TaskStore(str(d / "tasks.db")),
            "memory": MemoryStore(str(d / "mem.db")), "dir": d}


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _sync_for(dev, token, monkeypatch, backend):
    from ginkassistant.services import sync as sync_mod
    transport = httpx.ASGITransport(app=backend)
    monkeypatch.setattr(sync_mod.httpx, "AsyncClient", lambda **k: _REAL_ASYNC_CLIENT(transport=transport, **k))
    return sync_mod.SyncService(dev["dir"] / "state.json", lambda: "http://t", lambda: token, "ib@x.co",
                                dev["history"], dev["items"], dev["memory"])


def test_two_devices_stay_in_step(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "server.db"))
    from ginkassistant.services import backend_server as b
    token = b._token_response("ib@x.co", "Ibrahim")["token"]
    mac, phone = _device(tmp_path, "mac"), _device(tmp_path, "phone")

    # Mac: a chat, a task with a step, a reminder, an alarm, a memory
    mac["history"].save_message("s1", "user", "plan my exam revision")
    mac["history"].save_message("s1", "assistant", "Here's a plan...")
    t = mac["items"].add("task", "Revise maths")
    mac["items"].add("task", "Past papers", parent_id=t.id)
    mac["items"].add("reminder", "Call Mom", due=datetime.now() + timedelta(hours=2))
    mac["items"].add("alarm", "Wake up", due=datetime.now() + timedelta(hours=9))
    mac["memory"].add("Exams start on 12 November")

    async def go():
        s_mac, s_phone = _sync_for(mac, token, monkeypatch, b.app), _sync_for(phone, token, monkeypatch, b.app)
        assert await s_mac.sync_once()
        assert await s_phone.sync_once()
        # phone got everything except the alarm
        sessions = phone["history"].get_all_sessions()
        assert [m["content"] for m in sessions["s1"]["messages"]] == ["plan my exam revision", "Here's a plan..."]
        titles = sorted(i.title for i in phone["items"].list(include_done=True))
        assert titles == ["Call Mom", "Past papers", "Revise maths"]
        task = [i for i in phone["items"].list() if i.title == "Revise maths"][0]
        assert [c.title for c in phone["items"].children(task.id)] == ["Past papers"]
        assert [m["text"] for m in phone["memory"].list()] == ["Exams start on 12 November"]

        # phone: finish the task, delete the chat, forget the memory, add a chat
        await asyncio.sleep(0.01)
        phone["items"].set_done(task.id, True)
        phone["history"].clear_history("s1")
        phone["memory"].forget("exams")
        phone["history"].save_message("s2", "user", "hello from my phone")
        assert await s_phone.sync_once()
        assert await s_mac.sync_once()
        assert "s1" not in mac["history"].get_all_sessions()
        assert mac["history"].get_all_sessions()["s2"]["messages"][0]["content"] == "hello from my phone"
        mac_task = [i for i in mac["items"].list(include_done=True) if i.title == "Revise maths"][0]
        assert mac_task.done
        assert mac["memory"].list() == []
        assert [i.title for i in mac["items"].list(kind="alarm")] == ["Wake up"]    # alarm untouched

        # deleting an item syncs as a tombstone
        mac["items"].delete(mac_task.id)
        assert await s_mac.sync_once() and await s_phone.sync_once()
        assert not [i for i in phone["items"].list(include_done=True) if "maths" in i.title or "Past" in i.title]

        # no / bad token -> refused, nothing applied
        bad = _sync_for(_device(tmp_path, "intruder"), "not-a-token", monkeypatch, b.app)
        assert not await bad.sync_once() and "Sign in again" in bad.last_error
    asyncio.run(go())


# ------------------------------------------------------------------ attachments
def _png_bytes(size=(2400, 1200)):
    from PIL import Image
    img = Image.new("RGBA", size, (120, 200, 60, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _pdf_bytes(text="Exam timetable: Maths on 12 November"):
    # minimal valid one-page PDF with a text layer
    content = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return bytes(out)


def _docx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Shopping list</w:t></w:r></w:p>'
                                        '<w:p><w:r><w:t>Rice &amp; fish</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def test_attachment_types():
    from ginkassistant.services import attachments as a
    img = a.load_bytes(_png_bytes(), "photo.png")
    assert img.kind == "image" and img.data_url.startswith("data:image/jpeg;base64,") and img.thumb
    from PIL import Image
    full = Image.open(io.BytesIO(base64.b64decode(img.data_url.split(",")[1])))
    assert max(full.size) == a.MAX_IMAGE_SIDE                      # resized
    pdf = a.load_bytes(_pdf_bytes(), "timetable.pdf")
    assert pdf.kind == "text" and "Maths on 12 November" in pdf.text and pdf.pages == 1
    docx = a.load_bytes(_docx_bytes(), "list.docx")
    assert docx.text.splitlines() == ["Shopping list", "Rice & fish"]
    code = a.load_bytes(b"print('hi')\n", "hello.py")
    assert code.text.startswith("print")
    with pytest.raises(a.AttachmentError):
        a.load_bytes(b"\x00\x01binary", "thing.exe")
    pasted = a.load_data_url("data:image/png;base64," + base64.b64encode(_png_bytes((50, 50))).decode(), "pasted")
    assert pasted.kind == "image" and pasted.name == "pasted.png"
    prompt = a.build_prompt_text("When is maths?", [pdf, img])
    assert '<attached_file name="timetable.pdf">' in prompt and prompt.endswith("When is maths?")
    assert a.history_text("When is maths?", [pdf, img]) == "When is maths?\n\n\U0001F4CE timetable.pdf, photo.png"


def test_vision_request_and_memory_in_prompt(tmp_path, monkeypatch):
    from ginkassistant.services import attachments as a
    from ginkassistant.services.groq_worker import GroqBrain
    from ginkassistant.services.memory import MemoryStore
    sent = {}

    class Stream:
        def __init__(self): self.done = False
        def __aiter__(self): return self
        async def __anext__(self):
            if self.done: raise StopAsyncIteration
            self.done = True
            class C: pass
            c = C(); c.choices = [C()]; c.choices[0].delta = C(); c.choices[0].delta.content = "A green square."
            return c

    class Completions:
        async def create(self, **kw):
            sent.update(kw); return Stream()

    brain = GroqBrain.__new__(GroqBrain)
    brain.api_key, brain.session_id = "k", "s"
    brain.client = type("X", (), {"chat": type("Y", (), {"completions": Completions()})()})()
    brain.active_models = ["llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct"]
    brain.history = _Hist(tmp_path / "h.db")
    mem = MemoryStore(str(tmp_path / "m.db")); mem.add("Prefers short answers")
    brain.memory_provider = mem.as_prompt
    img = a.load_bytes(_png_bytes((300, 300)), "square.png")
    reply = asyncio.run(brain.ask("What is this?", attachments=[img]))
    assert reply == "A green square."
    assert sent["model"] == "meta-llama/llama-4-scout-17b-16e-instruct"
    user = sent["messages"][-1]["content"]
    assert user[0] == {"type": "text", "text": "What is this?"} and user[1]["image_url"]["url"].startswith("data:image/jpeg")
    assert "Prefers short answers" in sent["messages"][0]["content"]
    saved = brain.history.get_history("s")
    assert saved[0]["content"] == "What is this?\n\n\U0001F4CE square.png"        # no image data in history


def test_memory_tools_offline(tmp_path):
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner
    from ginkassistant.services.memory import MemoryStore
    mem = MemoryStore(str(tmp_path / "m.db"))
    agent = TaskAgent(ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)), memory=mem), api_key="")
    r = asyncio.run(agent.run("Remember that my exams start on 12 November"))
    assert "remember" in r.text.lower() and [m["text"] for m in mem.list()] == ["My exams start on 12 November"]
    asyncio.run(agent.run("remember that my exams start on 12 November"))       # no duplicate
    assert len(mem.list()) == 1
    assert "exams" in asyncio.run(agent.run("what do you remember about me")).text
    asyncio.run(agent.run("forget my exams"))
    assert mem.list() == [] and mem.as_prompt() == ""


# ------------------------------------------------------------------ briefing
def test_briefing_content_and_schedule(tmp_path):
    from ginkassistant.services import briefing
    from ginkassistant.services.actions import TaskStore
    store = TaskStore(str(tmp_path / "t.db"))
    now = datetime(2026, 10, 12, 7, 45)
    store.add("alarm", "Wake up", due=now.replace(hour=6, minute=30))
    store.add("event", "Team meeting", due=now.replace(hour=10, minute=0))
    store.add("reminder", "Pay rent", due=now - timedelta(days=2))
    t = store.add("task", "Revise maths")
    store.add("task", "Past papers", parent_id=t.id)

    async def news():
        return "", [{"title": "Big news today", "link": "https://example.com/n"}]
    md, said = asyncio.run(briefing.build_briefing(store, {"briefing_city": ""}, "Ibrahim", news_fn=news, now=now))
    assert "Good morning, Ibrahim" in md and "06:30 \u2014 Wake up" in md and "10:00 \u2014 Team meeting" in md
    assert "Pay rent" in md and "Revise maths \u2014 0/1 steps" in md and "[Big news today](https://example.com/n)" in md
    assert "Add your city" in md and "Team meeting at 10:00" in said
    p = {"briefing_enabled": True, "briefing_time": "07:30", "briefing_last_date": ""}
    assert briefing.is_due(p, now) and not briefing.is_due(p, now.replace(hour=7, minute=0))
    assert briefing.is_due(p, now.replace(hour=11, minute=50)) and not briefing.is_due(p, now.replace(hour=12, minute=5))
    assert not briefing.is_due({**p, "briefing_last_date": "2026-10-12"}, now)
    assert not briefing.is_due({**p, "briefing_enabled": False}, now)
