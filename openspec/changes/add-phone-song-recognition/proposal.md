## Why

"Identify a song" never worked on Android: shazamio (Rust core) and sounddevice have no Android
builds, so recording and recognition both silently returned nothing ("Couldn't recognise a song").

## What Changes

- Android records ~8 s of 16 kHz mono audio with android.media.AudioRecord (android_voice.record_wav).
- Server: POST /media/song (signed in) takes a short .wav, asks Shazam via shazamio, deletes the
  recording, returns {match, title, artist, url}. Per-account daily allowance GINK_SONG_DAILY
  (default 40), counted before the call and refunded if Shazam fails. shazamio added to the server image.
- song_recognition: shazamio on the device when installed (desktops, unchanged), otherwise the
  server; the local fingerprint database stays the last fallback.
- "Identify a song" takes the mic from "Hey Gink" first and shows the real reason when it can't.

Out of scope: iPhone recording, the continuous "notice a song playing" loop on phones, plan-based limits.

Platforms: Android 64/32-bit (new), server (new endpoint). Desktop unchanged except the Hey Gink pause.

## Impact

- New spec: song-recognition.
- Server image grows by shazamio + shazamio-core (manylinux_2_28 wheel; python:3.12-slim is fine).
- shazamio uses Shazam's unofficial API: Shazam may slow down or block heavy use from one server.
