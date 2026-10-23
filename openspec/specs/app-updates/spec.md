# App updates

## Purpose
People hear about new versions and get the right installer.

## Requirements

### Requirement: Update notice
The apps SHALL check the server's /app/version at most once a day (the server asks GitHub, cached an hour) and, when a newer version exists, offer the installer for this device (Apple Silicon or Intel Mac, Windows, Linux, Android 64-bit or 32-bit; nothing on iPhone); "Later" SHALL hide that version only.

#### Scenario: 32-bit phone
- **WHEN** an Android phone reports a processor without "64" (armv7l, armv8l)
- **THEN** it is offered Gink-android-32bit.apk
