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
