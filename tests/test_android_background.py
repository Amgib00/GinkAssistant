"""Hey Gink in the background on Android (services/android_fgs.py): a foreground service of type
"microphone", started while Gink is on screen, that never lets an error crash the app."""
import importlib, os, sys, tomllib, types
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Rec:
    calls = []
    sdk = 34
    granted = {"android.permission.POST_NOTIFICATIONS": False}
    fail_start = False
    missing_class = False
    undeclared = False


def _fake_modules():
    calls = Rec.calls

    class Obj:
        def __init__(self, *a):
            self.args = a

        def __getattr__(self, name):                   # any builder / manager method
            def m(*a):
                calls.append((name, a))
                return self
            return m

    class Static:
        def __init__(self, name):
            self.name = name

        def __call__(self, *a):
            return Obj(self.name, *a)

        def __getattr__(self, attr):
            consts = {"SDK_INT": Rec.sdk, "PERMISSION_GRANTED": 0, "IMPORTANCE_LOW": 2,
                      "FOREGROUND_SERVICE_TYPE_MICROPHONE": 128, "FLAG_UPDATE_CURRENT": 1 << 27,
                      "FLAG_IMMUTABLE": 1 << 26, "FOREGROUND_SERVICE_IMMEDIATE": 1}
            if attr in consts:
                return consts[attr]
            if attr == "singletonThis":
                return Activity()
            if attr == "getActivity":
                return lambda *a: ("pending", a)
            raise AttributeError(attr)

    class Activity(Obj):
        def checkSelfPermission(self, perm):
            return 0 if Rec.granted.get(perm, True) else -1

        def requestPermissions(self, perms, code):
            calls.append(("requestPermissions", (list(perms), code)))

        def startForegroundService(self, intent):
            calls.append(("startForegroundService", intent.args))
            return None if Rec.undeclared else "ComponentInfo{com.amgib.ginkassistant/HeyGinkService}"

        def startService(self, intent):
            calls.append(("startService", intent.args))
            return None if Rec.undeclared else "ComponentInfo"

        def stopService(self, intent):
            calls.append(("stopService", intent.args))

        def getApplicationInfo(self):
            return types.SimpleNamespace(icon=42)

        def getSystemService(self, cls):
            return Obj()

    def jclass(name):
        if name == "ginkassistant.services.android_fgs.HeyGinkService" and Rec.missing_class:
            raise Exception("ClassNotFoundException")
        return Static(name)

    java = types.ModuleType("java")
    java.jclass = jclass
    java.jint, java.jvoid = int, None
    java.Override = lambda ret, args: (lambda f: f)
    java.static_proxy = lambda base: base
    java.jarray = lambda t: (lambda items: list(items))

    class Service(Activity):
        START_NOT_STICKY = 2

        def startForeground(self, *a):
            if Rec.fail_start:
                raise RuntimeError("ForegroundServiceStartNotAllowedException")
            calls.append(("startForeground", a))

        def stopSelf(self):
            calls.append(("stopSelf", ()))

        def onDestroy(self):
            calls.append(("super.onDestroy", ()))

    class Intent:
        FLAG_ACTIVITY_NEW_TASK, FLAG_ACTIVITY_SINGLE_TOP = 1, 2

        def __init__(self, *a):
            self.args = a

        def setFlags(self, f):
            pass

    mods = {"java": java, "android": types.ModuleType("android"),
            "android.app": types.ModuleType("android.app"), "android.content": types.ModuleType("android.content"),
            "android.os": types.ModuleType("android.os")}
    mods["android.app"].Service = Service
    mods["android.content"].Intent = Intent
    mods["android.os"].IBinder = object
    return mods


@pytest.fixture
def fgs(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "src"))
    Rec.calls.clear(); Rec.sdk = 34; Rec.fail_start = False; Rec.missing_class = False; Rec.undeclared = False
    Rec.granted = {"android.permission.POST_NOTIFICATIONS": False}
    for name, mod in _fake_modules().items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "ginkassistant.services.android_fgs", raising=False)
    m = importlib.import_module("ginkassistant.services.android_fgs")
    yield m
    sys.modules.pop("ginkassistant.services.android_fgs", None)


