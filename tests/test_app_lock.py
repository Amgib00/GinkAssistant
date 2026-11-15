"""Lock Gink (0.1.154) across the suite: the apps unlock with the DEVICE's own Face ID / Touch ID / Optic ID /
Windows Hello / Android face-fingerprint-PIN / fprintd -- Gink gets only yes or no; browsers (the web app, Genie,
the console) with one of the account's own passkeys; the Gink Genie app asks the device; `gink login` says passkeys
work. The system calls are stood in for here (each platform's real API can only run on that platform)."""
import asyncio
import base64
import hashlib
import json
import os
import struct
import sys
import threading
import time
import types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---------------------------------------------------------------- the device check, platform by platform
def test_genie_has_the_same_device_check():
    assert read("src", "ginkgenie", "biometric.py") == read("src", "ginkassistant", "services", "biometric.py")


def test_apple_local_authentication(monkeypatch):
    from ginkassistant.services import biometric as bio
    seen, loaded = [], []

    class Ctx:
        biometryType = 2                               # Face ID
        def __init__(self, ok): self.ok = ok
        def canEvaluatePolicy_error_(self, policy, error): return True
        def evaluatePolicy_localizedReason_reply_(self, policy, reason, block):
            seen.append((policy, reason))              # the system answers on another thread
            threading.Thread(target=lambda: block.func(self.ok, None if self.ok else "error")).start()

    class Block:
        def __init__(self, func, restype, *argtypes): self.func, self.types = func, (restype,) + argtypes

    ctx = {"value": Ctx(True)}
    objc = types.ModuleType("rubicon.objc")
    objc.ObjCClass = lambda name: types.SimpleNamespace(alloc=lambda: types.SimpleNamespace(init=lambda: ctx["value"]))
    objc.Block, objc.objc_id = Block, object
    objc.ObjCInstance = lambda e: types.SimpleNamespace(code=-2)
    runtime = types.ModuleType("rubicon.objc.runtime"); runtime.load_library = loaded.append
    for name, mod in (("rubicon", types.ModuleType("rubicon")), ("rubicon.objc", objc), ("rubicon.objc.runtime", runtime)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(bio, "platform", lambda: "ios")
    assert asyncio.run(bio.kind()) == "Face ID"
    assert asyncio.run(bio.authenticate("Unlock Gink")) == (True, "")
    assert seen[-1] == (bio.LA_POLICY_OWNER, "Unlock Gink") and "LocalAuthentication" in loaded   # passcode fallback, like Apple
    ctx["value"] = Ctx(False)
    assert asyncio.run(bio.authenticate("Unlock Gink")) == (False, "Cancelled.")


def test_windows_hello(monkeypatch):
    from ginkassistant.services import biometric as bio
    asked = []

    class Avail: AVAILABLE, DEVICE_NOT_PRESENT = 0, 1
    class Res: VERIFIED, CANCELED = 0, 6
    class Verifier:
        state = {"avail": Avail.AVAILABLE, "res": Res.VERIFIED}
        @staticmethod
        async def check_availability_async(): return Verifier.state["avail"]
        @staticmethod
        async def request_verification_async(msg): asked.append(msg); return Verifier.state["res"]

    ui = types.ModuleType("winrt.windows.security.credentials.ui")
    ui.UserConsentVerifier, ui.UserConsentVerifierAvailability, ui.UserConsentVerificationResult = Verifier, Avail, Res
    for name in ("winrt", "winrt.windows", "winrt.windows.security", "winrt.windows.security.credentials"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "winrt.windows.security.credentials.ui", ui)
    monkeypatch.setattr(bio, "platform", lambda: "windows")
    assert asyncio.run(bio.kind()) == "Windows Hello"
    assert asyncio.run(bio.authenticate("Unlock Gink")) == (True, "") and asked == ["Unlock Gink"]
    Verifier.state["res"] = Res.CANCELED
    assert asyncio.run(bio.authenticate("Unlock Gink")) == (False, "Cancelled.")
    Verifier.state["avail"] = Avail.DEVICE_NOT_PRESENT
    assert asyncio.run(bio.kind()) == "" and "Windows Hello" in asyncio.run(bio.authenticate())[1]


def test_android_screen_lock(monkeypatch):
    from ginkassistant.services import biometric as bio
    intents = []

    class Keyguard:
        secure = True
        def isDeviceSecure(self): return self.secure
        def createConfirmDeviceCredentialIntent(self, title, text): intents.append((title, text)); return "intent"
    keyguard = Keyguard()
    activity = types.SimpleNamespace(getSystemService=lambda what: keyguard if what == "keyguard" else None)
    result = {"code": -1}

    async def intent_result(intent): return {"resultCode": result["code"]}
    app = types.SimpleNamespace(_impl=types.SimpleNamespace(native=activity, intent_result=intent_result))
    content = types.ModuleType("android.content"); content.Context = types.SimpleNamespace(KEYGUARD_SERVICE="keyguard")
    appmod = types.ModuleType("android.app"); appmod.Activity = types.SimpleNamespace(RESULT_OK=-1)
    java = types.ModuleType("java"); java.jclass = lambda name: "biometric"
    for name, mod in (("android", types.ModuleType("android")), ("android.content", content), ("android.app", appmod), ("java", java)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(bio, "platform", lambda: "android")
    assert asyncio.run(bio.kind(app)) == "Screen lock"
    assert asyncio.run(bio.authenticate("Unlock Gink", app)) == (True, "") and intents == [("Unlock Gink", "Unlock Gink")]
    result["code"] = 0
    assert asyncio.run(bio.authenticate("Unlock Gink", app))[0] is False
    keyguard.secure = False
    assert asyncio.run(bio.authenticate("Unlock Gink", app)) == (False, bio.NONE_SET_UP["android"])


def test_linux_fingerprint_and_nothing_set_up(monkeypatch):
    from ginkassistant.services import biometric as bio
    monkeypatch.setattr(bio, "platform", lambda: "linux")
    monkeypatch.setattr(bio.shutil, "which", lambda name: "/usr/bin/fprintd-verify")
    monkeypatch.setattr(bio.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="Verify result: verify-match (done)"))
    assert asyncio.run(bio.kind()) == "Fingerprint" and asyncio.run(bio.authenticate()) == (True, "")
    monkeypatch.setattr(bio.shutil, "which", lambda name: None)
    assert asyncio.run(bio.kind()) == "" and asyncio.run(bio.authenticate()) == (False, bio.NONE_SET_UP["linux"])
    monkeypatch.setattr(bio, "platform", lambda: "macos")                  # no rubicon here: never raises
    ok, msg = asyncio.run(bio.authenticate())
    assert ok is False and msg.startswith(bio.UNAVAILABLE)


# ---------------------------------------------------------------- the apps: settings, start-locked page, wiring
@pytest.fixture
def app(tmp_path, monkeypatch):
    from ginkassistant.services import prefs
    monkeypatch.setattr(prefs, "config_dir", lambda _app: tmp_path)
    return types.SimpleNamespace()


def test_lock_setting_needs_the_device_first(app):
    from ginkassistant.services import prefs
    from ginkassistant.ui.settings_controller import SettingsController
    ctl = SettingsController.__new__(SettingsController)
    ctl.app, ctl.lock_kind = app, "Face ID"
    toasts = []

    async def toast(text, kind=""): toasts.append((text, kind))
    async def push(*a, **k): pass
    ctl.web, ctl.push, ctl.apply_all = types.SimpleNamespace(settings_toast=toast), push, lambda: None

    async def yes(on): return True, ""
    async def no(on): return False, "Cancelled."
    ctl.lock_check = yes
    asyncio.run(ctl.on_setting("app_lock", True))
    assert prefs.load(app)["app_lock"] is True and toasts[-1] == ("Gink now locks with Face ID.", "")
    ctl.lock_check = no
    asyncio.run(ctl.on_setting("app_lock", False))
    assert prefs.load(app)["app_lock"] is True and toasts[-1] == ("Cancelled.", "err")       # still on: it wasn't you
    asyncio.run(ctl.on_setting("app_lock_after", "15"))
    assert prefs.load(app)["app_lock_after"] == "15"
    asyncio.run(ctl.on_setting("memory_suggest", False))                                    # fixed: it did nothing in the apps
    assert prefs.load(app)["memory_suggest"] is False
    assert {"app_lock", "app_lock_after", "people_on"}.isdisjoint(prefs.SYNCED)               # this device only


def test_page_lock_screen_and_start_locked():
    from ginkassistant.ui.web_chat_view import _build_page_html
    html = _build_page_html("Hi", "x")
    assert "window.appLock = function (on, opts)" in html and "ginkEmit('unlock', true)" in html
    assert "ginkEmit('lock_signout', true)" in html and "closeLive()" in html
    assert "if (el && !el.contains(e.target)) { e.preventDefault(); e.stopPropagation(); }" in html   # no typing behind it
    assert "ginkEmit('page_visibility'" in html and "appLock(true, {busy: true" not in html
    locked = _build_page_html("Hi", "x", True)
    assert "appLock(true, {busy: true, message: 'Checking it’s you…'})" in locked             # covered from the first frame


def test_apps_wiring():
    main = read("src", "ginkassistant", "ui", "main_screen.py")
    for must in ('biometric.authenticate("Unlock Gink", app)', 'LOCKED_OK = {"unlock", "lock_signout", "page_visibility"}',
                 "if lock[\"locked\"] and kind not in LOCKED_OK:", "app.main_window.on_lose_focus = went_away",
                 "app.main_window.on_gain_focus = came_back", "start_locked=bool(prefs.load(app).get(\"app_lock\"))",
                 "settings.lock_check = check_lock_setting", 'lock.update(locked=False, away=None, quiet_until=time.time() + 3)'):
        assert must in main, must
    project = read("pyproject.toml")
    assert "NSFaceIDUsageDescription" in project and project.count('"winrt-Windows.Security.Credentials.UI"') == 2
    page = read("src", "ginkassistant", "ui", "settings_page.py")
    assert "'Require ' + info.lock_kind + ' to open Gink'" in page and "key: 'app_lock_after'" in page


# ---------------------------------------------------------------- browsers: a passkey of your own
def soft_passkey():
    """A software passkey (P-256), to test the server's checks for real."""
    import cbor2
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    nums = key.public_key().public_numbers()
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})

    def assertion(cid, challenge, origin="http://testserver", rp_id="testserver", count=1):
        client = json.dumps({"type": "webauthn.get", "challenge": challenge, "origin": origin, "crossOrigin": False}).encode()
        auth = hashlib.sha256(rp_id.encode()).digest() + bytes([0x05]) + struct.pack(">I", count)     # user present + verified
        sig = key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": cid, "rawId": cid, "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64(client), "authenticatorData": b64(auth), "signature": b64(sig), "userHandle": None}}
    return b64(cose), assertion


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "lock.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    b._upsert_user("eve@example.com", "Eve", None, "password")
    me = {"Authorization": "Bearer " + b._token_response("ib@example.com", "Ibrahim")["token"]}
    eve = {"Authorization": "Bearer " + b._token_response("eve@example.com", "Eve")["token"]}
    return b, c, me, eve


