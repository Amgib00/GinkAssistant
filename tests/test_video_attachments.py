"""Videos as attachments (0.1.162): the chat page takes a few frames from a video (the browser engine plays it, no extra
library) and they go to the AI as pictures, in order, with a sentence saying what they are -- in the apps and the web
app. Before, a .mov or .mp4 was refused ("Gink can't read .mov files yet")."""
import base64
import io
import os
import sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def frame(colour=(200, 40, 40)):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (64, 36), colour).save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def test_frames_become_one_video_attachment_with_a_sentence_for_the_ai():
    from ginkassistant.services import attachments as a
    frames = [{"at": t, "data": frame((40 * i, 80, 120))} for i, t in enumerate((7.0, 1.0, 3.0, 5.0, 9.0, 11.0))]
    v = a.video_attachment("../Camera test.mov", 12.4, frames + [{"at": 2, "data": "javascript:alert(1)"}, "x"])
    assert v.kind == "video" and v.name == "Camera test.mov" and [f["at"] for f in v.frames] == [1.0, 3.0, 5.0, 7.0, 9.0]
    assert v.chip()["note"] == "5 frames · 0:12" and v.thumb.startswith("data:image/")
    parts = a.picture_parts("Why does my camera look like this?", [v])
    assert [p["type"] for p in parts] == ["text"] + ["image_url"] * 5
    assert "frames taken from it in order, at 0:01, 0:03, 0:05, 0:07, 0:09" in parts[0]["text"]
    assert parts[0]["text"].endswith("Why does my camera look like this?")
    # photos first, five pictures at most
    photo = a.Attachment(name="p.jpg", kind="image", data_url=frame(), thumb=frame())
    parts = a.picture_parts("", [v, photo, photo])
    assert len(parts) == 6 and parts[1]["image_url"]["url"] == photo.data_url and "as 3 pictures" in parts[0]["text"]
    assert a.picture_parts("", [v])[0]["text"].endswith("What happens in this video?")
    with pytest.raises(a.AttachmentError):
        a.video_attachment("x.mp4", 3, [{"at": 1, "data": "data:text/html;base64,AA"}])
    assert "Try an .mp4" in a.video_problem("x.mov", "unreadable") and "shorter clip" in a.video_problem("x.mov", "slow")
    assert a.history_text("look", [v]) == "look\n\n\U0001F4CE Camera test.mov"          # history keeps the name only


def test_picked_videos_go_to_the_page_and_others_are_explained():
    from ginkassistant.services import attachments as a
    with pytest.raises(a.VideoFile) as got:
        a.load_path("/tmp/clip.MOV")
    assert got.value.path == "/tmp/clip.MOV"
    with pytest.raises(a.AttachmentError) as got:
        a.load_bytes(b"\x00\x00\x00\x18ftypmp42", "clip.mp4")
    assert "Drag clip.mp4 into the message box" in str(got.value)
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    assert 'kind == "attach_video"' in main and "await hand_video(str(path))" in main and "att_svc.VIDEO_EXT" in main
    assert 'has_photo = any(a.kind in ("image", "video")' in main and "Watching your video" in main
    worker = read("src", "ginkassistant", "services", "groq_worker.py")
    assert "picture_parts(prompt_text, attachments)" in worker
    page = read("src", "ginkassistant", "ui", "web_chat_view.py")
    assert "function videoFrames(src, done)" in page and "window.videoFromData" in page and "if (isVideo(file))" in page
    bridge = read("webapp", "bridge.js")
    assert "attach_video: function (v)" in bridge and 'a.kind === "video"' in bridge
    assert "is attached as \" +" in bridge                                                 # the same sentence as the apps


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


