## ADDED Requirements

### Requirement: Notifications on the device
Every notification card Gink shows (a scheduled task's result, a reminder, an update, a notice, a policy change) SHALL also go to the device's own notifications -- Notification Center on a Mac or iPhone, Windows, Linux and Android notifications -- with a banner when Gink isn't in front; quick confirmations of something the person just did SHALL stay in the window.

#### Scenario: A task result while Gink is in the background
- **WHEN** a scheduled task's result arrives while another app is in front
- **THEN** a notification from Gink shows on the device

#### Scenario: Gink in front
- **WHEN** a notification arrives while Gink's window is in front
- **THEN** the card shows in the window without a second banner (on macOS 11 and later it goes quietly into Notification Center's list)

### Requirement: The person decides
Settings SHALL let the person turn the device's notifications off and send a test; when the system's own setting turns Gink's notifications off, Gink SHALL respect it and say where to change it; the web app SHALL use the browser's notifications only after the browser's permission.

#### Scenario: Turned off in macOS
- **WHEN** Gink's notifications are off in macOS's settings
- **THEN** Gink posts none and Settings says where to turn them on
