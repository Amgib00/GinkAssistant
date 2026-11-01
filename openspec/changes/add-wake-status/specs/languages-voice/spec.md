## ADDED Requirements

### Requirement: "Hey Gink" status
While "Hey Gink" is switched on, the computer and Android apps SHALL show a status chip in the composer saying whether Gink is waiting for its name, paused while it uses the microphone, has heard its name, is getting ready (with download progress) or retrying, or can't listen (with the reason); clicking it SHALL open Settings > Voice, and Settings > Voice SHALL describe the same state.

#### Scenario: Waiting for its name
- **WHEN** "Hey Gink" is on and the listener is running
- **THEN** the chip is green and its description says Gink is listening for "Hey Gink"

#### Scenario: Microphone permission off on Android
- **WHEN** the Android listener stops because the microphone permission is off
- **THEN** the chip is red and says so, and Settings > Voice gives the same reason instead of "Off"

#### Scenario: Switched off
- **WHEN** "Hey Gink" is off, or the device is an iPhone
- **THEN** no chip is shown
