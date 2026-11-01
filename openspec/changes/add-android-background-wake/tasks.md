## 1. Build
- [x] 1.1 services/android_fgs.py: HeyGinkService (static proxy), start/stop/is_running/last_error
- [x] 1.2 pyproject.toml: service in the manifest, staticProxy, three permissions
- [x] 1.3 Setting wake_background (prefs, Settings > Voice, device-only); main_screen starts/stops the service
- [x] 1.4 Chip / Settings text: background on, or why it couldn't start
- [x] 1.5 Tests: tests/test_android_background.py (fake Chaquopy), startup tests skip the Java-only module

## 2. Check on the TECNO BF6 (32-bit, Android 12) and a 64-bit phone
- [ ] 2.1 The APK builds (the static proxy compiles in Gradle)
- [ ] 2.2 Switch it on: the notification appears; press Home; say "Hey Gink, what time is it?" -> answered out loud
- [ ] 2.3 Swipe Gink away: the notification goes; turn the setting off: the notification goes
- [ ] 2.4 Android 13+: the notification permission is asked once
