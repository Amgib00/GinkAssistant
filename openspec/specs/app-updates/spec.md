# App updates

## Purpose
People hear about new versions and get the right installer.

## Requirements

### Requirement: Update notice
The apps SHALL check the server's /app/version at most once a day (the server asks GitHub, cached an hour) and, when a newer version exists, offer the installer for this device (Apple Silicon or Intel Mac, Windows, Linux, Android 64-bit or 32-bit; nothing on iPhone); "Later" SHALL hide that version only.

#### Scenario: 32-bit phone
- **WHEN** an Android phone reports a processor without "64" (armv7l, armv8l)
- **THEN** it is offered Gink-android-32bit.apk

### Requirement: What's new after an update
After the apps update, the first launch SHALL show the changelog points of each new version since the version that device last ran (at most 3 versions, never newer than the running app), once; a fresh install SHALL show nothing, and a device that ran Gink before this existed SHALL see the current version's points once. The apps SHALL ship an identical copy of the changelog.

#### Scenario: Updating from 0.1.45 to 0.1.49
- **WHEN** a device that last ran 0.1.45 starts 0.1.49
- **THEN** it shows the points for 0.1.49, 0.1.48 and 0.1.47 once
