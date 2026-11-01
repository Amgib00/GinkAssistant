"""
"Hey Gink" in the background on Android: a foreground service with a "microphone" type.

Android only lets an app use the microphone while it's on screen -- unless it runs a foreground
service of type "microphone", which shows a notification for as long as it runs ("Gink is listening
for 'Hey Gink'"). That notification is the honest signal: Android also shows its own mic indicator.

  * It's OFF unless the person switches on Settings > Voice > "Keep listening in the background".
  * Android 12+ refuses to START a foreground service from the background, so Gink starts it while
    it's on screen (when Hey Gink starts) and keeps it running; it stops when Hey Gink or the setting
    is turned off, on sign-out, and when the person swipes Gink away (stopWithTask in the manifest).
  * The service itself does nothing but keep the notification up: the listening stays in
    services/android_voice.AndroidWakeListener on Gink's own loop (the app process stays alive
    because of the service).

HeyGinkService is a Chaquopy *static proxy*: a real Java class generated from this file at build
time (pyproject.toml: chaquopy.defaultConfig.staticProxy("ginkassistant.services.android_fgs")),
named ginkassistant.services.android_fgs.HeyGinkService and declared in the manifest. Its methods
never let an exception reach Android (an exception in onStartCommand would crash the app).

This module is only imported on Android (it imports Java classes at the top, which the static
proxy generator needs). Use start() / stop() / is_running() from other code.
"""
from java import Override, jclass, jint, jvoid, static_proxy

from android.app import Service
from android.content import Intent
from android.os import IBinder

SERVICE_CLASS = "ginkassistant.services.android_fgs.HeyGinkService"
CHANNEL_ID = "gink_hey_gink"
NOTIFICATION_ID = 7202
NOTIFY_PERMISSION = "android.permission.POST_NOTIFICATIONS"      # Android 13+: asked once
_state = {"running": False, "error": ""}


def _sdk() -> int:
    return int(jclass("android.os.Build$VERSION").SDK_INT)


def _notification(context):
    """The ongoing notification: tap it to open Gink."""
    sdk = _sdk()
    Notification = jclass("android.app.Notification")
    if sdk >= 26:
        NotificationChannel = jclass("android.app.NotificationChannel")
        NotificationManager = jclass("android.app.NotificationManager")
        channel = NotificationChannel(CHANNEL_ID, "Hey Gink", NotificationManager.IMPORTANCE_LOW)
        channel.setDescription("Shown while Gink listens for \u201cHey Gink\u201d in the background")
        channel.setShowBadge(False)
        context.getSystemService(NotificationManager).createNotificationChannel(channel)
        builder = jclass("android.app.Notification$Builder")(context, CHANNEL_ID)
    else:
        builder = jclass("android.app.Notification$Builder")(context)
    PendingIntent = jclass("android.app.PendingIntent")
    open_app = Intent(context, jclass("org.beeware.android.MainActivity"))
    open_app.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
    flags = PendingIntent.FLAG_UPDATE_CURRENT | (PendingIntent.FLAG_IMMUTABLE if sdk >= 23 else 0)
    builder.setContentTitle("Gink is listening for \u201cHey Gink\u201d")
    builder.setContentText("Say \u201cHey Gink\u201d any time. Tap to open Gink; turn it off in Settings > Voice.")
    builder.setSmallIcon(context.getApplicationInfo().icon)
    builder.setOngoing(True)
    builder.setShowWhen(False)
    builder.setContentIntent(PendingIntent.getActivity(context, 0, open_app, flags))
    if sdk >= 31:
        builder.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
    return builder.build()


class HeyGinkService(static_proxy(Service)):
    @Override(jint, [Intent, jint, jint])
    def onStartCommand(self, intent, flags, start_id):
        try:
            note = _notification(self)
            if _sdk() >= 29:
                mic = jclass("android.content.pm.ServiceInfo").FOREGROUND_SERVICE_TYPE_MICROPHONE
                self.startForeground(NOTIFICATION_ID, note, mic)
            else:
                self.startForeground(NOTIFICATION_ID, note)
            _state.update(running=True, error="")
        except Exception as exc:                     # never let Android see an exception from here
            _state.update(running=False, error=f"Android didn\u2019t allow it ({exc.__class__.__name__})")
            try:
                self.stopSelf()
            except Exception:
                pass
        return Service.START_NOT_STICKY             # if Android kills Gink, don't restart it silently

    @Override(IBinder, [Intent])
    def onBind(self, intent):
        return None

    @Override(jvoid, [])
    def onDestroy(self):
        _state["running"] = False
        try:
            super().onDestroy()
        except Exception:
            pass


# ---------------------------------------------------------------- used by the app
def _context():
    return jclass("org.beeware.android.MainActivity").singletonThis


def ask_notification_permission() -> None:
    """Android 13+: notifications need permission (the service still runs without it, but
    the person couldn't see it -- so ask once)."""
    try:
        if _sdk() < 33:
            return
        activity = _context()
        granted = jclass("android.content.pm.PackageManager").PERMISSION_GRANTED
        if activity.checkSelfPermission(NOTIFY_PERMISSION) != granted:
            from java import jarray
            activity.requestPermissions(jarray("java.lang.String")([NOTIFY_PERMISSION]), 7102)
    except Exception:
        pass


def start() -> bool:
    """Start the service (call while Gink is on screen). True if Android accepted it."""
    if _state["running"]:
        return True
    try:
        context = _context()
        intent = Intent(context, jclass(SERVICE_CLASS))     # fails cleanly if the build lacks the class
        ask_notification_permission()
        started = context.startForegroundService(intent) if _sdk() >= 26 else context.startService(intent)
        if started is None:                                  # Android found no such service in the manifest
            _state.update(running=False, error="this Gink build has no background service (update Gink)")
            return False
        _state.update(running=True, error="")                # onStartCommand confirms (or reports why not)
        return True
    except Exception as exc:
        _state.update(running=False, error=f"Android didn\u2019t allow it ({exc.__class__.__name__})")
        return False


def stop() -> None:
    try:
        context = _context()
        context.stopService(Intent(context, jclass(SERVICE_CLASS)))
    except Exception:
        pass
    _state["running"] = False


def is_running() -> bool:
    return bool(_state["running"])


def last_error() -> str:
    return _state["error"]
