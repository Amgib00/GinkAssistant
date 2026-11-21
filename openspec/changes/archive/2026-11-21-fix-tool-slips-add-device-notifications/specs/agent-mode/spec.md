## ADDED Requirements

### Requirement: Using its tools by itself
In the apps' chats (typed or spoken, without photos) the AI SHALL be able to hand a request to Gink's own tools by itself, and the agent SHALL then do it in the same reply; a request about a device part that isn't working, or to run a check, SHALL go to the tools directly.

#### Scenario: A camera that isn't working
- **WHEN** someone asks "can you run some check for why my camera is not working"
- **THEN** Gink runs the device check focused on the camera and says what it found and what to do

#### Scenario: The AI chooses
- **WHEN** a request in other words needs something done on the device and the AI hands it over
- **THEN** the agent does it in the same reply, with its steps shown

### Requirement: Camera and microphone checks
The device check SHALL be able to focus on the camera or the microphone: whether the system sees it, whether it reports a problem, whether access is turned off (and Gink's own permission on a Mac), and which open apps may be holding it -- read-only, like the rest of the check.

#### Scenario: Another app holds the camera
- **WHEN** a video-call app is open during a camera check
- **THEN** the check names it and suggests quitting the ones not in use

### Requirement: Answers always finish
A chat answer SHALL always end in plain words: when the AI service fails or a model slips on a tool call, the reply keeps what was written and says what happened, and its spinner stops; a raw error is never shown.

#### Scenario: A slip in the middle of an answer
- **WHEN** the answer stops because of an error
- **THEN** the reply ends with a sentence saying it stopped early, and nothing keeps spinning
