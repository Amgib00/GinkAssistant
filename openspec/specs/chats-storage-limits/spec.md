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

### Requirement: Shared chat links
A chat SHALL be shareable from its menu as a public, read-only snapshot at /c/<id> containing only the user's messages and Gink's answers (pictures become "[attachment]"), rendered without any scripts; Settings > Privacy > Shared links SHALL list them with views and let the owner delete them, after which the link stops working.

#### Scenario: A message contains a script
- **WHEN** a shared chat contains "<script>" in a message
- **THEN** the page shows it as text and runs nothing

### Requirement: Temporary chats
From the new-chat screen a person SHALL be able to start a temporary chat, shown with a notice and a dashed message box, that is never written to storage, never synced, never listed in Recents, and is discarded when they leave it; Gink still keeps its messages in mind while it lasts.

#### Scenario: Leaving a temporary chat
- **WHEN** a person has a temporary chat and starts a new chat
- **THEN** the temporary chat is gone and the new chat is a normal one

### Requirement: Code viewer
Code blocks of 15 lines or more SHALL offer "Open", showing the code in a side panel with a title (from a file name mentioned just before it, else the language), a language badge, Copy with a menu (Copy, Download), Expand, Close and line numbers aligned with the code; a new answer's longest code block of 30 lines or more SHALL open by itself on screens 900 px or wider, never for chats opened from history.

#### Scenario: A long file in an answer
- **WHEN** Gink answers with "Here's voice_bridge.py" and 40 lines of Python
- **THEN** the viewer opens titled "Voice bridge" with a PY badge and 40 numbered lines
