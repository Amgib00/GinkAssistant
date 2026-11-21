"""Gink's notifications on the device itself (0.1.162).

Every notification card in the app -- a scheduled task's result, a reminder, "Privacy policy and terms updated", a new
version, "Gink is having trouble" -- also goes to the system when Gink isn't in front: Notification Center on a Mac
(and iPhone/iPad), the notification area on Windows, the desktop's notifications on Linux, the notification shade on
Android. While Gink is in front the card in the window is the alert: on a Mac (macOS 11+) it still goes quietly into
Notification Center's list, so every Gink notification is there; elsewhere it isn't posted twice. Settings > General > Notifications
> "Show in Notification Center" turns it off; "Test notification" sends one at once.

Mac and iOS: Apple's UserNotifications (Gink's own name and icon; macOS asks permission once). The built app only: from
source there's no app bundle, and asking would stop the process -- osascript's notification is used there instead (it
shows as Script Editor), and also when macOS doesn't let this copy of Gink post its own. Windows and Linux:
actions/notify.py. Android: a "Gink" notification channel (Android 13+ asks permission once).
Never raises: a notification must never break anything."""
from __future__ import annotations

import os
import sys
import time
from typing import Optional

MAC, WIN, IOS = sys.platform == "darwin", sys.platform.startswith("win"), sys.platform == "ios"
ANDROID = hasattr(sys, "getandroidapilevel")
CHANNEL_ID = "gink_notifications"
REPEAT_QUIET = 1800                   # the same notification again within 30 minutes: once is enough
SAME_STATE_QUIET = 12 * 3600          # "Gink is having trouble", a new version, the policy: twice a day at most

_state = {"center": None, "asked": False, "granted": None, "refused": False, "block": None, "recent": {}}


def where() -> str:
    """Where Gink's notifications go on this device (Settings shows it)."""
    if MAC or IOS:
        return "Notification Center"
    if WIN:
        return "Windows notifications"
    if ANDROID:
        return "Android notifications"
    if sys.platform.startswith("linux"):
        return "desktop notifications"
    return ""


def status() -> str:
    """For Settings: whether the system lets Gink post, when that's known."""
    if MAC or IOS:
        if _apple_center() is None:
            return "Running from source: notifications come from Script Editor." if MAC else ""
        if _state["granted"] is False and not _state["refused"]:
            return ("Notifications are turned off for Gink: turn them on in System Settings > Notifications > Gink."
                    if MAC else "Notifications are turned off for Gink: Settings > Notifications > Gink.")
        if _state["granted"]:
            return "Allowed."
    if ANDROID and _android_sdk() >= 33 and not _android_allowed():
        return "Android asks once for permission to show notifications."
    return ""


def in_front() -> Optional[bool]:
    """Is Gink the app in front right now? None when the system can't say."""
    try:
        if MAC:
            from rubicon.objc import ObjCClass
            return bool(ObjCClass("NSApplication").sharedApplication.isActive)
        if IOS:
            from rubicon.objc import ObjCClass
            return int(ObjCClass("UIApplication").sharedApplication.applicationState) == 0     # active
        if WIN:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value == os.getpid()
    except Exception:
        return None
    return None


def mac_lists_quietly() -> bool:
    """macOS 11 and later can put a notification in Notification Center's list without a banner or a sound."""
    if not MAC:
        return False
    try:
        import platform
        return int((platform.mac_ver()[0] or "0").split(".")[0]) >= 11
    except Exception:
        return False


def post(title: str, body: str = "", ident: str = "", page_visible: Optional[bool] = None, force: bool = False) -> bool:
    """Show it on the device: a banner when Gink isn't in front; with Gink in front only quietly in Notification
    Center's list (macOS 11+ from the app -- the card in the window is the alert), otherwise not at all.
    force: a banner always ("Test notification"). -> was it sent?"""
    title, body = " ".join(str(title or "Gink").split())[:120], " ".join(str(body or "").split())[:400]
    quietly = False
    if not force:
        front = in_front()
        if front is None:
            front = bool(page_visible) if page_visible is not None else False
        if front:
            if not (mac_lists_quietly() and _apple_center() is not None):
                return False                               # the card in the window is enough
            quietly = True                                 # in the list, no banner: no double alert
        key, now = (ident or title, title, body), time.time()
        quiet = SAME_STATE_QUIET if ident in ("status", "update", "policy") else REPEAT_QUIET
        if now - _state["recent"].get(key, 0) < quiet:
            return False
        _state["recent"][key] = now
        if len(_state["recent"]) > 200:
            for k in sorted(_state["recent"], key=_state["recent"].get)[:100]:
                _state["recent"].pop(k, None)
    try:
        if MAC or IOS:
            if _apple_post(title, body, ident, quietly):
                return True
            if IOS or quietly:
                return False
            if _state["granted"] is False and not _state["refused"]:
                return False                               # the person turned Gink's notifications off: respected
            from .actions.notify import notify
            return notify(title, body)                      # from source, or macOS won't let this copy post its own
        if ANDROID:
            return _android_post(title, body, ident)
        from .actions.notify import notify
        return notify(title, body)
    except Exception:
        return False


def ask_permission() -> None:
    """Ask once (Mac/iOS: the system's prompt; Android 13+: its permission dialog). Safe to call at every start."""
    try:
        if (MAC or IOS) and _apple_center() is not None:
            _apple_ask()
        elif ANDROID and _android_sdk() >= 33:
            from . import android_fgs
            android_fgs.ask_notification_permission()
    except Exception:
        pass


