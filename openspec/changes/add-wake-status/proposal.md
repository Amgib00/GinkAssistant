## Why

When "Hey Gink" was on, nothing on the main screen showed whether Gink was actually listening. If
the microphone permission was off, the model was still downloading or the mic was busy, people
said "Hey Gink" and nothing happened, with no clue why. On Android, Settings even said "Off" when
listening had stopped because the microphone permission was off.

## What Changes

- A "Hey Gink" chip in the composer, beside the + button, whenever Hey Gink is switched on:
  ready (green), paused while Gink uses the mic (grey), heard (lime), getting ready or retrying
  (amber, with download progress), and can't listen (red, with the reason). Clicking it opens
  Settings > Voice. On narrow screens and the centred home composer it shows only the dot.
- One source of truth (services/wake_status.py) for the chip and the Settings > Voice line.
- Fixed: the Android listener stopping with an error is shown as a problem, not "Off".

Out of scope: "Hey Gink" on iPhone, listening while the Android app is in the background (a
foreground service, a separate change), the web app (it has no "Hey Gink").

Platforms: macOS, Windows, Linux, Android 64-bit and 32-bit. iOS and web unchanged.

## Impact

- Modified spec: languages-voice ("Hey Gink" status).