ME_ID = base64.urlsafe_b64encode(b"credential-of-ib").rstrip(b"=").decode()       # real ids are base64url bytes
EVE_ID = base64.urlsafe_b64encode(b"credential-of-ev").rstrip(b"=").decode()


def test_passkey_unlocks_only_its_owner(srv):
    b, c, me, eve = srv
    assert c.post("/account/passkeys/verify/begin", headers=me).status_code == 409          # add a passkey first
    public, assertion = soft_passkey()
    b._pk_db(lambda con: con.execute("INSERT INTO passkeys (id, email, public_key, sign_count, created) VALUES (?, ?, ?, 0, ?)",
                                     (ME_ID, "ib@example.com", public, time.time())))
    begin = c.post("/account/passkeys/verify/begin", headers=me).json()
    assert [x["id"] for x in begin["options"]["allowCredentials"]] == [ME_ID]           # only this account's passkeys
    assert begin["options"]["userVerification"] == "required"
    r = c.post("/account/passkeys/verify/finish", headers=me,
               json={"request_id": begin["request_id"], "credential": assertion(ME_ID, begin["options"]["challenge"])})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert b._pk_db(lambda con: con.execute("SELECT sign_count, last_used FROM passkeys WHERE id=?", (ME_ID,)).fetchone())[0] == 1
    again = c.post("/account/passkeys/verify/finish", headers=me,
                   json={"request_id": begin["request_id"], "credential": assertion(ME_ID, begin["options"]["challenge"], count=2)})
    assert again.status_code == 400                                                         # used once only
    b._pk_db(lambda con: con.execute("INSERT INTO passkeys (id, email, public_key, sign_count, created) VALUES (?, ?, ?, 0, ?)",
                                     (EVE_ID, "eve@example.com", public, time.time())))
    begin = c.post("/account/passkeys/verify/begin", headers=me).json()
    r = c.post("/account/passkeys/verify/finish", headers=me,
               json={"request_id": begin["request_id"], "credential": assertion(EVE_ID, begin["options"]["challenge"], count=3)})
    assert r.status_code == 401                                                             # someone else's passkey
    begin = c.post("/account/passkeys/verify/begin", headers=eve).json()
    r = c.post("/account/passkeys/verify/finish", headers=me,                              # another account's request
               json={"request_id": begin["request_id"], "credential": assertion(ME_ID, begin["options"]["challenge"], count=4)})
    assert r.status_code == 401
    begin = c.post("/account/passkeys/verify/begin", headers=me).json()
    r = c.post("/account/passkeys/verify/finish", headers=me,
               json={"request_id": begin["request_id"], "credential": assertion(ME_ID, "wrong-challenge", count=5)})
    assert r.status_code == 401                                                             # signed for something else


