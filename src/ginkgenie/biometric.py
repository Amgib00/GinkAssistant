"""
Face ID, Touch ID, Optic ID, Windows Hello, Android face or fingerprint unlock (and fingerprint on Linux): the
DEVICE checks that it's you and tells Gink only "yes" or "no". Gink never sees, keeps or sends a face or a
fingerprint -- the same way Apple's apps use Face ID.

Used by "Lock Gink" (Settings > Privacy) in Gink, and by Gink Genie: src/ginkgenie/biometric.py is a copy of
this file (tests/test_app_lock.py keeps the two the same).

    await kind()                      -> "Face ID" | "Touch ID" | "Optic ID" | "Windows Hello" |
                                         "Face or fingerprint unlock" | "Fingerprint" | "Passcode" | "Password" | ""
    await authenticate(reason, app)   -> (ok, message)    message says why not, in plain words
"""
import asyncio
import shutil
import subprocess
import sys

LA_POLICY_BIOMETRICS = 1        # LAPolicyDeviceOwnerAuthenticationWithBiometrics
LA_POLICY_OWNER = 2             # LAPolicyDeviceOwnerAuthentication: biometrics first, then the passcode/password
BIOMETRY = {1: "Touch ID", 2: "Face ID", 4: "Optic ID"}           # LABiometryType
LA_ERRORS = {-1: "That wasn't recognised. Try again.", -2: "Cancelled.", -4: "Cancelled.", -8: "Too many tries: "
             "unlock your device with its passcode first, then try again.", -5: "Set a passcode on this device first.",
             -6: "Face ID or Touch ID isn't available on this device.", -7: "Set up Face ID or Touch ID first.",
             -9: "Cancelled.", -1004: "Cancelled."}
UNAVAILABLE = "This device has no Face ID, Touch ID, Windows Hello, fingerprint or screen lock that Gink can use."
NONE_SET_UP = {
    "macos": "Set up Touch ID or a login password on this Mac first.",
    "ios": "Set up Face ID or a passcode on this device first.",
    "android": "Set up a screen lock (face, fingerprint or PIN) on this phone first.",
    "windows": "Set up Windows Hello (face, fingerprint or PIN) in Windows Settings first.",
    "linux": "No fingerprint reader is set up on this computer (fprintd).",
}


def platform() -> str:
    if hasattr(sys, "getandroidapilevel"):
        return "android"
    if sys.platform == "ios":
        return "ios"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


# ---------------------------------------------------------------- Apple: LocalAuthentication (macOS, iOS)
def _la_context():
    from rubicon.objc import ObjCClass
    from rubicon.objc.runtime import load_library
    load_library("LocalAuthentication")
    return ObjCClass("LAContext").alloc().init()


def _apple_kind() -> str:
    ctx = _la_context()
    if ctx.canEvaluatePolicy_error_(LA_POLICY_BIOMETRICS, None):
        return BIOMETRY.get(int(ctx.biometryType), "Touch ID")
    if ctx.canEvaluatePolicy_error_(LA_POLICY_OWNER, None):
        return "Passcode" if platform() == "ios" else "Password"
    return ""


async def _apple_authenticate(reason: str):
    from rubicon.objc import Block, ObjCInstance, objc_id
    loop = asyncio.get_running_loop()
    done = loop.create_future()
    ctx = _la_context()
    if not ctx.canEvaluatePolicy_error_(LA_POLICY_OWNER, None):
        return False, NONE_SET_UP[platform()]

    def reply(success, error):                     # called on a background thread by the system
        code = 0
        if not success and error:
            try:
                code = int(ObjCInstance(error).code)
            except Exception:
                code = -1
        loop.call_soon_threadsafe(lambda: done.done() or done.set_result((bool(success), code)))
    block = Block(reply, None, bool, objc_id)
    ctx.evaluatePolicy_localizedReason_reply_(LA_POLICY_OWNER, reason, block)
    ok, code = await done
    del block                                      # kept alive until the system answered
    return ok, "" if ok else LA_ERRORS.get(code, "Not unlocked.")