@pytest.mark.skipif(_browser() is None, reason="needs Playwright with Chromium")
def test_the_page_takes_frames_from_a_real_video(tmp_path):
    from ginkassistant.ui.web_chat_view import _build_page_html
    (tmp_path / "p.html").write_text(_build_page_html("Hi", "x"), encoding="utf-8")
    with _browser()() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no Chromium here ({type(exc).__name__})")
        page = browser.new_page()
        page.goto((tmp_path / "p.html").as_uri())
        page.evaluate("() => { window.__ev = []; window.ginkEmit = function (t, v) { window.__ev.push([t, v]); }; }")
        # a clip recorded right here (a canvas changing colour), dropped into the message box like a file
        page.evaluate("""() => new Promise(done => {
            const c = document.createElement('canvas'); c.width = 64; c.height = 36; const g = c.getContext('2d');
            const rec = new MediaRecorder(c.captureStream(10), {mimeType: 'video/webm'}), parts = [];
            rec.ondataavailable = e => parts.push(e.data);
            rec.onstop = () => {
              const dt = new DataTransfer(); dt.items.add(new File(parts, 'Camera test.webm', {type: 'video/webm'}));
              document.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); done();
            };
            let i = 0; rec.start();
            const t = setInterval(() => { g.fillStyle = ['red', 'green', 'blue'][i % 3]; g.fillRect(0, 0, 64, 36);
                                          if (++i > 14) { clearInterval(t); rec.stop(); } }, 100);
        })""")
        page.wait_for_function("() => window.__ev.some(e => e[0] === 'attach_video')", timeout=30000)
        got = page.evaluate("() => window.__ev.find(e => e[0] === 'attach_video')[1]")
        assert not got.get("error") and len(got["frames"]) >= 2 and got["name"] == "Camera test.webm"
        assert all(f["data"].startswith("data:image/jpeg;base64,") for f in got["frames"])
        assert [f["at"] for f in got["frames"]] == sorted(f["at"] for f in got["frames"])
        page.evaluate("() => { window.__ev = []; videoFromData('data:video/mp4;base64,AAAA', 'broken.mp4'); }")
        page.wait_for_function("() => window.__ev.some(e => e[0] === 'attach_video')", timeout=30000)
        assert page.evaluate("() => window.__ev.find(e => e[0] === 'attach_video')[1]") == {"name": "broken.mp4", "error": "unreadable"}
        browser.close()
    from ginkassistant.services import attachments as a
    v = a.video_attachment(got["name"], got["duration"], got["frames"])
    assert v.frames and a.picture_parts("", [v])[1]["image_url"]["url"] == v.frames[0]["data"]


def test_the_sdks_and_cli_send_videos_like_the_apps(monkeypatch, tmp_path):
    import json
    import shutil
    import subprocess
    sys.path.insert(0, os.path.join(ROOT, "cli"))
    from gink import client as sdk
    from ginkassistant.services import attachments as a
    f = frame()
    parts = sdk.video_parts([f, f, f], "what happens?", "clip.mp4", 9.0)
    app = a.picture_parts("what happens?", [a.video_attachment("clip.mp4", 9.0, [{"at": t, "data": f} for t in (1.5, 4.5, 7.5)])])
    assert parts[0]["text"] == app[0]["text"] and len(parts) == 4                    # the same sentence as the apps'
    seen = {}
    monkeypatch.setattr(sdk.Client, "chat", lambda self, messages, model="", **k: seen.update(m=messages) or "A blue screen.")
    c = sdk.Client.__new__(sdk.Client)
    assert c.watch([f, f], "why?", duration=4) == "A blue screen." and len(seen["m"][0]["content"]) == 3
    monkeypatch.setattr(shutil, "which", lambda name: None)                           # no ffmpeg: said plainly
    with pytest.raises(sdk.GinkAPIError) as got:
        sdk.video_frames(str(tmp_path / "clip.mp4"))
    assert "needs ffmpeg" in str(got.value)
    main = read("cli", "gink_cli", "main.py")
    assert 'if argv[:1] == ["watch"]:' in main and 'gink watch VIDEO ["question"]' in main
    monkeypatch.undo()
    node = shutil.which("node")
    if node:                                                                          # the JS SDK: the same sentence
        out = subprocess.run([node, "--input-type=module", "-e",
                              "import {videoParts} from './sdk/js/index.js';"
                              f"console.log(JSON.stringify(videoParts([{json.dumps(f)}, {json.dumps(f)}, {json.dumps(f)}],"
                              " {name: 'clip.mp4', duration: 9, question: 'what happens?'})[0].text));"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert json.loads(out.stdout) == app[0]["text"], out.stderr
    assert "videoFrames" in read("sdk", "js", "index.d.ts") and "watch(frames" in read("sdk", "js", "index.d.ts")
