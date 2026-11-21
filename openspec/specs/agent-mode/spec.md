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

### Requirement: Working on code projects
On a computer, Gink's agent SHALL be able to map a code project in the home folder, find where something is in its code, change files with a backup first, and run the project's own tests, linter or build.

#### Scenario: Fix and check
- **WHEN** someone asks Gink to fix the failing test in their project
- **THEN** Gink finds the code, changes it, runs the project's tests and says which files changed and whether the tests pass

#### Scenario: A phone
- **WHEN** the app runs on a phone
- **THEN** the code project tools are not offered

### Requirement: Only the project's own checks
The checks SHALL run only a command chosen from the project's own files (never one written by the AI or found in the conversation), without a shell and with a time limit, and the agent SHALL ask first when it runs them inside a longer task.

#### Scenario: Asked first in a chain
- **WHEN** the agent decides to run the tests while fixing code
- **THEN** it asks "Run the tests of shop?" before running them

### Requirement: Reading repositories
GitHub repositories mentioned in a chat, and Gink's own source when asked how Gink works, SHALL be read by the server so answers come from the real code, the source files before their tests.

#### Scenario: Where is sign-in
- **WHEN** someone asks where sign-in is handled in github.com/owner/app
- **THEN** the answer names the files from that repository

### Requirement: Scheduling from the agent
The apps' agent SHALL be able to schedule a task for Gink's server (schedule_task), which appears in its answer as the same task card as in a chat.

#### Scenario: Every day at 9
- **WHEN** someone tells the agent "every day at 9 remind me to drink water"
- **THEN** the answer has a task card and the task is made on Gink's server

### Requirement: More room and thought
For something being built (a page, an app, a long document) the apps and the web app SHALL allow a longer answer, and for hard questions (proofs, step-by-step problems) more reasoning.

#### Scenario: A landing page
- **WHEN** someone asks for a complete landing page
- **THEN** the answer has room to finish the page

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
