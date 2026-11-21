## ADDED Requirements

### Requirement: Wake on just "Gink"
Besides "Hey Gink", Gink SHALL wake when what it heard starts with "Gink", on computers, Android and the web app, unless the person turns that off in Settings > Voice.

#### Scenario: "Gink, what time is it?"
- **WHEN** someone says "Gink, what time is it?" with Hey Gink on
- **THEN** Gink wakes with the glow and answers

#### Scenario: Not at the start
- **WHEN** someone says "I think Gink is great"
- **THEN** Gink doesn't wake