def test_browser_lock_everywhere(srv):
    b, c, me, eve = srv
    r = c.get("/app/lock.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"] and "gink-genie://unlock" in r.text
    assert "/account/passkeys/verify/begin" in r.text and "gink_unlocked_at" in r.text
    for page in ("genie.html", "console.html"):
        assert '<script src="/app/lock.js"></script>' in read("src", "ginkassistant", "services", "web_app", page), page
    assert 'id="lock-btn"' in read("src", "ginkassistant", "services", "web_app", "genie.html")
    bridge = read("webapp", "bridge.js")
    for must in ("HANDLERS.unlock = function", "function passkeyCheck()", "if (LK.locked && !LOCKED_OK[type]) return;",
                 'if (v.key === "app_lock") {', "lockMark()", '"/account/passkeys/verify/finish"'):
        assert must in bridge, must
    assert "Face ID, Touch ID, Windows Hello" in read("cli", "gink_cli", "main.py")          # gink login: passkeys work


def test_genie_app_asks_the_device(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from ginkgenie import app as genie_app, biometric as genie_bio
    calls = []

    async def device(reason, app=None):
        calls.append(reason); return (len(calls) == 1, "" if len(calls) == 1 else "Cancelled.")
    monkeypatch.setattr(genie_bio, "authenticate", device)

    class Web:
        def __init__(self): self.js = []
        def evaluate_javascript(self, script): self.js.append(script)
    g = genie_app.GinkGenie.__new__(genie_app.GinkGenie)
    g.web, g.server, g.showing_status, g.quiet_until, g.away = Web(), "https://x", False, 0.0, None

    async def run():
        assert g.navigating(None, url="gink-genie://unlock") is False
        await asyncio.sleep(0.05)
        assert g.navigating(None, url="gink-genie://lock-off") is False
        await asyncio.sleep(0.05)
    asyncio.run(run())
    assert calls == ["Unlock Gink Genie", "Turn off Lock"]
    assert g.web.js[0] == "window.GinkLock && GinkLock.unlocked()"
    assert g.web.js[1] == 'window.GinkLock && GinkLock.toggled(false, "Cancelled.")'
    g.went_away()
    assert g.away is None                     # just after the system's own sheet: focus changes don't count
    g.quiet_until = 0
    g.went_away(); g.away -= 120; g.came_back()
    assert g.web.js[-1].startswith("window.GinkLock && GinkLock.checkAway(") and g.away is None
