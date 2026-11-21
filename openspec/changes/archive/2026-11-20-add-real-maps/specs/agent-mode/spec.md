## ADDED Requirements

### Requirement: Knowing the device
The apps SHALL tell the AI which device they run on (model, system, chip, memory, laptop or phone), and the web app SHALL describe the browser and system it sees; asked which device or system they're using, Gink SHALL answer, and it SHALL never ask the person which operating system they use.

#### Scenario: Which device
- **WHEN** someone on a MacBook Air with macOS Catalina asks "which device am I using?"
- **THEN** Gink answers that it's a MacBook Air with macOS 10.15 Catalina

### Requirement: Checking the device itself
On computers, "do a check", "check my computer" or "why is my laptop so slow" SHALL run a read-only device check (system and whether it still gets security updates, time since restart, processor and memory, storage, battery health, the busiest apps, protection, and updates when asked) and Gink SHALL explain what it found and what to do, instead of giving steps to check by hand.

#### Scenario: Do a check now
- **WHEN** someone types "do a check now please"
- **THEN** the device check runs and the answer lists what it found and what to do about each issue
