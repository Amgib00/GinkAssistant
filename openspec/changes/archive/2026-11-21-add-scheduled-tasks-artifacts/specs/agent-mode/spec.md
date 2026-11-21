## ADDED Requirements

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
