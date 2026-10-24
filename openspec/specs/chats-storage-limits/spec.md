# Chats, storage and usage limits

## Purpose
People keep Recents tidy without losing chats, see and free what Gink stores on a device, and always know when a usage limit resets.

## Requirements

### Requirement: Archived chats
A chat SHALL be archivable from its menu (apps and web): it leaves Recents, stays in Settings > Privacy > Archived chats with Unarchive, syncs as archived to the person's other devices, and "Archive all chats" SHALL archive every chat without deleting anything.

#### Scenario: Archive on one device
- **WHEN** a chat is archived on the computer
- **THEN** it is archived on the phone after syncing, and Unarchive brings it back to Recents

### Requirement: Storage
On the apps, Settings > Storage SHALL show how much space Gink uses on the device and what remains free, by kind (chats, images, files, offline AI model, "Hey Gink" speech model, song data), and SHALL free one kind at a time after a second click, without touching the others.

#### Scenario: Freeing images
- **WHEN** the person deletes Images (clicking twice)
- **THEN** images Gink made are removed and files Gink made are kept

### Requirement: Usage-limit reset times
A daily-limit answer SHALL include the exact reset time (resets_at, plus Retry-After); the apps and web app SHALL show it in the person's local time, and the web app SHALL show a notice when the limit has reset, also after a reload.

#### Scenario: Limit reached
- **WHEN** the person sends a message after today's allowance is used
- **THEN** the message says when it resets in their own time (for example "12:00 AM tomorrow"), not "midnight (UTC)"