def names():
    return [c[0] for c in Rec.calls]


def test_service_runs_in_the_foreground_as_microphone(fgs):
    svc = fgs.HeyGinkService()
    assert svc.onStartCommand(None, 0, 1) == 2                       # START_NOT_STICKY
    fg = [c for c in Rec.calls if c[0] == "startForeground"][0][1]
    assert fg[0] == fgs.NOTIFICATION_ID and fg[2] == 128                # type: microphone
    assert ("setOngoing", (True,)) in Rec.calls and fgs.is_running()
    svc.onDestroy()
    assert not fgs.is_running() and "super.onDestroy" in names()


def test_old_android_has_no_service_type(fgs):
    Rec.sdk = 28
    fgs.HeyGinkService().onStartCommand(None, 0, 1)
    fg = [c for c in Rec.calls if c[0] == "startForeground"][0][1]
    assert len(fg) == 2


def test_refusal_never_crashes_the_app(fgs):
    Rec.fail_start = True
    assert fgs.HeyGinkService().onStartCommand(None, 0, 1) == 2         # no exception reaches Android
    assert "stopSelf" in names() and not fgs.is_running() and "didn\u2019t allow" in fgs.last_error()


def test_start_asks_for_notifications_and_starts_the_service(fgs):
    assert fgs.start() is True
    assert ("requestPermissions", (["android.permission.POST_NOTIFICATIONS"], 7102)) in Rec.calls
    assert "startForegroundService" in names()
    fgs.stop()
    assert "stopService" in names() and not fgs.is_running()


def test_no_notification_question_before_android_13(fgs):
    Rec.sdk = 31
    fgs.start()
    assert "requestPermissions" not in names() and "startForegroundService" in names()


def test_a_build_without_the_service_falls_back(fgs):
    Rec.missing_class = True
    assert fgs.start() is False and fgs.last_error() and "startForegroundService" not in names()


def test_manifest_and_static_proxy_match_the_class():
    app = tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))["tool"]["briefcase"]["app"]["ginkassistant"]["android"]
    assert 'android:name="ginkassistant.services.android_fgs.HeyGinkService"' in app["android_manifest_application_extra_content"]
    assert 'android:foregroundServiceType="microphone"' in app["android_manifest_application_extra_content"]
    assert 'android:stopWithTask="true"' in app["android_manifest_application_extra_content"]
    assert 'staticProxy("ginkassistant.services.android_fgs")' in app["build_gradle_extra_content"]
    for perm in ("android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_MICROPHONE",
                 "android.permission.POST_NOTIFICATIONS"):
        assert perm in app["permission"]


def test_background_listening_is_off_by_default_and_device_only():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from ginkassistant.services import prefs
    assert prefs.DEFAULTS["wake_background"] is False
    assert "wake_background" not in prefs.SYNCED


def test_chip_says_whether_background_listening_works():
    from ginkassistant.services.wake_status import describe

    class L:
        running, paused, error, prefer_offline = True, False, "", True
    on = describe(enabled=True, supported=True, listener=L(), device="phone", background={"on": True, "error": ""})
    assert "isn\u2019t on screen" in on["detail"]
    off = describe(enabled=True, supported=True, listener=L(), device="phone",
                   background={"on": False, "error": "not in this build (ImportError)"})
    assert off["state"] == "ready" and "couldn\u2019t start" in off["detail"] and "ImportError" in off["detail"]


def test_a_manifest_without_the_service_is_reported(fgs):
    """An old Briefcase that ignores android_manifest_application_extra_content: Android returns null."""
    Rec.undeclared = True
    assert fgs.start() is False and "no background service" in fgs.last_error() and not fgs.is_running()
