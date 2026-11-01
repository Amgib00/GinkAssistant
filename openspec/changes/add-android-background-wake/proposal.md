## Why

On Android, "Hey Gink" only worked while Gink was on screen: Android stops an app's microphone
access in the background unless it runs a foreground service of type "microphone".

## What Changes

- New setting (Android only, off by default, this device only): Settings > Voice > "Keep listening
  in the background".
- services/android_fgs.py: HeyGinkService, a Chaquopy static proxy declared in the manifest with
  foregroundServiceType="microphone" and stopWithTask="true". It only shows the ongoing
  notification; listening stays in AndroidWakeListener, kept alive by the service.
- Started while Gink is on screen (Android 12+ forbids starting it from the background); stopped
  when Hey Gink or the setting is turned off, on sign-out, and when Gink is swiped away.
- Permissions: FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE (Android 14+),
  POST_NOTIFICATIONS (Android 13+, asked once when the setting is switched on).
- Never crashes: errors in the service are caught; a build or manifest without the service, or
  Android refusing, falls back to listening while open, and the chip's description says why.
- The Android Hey Gink description no longer claims listening is always on the device.

Out of scope: opening Gink's window when woken in the background (Android restricts starting
activities from the background: Gink answers out loud instead), a Stop button in the notification,
iPhone.

Platforms: Android 64-bit and 32-bit. Desktop, iOS and web unchanged.

## Impact

- Modified spec: languages-voice.
- Risk to check on a real phone: whether the phone's speech recognizer keeps working with Gink in
  the background (it runs in the speech app's process). If it doesn't, the next step is an on-device
  recognizer inside Gink's own process.
