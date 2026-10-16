"""Computer control: exact commands, safe handling of user text, routing, and voice/wake fixes."""
import os, sys
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def mac(monkeypatch, tmp_path):
    from ginkassistant.services.actions import computer as c
    monkeypatch.setattr(c, "MAC", True); monkeypatch.setattr(c, "WIN", False)
    monkeypatch.setattr(c, "LINUX", False); monkeypatch.setattr(c, "MOBILE", False)
    calls, replies = [], {}

    def fake_run(cmd, timeout=20):
        calls.append(cmd)
        script = " ".join(cmd)
        for key, val in replies.items():
            if key in script:
                return val
        return True, ""
    monkeypatch.setattr(c, "run", fake_run)
    return c, calls, replies, tmp_path


def test_volume(mac):
    c, calls, replies, _ = mac
    replies["return output volume"] = (True, "40")
    pc = c.ComputerControl()
    assert pc.set_volume(action="up")["message"] == "Volume set to 55%."
    assert calls[-1][-1] == "55" and "on run argv" in calls[-1]              # level passed as an argument
    assert pc.set_volume(level=130)["level"] == 100
    assert pc.set_volume(action="mute")["message"] == "Muted."


def test_music_uses_the_running_app(mac):
    c, calls, replies, _ = mac
    replies['is running -e end run Spotify'] = (True, "false")
    replies['is running -e end run Music'] = (True, "true")
    r = c.ComputerControl().media_control("next")
    assert r["ok"] and r["message"] == "Next song in Music."
    assert any('tell application "Music" to next track' in " ".join(x) for x in calls)
    assert c.ComputerControl().media_control("dance")["ok"] is False


def test_note_text_is_passed_as_data_not_code(mac):
    c, calls, _, _ = mac
    evil = 'Buy rice" & (do shell script "rm -rf ~") & "'
    assert c.ComputerControl().create_note(evil, evil)["ok"]
    cmd = calls[-1]
    script = " ".join(cmd[:cmd.index("end run") + 1])
    assert "do shell script" not in script and "rm -rf" not in script         # never inside the script itself
    assert "do shell script" in cmd[-1] and cmd[-1].startswith("<h1>")        # only as the argument (HTML-escaped)


def test_quit_app_refuses_gink_and_checks_running(mac):
    c, calls, replies, _ = mac
    pc = c.ComputerControl()
    assert pc.quit_app("Gink")["ok"] is False and pc.quit_app("Finder")["ok"] is False
    replies["is running"] = (True, "false")
    assert pc.quit_app("Safari")["message"] == "Safari isn't open."


def test_find_and_open_files(mac, monkeypatch):
    c, calls, replies, tmp = mac
    home = tmp / "home"; (home / "Documents").mkdir(parents=True)
    cv = home / "Documents" / "Ibrahim CV 2026.pdf"; cv.write_text("x")
    (home / "Documents" / "notes.txt").write_text("x")
    monkeypatch.setattr(c.os.path, "expanduser", lambda p: str(home) if p == "~" else p.replace("~", str(home)))
    replies["mdfind"] = (True, str(cv))
    pc = c.ComputerControl()
    r = pc.find_files("cv")
    assert r["ok"] and "Ibrahim CV 2026.pdf" in r["message"] and "~/Documents" in r["message"]
    assert pc.resolve_file("1") == str(cv) and pc.resolve_file("number 1") == str(cv) and pc.resolve_file("CV 2026") == str(cv)
    assert pc.resolve_file("7") is None


def test_screenshot_card_and_status(mac, monkeypatch):
    c, calls, replies, tmp = mac
    def fake_shot(cmd, timeout=20):
        calls.append(cmd)
        if cmd[0] == "screencapture":
            open(cmd[-1], "wb").write(b"\x89PNG fake")
            return True, ""
        if cmd[:2] == ["pmset", "-g"]:
            return True, "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t76%; discharging; 4:12 remaining present: true"
        if cmd[0] == "sw_vers":
            return True, "10.15.7"
        return True, ""
    monkeypatch.setattr(c, "run", fake_shot)
    pc = c.ComputerControl(files_dir=str(tmp / "files"))
    r = pc.take_screenshot()
    assert r["ok"] and "(gink://file/Screenshot" in r["message"] and os.path.exists(r["path"])
    st = pc.system_status()["message"]
    assert "Battery 76% (on battery)" in st and "macOS 10.15.7" in st and "GB free" in st


def test_not_on_phones(monkeypatch):
    from ginkassistant.services.actions import computer as c
    monkeypatch.setattr(c, "MOBILE", True)
    assert "phone" in c.ComputerControl().set_volume(action="up")["message"]


def test_phrasings_route_instantly():
    from ginkassistant.services.actions import quick_parse as q
    assert q.parse("volume up") == ("set_volume", {"action": "up"})
    assert q.parse("set the volume to 30") == ("set_volume", {"level": 30})
    assert q.parse("next song") == ("media_control", {"action": "next"})
    assert q.parse("take a screenshot") == ("take_screenshot", {})
    assert q.parse("turn on dark mode") == ("set_dark_mode", {"mode": "on"})
    assert q.parse("find my cv") == ("find_files", {"query": "cv"})
    assert q.parse("quit safari") == ("quit_app", {"name": "Safari"})
    assert q.parse("find a restaurant near me") is None and q.parse("close it") is None


def test_wake_phrases_only_use_known_words():
    from ginkassistant.services.wake_word import WAKE_PHRASES, matches
    assert all("gink" not in p.split() and "jink" not in p.split() for p in WAKE_PHRASES)   # Vosk dropped these
    assert matches("hey ginkgo") and matches("hey king") and matches("hi gink") and not matches("hey kingdom")


def test_best_mac_voice():
    from ginkassistant.services import voice_bridge as vb
    if not hasattr(vb, "best_mac_voice"):
        pytest.skip("desktop voice code not loaded")
    catalina = [("Alex", "en_US"), ("Daniel", "en_GB"), ("Samantha", "en_US"), ("Thomas", "fr_FR"), ("Amelie", "fr_CA")]
    assert vb.best_mac_voice("Female (Jenny)", catalina) == "Samantha" and vb.best_mac_voice("Male (Guy)", catalina) == "Alex"
    assert vb.best_mac_voice("henri", catalina) == "Thomas" and vb.best_mac_voice("ryan", catalina) == "Daniel"
    assert vb.best_mac_voice("Female (Jenny)", catalina + [("Ava (Premium)", "en_US")]) == "Ava (Premium)"
