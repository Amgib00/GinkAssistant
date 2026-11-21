# Agent mode

## Purpose
Gink carries out multi-step tasks with its tools, shows what it is doing, and asks before anything sensitive happens.

## Requirements

### Requirement: Multi-step tasks
The agent SHALL be able to use tools over up to 12 rounds for one request, and SHALL show each step as it runs (running, done, failed, skipped) in typed chats.

#### Scenario: Several actions
- **WHEN** a person asks to set an alarm and message someone
- **THEN** the checklist shows both steps and their outcome

### Requirement: Approval before sensitive actions
In typed chats with "Ask before sensitive actions" on, the agent SHALL ask the person before sending a message, making a call, deleting an item or forgetting a memory, and before quitting an app, locking or sleeping the computer, reading the clipboard or taking a screenshot when it chose that step itself as part of a longer task; no answer within 2 minutes SHALL count as no.

#### Scenario: Declined
- **WHEN** the person taps Don't allow
- **THEN** the step is not done, the AI is told, and the final answer says it wasn't done

#### Scenario: Asked for directly
- **WHEN** the person directly asks "lock my screen"
- **THEN** it happens without an approval question

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