# ---------------------------------------------------------------- Android: the phone's own lock (face, fingerprint, PIN)
def _android_activity(app):
    import toga
    app = app or toga.App.app
    return app, app._impl.native


def _android_kind(app=None) -> str:
    from android.content import Context
    _app, activity = _android_activity(app)
    keyguard = activity.getSystemService(Context.KEYGUARD_SERVICE)
    if not keyguard.isDeviceSecure():
        return ""
    try:                                           # Android 10+: is a face or fingerprint enrolled?
        from java import jclass
        manager = activity.getSystemService(jclass("android.hardware.biometrics.BiometricManager"))
        if manager is not None and manager.canAuthenticate() == 0:          # BIOMETRIC_SUCCESS
            return "Face or fingerprint unlock"
    except Exception:
        pass
    return "Screen lock"


async def _android_authenticate(reason: str, app=None):
    from android.app import Activity
    from android.content import Context
    app, activity = _android_activity(app)
    keyguard = activity.getSystemService(Context.KEYGUARD_SERVICE)
    if not keyguard.isDeviceSecure():
        return False, NONE_SET_UP["android"]
    intent = keyguard.createConfirmDeviceCredentialIntent("Unlock Gink", reason)   # the system's own face/fingerprint/PIN
    if intent is None:
        return False, NONE_SET_UP["android"]
    result = await app._impl.intent_result(intent)
    ok = int(result.get("resultCode", 0)) == Activity.RESULT_OK
    return ok, "" if ok else "Not unlocked."


# ---------------------------------------------------------------- Windows Hello
def _hello():
    from winrt.windows.security.credentials.ui import (UserConsentVerificationResult, UserConsentVerifier,
                                                       UserConsentVerifierAvailability)
    return UserConsentVerifier, UserConsentVerifierAvailability, UserConsentVerificationResult


async def _windows_kind() -> str:
    verifier, availability, _result = _hello()
    return "Windows Hello" if await verifier.check_availability_async() == availability.AVAILABLE else ""


async def _windows_authenticate(reason: str):
    verifier, availability, result = _hello()
    if await verifier.check_availability_async() != availability.AVAILABLE:
        return False, NONE_SET_UP["windows"]
    outcome = await verifier.request_verification_async(reason)
    if outcome == result.VERIFIED:
        return True, ""
    return False, "Cancelled." if outcome == result.CANCELED else "Not unlocked."


# ---------------------------------------------------------------- Linux: fingerprint readers (fprintd)
def _linux_kind() -> str:
    return "Fingerprint" if shutil.which("fprintd-verify") else ""


def _fprintd_verify() -> bool:
    exe = shutil.which("fprintd-verify")
    if not exe:
        return False
    try:
        r = subprocess.run([exe], capture_output=True, text=True, timeout=40)   # "Verify result: verify-match (done)"
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "verify-match" in (r.stdout or "")


async def _linux_authenticate(reason: str):
    if not shutil.which("fprintd-verify"):
        return False, NONE_SET_UP["linux"]
    ok = await asyncio.get_running_loop().run_in_executor(None, _fprintd_verify)
    return ok, "" if ok else "That fingerprint wasn't recognised. Try again."


# ---------------------------------------------------------------- the two calls the apps make
async def kind(app=None) -> str:
    """What this device unlocks with, for labels ("Unlock with Face ID"); "" when nothing is set up."""
    where = platform()
    try:
        if where in ("macos", "ios"):
            return _apple_kind()
        if where == "android":
            return _android_kind(app)
        if where == "windows":
            return await _windows_kind()
        return _linux_kind()
    except Exception:                              # no framework, no package, an old OS: nothing to offer
        return ""


async def authenticate(reason: str = "Unlock Gink", app=None):
    """The device's own check. (ok, message) -- never raises."""
    where = platform()
    try:
        if where in ("macos", "ios"):
            return await _apple_authenticate(reason)
        if where == "android":
            return await _android_authenticate(reason, app)
        if where == "windows":
            return await _windows_authenticate(reason)
        return await _linux_authenticate(reason)
    except Exception as exc:
        return False, f"{UNAVAILABLE} ({type(exc).__name__})"
