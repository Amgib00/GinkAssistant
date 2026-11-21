## ADDED Requirements

### Requirement: Videos in a chat
A video attached or dragged into a chat SHALL be sent to the AI as a few frames taken in order (five pictures at most with any photos), with a sentence saying what they are; the video itself SHALL stay on the device, and one that can't be played SHALL be explained in plain words.

#### Scenario: A short clip
- **WHEN** someone drags a 10-second video into the message box and asks what happens
- **THEN** Gink answers from frames taken across the clip

#### Scenario: A format the device can't play
- **WHEN** the video can't be played on the device
- **THEN** Gink says so and suggests an .mp4 video or a photo