# ---------------------------------------------------------------- Mac and iOS: UserNotifications
def _apple_center():
    """The app's UNUserNotificationCenter -- only inside the built app (Gink.app): elsewhere asking for it stops the
    process ("bundleProxyForCurrentProcess is nil"), so from source this is None."""
    if _state["center"] is not None:
        return _state["center"] or None
    center = False
    try:
        from rubicon.objc import ObjCClass
        from rubicon.objc.runtime import load_library
        bundle = ObjCClass("NSBundle").mainBundle
        path, ident = str(bundle.bundlePath or ""), str(bundle.bundleIdentifier or "")
        if path.endswith(".app") and "gink" in ident.lower():
            load_library("UserNotifications")
            center = ObjCClass("UNUserNotificationCenter").currentNotificationCenter()
            try:                                           # shown even with Gink in front (Settings > Test notification)
                _state["delegate"] = _delegate()
                center.setDelegate_(_state["delegate"])
            except Exception:
                pass
    except Exception:
        center = False
    _state["center"] = center
    return center or None


def _delegate():
    """The center's delegate, for notifications posted while Gink is in front (macOS asks it how to show them):
    "gink-quiet-..." only into the list; the rest -- the Settings test -- sound, banner and list."""
    from ctypes import c_ulong
    from rubicon.objc import NSObject, ObjCBlock, objc_method

    class GinkNotificationDelegate(NSObject):
        @objc_method
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, note, handler) -> None:
            try:
                ident = str(note.request.identifier)
            except Exception:
                ident = ""
            try:                                    # list = 8 (11+); sound 2, alert 4 (10.15), banner 16 (11+)
                ObjCBlock(handler, None, c_ulong)(8 if ident.startswith("gink-quiet-") else 2 | 4 | 8 | 16)
            except Exception:
                pass

    return GinkNotificationDelegate.alloc().init()


def _apple_ask() -> None:
    if _state["asked"]:
        return
    _state["asked"] = True
    center = _apple_center()
    if center is None:
        return
    from ctypes import c_bool
    from rubicon.objc import Block, objc_id

    def done(granted, error) -> None:              # on a system thread: just note the answer
        _state["granted"] = bool(granted)
        _state["refused"] = (not granted) and bool(error)     # an error = the system won't let this copy post

    _state["block"] = Block(done, None, c_bool, objc_id)      # kept alive until the system calls it
    center.requestAuthorizationWithOptions_completionHandler_(7, _state["block"])   # alert, sound, badge


def _apple_post(title: str, body: str, ident: str, quietly: bool = False) -> bool:
    center = _apple_center()
    if center is None or _state["refused"]:
        return False
    if not _state["asked"]:
        _apple_ask()
    if _state["granted"] is False:
        return False
    from rubicon.objc import ObjCClass
    content = ObjCClass("UNMutableNotificationContent").alloc().init()
    content.setTitle_(title)
    if body:
        content.setBody_(body)
    if not quietly:
        sound = ObjCClass("UNNotificationSound").defaultSound
        content.setSound_(sound() if callable(sound) else sound)
    request = ObjCClass("UNNotificationRequest").requestWithIdentifier_content_trigger_(
        ("gink-quiet-" if quietly else "gink-") + (ident or str(int(time.time() * 1000))), content, None)
    center.addNotificationRequest_withCompletionHandler_(request, None)
    return True


# ---------------------------------------------------------------- Android
def _android_sdk() -> int:
    try:
        from java import jclass
        return int(jclass("android.os.Build$VERSION").SDK_INT)
    except Exception:
        return 0


def _android_allowed() -> bool:
    try:
        from java import jclass
        activity = jclass("org.beeware.android.MainActivity").singletonThis
        granted = jclass("android.content.pm.PackageManager").PERMISSION_GRANTED
        return activity.checkSelfPermission("android.permission.POST_NOTIFICATIONS") == granted
    except Exception:
        return True


def _android_post(title: str, body: str, ident: str) -> bool:
    from java import jclass
    ctx = jclass("org.beeware.android.MainActivity").singletonThis
    sdk = _android_sdk()
    if sdk >= 33 and not _android_allowed():
        return False
    manager = ctx.getSystemService(jclass("android.content.Context").NOTIFICATION_SERVICE)
    if sdk >= 26:
        channel = jclass("android.app.NotificationChannel")(CHANNEL_ID, "Gink",
                                                            jclass("android.app.NotificationManager").IMPORTANCE_DEFAULT)
        channel.setDescription("Scheduled task results, reminders, updates and notices from Gink")
        manager.createNotificationChannel(channel)
        builder = jclass("android.app.Notification$Builder")(ctx, CHANNEL_ID)
    else:
        builder = jclass("android.app.Notification$Builder")(ctx)
    Intent, PendingIntent = jclass("android.content.Intent"), jclass("android.app.PendingIntent")
    open_app = Intent(ctx, jclass("org.beeware.android.MainActivity"))
    open_app.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
    flags = PendingIntent.FLAG_UPDATE_CURRENT | (PendingIntent.FLAG_IMMUTABLE if sdk >= 23 else 0)
    builder.setContentTitle(title)
    if body:
        builder.setContentText(body)
        builder.setStyle(jclass("android.app.Notification$BigTextStyle")().bigText(body))
    builder.setSmallIcon(ctx.getApplicationInfo().icon)
    builder.setAutoCancel(True)
    builder.setContentIntent(PendingIntent.getActivity(ctx, 0, open_app, flags))
    manager.notify(abs(hash(ident or title)) % 100000 + 1000, builder.build())
    return True
