"""The "Hey Gink" chip always says truthfully whether Gink is listening for its name."""
from ginkassistant.services.wake_status import describe


class Desktop:                                    # like services/wake_word.WakeWordListener
    def __init__(self, running=True, paused=False, error=""):
        self.running, self.paused, self.error = running, paused, error


class Phone:                                      # like services/android_voice.AndroidWakeListener
    def __init__(self, running=True, error="", prefer_offline=True):
        self.running, self.error, self.prefer_offline, self._paused = running, error, prefer_offline, False


def d(**kw):
    base = dict(enabled=True, supported=True)
    base.update(kw)
    return describe(**base)


def test_hidden_when_off_or_on_iphone():
    assert d(enabled=False)["state"] == "off"
    out = d(supported=False)
    assert out["state"] == "off" and "isn\u2019t available" in out["detail"]


def test_ready_says_nothing_leaves_the_device():
    out = d(listener=Desktop())
    assert out["state"] == "ready" and out["label"] == "Hey Gink" and "Nothing leaves this computer" in out["detail"]
    assert "this phone" in d(listener=Phone(), device="phone")["detail"]


def test_phone_without_offline_speech_is_honest():
    out = d(listener=Phone(prefer_offline=False), device="phone")
    assert out["state"] == "ready" and "online speech service" in out["detail"]


def test_paused_while_gink_uses_the_mic():
    assert d(listener=Desktop(paused=True))["state"] == "paused"


def test_active_after_hey_gink():
    assert d(listener=Desktop(paused=True), busy=True)["state"] == "active"


def test_download_progress():
    out = d(downloading=True, progress=0.42)
    assert out["state"] == "starting" and out["label"] == "Getting ready 42%"
    assert d(downloading=True)["label"] == "Getting ready"


def test_cant_start_is_a_problem_with_the_reason():
    out = d(status="Can\u2019t listen: no microphone found")
    assert out["state"] == "problem" and "no microphone found" in out["detail"]


def test_phone_mic_permission_off_is_a_problem_not_off():
    """Regression: Settings said "Off" when Android stopped listening because the mic permission was off."""
    out = d(listener=Phone(running=False, error="the microphone permission is off"), device="phone")
    assert out["state"] == "problem" and "microphone permission" in out["detail"]


def test_passing_trouble_keeps_trying():
    out = d(listener=Phone(error="the speech service is busy"), device="phone")
    assert out["state"] == "retrying" and "keeps trying" in out["detail"]


def test_starting():
    assert d()["state"] == "starting"
    assert d(listener=Desktop(running=False))["state"] == "starting"


def test_chip_is_in_the_page_and_clicks_open_voice_settings():
    from ginkassistant.ui import wake_ui
    assert "function wakeChip(" in wake_ui.JS and "ginkEmit('wake_chip')" in wake_ui.JS
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "ui", "main_screen.py"), encoding="utf-8").read()
    assert 'kind == "wake_chip"' in src and 'open_settings(panel="voice")' in src
