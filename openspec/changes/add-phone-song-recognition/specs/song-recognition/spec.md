## ADDED Requirements

### Requirement: Song recognition on phones
On Android, "Identify a song" SHALL record a few seconds of audio and ask the person's Gink server, which SHALL identify it with Shazam and delete the recording immediately.

#### Scenario: Music playing
- **WHEN** a signed-in person taps Identify a song while music plays
- **THEN** Gink shows the song's title and artist

### Requirement: Song recognition limits and reasons
The server SHALL accept only short .wav recordings from signed-in accounts and allow GINK_SONG_DAILY songs per account per day (default 40), not counting attempts Shazam failed to answer; the app SHALL show the reason when it can't recognise (microphone permission, not signed in, daily limit).

#### Scenario: Microphone permission off
- **WHEN** the microphone permission is off
- **THEN** Gink says it needs the microphone instead of "Couldn't recognise a song"

#### Scenario: Daily allowance used
- **WHEN** an account has recognised today's allowance
- **THEN** the server refuses with a message saying more are available tomorrow
