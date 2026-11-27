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

### Requirement: Design preview
For HTML and SVG code the viewer SHALL offer Preview and Code, opening on Preview: the page or graphic rendered in a sandbox that runs its scripts but cannot reach Gink (no same-origin access).

#### Scenario: An HTML card
- **WHEN** Gink answers with an HTML card that runs a script and tries to read Gink's sign-in
- **THEN** the preview shows the card with its script's result, and the sign-in stays unreachable

### Requirement: Videos in a chat
A video attached or dragged into a chat SHALL be sent to the AI as a few frames taken in order (five pictures at most with any photos), with a sentence saying what they are; the video itself SHALL stay on the device, and one that can't be played SHALL be explained in plain words.

#### Scenario: A short clip
- **WHEN** someone drags a 10-second video into the message box and asks what happens
- **THEN** Gink answers from frames taken across the clip

#### Scenario: A format the device can't play
- **WHEN** the video can't be played on the device
- **THEN** Gink says so and suggests an .mp4 video or a photo

### Requirement: Long chats keep working
A chat SHALL never fail because it has grown long: earlier versions of an artifact SHALL not be sent again (the newest stays), and every request SHALL fit the AI model's limit -- less room for the answer, then older turns left out, keeping the newest version of every artifact and the last turns as long as possible -- or go to a model that takes more; the model's real limits SHALL be learned from the AI service's own answers.

#### Scenario: A page made three times
- **WHEN** a chat that made a page three times asks for one more section
- **THEN** only the newest version of the page goes along and the answer comes, from a model that takes it if needed

### Requirement: Plain words when the AI refuses
When the AI service still refuses a request, or is busy, the person SHALL see plain words -- the chat is too long, or Gink's AI is busy and when to try again -- never the service's own message or Gink's account details.

#### Scenario: Busy everywhere
- **WHEN** every model has used up this minute
- **THEN** the person reads that Gink's AI is busy and when to try again, without an organization id or an upgrade link

### Requirement: Opened chats on the web are readable at once
In the web app, an answer SHALL be formatted as it arrives and an opened chat SHALL show its answers formatted at once (no raw Markdown, no artifact code), then with the server's formatting; a question card answered by the next message SHALL show closed with its answer; a chat opened again SHALL show formatted without waiting; and an opened chat SHALL never make its scheduled task again.

#### Scenario: Opening a chat with a question card
- **WHEN** the person opens a chat where Gink asked a question and they answered it
- **THEN** the card shows their answer, closed, and the artifact that followed shows as its card
