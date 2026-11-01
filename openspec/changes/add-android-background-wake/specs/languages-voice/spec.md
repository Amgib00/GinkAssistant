## ADDED Requirements

### Requirement: Hey Gink in the background on Android
On Android, when the person switches on "Keep listening in the background" (off by default, this device only), Gink SHALL keep listening for "Hey Gink" while not on screen, using a microphone foreground service with an ongoing notification that is started only while Gink is on screen.

#### Scenario: Asking from the home screen
- **WHEN** background listening is on, the person presses Home and says "Hey Gink, what time is it?"
- **THEN** Gink answers out loud, and the notification shows while it listens

### Requirement: Background listening stops and fails safely
The Android background service SHALL stop when Hey Gink or the setting is turned off, on sign-out, or when Gink is swiped away; if Android refuses it or the build lacks it, Gink SHALL keep listening while on screen and say why in the Hey Gink status.

#### Scenario: Switched off
- **WHEN** the person turns the setting off or swipes Gink away
- **THEN** the service and its notification stop

#### Scenario: Android refuses
- **WHEN** the service can't start
- **THEN** the app doesn't crash, listens while on screen, and the status explains why
